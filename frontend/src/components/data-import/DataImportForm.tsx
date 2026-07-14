import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Card, Form, Input, List, Radio, Space, Tabs, Tag, Typography, Upload } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { UploadFile } from "antd";
import { api, type BankOcrJob, type BankOcrProfile } from "../../api";
import { SOURCE_LABELS, SourceType } from "./constants";

const { Dragger } = Upload;
const { Text } = Typography;
const SOURCE_KEYS = Object.keys(SOURCE_LABELS) as SourceType[];

function createFileMap(): Record<SourceType, UploadFile[]> {
  return {
    bank: [],
    commercial: [],
    enterprise: [],
    wechat: [],
    telecom: [],
  };
}

function createTextMap(defaultValue = ""): Record<SourceType, string> {
  return {
    bank: defaultValue,
    commercial: defaultValue,
    enterprise: defaultValue,
    wechat: defaultValue,
    telecom: defaultValue,
  };
}

function fileNameWithoutExt(name: string) {
  return name.replace(/\.(xlsx|xls|jpg|jpeg|png|pdf)$/i, "");
}

export interface DataImportFormValues {
  source_type: SourceType;
  bank_name: string;
  batch_name: string;
}

export interface DataImportPayload {
  values: DataImportFormValues;
  files: File[];
  bankImportMode: "excel" | "ocr";
}

interface UseDataImportFormOptions {
  disabled?: boolean;
  allowOcr?: boolean;
  compact?: boolean;
  hideUploadList?: boolean;
}

export function useDataImportForm(options: UseDataImportFormOptions = {}) {
  const { disabled = false, allowOcr = true, compact = false, hideUploadList = false } = options;
  const [form] = Form.useForm<DataImportFormValues>();
  const [filesBySource, setFilesBySource] = useState<Record<SourceType, UploadFile[]>>(() => createFileMap());
  const [ocrFiles, setOcrFiles] = useState<UploadFile[]>([]);
  const [batchNames, setBatchNames] = useState<Record<SourceType, string>>(() => createTextMap());
  const [bankNames, setBankNames] = useState<Record<SourceType, string>>(() => createTextMap("默认来源"));
  const [autoBatchNames, setAutoBatchNames] = useState<Record<SourceType, string>>(() => createTextMap());
  const [bankImportMode, setBankImportMode] = useState<"excel" | "ocr">("excel");
  const [ocrJobs, setOcrJobs] = useState<BankOcrJob[]>([]);
  const [ocrFormatHint, setOcrFormatHint] = useState("支持 PNG、JPEG、BMP、TIFF、WebP、GIF、SVG 及 PDF");
  const sourceType = Form.useWatch("source_type", form) as SourceType | undefined;
  const activeSource = sourceType || "bank";
  const activeFiles = filesBySource[activeSource] || [];
  const hasExcelFiles = SOURCE_KEYS.some((key) => filesBySource[key].length > 0);
  const hasOcrFiles = ocrFiles.length > 0;
  const sourceTypeRef = useRef<SourceType>("bank");

  useEffect(() => {
    if (!allowOcr) return;
    let active = true;
    void Promise.all([
      api.listBankOcrJobs("ready"),
      api.listBankOcrProfiles().catch(() => ({ items: [] as BankOcrProfile[], format_hint: "" })),
    ]).then(([ocrData, profileData]) => {
      if (!active) return;
      setOcrJobs(ocrData.items);
      if (profileData.format_hint) setOcrFormatHint(profileData.format_hint);
    });
    return () => {
      active = false;
    };
  }, [allowOcr]);

  useEffect(() => {
    sourceTypeRef.current = activeSource;
    form.setFieldsValue({
      batch_name: batchNames[activeSource] || "",
      bank_name: bankNames[activeSource] || "默认来源",
    });
  }, [activeSource, batchNames, bankNames, form]);

  const syncBatchNameFromFiles = (type: SourceType, fileList: UploadFile[]) => {
    const nextAutoName = fileList[0]?.name ? fileNameWithoutExt(fileList[0].name) : "";
    setAutoBatchNames((prev) => ({ ...prev, [type]: nextAutoName }));
    setBatchNames((prev) => {
      const current = prev[type] || "";
      const previousAutoName = autoBatchNames[type] || "";
      if (!nextAutoName || (current && current !== previousAutoName)) return prev;
      return { ...prev, [type]: nextAutoName };
    });
    if (sourceTypeRef.current === type) {
      const current = String(form.getFieldValue("batch_name") || "").trim();
      if (!current || current === (autoBatchNames[type] || "")) {
        form.setFieldsValue({ batch_name: nextAutoName });
      }
    }
  };

  const updateFilesForSource = (type: SourceType, fileList: UploadFile[]) => {
    setFilesBySource((prev) => ({ ...prev, [type]: fileList }));
    syncBatchNameFromFiles(type, fileList);
  };

  const handleValuesChange = (changed: Partial<DataImportFormValues>) => {
    const type = sourceTypeRef.current;
    if (Object.prototype.hasOwnProperty.call(changed, "batch_name")) {
      setBatchNames((prev) => ({ ...prev, [type]: changed.batch_name || "" }));
    }
    if (Object.prototype.hasOwnProperty.call(changed, "bank_name")) {
      setBankNames((prev) => ({ ...prev, [type]: changed.bank_name || "" }));
    }
  };

  const toRealFiles = (fileList: UploadFile[]) =>
    fileList
      .map((item) => item.originFileObj as File | undefined)
      .filter((file): file is File => Boolean(file));

  const selectedExcelPayloads = useMemo<DataImportPayload[]>(
    () =>
      SOURCE_KEYS.flatMap((type) => {
        const realFiles = toRealFiles(filesBySource[type]);
        if (!realFiles.length) return [];
        return [{
          values: {
            source_type: type,
            bank_name: bankNames[type] || "默认来源",
            batch_name: batchNames[type] || fileNameWithoutExt(realFiles[0].name),
          },
          files: realFiles,
          bankImportMode: "excel" as const,
        }];
      }),
    [bankNames, batchNames, filesBySource]
  );

  const clearFilesForSource = (type: SourceType) => {
    updateFilesForSource(type, []);
  };

  const removeFileForSource = (type: SourceType, file: File) => {
    const nextFiles = filesBySource[type].filter((item) => item.originFileObj !== file);
    updateFilesForSource(type, nextFiles);
  };

  const reset = () => {
    form.resetFields();
    setFilesBySource(createFileMap());
    setOcrFiles([]);
    setBatchNames(createTextMap());
    setBankNames(createTextMap("默认来源"));
    setAutoBatchNames(createTextMap());
    setBankImportMode("excel");
  };

  const getPayload = async (): Promise<DataImportPayload> => {
    const values = await form.validateFields();
    const useOcr = values.source_type === "bank" && bankImportMode === "ocr";
    const activeList = useOcr ? ocrFiles : filesBySource[values.source_type];
    const realFiles = toRealFiles(activeList);
    if (!realFiles.length) {
      throw new Error(useOcr ? "请先选择至少一个图片或 PDF 文件" : "请先选择至少一个表格文件（.xlsx 或 .xls）");
    }
    const batchName = values.batch_name || fileNameWithoutExt(realFiles[0].name);
    return { values: { ...values, batch_name: batchName }, files: realFiles, bankImportMode: useOcr ? "ocr" : "excel" };
  };

  const getAllPayloads = async (): Promise<DataImportPayload[]> => {
    const values = await form.validateFields();
    const currentSource = values.source_type;
    const nextBatchNames = { ...batchNames, [currentSource]: values.batch_name || "" };
    const nextBankNames = { ...bankNames, [currentSource]: values.bank_name || "默认来源" };
    const payloads = SOURCE_KEYS.flatMap((type) => {
      const realFiles = toRealFiles(filesBySource[type]);
      if (!realFiles.length) return [];
      const batchName = nextBatchNames[type] || fileNameWithoutExt(realFiles[0].name);
      return [{
        values: {
          source_type: type,
          bank_name: nextBankNames[type] || "默认来源",
          batch_name: batchName,
        },
        files: realFiles,
        bankImportMode: "excel" as const,
      }];
    });
    if (!payloads.length) {
      throw new Error("请先至少为一个数据来源选择表格文件（.xlsx 或 .xls）");
    }
    return payloads;
  };

  const isOcrMode = sourceType === "bank" && bankImportMode === "ocr";

  const uploadSection =
    sourceType === "bank" && allowOcr ? (
      <Tabs
        activeKey={bankImportMode}
        onChange={(key) => setBankImportMode(key as "excel" | "ocr")}
        items={[
          {
            key: "excel",
            label: "Excel 导入",
            children: (
              <Form.Item label="选择表格文件" className="data-import-upload-item">
                <Dragger
                  className="import-upload-dragger"
                  multiple
                  disabled={disabled}
                  beforeUpload={() => false}
                  fileList={filesBySource.bank}
                  showUploadList={!hideUploadList}
                  accept=".xlsx,.xls"
                  onChange={(info) => updateFilesForSource("bank", info.fileList)}
                >
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽表格文件到此区域</p>
                  <p className="ant-upload-hint">支持 .xlsx、.xls；数据仅写入本地数据库</p>
                </Dragger>
              </Form.Item>
            ),
          },
          {
            key: "ocr",
            label: "图片/PDF 导入（OCR）",
            children: (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message={`离线 OCR 识别银行流水扫描件，识别后需人工校对再录入。${ocrFormatHint}`}
                />
                <Form.Item label="选择图片或 PDF" className="data-import-upload-item">
                  <Dragger
                    className="import-upload-dragger"
                    multiple
                    disabled={disabled}
                    beforeUpload={() => false}
                    fileList={ocrFiles}
                    accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,.gif,.svg,.pdf"
                    onChange={(info) => setOcrFiles(info.fileList)}
                  >
                    <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                    <p className="ant-upload-text">点击或拖拽图片或 PDF 到此区域</p>
                    <p className="ant-upload-hint">{ocrFormatHint}；支持多页 PDF 合并为一个批次校对</p>
                  </Dragger>
                </Form.Item>
                {ocrJobs.length > 0 ? (
                  <Card size="small" title="待校对任务" style={{ marginBottom: 16 }}>
                    <List
                      size="small"
                      dataSource={ocrJobs}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Link key="review" to={`/bank-ocr/${item.job_id}`}>
                              去校对
                            </Link>,
                          ]}
                        >
                          <Space direction="vertical" size={0}>
                            <span>{item.batch_name || item.job_id.slice(0, 8)}</span>
                            <Text type="secondary">{item.bank_name} · {item.page_count} 页 · {item.rows?.length || 0} 行</Text>
                          </Space>
                          <Tag color="gold">待校对</Tag>
                        </List.Item>
                      )}
                    />
                  </Card>
                ) : null}
              </>
            ),
          },
        ]}
      />
    ) : (
      <Form.Item label="选择表格文件" className="data-import-upload-item">
        <Dragger
          className="import-upload-dragger"
          multiple
          disabled={disabled}
          beforeUpload={() => false}
          fileList={activeFiles}
          showUploadList={!hideUploadList}
          accept=".xlsx,.xls"
          onChange={(info) => updateFilesForSource(activeSource, info.fileList)}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽表格文件到此区域</p>
          <p className="ant-upload-hint">支持多选；支持扩展名 .xlsx、.xls；数据仅写入本地数据库</p>
        </Dragger>
      </Form.Item>
    );

  const formElement = useMemo(
    () => (
      <Form
        form={form}
        layout="vertical"
        className={`data-import-form${compact ? " data-import-form-compact" : ""}`}
        initialValues={{ source_type: "bank", bank_name: "默认来源" }}
        onValuesChange={handleValuesChange}
      >
        <Form.Item label="数据来源" name="source_type" rules={[{ required: true }]}>
          <Radio.Group className="data-import-source-group" disabled={disabled}>
            {(Object.keys(SOURCE_LABELS) as SourceType[]).map((key) => (
              <Radio.Button value={key} key={key}>
                <Space size={6}>
                  <span>{SOURCE_LABELS[key]}</span>
                  {filesBySource[key].length > 0 ? <Tag bordered={false}>{filesBySource[key].length}</Tag> : null}
                </Space>
              </Radio.Button>
            ))}
          </Radio.Group>
        </Form.Item>
        <Form.Item
          label="批次名称"
          name="batch_name"
          tooltip="导入后可识别该批数据的名称"
          rules={[{ max: 120, message: "批次名称不能超过 120 个字符" }]}
        >
          <Input placeholder="如：张三建行流水 / 2024年商务网询价" disabled={disabled} />
        </Form.Item>
        <Form.Item
          label="来源标识 / 银行名称"
          name="bank_name"
          tooltip="银行流水建议填写银行简称"
        >
          <Input placeholder="如：工商银行 / 光大银行 / 商务网 / 微信" disabled={disabled} />
        </Form.Item>
        {uploadSection}
      </Form>
    ),
    [compact, disabled, filesBySource, form, uploadSection]
  );

  return {
    form,
    formElement,
    getPayload,
    getAllPayloads,
    reset,
    clearFilesForSource,
    removeFileForSource,
    sourceType,
    bankImportMode,
    isOcrMode,
    hasExcelFiles,
    hasOcrFiles,
    selectedExcelPayloads,
  };
}

export type DataImportFormHandle = ReturnType<typeof useDataImportForm>;
