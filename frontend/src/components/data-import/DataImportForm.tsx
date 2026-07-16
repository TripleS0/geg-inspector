import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Form, Input, List, Radio, Select, Space, Tabs, Tag, Typography, Upload, message } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { UploadFile } from "antd";
import { api, type BankCatalogItem, type BankOcrJob, type BankOcrProfile, type BankTemplateType, type UserBankTemplate } from "../../api";
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
  sheetAssignments?: Record<string, BankFileAssignment>;
}

interface BankSheetAssignment {
  template_id: string;
  template_type: BankTemplateType;
  headers: string[];
  suggested_template_id: string;
}

interface BankFileAssignment {
  bank_id: string;
  suggested_bank_name?: string;
  default_account_template_id?: string;
  default_txn_template_id?: string;
  sheets: Record<string, BankSheetAssignment>;
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
  const [bankTemplates, setBankTemplates] = useState<UserBankTemplate[]>([]);
  const [banks, setBanks] = useState<BankCatalogItem[]>([]);
  const [bankAssignments, setBankAssignments] = useState<Record<string, BankFileAssignment>>({});
  const [selectedBankFiles, setSelectedBankFiles] = useState<string[]>([]);
  const [batchBankId, setBatchBankId] = useState("");
  const [batchAccountTemplateId, setBatchAccountTemplateId] = useState("");
  const [batchTxnTemplateId, setBatchTxnTemplateId] = useState("");
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
    void Promise.all([api.listBankTemplates(), api.listBanks(true)]).then(([templateData, bankData]) => {
      setBankTemplates(templateData.items || []);
      setBanks(bankData.items || []);
    }).catch(() => {
      setBankTemplates([]);
      setBanks([]);
    });
  }, []);

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
    if (type === "bank") {
      setBankAssignments((prev) => Object.fromEntries(fileList.map((item) => {
        const file = item.originFileObj as File | undefined;
        const fileName = file?.name || item.name;
        return [fileName, prev[fileName] || { bank_id: "", sheets: {} }];
      })));
    }
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
          sheetAssignments: type === "bank" ? bankAssignments : undefined,
        }];
      }),
    [bankAssignments, bankNames, batchNames, filesBySource]
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
    setBankAssignments({});
    setSelectedBankFiles([]);
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
        sheetAssignments: type === "bank" ? bankAssignments : undefined,
      }];
    });
    if (!payloads.length) {
      throw new Error("请先至少为一个数据来源选择表格文件（.xlsx 或 .xls）");
    }
    const bankPayload = payloads.find((item) => item.values.source_type === "bank");
    if (bankPayload) {
      for (const file of bankPayload.files) {
        const config = bankAssignments[file.name];
        if (!config?.bank_id) throw new Error(`请先确认文件“${file.name}”所属银行`);
        if (!Object.keys(config.sheets).length && !config.default_account_template_id && !config.default_txn_template_id) {
          throw new Error(`请先为“${file.name}”选择开户信息或交易流水模板`);
        }
      }
    }
    return payloads;
  };

  const applyBatchAssignment = () => {
    if (!selectedBankFiles.length) return;
    if (!batchBankId && !batchAccountTemplateId && !batchTxnTemplateId) {
      message.warning("请先选择要应用的银行或模板");
      return;
    }
    const validFiles = selectedBankFiles.filter((fileName) => bankAssignments[fileName]);
    if (!validFiles.length) {
      message.warning("文件仍在解析中，请稍后再试");
      return;
    }
    setBankAssignments((prev) => {
      const next = { ...prev };
      selectedBankFiles.forEach((fileName) => {
        const current = next[fileName];
        if (!current) return;
        const bankId = batchBankId || current.bank_id;
        next[fileName] = {
          ...current,
          bank_id: bankId,
          default_account_template_id: batchAccountTemplateId || (current.default_account_template_id && bankTemplates.find((item) => item.template_id === current.default_account_template_id)?.bank_id === bankId ? current.default_account_template_id : ""),
          default_txn_template_id: batchTxnTemplateId || (current.default_txn_template_id && bankTemplates.find((item) => item.template_id === current.default_txn_template_id)?.bank_id === bankId ? current.default_txn_template_id : ""),
          sheets: Object.fromEntries(Object.entries(current.sheets).map(([sheetName, sheet]) => {
            const selectedId = sheet.template_type === "account_profile"
              ? batchAccountTemplateId
              : batchTxnTemplateId;
            const currentTemplate = bankTemplates.find((item) => item.template_id === sheet.template_id);
            return [sheetName, {
              ...sheet,
              template_id: selectedId || (currentTemplate?.bank_id === bankId ? sheet.template_id : ""),
            }];
          })),
        };
      });
      return next;
    });
    const bankLabel = banks.find((item) => item.bank_id === batchBankId)?.display_name;
    const applied = [bankLabel, batchAccountTemplateId ? "开户信息模板" : "", batchTxnTemplateId ? "交易流水模板" : ""].filter(Boolean);
    message.success(`已将${applied.join("、")}应用到 ${validFiles.length} 个文件`);
    setSelectedBankFiles([]);
  };
  const clearBatchTemplates = () => {
    setBankAssignments((prev) => {
      const next = { ...prev };
      selectedBankFiles.forEach((fileName) => {
        if (!next[fileName]) return;
        next[fileName] = {
          ...next[fileName],
          default_account_template_id: "",
          default_txn_template_id: "",
          sheets: Object.fromEntries(Object.entries(next[fileName].sheets).map(([name, sheet]) => [name, { ...sheet, template_id: "" }])),
        };
      });
      return next;
    });
  };
  const toggleBankFileSelection = (fileName: string, checked: boolean) => {
    setSelectedBankFiles((prev) => checked ? [...new Set([...prev, fileName])] : prev.filter((name) => name !== fileName));
  };
  const replaceBankFileSelection = (fileNames: string[]) => {
    setSelectedBankFiles([...new Set(fileNames)]);
  };
  const bankAssignmentSummaries = useMemo(() => Object.fromEntries(
    Object.entries(bankAssignments).map(([fileName, config]) => {
      const sheetItems = Object.values(config.sheets);
      return [fileName, {
        bankName: banks.find((bank) => bank.bank_id === config.bank_id)?.display_name || "银行待确认",
        confirmedTemplates: sheetItems.filter((sheet) => sheet.template_id).length,
        sheetCount: sheetItems.length,
        hasPresetTemplate: Boolean(config.default_account_template_id || config.default_txn_template_id),
      }];
    })
  ), [bankAssignments, banks]);
  const isOcrMode = sourceType === "bank" && bankImportMode === "ocr";

  const bankBatchToolbar = filesBySource.bank.length ? (
    <Space wrap>
      <Checkbox
        checked={selectedBankFiles.length === filesBySource.bank.length}
        indeterminate={selectedBankFiles.length > 0 && selectedBankFiles.length < filesBySource.bank.length}
        onChange={(event) => setSelectedBankFiles(event.target.checked ? filesBySource.bank.map((item) => item.name) : [])}
      >全选银行文件</Checkbox>
      <Select placeholder="批量归属银行" value={batchBankId || undefined} onChange={(value) => {
        setBatchBankId(value);
        setBatchAccountTemplateId("");
        setBatchTxnTemplateId("");
      }} style={{ width: 170 }} options={banks.map((item) => ({ label: item.display_name, value: item.bank_id }))} />
      <Select placeholder="开户信息模板" value={batchAccountTemplateId || undefined} onChange={setBatchAccountTemplateId} allowClear disabled={!batchBankId} style={{ width: 220 }}
        options={bankTemplates.filter((item) => item.bank_id === batchBankId && item.template_type === "account_profile" && item.is_active !== 0).map((item) => ({ label: `${item.is_builtin ? "内置" : "自定义"} · ${item.display_name}`, value: item.template_id }))} />
      <Select placeholder="交易流水模板" value={batchTxnTemplateId || undefined} onChange={setBatchTxnTemplateId} allowClear disabled={!batchBankId} style={{ width: 220 }}
        options={bankTemplates.filter((item) => item.bank_id === batchBankId && item.template_type === "txn_detail" && item.is_active !== 0).map((item) => ({ label: `${item.is_builtin ? "内置" : "自定义"} · ${item.display_name}`, value: item.template_id }))} />
      <Button onClick={applyBatchAssignment} disabled={!selectedBankFiles.length}>应用到已勾选文件</Button>
      <Button onClick={clearBatchTemplates} disabled={!selectedBankFiles.length}>清除模板</Button>
      <Link to="/data-center/manage/bank-templates"><Button type="link">管理银行与模板</Button></Link>
    </Space>
  ) : null;

  const bankPreview = filesBySource.bank.length ? (
    <Card size="small" title="银行文件预览与模板选择" style={{ marginTop: 12 }}>
      <div style={{ marginBottom: 10 }}>{bankBatchToolbar}</div>
      <List size="small" dataSource={filesBySource.bank} renderItem={(item) => {
        const file = item.originFileObj as File | undefined;
        const fileName = file?.name || item.name;
        const config = bankAssignments[fileName];
        const sheets = config?.sheets || {};
        const hasPresetTemplate = Boolean(config?.default_account_template_id || config?.default_txn_template_id);
        const complete = Boolean(config?.bank_id) && (hasPresetTemplate || (Object.keys(sheets).length > 0 && Object.values(sheets).every((sheet) => sheet.template_id)));
        return <List.Item>
          <Space direction="vertical" style={{ width: "100%" }} size={6}>
            <Space wrap>
              <Checkbox checked={selectedBankFiles.includes(fileName)} onChange={(event) => setSelectedBankFiles((prev) => event.target.checked ? [...new Set([...prev, fileName])] : prev.filter((name) => name !== fileName))}>{fileName}</Checkbox>
              <Tag color={complete ? "success" : "warning"}>{complete ? "已确认" : "待确认"}</Tag>
              <Text type="secondary">{Object.keys(sheets).length ? `${Object.keys(sheets).length} 个 Sheet` : "导入时统一识别 Sheet"}</Text>
              <Select placeholder="确认所属银行" value={config?.bank_id || undefined} style={{ width: 170 }} onChange={(bankId) => setBankAssignments((prev) => {
                const current = prev[fileName];
                if (!current) return prev;
                return { ...prev, [fileName]: {
                  ...current,
                  bank_id: bankId,
                  sheets: Object.fromEntries(Object.entries(current.sheets).map(([name, sheet]) => {
                    const template = bankTemplates.find((entry) => entry.template_id === sheet.template_id);
                    return [name, { ...sheet, template_id: template?.bank_id === bankId ? sheet.template_id : "" }];
                  })),
                }};
              })} options={banks.map((entry) => ({ label: entry.display_name, value: entry.bank_id }))} />
            </Space>
            {Object.keys(sheets).map((sheet) => {
              const sheetConfig = sheets[sheet];
              const candidates = bankTemplates.filter((entry) => entry.bank_id === config?.bank_id && entry.template_type === sheetConfig.template_type && entry.is_active !== 0);
              return <Space key={sheet} wrap style={{ paddingLeft: 24 }}><Tag>{sheet}</Tag>
                <Tag color="blue">{sheetConfig.template_type === "account_profile" ? "开户信息" : "交易流水"}</Tag>
                <Text style={{ width: 260 }} ellipsis={{ tooltip: sheetConfig.headers.join("、") }}>{sheetConfig.headers.join("、") || "未识别到表头"}</Text>
                <Select placeholder="选择模板" value={sheetConfig.template_id || undefined} style={{ width: 250 }} onChange={(value) => setBankAssignments((prev) => ({ ...prev, [fileName]: { ...prev[fileName], sheets: { ...prev[fileName].sheets, [sheet]: { ...prev[fileName].sheets[sheet], template_id: value } } } }))}
                  options={candidates.map((entry) => ({ label: `${entry.is_builtin ? "内置" : "自定义"} · ${entry.display_name}`, value: entry.template_id }))} />
                {sheetConfig.suggested_template_id && sheetConfig.template_id === sheetConfig.suggested_template_id ? <Text type="secondary">系统推荐</Text> : null}
              </Space>;
            })}
          </Space>
        </List.Item>;
      }} />
    </Card>
  ) : null;

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
              <>
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
              {bankPreview}
              </>
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
    bankBatchToolbar,
    selectedBankFiles,
    toggleBankFileSelection,
    replaceBankFileSelection,
    bankAssignmentSummaries,
  };
}

export type DataImportFormHandle = ReturnType<typeof useDataImportForm>;
