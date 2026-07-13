import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Form, Input, List, Radio, Space, Tabs, Tag, Typography, Upload } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { UploadFile } from "antd";
import dayjs from "dayjs";
import { api, type BankOcrJob, type BankOcrProfile } from "../../api";
import { SOURCE_LABELS, SourceType } from "./constants";

const { Dragger } = Upload;
const { Text } = Typography;

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
}

export function useDataImportForm(options: UseDataImportFormOptions = {}) {
  const { disabled = false, allowOcr = true, compact = false } = options;
  const [form] = Form.useForm<DataImportFormValues>();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [ocrFiles, setOcrFiles] = useState<UploadFile[]>([]);
  const [bankImportMode, setBankImportMode] = useState<"excel" | "ocr">("excel");
  const [ocrJobs, setOcrJobs] = useState<BankOcrJob[]>([]);
  const [ocrFormatHint, setOcrFormatHint] = useState("支持 PNG、JPEG、BMP、TIFF、WebP、GIF、SVG 及 PDF");
  const sourceType = Form.useWatch("source_type", form) as SourceType | undefined;

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
    const activeFiles = sourceType === "bank" && bankImportMode === "ocr" ? ocrFiles : files;
    if (activeFiles.length === 0) return;
    const current = String(form.getFieldValue("batch_name") || "").trim();
    if (current) return;
    if (sourceType === "commercial") {
      form.setFieldsValue({ batch_name: `商务网-${dayjs().format("YYYY-MM-DD-HHmmss")}` });
      return;
    }
    const first = activeFiles[0].name.replace(/\.(xlsx|xls|jpg|jpeg|png|pdf)$/i, "");
    form.setFieldsValue({ batch_name: first });
  }, [files, ocrFiles, form, sourceType, bankImportMode]);

  const reset = () => {
    form.resetFields();
    setFiles([]);
    setOcrFiles([]);
    setBankImportMode("excel");
  };

  const getPayload = async (): Promise<DataImportPayload> => {
    const values = await form.validateFields();
    const useOcr = values.source_type === "bank" && bankImportMode === "ocr";
    const activeList = useOcr ? ocrFiles : files;
    const realFiles = activeList
      .map((item) => item.originFileObj as File | undefined)
      .filter((file): file is File => Boolean(file));
    if (!realFiles.length) {
      throw new Error(useOcr ? "请先选择至少一个图片或 PDF 文件" : "请先选择至少一个表格文件（.xlsx 或 .xls）");
    }
    return { values, files: realFiles, bankImportMode: useOcr ? "ocr" : "excel" };
  };

  const isOcrMode = sourceType === "bank" && bankImportMode === "ocr";

  const isCommercial = sourceType === "commercial";

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
                  fileList={files}
                  accept=".xlsx,.xls"
                  onChange={(info) => setFiles(info.fileList)}
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
          fileList={files}
          accept=".xlsx,.xls"
          onChange={(info) => setFiles(info.fileList)}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽表格文件到此区域</p>
          <p className="ant-upload-hint">
            {isCommercial
              ? "支持多选；同一批次可合并多个发电厂/采购单位文件（如 A发电厂.xlsx + B发电厂.xlsx），分析时按批次统一统计"
              : "支持多选；支持扩展名 .xlsx、.xls；数据仅写入本地数据库"}
          </p>
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
      >
        <Form.Item label="数据来源" name="source_type" rules={[{ required: true }]}>
          <Radio.Group className="data-import-source-group" disabled={disabled}>
            {(Object.keys(SOURCE_LABELS) as SourceType[]).map((key) => (
              <Radio.Button value={key} key={key}>
                {SOURCE_LABELS[key]}
              </Radio.Button>
            ))}
          </Radio.Group>
        </Form.Item>
        {isCommercial ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="多文件请一次选齐导入，或到「批次管理」追加到已有批次"
            description="每次导入都会创建新的独立批次；批次名称仅用于显示识别。若要把文件合并进已有批次，请在批次管理中选择目标批次后追加导入。"
          />
        ) : null}
        <Form.Item
          label="批次名称"
          name="batch_name"
          tooltip={
            isCommercial
              ? "一次导入对应一个批次；多文件会整合到该批次，后续分析与导出均按批次进行"
              : "导入后可识别该批数据的名称"
          }
          rules={[{ max: 120, message: "批次名称不能超过 120 个字符" }]}
        >
          <Input
            placeholder={isCommercial ? "如：2024年商务网询价（含多发电厂）" : "如：张三建行流水 / 2024年商务网询价"}
            disabled={disabled}
          />
        </Form.Item>
        <Form.Item
          label={isCommercial ? "默认采购单位（单文件可选）" : "来源标识 / 银行名称"}
          name="bank_name"
          tooltip={
            isCommercial
              ? "多文件导入时按文件名识别采购单位（如 A发电厂数据.xlsx）；单文件时可在此填写默认采购单位"
              : "银行流水建议填写银行简称"
          }
        >
          <Input
            placeholder={isCommercial ? "多文件可留空，将按各文件名识别" : "如：工商银行 / 光大银行 / 商务网 / 微信"}
            disabled={disabled}
          />
        </Form.Item>
        {uploadSection}
      </Form>
    ),
    [compact, disabled, form, isCommercial, uploadSection]
  );

  return {
    form,
    formElement,
    getPayload,
    reset,
    sourceType,
    bankImportMode,
    isOcrMode,
  };
}

export type DataImportFormHandle = ReturnType<typeof useDataImportForm>;
