import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { QuestionCircleOutlined, SaveOutlined, SettingOutlined } from "@ant-design/icons";
import { api, FusionModelItem } from "../../api";

const { Title, Text, Paragraph } = Typography;

const PARAM_LABELS: Record<string, string> = {
  large_amount_threshold: "大额资金阈值（元）",
  top_n: "Top N 排名",
  repeat_amount_min_count: "重复金额最少次数",
  special_amount_whitelist: "特殊金额白名单",
  min_win_count: "最少中标次数",
  weight: "规则权重",
  min_shared_inquiries: "最少同场次数",
  min_co_rate: "高频陪标同场占比阈值（0-1）",
  min_rotating_exclusive_wins: "轮流中标最少交替次数",
  min_alternation_score: "轮流中标交替率阈值（0-1）",
};

const PARAM_TOOLTIPS: Record<string, string> = {
  min_shared_inquiries:
    "关联企业进入分析列表所需的最低同场询价次数。低于该次数的企业不会出现在同场关联表中。",
  min_co_rate:
    "同场次数 ÷ 目标企业参标项目数。达到该比例时标记「高频陪标」。例如 0.25 表示同场占比 ≥ 25%。",
  min_rotating_exclusive_wins:
    "判定「轮流中标」所需的最少交替中标次数：双方在同场询价中轮流成为唯一中标方的项目数。",
  min_alternation_score:
    "中标方交替率（0–1）。1 表示相邻项目中标方每次都切换；0.55 表示约一半相邻项目会换人中标。",
  large_amount_threshold: "单笔交易金额达到该值时触发大额类事件。",
  top_n: "排名类分析保留的前 N 名数量。",
  repeat_amount_min_count: "同一金额重复出现达到此次数时标记为特殊金额。",
  min_win_count: "同一企业中标次数达到该值时标记重复中标。",
  weight: "风险规则权重，影响风险分计算。",
  special_amount_whitelist: "不视为异常的特殊金额列表，逗号分隔。",
};

const RATE_PARAM_KEYS = new Set(["min_co_rate", "min_alternation_score"]);

const CATEGORY_COLORS: Record<string, string> = {
  bank: "blue",
  wechat: "green",
  commercial: "purple",
  risk: "volcano",
};

interface FusionModelManagePanelProps {
  caseId: number;
  caseName?: string;
}

function FusionModelManagePanel({ caseId, caseName }: FusionModelManagePanelProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState<FusionModelItem[]>([]);
  const [categories, setCategories] = useState<Array<{ category: string; category_label: string; models: FusionModelItem[] }>>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, FusionModelItem>>({});
  const [paramForm] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listFusionModels(caseId);
      setModels(data.items);
      setCategories(data.categories);
      const map: Record<string, FusionModelItem> = {};
      for (const item of data.items) {
        map[item.model_key] = { ...item, params: { ...item.params } };
      }
      setDraft(map);
      setSelectedKey((prev) => prev ?? data.items.find((m) => m.enabled)?.model_key ?? data.items[0]?.model_key ?? null);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selected = selectedKey ? draft[selectedKey] : null;

  useEffect(() => {
    if (!selected) {
      paramForm.resetFields();
      return;
    }
    paramForm.setFieldsValue(selected.params);
  }, [selected, paramForm]);

  const toggleModel = (modelKey: string, enabled: boolean) => {
    setDraft((prev) => ({
      ...prev,
      [modelKey]: { ...prev[modelKey], enabled },
    }));
  };

  const onParamChange = () => {
    if (!selectedKey) return;
    const values = paramForm.getFieldsValue(true);
    setDraft((prev) => ({
      ...prev,
      [selectedKey]: { ...prev[selectedKey], params: { ...prev[selectedKey].params, ...values } },
    }));
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const items = Object.values(draft).map((item) => ({
        model_key: item.model_key,
        enabled: item.enabled,
        params: item.params,
      }));
      const data = await api.saveFusionModels(caseId, items);
      setModels(data.items);
      setCategories(data.categories);
      message.success("模型配置已保存");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const tableData = useMemo(
    () =>
      models.map((item) => ({
        key: item.model_key,
        ...item,
        enabled: draft[item.model_key]?.enabled ?? item.enabled,
      })),
    [models, draft]
  );

  const columns = [
    {
      title: "启用",
      dataIndex: "enabled",
      width: 72,
      render: (_: boolean, row: FusionModelItem & { key: string }) => (
        <Checkbox
          checked={draft[row.model_key]?.enabled ?? row.enabled}
          onChange={(e) => toggleModel(row.model_key, e.target.checked)}
        />
      ),
    },
    {
      title: "模型名称",
      dataIndex: "name",
      render: (name: string, row: FusionModelItem & { key: string }) => (
        <Button
          type="link"
          className="fusion-model-name-btn"
          onClick={() => setSelectedKey(row.model_key)}
          style={{ padding: 0, fontWeight: selectedKey === row.model_key ? 600 : 400 }}
        >
          {name}
        </Button>
      ),
    },
    {
      title: "分类",
      dataIndex: "category_label",
      width: 160,
      render: (label: string, row: FusionModelItem) => (
        <Tag color={CATEGORY_COLORS[row.category] || "default"}>{label}</Tag>
      ),
    },
    {
      title: "触发事件类型",
      dataIndex: "event_type_label",
      width: 120,
      render: (label: string) => <Tag>{label}</Tag>,
    },
    {
      title: "说明",
      dataIndex: "description",
      ellipsis: true,
    },
  ];

  const paramFields = selected?.param_schema ?? [];

  const renderParamLabel = (field: string) => (
    <span className="fusion-param-label">
      {PARAM_LABELS[field] || field}
      {PARAM_TOOLTIPS[field] ? (
        <Tooltip title={PARAM_TOOLTIPS[field]} placement="topLeft">
          <QuestionCircleOutlined className="fusion-param-help-icon" />
        </Tooltip>
      ) : null}
    </span>
  );

  return (
    <div className="fusion-model-manage">
      <Card className="app-card fusion-hub-panel" bordered={false}>
        <div className="fusion-panel-head">
          <div>
            <Title level={4} style={{ margin: 0 }}>
              <SettingOutlined style={{ marginRight: 8, color: "#9a3412" }} />
              模型管理
            </Title>
            <Paragraph type="secondary" style={{ margin: "6px 0 0" }}>
              配置银行流水、微信转账、商务网与围串标风险模型的启用状态与参数；保存后事件管理将按此规则扫描案件数据。
              {caseName ? ` 当前案件：${caseName}` : ""}
            </Paragraph>
          </div>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void onSave()}>
            保存配置
          </Button>
        </div>

        {loading ? (
          <div className="fusion-panel-loading">
            <Spin tip="加载模型配置…" />
          </div>
        ) : (
          <Row gutter={[20, 20]}>
            <Col xs={24} lg={15}>
              {categories.map((cat) => (
                <div key={cat.category} className="fusion-model-category">
                  <div className="fusion-model-category-head">
                    <Tag color={CATEGORY_COLORS[cat.category] || "default"}>{cat.category_label}</Tag>
                    <Text type="secondary">
                      {cat.models.filter((m) => draft[m.model_key]?.enabled).length}/{cat.models.length} 已启用
                    </Text>
                  </div>
                </div>
              ))}
              <Table
                className="fusion-model-table"
                size="middle"
                columns={columns}
                dataSource={tableData}
                pagination={{ pageSize: 12, showSizeChanger: false }}
                rowClassName={(row) => (row.key === selectedKey ? "fusion-model-row-selected" : "")}
              />
            </Col>
            <Col xs={24} lg={9}>
              <Card className="fusion-model-params-card" title="参数配置" bordered={false}>
                {!selected ? (
                  <Empty description="请选择左侧模型" />
                ) : paramFields.length === 0 ? (
                  <Alert
                    type="info"
                    showIcon
                    message={`「${selected.name}」无需额外参数`}
                    description={selected.description}
                  />
                ) : (
                  <Form form={paramForm} layout="vertical" onValuesChange={onParamChange}>
                    <Paragraph type="secondary">{selected.description}</Paragraph>
                    {paramFields.includes("large_amount_threshold") && (
                      <Form.Item name="large_amount_threshold" label={renderParamLabel("large_amount_threshold")}>
                        <InputNumber style={{ width: "100%" }} min={0} step={10000} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",")} />
                      </Form.Item>
                    )}
                    {paramFields.includes("top_n") && (
                      <Form.Item name="top_n" label={renderParamLabel("top_n")}>
                        <InputNumber style={{ width: "100%" }} min={1} max={100} />
                      </Form.Item>
                    )}
                    {paramFields.includes("repeat_amount_min_count") && (
                      <Form.Item name="repeat_amount_min_count" label={renderParamLabel("repeat_amount_min_count")}>
                        <InputNumber style={{ width: "100%" }} min={2} max={20} />
                      </Form.Item>
                    )}
                    {paramFields.includes("min_win_count") && (
                      <Form.Item name="min_win_count" label={renderParamLabel("min_win_count")}>
                        <InputNumber style={{ width: "100%" }} min={2} max={50} />
                      </Form.Item>
                    )}
                    {paramFields.includes("weight") && (
                      <Form.Item name="weight" label={renderParamLabel("weight")}>
                        <InputNumber style={{ width: "100%" }} min={0.1} max={5} step={0.1} />
                      </Form.Item>
                    )}
                    {paramFields
                      .filter(
                        (field) =>
                          ![
                            "large_amount_threshold",
                            "top_n",
                            "repeat_amount_min_count",
                            "min_win_count",
                            "weight",
                            "special_amount_whitelist",
                          ].includes(field),
                      )
                      .map((field) => (
                        <Form.Item key={field} name={field} label={renderParamLabel(field)}>
                          <InputNumber
                            style={{ width: "100%" }}
                            min={RATE_PARAM_KEYS.has(field) ? 0 : 1}
                            max={RATE_PARAM_KEYS.has(field) ? 1 : 100}
                            step={RATE_PARAM_KEYS.has(field) ? 0.05 : 1}
                          />
                        </Form.Item>
                      ))}
                    {paramFields.includes("special_amount_whitelist") && (
                      <Form.Item
                        name="special_amount_whitelist"
                        label={renderParamLabel("special_amount_whitelist")}
                        tooltip="逗号分隔，如 520,1314,666"
                      >
                        <Input
                          onChange={(e) => {
                            const nums = e.target.value
                              .split(/[,，\s]+/)
                              .map((s) => parseFloat(s.trim()))
                              .filter((n) => !Number.isNaN(n));
                            paramForm.setFieldValue("special_amount_whitelist", nums);
                            onParamChange();
                          }}
                          value={(paramForm.getFieldValue("special_amount_whitelist") as number[] | undefined)?.join(", ") ?? ""}
                        />
                      </Form.Item>
                    )}
                  </Form>
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Card>
    </div>
  );
}

export default FusionModelManagePanel;
