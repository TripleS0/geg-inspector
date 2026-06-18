import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Collapse,
  Drawer,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  EntityMatchRow,
  RiskEvent,
  RiskRuleItem,
  RiskSummary,
  pollTask,
} from "../api";
import { chartPalette, riskLevelChartColors } from "../theme";

const { Title, Paragraph } = Typography;

const RISK_LEVEL_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const EVIDENCE_FIELD_LABELS: Record<string, string> = {
  rule_code: "规则编号",
  rule_name: "规则名称",
  enterprise_name: "企业名称",
  inquiry_no: "询价单号",
  quote_amount: "报价金额",
  winner: "中标情况",
  bidder_count: "参与企业数",
  relation: "关联关系",
  reason: "判断依据",
  description: "说明",
  legal_person: "法定代表人",
  peer_enterprise: "关联企业",
  shared_inquiries: "共同询价数",
  jaccard: "Jaccard",
};

function riskLevelLabel(level: string) {
  return RISK_LEVEL_LABELS[level] || level || "未分级";
}

function stringifyEvidenceValue(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function parseEvidence(value: string): Array<[string, string]> {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return Object.entries(parsed as Record<string, unknown>).map(([key, item]) => [
        EVIDENCE_FIELD_LABELS[key] || key,
        stringifyEvidenceValue(item),
      ]);
    }
    return [["证据内容", stringifyEvidenceValue(parsed)]];
  } catch (err) {
    return [["证据内容", value]];
  }
}

function EvidenceBlock({ value, compact = false }: { value: string; compact?: boolean }) {
  const entries = parseEvidence(value);
  if (entries.length === 0) {
    return <span className="analysis-empty">暂无证据</span>;
  }

  return (
    <div className={compact ? "evidence-list evidence-list-compact" : "evidence-list"}>
      {entries.map(([label, content], index) => (
        <div className="evidence-item" key={`${label}-${index}`}>
          <span className="evidence-label">{label}</span>
          <span className="evidence-value">{content}</span>
        </div>
      ))}
    </div>
  );
}

function RuleEditorPanel({ rule, onAfterSave }: { rule: RiskRuleItem; onAfterSave: () => void }) {
  const [weight, setWeight] = useState(rule.weight);
  const [enabled, setEnabled] = useState(rule.enabled === 1);
  const [params, setParams] = useState<Record<string, unknown>>(() => ({ ...rule.params }));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setWeight(rule.weight);
    setEnabled(rule.enabled === 1);
    setParams({ ...rule.params });
  }, [rule.rule_code, rule.version]);

  const setParam = (k: string, v: unknown) => setParams((p) => ({ ...p, [k]: v }));

  const onSave = async () => {
    setSaving(true);
    try {
      const nextParams: Record<string, unknown> = { ...params };
      for (const [k, v] of Object.entries(nextParams)) {
        if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) {
          nextParams[k] = Number(v);
        }
      }
      await api.patchRiskRule(rule.rule_code, {
        weight,
        enabled: enabled ? 1 : 0,
        params: nextParams,
      });
      message.success(`${rule.rule_code} 已保存`);
      onAfterSave();
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const paramEntries = Object.entries(params);

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Space wrap>
        <span>权重</span>
        <InputNumber step={0.1} value={weight} onChange={(v) => setWeight(Number(v) ?? 0)} />
        <span>启用</span>
        <Switch checked={enabled} onChange={setEnabled} />
        <Button type="primary" size="small" loading={saving} onClick={() => void onSave()}>
          保存本规则
        </Button>
      </Space>
      {paramEntries.length === 0 ? (
        <span className="analysis-empty">无数值参数（说明类规则）</span>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 200px) 1fr", gap: 8 }}>
          {paramEntries.map(([k, v]) => (
            <Fragment key={k}>
              <span style={{ alignSelf: "center", wordBreak: "break-all" }}>{k}</span>
              {typeof v === "number" ? (
                <InputNumber
                  style={{ width: "100%" }}
                  value={v as number}
                  onChange={(n) => setParam(k, n ?? 0)}
                />
              ) : (
                <Input value={String(v ?? "")} onChange={(e) => setParam(k, e.target.value)} />
              )}
            </Fragment>
          ))}
        </div>
      )}
    </Space>
  );
}

function CommercialRiskPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [commercialBatches, setCommercialBatches] = useState<BatchInfo[]>([]);
  const [enterpriseBatches, setEnterpriseBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState(() => searchParams.get("batch") || "");
  const [enterpriseBatch, setEnterpriseBatch] = useState<string | undefined>(() => {
    const eb = searchParams.get("enterpriseBatch")?.trim();
    return eb || undefined;
  });
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [summary, setSummary] = useState<RiskSummary[]>([]);
  const [matches, setMatches] = useState<EntityMatchRow[]>([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ruleFilter, setRuleFilter] = useState<string[]>([]);
  const [rulesDrawerOpen, setRulesDrawerOpen] = useState(false);
  const [riskRules, setRiskRules] = useState<RiskRuleItem[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const [comm, ent] = await Promise.all([
          api.listBatches("commercial"),
          api.listBatches("enterprise"),
        ]);
        setCommercialBatches(comm.items);
        setEnterpriseBatches(ent.items);
        setBatchId((prev) => prev || comm.items[0]?.import_batch_id || "");
      } catch (err) {
        message.error((err as Error).message);
      }
    })();
  }, []);

  const refreshTables = useCallback(async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const [ev, sm, em] = await Promise.all([
        api.riskEvents(batchId),
        api.riskSummary(batchId),
        api.entityMatches(batchId, enterpriseBatch, 2000),
      ]);
      setEvents(ev.items);
      setSummary(sm.items);
      setMatches(em.items);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [batchId, enterpriseBatch]);

  useEffect(() => {
    if (!batchId) return;
    const p = new URLSearchParams();
    p.set("batch", batchId);
    if (enterpriseBatch) p.set("enterpriseBatch", enterpriseBatch);
    else p.delete("enterpriseBatch");
    setSearchParams(p);
    void refreshTables();
  }, [batchId, enterpriseBatch, refreshTables, setSearchParams]);

  const reloadRiskRules = useCallback(async () => {
    setRulesLoading(true);
    try {
      const { items } = await api.listRiskRules();
      setRiskRules(items);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setRulesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (rulesDrawerOpen) void reloadRiskRules();
  }, [rulesDrawerOpen, reloadRiskRules]);

  const runRisk = async () => {
    if (!batchId) return;
    setRunning(true);
    try {
      const { task_id } = await api.runRisk(batchId, enterpriseBatch);
      const status = await pollTask(task_id);
      const result = status.result as { event_count?: number; summary_count?: number };
      message.success(`风险分析完成：事件 ${result.event_count ?? 0} 条，企业 ${result.summary_count ?? 0} 条`);
      await refreshTables();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const exportReport = async () => {
    if (!batchId) return;
    try {
      message.loading({ content: "正在导出风险报告…", key: "risk-export" });
      const { task_id } = await api.exportRiskReport(batchId);
      const status = await pollTask(task_id);
      message.success({
        content: `导出完成：${(status.result as { output_path?: string }).output_path}`,
        key: "risk-export",
        duration: 5,
      });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "risk-export" });
    }
  };

  const ruleStat = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of events) {
      counts.set(e.rule_code, (counts.get(e.rule_code) || 0) + 1);
    }
    const data = Array.from(counts.entries()).map(([k, v]) => ({ name: k, value: v }));
    return {
      color: [...chartPalette],
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{ type: "pie", radius: ["50%", "75%"], data }],
    };
  }, [events]);

  const levelStat = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of summary) {
      counts.set(s.risk_level, (counts.get(s.risk_level) || 0) + 1);
    }
    const keys = Array.from(counts.keys());
    const values = keys.map((k) => counts.get(k) || 0);
    return {
      tooltip: {},
      grid: { top: 16, left: 16, right: 24, bottom: 28, containLabel: true },
      xAxis: { type: "category", data: keys.map(riskLevelLabel) },
      yAxis: { type: "value" },
      series: [
        {
          type: "bar",
          barMaxWidth: 52,
          data: keys.map((k, i) => ({
            value: values[i],
            itemStyle: {
              color: riskLevelChartColors[k] || chartPalette[i % chartPalette.length],
              borderRadius: [6, 6, 0, 0],
            },
          })),
        },
      ],
    };
  }, [summary]);

  const filteredEvents = useMemo(() => {
    if (!ruleFilter.length) return events;
    const set = new Set(ruleFilter);
    return events.filter((e) => set.has(e.rule_code));
  }, [events, ruleFilter]);

  const ruleFilterOptions = useMemo(() => {
    const codes = new Set<string>();
    for (const e of events) codes.add(e.rule_code);
    for (const r of riskRules) codes.add(r.rule_code);
    return Array.from(codes)
      .sort()
      .map((c) => {
        const name = riskRules.find((r) => r.rule_code === c)?.rule_name;
        return { value: c, label: name ? `${c} ${name}` : c };
      });
  }, [events, riskRules]);

  const eventColumns = useMemo(
    () => [
      { title: "规则编号", dataIndex: "rule_code", width: 90 },
      { title: "名称", dataIndex: "rule_name", width: 140 },
      {
        title: "等级",
        dataIndex: "risk_level",
        width: 80,
        render: (v: string) => (
          <Tag color={v === "high" ? "red" : v === "medium" ? "orange" : "gold"}>{riskLevelLabel(v)}</Tag>
        ),
      },
      { title: "分数", dataIndex: "risk_score", width: 80 },
      { title: "企业", dataIndex: "enterprise_name", ellipsis: true },
      { title: "询价单号", dataIndex: "inquiry_no", width: 160 },
      {
        title: "证据",
        dataIndex: "evidence_json",
        width: 360,
        render: (v: string) => <EvidenceBlock value={v} compact />,
      },
    ],
    []
  );

  const summaryColumns = useMemo(
    () => [
      { title: "企业", dataIndex: "enterprise_name", ellipsis: true },
      { title: "总分", dataIndex: "total_score", width: 90 },
      { title: "命中次数", dataIndex: "hit_count", width: 90 },
      {
        title: "等级",
        dataIndex: "risk_level",
        width: 80,
        render: (v: string) => (
          <Tag color={v === "high" ? "red" : v === "medium" ? "orange" : "gold"}>{riskLevelLabel(v)}</Tag>
        ),
      },
    ],
    []
  );

  const matchColumns = useMemo(
    () => [
      { title: "询价单号", dataIndex: "inquiry_no", width: 140, ellipsis: true },
      { title: "商务名称", dataIndex: "biz_company_name", ellipsis: true },
      { title: "工商名称", dataIndex: "enterprise_name", ellipsis: true },
      { title: "统一社会信用代码", dataIndex: "credit_code", width: 160, ellipsis: true },
      { title: "法定代表人", dataIndex: "legal_person", width: 100, ellipsis: true },
      { title: "得分", dataIndex: "match_score", width: 72 },
      { title: "方式", dataIndex: "match_method", width: 88 },
    ],
    []
  );

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          商务网风险分析
        </Title>
        <Space wrap>
          <span>商务网批次：</span>
          <Select
            style={{ minWidth: 280 }}
            value={batchId || undefined}
            onChange={(val) => setBatchId(val)}
            options={commercialBatches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} · ${b.imported_at})`,
            }))}
          />
          <span>工商批次（可空）：</span>
          <Select
            allowClear
            style={{ minWidth: 220 }}
            value={enterpriseBatch}
            onChange={(val) => setEnterpriseBatch(val || undefined)}
            options={enterpriseBatches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} 条)`,
            }))}
          />
          <Button type="primary" loading={running} onClick={() => void runRisk()}>
            运行 7 项风险规则
          </Button>
          <Button onClick={() => void exportReport()}>导出风险报告</Button>
          <Button onClick={() => setRulesDrawerOpen(true)}>规则参数</Button>
        </Space>
      </div>
      <Paragraph style={{ color: "#5b6477" }}>
        基于已导入的商务网批次与工商企业库，自动分析围标、串标（含法定代表协同 R007）、陪标、关联异常、报价异常、轮流中标等 7
        类规则。导入企查查预览后可在「工商信息录入」页写入工商批次，此处选择同一批次以便关联匹配与 R007。
      </Paragraph>
      <Row gutter={16}>
        <Col span={10}>
          <div className="app-card">
            <Title level={5}>规则命中分布</Title>
            <ReactECharts option={ruleStat} style={{ height: 240 }} />
          </div>
        </Col>
        <Col span={14}>
          <div className="app-card">
            <Title level={5}>企业风险等级分布</Title>
            <ReactECharts option={levelStat} style={{ height: 240 }} />
          </div>
        </Col>
      </Row>

      <Tabs
        style={{ marginTop: 16 }}
        items={[
          {
            key: "matches",
            label: `关联匹配${matches.length ? ` (${matches.length})` : ""}`,
            children: (
              <div className="app-card">
                <Table<EntityMatchRow>
                  rowKey="match_id"
                  size="small"
                  loading={loading}
                  columns={matchColumns}
                  dataSource={matches}
                  scroll={{ x: "max-content" }}
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                  locale={{
                    emptyText: enterpriseBatch
                      ? "暂无匹配记录，请先对当前商务批次运行风险分析"
                      : "请选择工商批次以筛选与 std_enterprise_profile 的对应关系，或不选查看全部匹配",
                  }}
                />
              </div>
            ),
          },
          {
            key: "events",
            label: "风险事件与汇总",
            children: (
              <Row gutter={16}>
                <Col span={14}>
                  <div className="app-card">
                    <div style={{ marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                      <Title level={5} style={{ margin: 0, flex: 1 }}>
                        风险事件（最近 500 条）
                      </Title>
                      <Select
                        mode="multiple"
                        allowClear
                        placeholder="按规则编号筛选"
                        style={{ minWidth: 280 }}
                        value={ruleFilter}
                        onChange={(v) => setRuleFilter(v)}
                        options={ruleFilterOptions}
                      />
                    </div>
                    <Table
                      rowKey="event_id"
                      size="small"
                      loading={loading}
                      columns={eventColumns}
                      dataSource={filteredEvents}
                      scroll={{ x: "max-content" }}
                      pagination={{ pageSize: 20 }}
                      expandable={{
                        expandedRowRender: (record) => (
                          <div className="evidence-expanded">
                            <div className="evidence-expanded-title">证据详情</div>
                            <EvidenceBlock value={record.evidence_json} />
                          </div>
                        ),
                      }}
                    />
                  </div>
                </Col>
                <Col span={10}>
                  <div className="app-card">
                    <Title level={5}>企业风险汇总</Title>
                    <Table
                      rowKey="summary_id"
                      size="small"
                      loading={loading}
                      columns={summaryColumns}
                      dataSource={summary}
                      pagination={{ pageSize: 20 }}
                    />
                  </div>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      <Drawer
        title="风险规则参数（保存将整体替换 params）"
        width={520}
        open={rulesDrawerOpen}
        onClose={() => setRulesDrawerOpen(false)}
        destroyOnClose
      >
        {rulesLoading ? (
          <Paragraph type="secondary">加载中…</Paragraph>
        ) : (
          <Collapse
            items={riskRules.map((rule) => ({
              key: rule.rule_code,
              label: `${rule.rule_code} ${rule.rule_name}`,
              children: <RuleEditorPanel rule={rule} onAfterSave={() => void reloadRiskRules()} />,
            }))}
          />
        )}
      </Drawer>
    </Card>
  );
}

export default CommercialRiskPage;
