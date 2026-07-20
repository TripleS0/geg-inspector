import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tabs,
  Typography,
  Upload,
  message,
} from "antd";
import { CopyOutlined, DeleteOutlined, EditOutlined, ReloadOutlined, SaveOutlined, SettingOutlined, StopOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import {
  analyzeBankTemplateOcrSample,
  analyzeBankTemplateSample,
  api,
  BankTemplateAnalyzeResult,
  BankCatalogItem,
  BankTemplateType,
  listBankTemplateSampleSheets,
  UserBankTemplate,
} from "../api";
import { appTheme } from "../theme";

const { Title, Paragraph, Text } = Typography;

const STD_FIELDS: Record<BankTemplateType, Array<{ key: string; label: string; required?: boolean; desc: string }>> = {
  account_profile: [
    { key: "person_name", label: "姓名原字段", required: true, desc: "开户姓名 / 户名 -> person_name" },
    { key: "acct_no", label: "卡号/账号原字段", required: true, desc: "银行卡号或账号 -> acct_no" },
    { key: "id_no", label: "证件号原字段", desc: "可空 -> id_no" },
    { key: "mobile", label: "手机号原字段", desc: "可空，不用手机号可不映射 -> mobile" },
    { key: "open_date", label: "开户日期原字段", desc: "可空 -> open_date" },
  ],
  txn_detail: [
    { key: "person_name", label: "姓名原字段", desc: "可空；为空时从开户信息按卡号回填 -> person_name" },
    { key: "acct_no", label: "卡号/账号原字段", required: true, desc: "本方银行卡号 / 账号 -> acct_no" },
    { key: "txn_date", label: "交易日期原字段", desc: "交易日期；可与交易时间列合并 -> txn_date" },
    { key: "txn_time_raw", label: "交易时间原字段", required: true, desc: "完整时间或时间列 -> txn_time_raw" },
    { key: "txn_direction", label: "收支标志原字段", desc: "可空；不映射时按金额正负自动判断，正数收入、负数支出 -> txn_direction" },
    { key: "currency", label: "币种原字段", desc: "可空；缺省按 CNY -> currency" },
    { key: "txn_amount", label: "金额原字段", required: true, desc: "交易金额 -> txn_amount" },
    { key: "balance", label: "余额原字段", desc: "可空 -> balance" },
    { key: "counterparty_name", label: "对手名原字段", desc: "可空 -> counterparty_name" },
    { key: "counterparty_account", label: "对手卡号原字段", desc: "可空 -> counterparty_account" },
    { key: "summary", label: "交易描述原字段", desc: "可空 -> summary" },
    { key: "remark", label: "备注原字段", desc: "可空 -> remark" },
    { key: "txn_org_no", label: "交易机构号", desc: "交易行号 / 网点号" },
    { key: "txn_org_name", label: "交易机构名", desc: "交易行名 / 网点名" },
  ],
};

function firstFile(fileList: UploadFile[]): File | null {
  return (fileList[0]?.originFileObj as File | undefined) || null;
}

function splitKeywords(text: string | undefined): string[] {
  return (text || "")
    .split(/[\n,，、;；\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function normalizeDirectionKey(text: string): string {
  const raw = String(text || "").trim().replace(/,/g, "");
  if (!raw) return "";
  const n = Number(raw);
  if (Number.isFinite(n)) {
    return Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : String(n);
  }
  return raw;
}

function defaultDirectionRules(values: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  values.forEach((value) => {
    const key = normalizeDirectionKey(value);
    if (!key) return;
    if (/(借|支|付|出|debit|d)$/i.test(key) || key === "1") out[key] = "支出";
    else if (/(贷|收|入|credit|c)$/i.test(key) || key === "0" || key === "2") out[key] = "收入";
    else out[key] = "未知";
  });
  return out;
}

function BankTemplatesPage() {
  const [form] = Form.useForm<{
    template_type: BankTemplateType;
    bank_display_name: string;
    bank_id: string;
    display_name: string;
    sheet_name?: string;
    bank_keywords: string;
    sheet_keywords: string;
    match_priority: number;
    header_row_0based?: number | null;
  }>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [sampleKind, setSampleKind] = useState<"excel" | "ocr">("excel");
  const [sheetOptions, setSheetOptions] = useState<string[]>([]);
  const [templates, setTemplates] = useState<UserBankTemplate[]>([]);
  const [banks, setBanks] = useState<BankCatalogItem[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<BankTemplateAnalyzeResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [directionRules, setDirectionRules] = useState<Record<string, string>>({});
  const [ruleField, setRuleField] = useState<string | null>(null);
  const [templateView, setTemplateView] = useState<"preview" | "entry">("preview");
  const [newBankOpen, setNewBankOpen] = useState(false);
  const [newBankName, setNewBankName] = useState("");
  const [editingTemplateId, setEditingTemplateId] = useState("");
  const [editingBank, setEditingBank] = useState<BankCatalogItem | null>(null);
  const [editingBankName, setEditingBankName] = useState("");

  const templateType = Form.useWatch("template_type", form) || "txn_detail";
  const stdFields = STD_FIELDS[templateType];
  const mappedSources = useMemo(() => new Set(Object.values(mapping).filter(Boolean)), [mapping]);
  const sourceHeaders = analyzeResult?.source_headers || [...new Set(Object.values(mapping).filter(Boolean))];
  const bankOptions = useMemo(
    () => banks.filter((item) => item.is_active).map((item) => ({ label: item.display_name, value: item.bank_id })),
    [banks]
  );

  const confirmNewBank = async () => {
    const value = newBankName.trim();
    if (!value) return;
    try {
      const bank = await api.createBank({ display_name: value, aliases: [value] });
      setBanks((prev) => [...prev, bank]);
      form.setFieldsValue({ bank_id: bank.bank_id, bank_display_name: bank.display_name, bank_keywords: bank.display_name });
      setNewBankName("");
      setNewBankOpen(false);
      message.success("银行分类已创建");
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const refreshTemplates = async () => {
    const [templateData, bankData] = await Promise.all([api.listBankTemplates(), api.listBanks()]);
    setTemplates(templateData.items || []);
    setBanks(bankData.items || []);
  };

  useEffect(() => {
    form.setFieldsValue({ template_type: "txn_detail", match_priority: 0 });
    void refreshTemplates();
  }, [form]);

  const runAnalyze = async () => {
    const file = firstFile(fileList);
    if (!file) {
      message.warning(sampleKind === "ocr" ? "请先选择图片或 PDF 样本" : "请先选择 Excel 文件");
      return;
    }
    const values = await form.validateFields(["template_type", "bank_id", "bank_display_name"]);
    const selectedSheetName = form.getFieldValue("sheet_name") || "";
    setAnalyzing(true);
    try {
      const result =
        sampleKind === "ocr"
          ? await analyzeBankTemplateOcrSample({
              file,
              templateType: values.template_type,
              bankNameHint: values.bank_display_name,
            })
          : await analyzeBankTemplateSample({
              file,
              sheetName: selectedSheetName,
              templateType: values.template_type,
              bankNameHint: values.bank_display_name,
              headerRow0based: form.getFieldValue("header_row_0based") ?? null,
            });
      setAnalyzeResult(result);
      setMapping(result.suggested_mapping || {});
      setDirectionRules(defaultDirectionRules(result.direction_distinct_values || []));
      if (sampleKind === "excel") {
        form.setFieldsValue({ header_row_0based: result.header_row_selected_0based });
      }
      message.success(sampleKind === "ocr" ? "OCR 样本识别完成，请检查字段映射与规则" : "样本识别完成，请检查字段映射与规则");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleFileChange = async (next: UploadFile[]) => {
    setFileList(next);
    setAnalyzeResult(null);
    setMapping({});
    setDirectionRules({});
    const file = firstFile(next);
    if (!file) {
      setSheetOptions([]);
      form.setFieldsValue({ sheet_name: undefined });
      return;
    }
    if (sampleKind === "ocr") {
      setSheetOptions([]);
      form.setFieldsValue({ sheet_name: undefined });
      return;
    }
    try {
      const sheets = await listBankTemplateSampleSheets(file);
      setSheetOptions(sheets);
      if (sheets.length > 0) {
        form.setFieldsValue({ sheet_name: sheets[0] });
      }
    } catch (err) {
      setSheetOptions([]);
      message.warning(`读取 Sheet 失败：${(err as Error).message}`);
    }
  };

  const assignSource = (stdField: string, source: string) => {
    setMapping((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key !== stdField && next[key] === source) delete next[key];
      });
      if (source) next[stdField] = source;
      else delete next[stdField];
      return next;
    });
  };

  const saveTemplate = async () => {
    const values = await form.validateFields();
    const fieldMap: Record<string, string[]> = {};
    Object.entries(mapping).forEach(([std, source]) => {
      if (source) fieldMap[std] = [source];
    });
    const missing = stdFields.filter((f) => f.required && !fieldMap[f.key]);
    if (missing.length) {
      message.warning(`请先映射必填字段：${missing.map((x) => x.label).join("、")}`);
      return;
    }
    setSaving(true);
    try {
      const payload: UserBankTemplate = {
        display_name: values.display_name || `${values.bank_display_name}-${analyzeResult?.sheet_name || values.sheet_name || "第一个Sheet"}`,
        template_type: values.template_type,
        bank_display_name: values.bank_display_name,
        bank_id: values.bank_id,
        bank_keywords: splitKeywords(values.bank_keywords || values.bank_display_name),
        sheet_keywords: splitKeywords(values.sheet_keywords || analyzeResult?.sheet_name || values.sheet_name || ""),
        field_map: fieldMap,
        signature_columns: Object.values(fieldMap).flat(),
        header_row_0based: values.header_row_0based ?? analyzeResult?.header_row_selected_0based ?? null,
        match_priority: Number(values.match_priority || 0),
        template_group_id: null,
        direction_rules: values.template_type === "txn_detail" ? directionRules : {},
        datetime_patterns: {
          formats: [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y%m%d%H%M%S",
            "%Y%m%d",
          ],
        },
      };
      if (editingTemplateId) await api.updateBankTemplate(editingTemplateId, payload);
      else await api.createBankTemplate(payload);
      message.success(editingTemplateId ? "模板已更新" : "模板已保存");
      setEditingTemplateId("");
      await refreshTemplates();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const mappingColumns: ColumnsType<{ key: string; label: string; required?: boolean; desc: string }> = [
    {
      title: "标准字段",
      dataIndex: "label",
      width: 180,
      render: (label, row) => (
        <Space>
          {row.required ? <Text type="danger">*</Text> : null}
          <Text strong>{label}</Text>
        </Space>
      ),
    },
    { title: "字段说明", dataIndex: "desc", width: 260 },
    {
      title: "映射字段",
      render: (_, row) => (
        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            assignSource(row.key, event.dataTransfer.getData("text/plain"));
          }}
          style={{
            minHeight: 42,
            border: "1px dashed #d9d9d9",
            borderRadius: 8,
            padding: 6,
            background: mapping[row.key] ? "#fff7f5" : "#fafafa",
          }}
        >
          {mapping[row.key] ? (
            <Tag closable onClose={() => assignSource(row.key, "")} color="volcano">
              {mapping[row.key]}
            </Tag>
          ) : (
            <Text type="secondary">拖拽字段到这里</Text>
          )}
          <Select
            allowClear
            size="small"
            placeholder="或选择字段"
            value={mapping[row.key]}
            style={{ minWidth: 180, marginLeft: 8 }}
            onChange={(value) => assignSource(row.key, value || "")}
            options={sourceHeaders.map((header) => ({ label: header, value: header }))}
          />
        </div>
      ),
    },
    {
      title: "规则",
      width: 90,
      render: (_, row) => (
        <Button size="small" icon={<SettingOutlined />} onClick={() => setRuleField(row.key)}>
          配置
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack" style={{ minWidth: 760 }}>
      <Card className="app-card">
        <Title level={3}>银行模板管理</Title>
        <Paragraph type="secondary">
          在预览中查看已有模板；需要新格式时，再录入样本并配置字段。
        </Paragraph>
        {templateView === "entry" ? <Steps
          current={analyzeResult ? 1 : 0}
          items={[{ title: "上传/选源" }, { title: "拖拽映射" }, { title: "配置规则" }, { title: "预览保存" }]}
        /> : null}
        <Tabs activeKey={templateView} onChange={(key) => setTemplateView(key as "preview" | "entry")}
          items={[{ key: "preview", label: "银行模板预览" }, { key: "entry", label: "银行模板录入" }]} />
      </Card>

      {templateView === "entry" ? <>
      <Row gutter={[16, 16]}>
        <Col span={8}>
          <Card title="1. 上传与识别" className="app-card">
            <Form layout="vertical" form={form}>
              <Form.Item label="样本来源">
                <Radio.Group
                  value={sampleKind}
                  onChange={(event) => {
                    const next = event.target.value as "excel" | "ocr";
                    setSampleKind(next);
                    setFileList([]);
                    setSheetOptions([]);
                    setAnalyzeResult(null);
                    setMapping({});
                    setDirectionRules({});
                    form.setFieldsValue({ sheet_name: undefined, header_row_0based: undefined });
                  }}
                >
                  <Radio.Button value="excel">Excel 样本</Radio.Button>
                  <Radio.Button value="ocr">图片 / PDF（OCR）</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Form.Item label={sampleKind === "ocr" ? "样本图片 / PDF" : "样本 Excel"}>
                <Upload
                  accept={sampleKind === "ocr" ? ".png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp,.gif,.svg,.pdf" : ".xlsx,.xls"}
                  fileList={fileList}
                  beforeUpload={() => false}
                  maxCount={1}
                  onChange={({ fileList: next }) => void handleFileChange(next)}
                >
                  <Button>选择文件</Button>
                </Upload>
              </Form.Item>
              <Form.Item name="template_type" label="模板类型" rules={[{ required: true }]}>
                <Radio.Group>
                  <Radio.Button value="txn_detail">银行流水明细</Radio.Button>
                  <Radio.Button value="account_profile">开户信息</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Form.Item label="归属银行" required>
                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item name="bank_id" rules={[{ required: true, message: "请输入归属银行" }]} noStyle>
                    <Select showSearch allowClear placeholder="选择已有银行" options={bankOptions} style={{ width: "100%" }} onChange={(bankId) => {
                      const bank = banks.find((item) => item.bank_id === bankId);
                      form.setFieldsValue({ bank_display_name: bank?.display_name || "", bank_keywords: bank?.aliases.join(" ") || "" });
                    }} />
                  </Form.Item>
                  <Button onClick={() => setNewBankOpen(true)}>新增银行</Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item name="bank_display_name" hidden><Input /></Form.Item>
              <Form.Item name="sheet_name" label="Sheet 名称" hidden={sampleKind === "ocr"}>
                <Select
                  allowClear
                  showSearch
                  placeholder="上传后自动解析；不选默认第一个 Sheet"
                  options={sheetOptions.map((sheet) => ({ label: sheet, value: sheet }))}
                />
              </Form.Item>
              <Form.Item
                name="header_row_0based"
                label="表头行（清理空行/标题后的 0 基序号，可留空自动识别）"
                tooltip="有些银行导出会包含隐藏空行、Unnamed 行或标题行；这里的行号按系统清理后的样本区编号。"
                hidden={sampleKind === "ocr"}
              >
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Button type="primary" loading={analyzing} icon={<ReloadOutlined />} onClick={runAnalyze}>
                {sampleKind === "ocr" ? "OCR 识别样本" : "识别样本"}
              </Button>
            </Form>
          </Card>
        </Col>

        <Col span={16}>
          <Card title="2. 映射字段" className="app-card">
            {analyzeResult ? (
              <>
                <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
                  <Descriptions.Item label="文件">{analyzeResult.file_name}</Descriptions.Item>
                  <Descriptions.Item label="来源">
                    {analyzeResult.input_kind === "ocr" ? "OCR 识别" : "Excel"}
                  </Descriptions.Item>
                  <Descriptions.Item label="Sheet">{analyzeResult.sheet_name}</Descriptions.Item>
                  {analyzeResult.input_kind !== "ocr" ? (
                    <Descriptions.Item label="表头行">
                      清理后第 {analyzeResult.header_row_selected_0based} 行
                    </Descriptions.Item>
                  ) : null}
                </Descriptions>
                {analyzeResult.ocr_page_meta && Object.keys(analyzeResult.ocr_page_meta).length ? (
                  <Alert
                    style={{ marginBottom: 12 }}
                    type="info"
                    showIcon
                    message={`OCR 页眉：${Object.entries(analyzeResult.ocr_page_meta)
                      .map(([key, value]) => `${key}=${value}`)
                      .join("；")}`}
                  />
                ) : null}
                <div style={{ marginBottom: 12 }}>
                  <Text strong>源文件表头：</Text>
                  <Space wrap style={{ marginLeft: 8 }}>
                    {sourceHeaders.map((header) => (
                      <Tag
                        key={header}
                        draggable
                        color={mappedSources.has(header) ? "default" : "volcano"}
                        onDragStart={(event) => event.dataTransfer.setData("text/plain", header)}
                      >
                        {header}
                      </Tag>
                    ))}
                  </Space>
                </div>
                <Table
                  rowKey="key"
                  size="small"
                  pagination={false}
                  columns={mappingColumns}
                  dataSource={stdFields}
                />
              </>
            ) : (
              <Alert type="info" showIcon message="请先上传样本并识别，系统会自动给出初始映射建议。" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="3. 预览与保存" className="app-card">
        <Form layout="vertical" form={form}>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="display_name" label="模板显示名">
                <Input placeholder="如：工商银行交易明细模板" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="bank_keywords" label="银行关键词">
                <Input placeholder="如：工商银行 工行 icbc" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="sheet_keywords" label="Sheet 关键词">
                <Input placeholder="如：交易明细 流水" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="match_priority" label="匹配优先级">
                <InputNumber style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
        {analyzeResult?.datetime_analysis?.merged_preview?.length ? (
          <Alert
            style={{ marginBottom: 12 }}
            type="success"
            showIcon
            message={`时间预览：${analyzeResult.datetime_analysis.merged_preview.join("，")}`}
          />
        ) : null}
        {analyzeResult ? (
          <Table
            size="small"
            pagination={false}
            scroll={{ x: true }}
            columns={(analyzeResult.preview_columns || []).map((col) => ({ title: col, dataIndex: col, key: col }))}
            dataSource={(analyzeResult.preview_grid || []).map((row, idx) => {
              const obj: Record<string, string | number> = { key: idx };
              analyzeResult.preview_columns.forEach((col, colIdx) => {
                obj[col] = row[colIdx] || "";
              });
              return obj;
            })}
          />
        ) : null}
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={!analyzeResult && !editingTemplateId} onClick={saveTemplate}>
            {editingTemplateId ? "更新模板" : "保存模板"}
          </Button>
          <Button onClick={refreshTemplates}>刷新模板列表</Button>
        </Space>
      </Card>
      </> : null}

      {templateView === "preview" ? <Card title="已有银行模板" className="app-card">
        <Collapse
          defaultActiveKey={banks.filter((bank) => bank.is_active).map((bank) => bank.bank_id)}
          items={banks.map((bank) => ({
            key: bank.bank_id,
            label: <Space><Text strong>{bank.display_name}</Text><Tag>{bank.is_builtin ? "内置银行" : "自定义银行"}</Tag><Tag color={bank.is_active ? "success" : "default"}>{bank.is_active ? "启用" : "停用"}</Tag></Space>,
            extra: <Space onClick={(event) => event.stopPropagation()}>
              <Button size="small" disabled={bank.is_builtin} icon={<EditOutlined />} onClick={() => { setEditingBank(bank); setEditingBankName(bank.display_name); }}>改名</Button>
              <Button size="small" icon={<StopOutlined />} onClick={async () => { await api.updateBank(bank.bank_id, { is_active: bank.is_active ? 0 : 1 }); await refreshTemplates(); }}>{bank.is_active ? "停用" : "启用"}</Button>
            </Space>,
            children: <Table
              rowKey={(row) => row.template_id || row.display_name}
              size="small"
              pagination={false}
              columns={[
                { title: "模板名", dataIndex: "display_name" },
                { title: "类型", render: (_, row) => row.template_type === "account_profile" ? "开户信息" : "交易流水" },
                { title: "来源", render: (_, row) => <Tag>{row.is_builtin ? "内置" : "自定义"}</Tag> },
                { title: "状态", render: (_, row) => <Tag color={row.is_active !== 0 ? "success" : "default"}>{row.is_active !== 0 ? "启用" : "停用"}</Tag> },
                { title: "Sheet 关键词", render: (_, row) => row.sheet_keywords?.join("、") || "-" },
                { title: "字段映射", ellipsis: true, render: (_, row) => Object.entries(row.field_map || {}).map(([target, source]) => `${target} ← ${source.join("/")}`).join("；") || "-" },
                {
                  title: "操作",
                  width: 250,
                  render: (_, row) => row.is_builtin ? <Text type="secondary">内置模板只读</Text> : <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => {
                      setEditingTemplateId(row.template_id || "");
                      setTemplateView("entry");
                      setAnalyzeResult(null);
                      setMapping(Object.fromEntries(Object.entries(row.field_map || {}).map(([key, values]) => [key, values[0] || ""])));
                      setDirectionRules(row.direction_rules || {});
                      form.setFieldsValue({
                        template_type: row.template_type,
                        bank_id: row.bank_id || bank.bank_id,
                        bank_display_name: bank.display_name,
                        display_name: row.display_name,
                        bank_keywords: row.bank_keywords.join(" "),
                        sheet_keywords: row.sheet_keywords.join(" "),
                        match_priority: row.match_priority,
                        header_row_0based: row.header_row_0based,
                      });
                    }}>编辑</Button>
                    <Button size="small" icon={<CopyOutlined />} onClick={async () => { await api.createBankTemplate({ ...row, template_id: undefined, display_name: `${row.display_name} 副本` }); await refreshTemplates(); }}>复制</Button>
                    <Button size="small" icon={<StopOutlined />} onClick={async () => { if (row.template_id) await api.updateBankTemplate(row.template_id, { is_active: row.is_active === 0 ? 1 : 0 }); await refreshTemplates(); }}>{row.is_active === 0 ? "启用" : "停用"}</Button>
                    <Button danger size="small" icon={<DeleteOutlined />} onClick={async () => { if (row.template_id) await api.deleteBankTemplate(row.template_id); await refreshTemplates(); }}>删除</Button>
                  </Space>,
                },
              ]}
              dataSource={templates.filter((template) => template.bank_id === bank.bank_id)}
            />,
          }))}
        />
      </Card>
      : null}
      <Modal title="新增银行" open={newBankOpen} onOk={confirmNewBank} onCancel={() => setNewBankOpen(false)} okText="确认">
        <Input autoFocus value={newBankName} onChange={(event) => setNewBankName(event.target.value)} placeholder="如：长沙银行" />
      </Modal>
      <Modal title="修改银行名称" open={!!editingBank} onOk={async () => {
        if (!editingBank || !editingBankName.trim()) return;
        await api.updateBank(editingBank.bank_id, { display_name: editingBankName.trim() });
        setEditingBank(null);
        await refreshTemplates();
      }} onCancel={() => setEditingBank(null)} okText="保存">
        <Input value={editingBankName} onChange={(event) => setEditingBankName(event.target.value)} />
      </Modal>

      <Drawer title="字段规则配置" open={!!ruleField} onClose={() => setRuleField(null)} width={420}>
        {ruleField === "txn_direction" ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Alert type="info" showIcon message="将样本中的借贷标志取值映射为收入、支出或未知。" />
            {Object.entries(directionRules).map(([key, value]) => (
              <Space key={key}>
                <Input value={key} disabled style={{ width: 160 }} />
                <Select
                  value={value}
                  style={{ width: 120 }}
                  options={["收入", "支出", "未知"].map((x) => ({ label: x, value: x }))}
                  onChange={(next) => setDirectionRules((prev) => ({ ...prev, [key]: next }))}
                />
              </Space>
            ))}
          </Space>
        ) : (
          <Alert
            type="info"
            showIcon
            message="通用规则"
            description={`字段 ${ruleField || ""} 当前使用默认解析。日期/时间字段会自动尝试常见格式并在预览区展示。`}
          />
        )}
        <div style={{ marginTop: 24, color: appTheme.colorPrimary }}>规则会随模板保存并在标准化阶段优先应用。</div>
      </Drawer>
    </div>
  );
}

export default BankTemplatesPage;
