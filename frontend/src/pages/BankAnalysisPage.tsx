import { useEffect, useMemo, useState } from "react";
import { Button, Card, Col, Form, Input, InputNumber, Modal, Row, Select, Space, Table, Tabs, Tag, Typography, message } from "antd";
import { DownloadOutlined, DownOutlined, UpOutlined, WarningOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useSearchParams } from "react-router-dom";
import { api, BankFilter, BankRecordsResponse, BatchInfo, batchLabel, ModuleParams } from "../api";
import { chartPair, chartPalette } from "../theme";
import { AnalysisDateTimeFilterFields, AnalysisDateTimeFormFields, serializeAnalysisDateTimeFilters } from "../components/AnalysisDateTimeFilters";

type BankFilterForm = BankFilter & AnalysisDateTimeFormFields;

const { Title, Paragraph } = Typography;

type BankRecord = Record<string, string>;

function toAmount(row: BankRecord) {
  return Math.abs(Number(String(row.amount || "0").replace(/,/g, "")) || 0);
}

function signedAmount(row: BankRecord) {
  const amount = toAmount(row);
  return isExpenseDirection(row) ? -amount : amount;
}

function txnHour(row: BankRecord) {
  const match = String(row.txn_time || "").match(/(?:\s|T)(\d{1,2}):/);
  return match ? Number(match[1]) : Number.NaN;
}

function moneyText(value: number) {
  if (value >= 100000000) return `${(value / 100000000).toFixed(2)}亿`;
  if (value >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return value.toFixed(2);
}

function isIncomeDirection(row: BankRecord) {
  const text = String(row.txn_direction || "");
  return text.includes("收入") || text.includes("转入") || text.includes("收款") || text.includes("入") || text.includes("贷");
}

function isExpenseDirection(row: BankRecord) {
  const text = String(row.txn_direction || "");
  return text.includes("支出") || text.includes("转出") || text.includes("付款") || text.includes("出") || text.includes("借");
}

function participantNames(row: BankRecord) {
  return [row.person_name, row.counterparty_name]
    .map((value) => String(value || "").trim())
    .filter((value) => value && value !== "-" && value !== "--" && value !== "未知");
}

function specialTimeCategories(row: BankRecord) {
  const text = String(row.remark || row.txn_desc || "");
  const categories: string[] = [];
  if (text.includes("法定节假日") || text.includes("节假日") || text.includes("特殊日期")) {
    categories.push("法定节假日");
  }
  if (text.includes("凌晨") || text.includes("深夜") || text.includes("特殊时间") || text.includes("特殊时段")) {
    categories.push("特殊时段");
  }
  return categories;
}

const MODULES: Array<{ id: string; name: string; desc: string }> = [
  { id: "large_inout", name: "大额进出", desc: "按阈值挑出大额收支记录" },
  { id: "large_flow", name: "大额资金流向", desc: "按交易对手统计大额流向排名" },
  { id: "special_amount", name: "特殊金额", desc: "敏感金额、整数金额、重复金额" },
  { id: "special_time", name: "特殊时间", desc: "深夜、凌晨、节假日交易" },
];

function BankAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchId, setBatchId] = useState<string>("");
  const [filter] = Form.useForm<BankFilterForm>();
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<BankRecordsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [moduleParams] = Form.useForm<ModuleParams>();
  const [moduleResult, setModuleResult] = useState<Record<string, unknown> | null>(null);
  const [moduleLoading, setModuleLoading] = useState(false);
  const [activeModule, setActiveModule] = useState<string>(MODULES[0].id);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState("");
  const [detailRows, setDetailRows] = useState<BankRecord[]>([]);
  const [moduleSortMode, setModuleSortMode] = useState<"default" | "abs_desc">("default");

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.listBatches("bank");
        setBatches(data.items);
        const param = searchParams.get("batch") || "";
        const next = param || data.items[0]?.import_batch_id || "";
        setBatchId(next);
      } catch (err) {
        message.error((err as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!batchId) return;
    setSearchParams({ batch: batchId });
    setModuleResult(null);
    void api.bankFilterOptions(batchId).then(setFilterOptions).catch(() => setFilterOptions({}));
    void runQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runQuery = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const values = await filter.validateFields();
      const data = await api.bankRecords(batchId, serializeAnalysisDateTimeFilters(values));
      setRecords(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const runModule = async (moduleId: string) => {
    if (!batchId) return;
    setActiveModule(moduleId);
    setModuleResult(null);
    setModuleSortMode("default");
    setModuleLoading(true);
    try {
      const params = await moduleParams.validateFields().catch(() => ({}));
      const data = await api.bankModule(batchId, moduleId, params as ModuleParams);
      setModuleResult(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setModuleLoading(false);
    }
  };

  const displayedModuleResult = moduleResult?.module_id === activeModule ? moduleResult : null;

  const directionOption = useMemo(() => {
    if (!records) return null;
    const summary = records.summary as Record<string, number>;
    const inTotal = Number(summary.in_total || 0);
    const outTotal = Number(summary.out_total || 0);
    return {
      color: [chartPair.primary, chartPair.secondary],
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { name: "收入", value: inTotal },
            { name: "支出", value: outTotal },
          ],
        },
      ],
    };
  }, [records]);

  const topCounterpartyOption = useMemo(() => {
    if (!records) return null;
    const top = (records.summary?.top_counterparties as Array<[string, number]>) || [];
    if (top.length === 0) return null;
    return {
      color: chartPalette,
      tooltip: { trigger: "axis" },
      grid: { top: 12, left: 12, right: 36, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          hideOverlap: true,
          formatter: (v: number) => {
            if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
            if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: { type: "category", data: top.map(([name]) => name).reverse(), axisLabel: { width: 100, overflow: "truncate" } },
      series: [
        {
          type: "bar",
          data: top.map(([, val]) => val).reverse(),
          itemStyle: {
            color: chartPair.primary,
            borderRadius: [0, 6, 6, 0],
          },
        },
      ],
    };
  }, [records]);

  const anomalyCards = useMemo(() => {
    const rows = (records?.records || []) as BankRecord[];
    if (!rows.length) return [];
    const amounts = rows.map(toAmount).filter((value) => value > 0);
    const average = amounts.length ? amounts.reduce((sum, value) => sum + value, 0) / amounts.length : 0;
    const largeThreshold = Math.max(100000, average * 3);
    const largeRows = rows.filter((row) => toAmount(row) >= largeThreshold);
    const nightRows = rows.filter((row) => {
      const hour = txnHour(row);
      return Number.isFinite(hour) && (hour < 6 || hour >= 22);
    });
    const byAmount = new Map<string, BankRecord[]>();
    rows.forEach((row) => {
      const amount = String(row.amount || "").trim();
      if (!amount) return;
      byAmount.set(amount, [...(byAmount.get(amount) || []), row]);
    });
    const repeatedRows = Array.from(byAmount.values()).filter((group) => group.length >= 3).flat();
    const byCounterparty = new Map<string, BankRecord[]>();
    rows.forEach((row) => {
      const name = String(row.counterparty_name || "").trim();
      if (!name) return;
      byCounterparty.set(name, [...(byCounterparty.get(name) || []), row]);
    });
    const topCounterparty = Array.from(byCounterparty.entries()).sort((a, b) => b[1].length - a[1].length)[0];
    const topCounterpartyRows = topCounterparty?.[1] || [];
    return [
      {
        key: "large",
        title: "大额交易",
        value: largeRows.length,
        desc: `阈值 ${moneyText(largeThreshold)}`,
        rows: largeRows,
      },
      {
        key: "night",
        title: "夜间交易",
        value: nightRows.length,
        desc: "22:00 - 06:00",
        rows: nightRows,
      },
      {
        key: "repeat",
        title: "重复金额",
        value: repeatedRows.length,
        desc: "同金额出现 3 次以上",
        rows: repeatedRows,
      },
      {
        key: "counterparty",
        title: "高频对手",
        value: topCounterpartyRows.length,
        desc: topCounterparty?.[0] || "暂无",
        rows: topCounterpartyRows,
      },
    ];
  }, [records]);

  const anomalyOption = useMemo(() => {
    if (!anomalyCards.length) return null;
    return {
      color: ["#e85d45"],
      tooltip: { trigger: "axis" },
      grid: { top: 22, left: 36, right: 18, bottom: 28, containLabel: true },
      xAxis: { type: "category", data: anomalyCards.map((item) => item.title) },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { type: "dashed", color: "#eee" } } },
      series: [
        {
          type: "bar",
          barMaxWidth: 34,
          data: anomalyCards.map((item) => item.value),
          itemStyle: { borderRadius: [6, 6, 0, 0] },
        },
      ],
    };
  }, [anomalyCards]);

  const moduleHits = (displayedModuleResult?.hit_records as Array<Record<string, string>>) || [];
  const sortedModuleHits = useMemo(() => {
    if (moduleSortMode !== "abs_desc") return moduleHits;
    return [...moduleHits].sort((a, b) => toAmount(b as BankRecord) - toAmount(a as BankRecord));
  }, [moduleHits, moduleSortMode]);

  const moduleSummary = useMemo(() => {
    const rows = moduleHits as BankRecord[];
    const extra = (displayedModuleResult?.extra as Record<string, unknown>) || {};
    const summary = (displayedModuleResult?.summary as Record<string, unknown>) || {};
    const hitCount = Number(summary.txn_count || rows.length || 0);
    const incomeRows = rows.filter(isIncomeDirection);
    const expenseRows = rows.filter(isExpenseDirection);
    const incomeTotal = Number(extra.large_in_total ?? incomeRows.reduce((sum, row) => sum + toAmount(row), 0));
    const expenseTotal = Number(extra.large_out_total ?? expenseRows.reduce((sum, row) => sum + toAmount(row), 0));
    const threshold = Number(extra.threshold || moduleParams.getFieldValue("large_amount_threshold") || 0);
    const amountValues = rows.map(toAmount).filter((value) => value > 0);
    const maxAmount = amountValues.length ? Math.max(...amountValues) : 0;
    return {
      hitCount,
      incomeCount: Number(extra.large_in_count ?? incomeRows.length),
      expenseCount: Number(extra.large_out_count ?? expenseRows.length),
      incomeTotal,
      expenseTotal,
      threshold,
      maxAmount,
      netTotal: incomeTotal - expenseTotal,
    };
  }, [displayedModuleResult, moduleHits, moduleParams]);

  const moduleFrequentPeopleOption = useMemo(() => {
    if (!displayedModuleResult || moduleHits.length === 0) return null;
    const counts = new Map<string, number>();
    (moduleHits as BankRecord[]).forEach((row) => {
      participantNames(row).forEach((name) => {
        counts.set(name, (counts.get(name) || 0) + 1);
      });
    });
    const top = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 3);
    if (!top.length) return null;
    return {
      color: [chartPair.primary],
      tooltip: { trigger: "axis" },
      grid: { top: 16, left: 24, right: 24, bottom: 28, containLabel: true },
      xAxis: { type: "value", minInterval: 1 },
      yAxis: { type: "category", data: top.map(([name]) => name).reverse(), axisLabel: { width: 120, overflow: "truncate" } },
      series: [
        {
          type: "bar",
          barMaxWidth: 34,
          data: top.map(([, count]) => count).reverse(),
          itemStyle: { color: chartPair.primary, borderRadius: [0, 6, 6, 0] },
        },
      ],
    };
  }, [displayedModuleResult, moduleHits]);

  const moduleFlowOption = useMemo(() => {
    if (activeModule !== "large_flow" || !displayedModuleResult || moduleHits.length === 0) return null;
    const top = [...(moduleHits as BankRecord[])]
      .sort((a, b) => toAmount(b) - toAmount(a))
      .slice(0, 3);
    const labels = top.map((row) => {
      const person = String(row.person_name || "").trim();
      const counterparty = String(row.counterparty_name || "").trim();
      return counterparty ? `${person || "未知"} / ${counterparty}` : person || "未知";
    });
    return {
      color: [chartPair.primary],
      tooltip: { trigger: "axis" },
      grid: { top: 16, left: 24, right: 24, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => {
            const sign = v < 0 ? "-" : "";
            const abs = Math.abs(v);
            if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}亿`;
            if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: { type: "category", data: labels.reverse(), axisLabel: { width: 150, overflow: "truncate" } },
      series: [
        {
          type: "bar",
          barMaxWidth: 34,
          data: top.map((row) => signedAmount(row)).reverse(),
          itemStyle: { color: chartPair.primary, borderRadius: [0, 6, 6, 0] },
        },
      ],
    };
  }, [activeModule, displayedModuleResult, moduleHits]);

  const moduleSpecialTimePieOption = useMemo(() => {
    if (activeModule !== "special_time" || !displayedModuleResult || moduleHits.length === 0) return null;
    const counts = new Map<string, number>();
    (moduleHits as BankRecord[]).forEach((row) => {
      specialTimeCategories(row).forEach((category) => {
        counts.set(category, (counts.get(category) || 0) + 1);
      });
    });
    const data = ["法定节假日", "特殊时段"]
      .map((name) => ({ name, value: counts.get(name) || 0 }))
      .filter((item) => item.value > 0);
    if (!data.length) return null;
    return {
      color: [chartPair.primary, chartPair.secondary],
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data,
        },
      ],
    };
  }, [activeModule, displayedModuleResult, moduleHits]);

  const moduleSpecialTimeTopAmountOption = useMemo(() => {
    if (activeModule !== "special_time" || !displayedModuleResult || moduleHits.length === 0) return null;
    const top = [...(moduleHits as BankRecord[])]
      .sort((a, b) => toAmount(b) - toAmount(a))
      .slice(0, 3);
    if (!top.length) return null;
    const labels = top.map((row) => {
      const person = String(row.person_name || "").trim();
      const counterparty = String(row.counterparty_name || "").trim();
      return counterparty ? `${person || "未知"} / ${counterparty}` : person || "未知";
    });
    return {
      color: [chartPair.primary],
      tooltip: { trigger: "axis" },
      grid: { top: 16, left: 24, right: 24, bottom: 28, containLabel: true },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => {
            const sign = v < 0 ? "-" : "";
            const abs = Math.abs(v);
            if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}亿`;
            if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(0)}万`;
            return String(v);
          },
        },
      },
      yAxis: { type: "category", data: labels.reverse(), axisLabel: { width: 150, overflow: "truncate" } },
      series: [
        {
          type: "bar",
          barMaxWidth: 34,
          data: top.map((row) => signedAmount(row)).reverse(),
          itemStyle: { color: chartPair.primary, borderRadius: [0, 6, 6, 0] },
        },
      ],
    };
  }, [activeModule, displayedModuleResult, moduleHits]);

  const moduleCharts = useMemo(() => {
    if (activeModule === "large_inout") return [];
    if (activeModule === "large_flow") {
      return [{ title: "大额资金流向 Top3", option: moduleFlowOption }];
    }
    if (activeModule === "special_time") {
      return [
        { title: "特殊时间类型占比", option: moduleSpecialTimePieOption },
        { title: "特殊时间大额 Top3", option: moduleSpecialTimeTopAmountOption },
      ];
    }
    if (activeModule === "special_amount") {
      return [{ title: "高频出现人物 Top3", option: moduleFrequentPeopleOption }];
    }
    return [];
  }, [activeModule, moduleFlowOption, moduleFrequentPeopleOption, moduleSpecialTimePieOption, moduleSpecialTimeTopAmountOption]);

  const activeModuleName = MODULES.find((m) => m.id === activeModule)?.name || "固定分析";

  const recordColumns = useMemo(() => {
    const keys = [
      ["txn_time", "时间"],
      ["bank_type", "银行"],
      ["person_name", "姓名"],
      ["acct_no", "账号/卡号"],
      ["txn_direction", "方向"],
      ["amount", "金额"],
      ["balance", "余额"],
      ["counterparty_name", "对手"],
      ["counterparty_account", "对手账号"],
      ["txn_desc", "摘要"],
      ["remark", "备注"],
    ];
    return keys.map(([dataIndex, title]) => ({
      title,
      dataIndex,
      key: dataIndex,
      ellipsis: true,
    }));
  }, []);

  const openDetail = (title: string, rows: BankRecord[]) => {
    setDetailTitle(title);
    setDetailRows(rows);
  };

  const onTabChange = (key: string) => {
    if (key === "module" && !moduleResult && !moduleLoading) {
      void runModule("large_inout");
    }
  };

  const exportMatchedRecords = async () => {
    if (!batchId) return;
    if (!records?.records.length) {
      message.warning("当前没有可导出的命中记录");
      return;
    }
    try {
      const values = await filter.validateFields();
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const fileBase = `${batchLabel(currentBatch || { import_batch_id: batchId })}_命中记录`;
      const blob = await api.exportBankRecords(
        batchId,
        serializeAnalysisDateTimeFilters(values),
        fileBase
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${fileBase}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success("命中记录已导出");
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

  const exportModuleHits = async () => {
    if (!sortedModuleHits.length) {
      message.warning("当前没有可导出的命中明细");
      return;
    }
    try {
      const currentBatch = batches.find((item) => item.import_batch_id === batchId);
      const moduleName = MODULES.find((m) => m.id === activeModule)?.name || "固定分析";
      const fileBase = `${batchLabel(currentBatch || { import_batch_id: batchId })}_${moduleName}_命中明细`;
      const blob = await api.exportRowsToExcel(
        sortedModuleHits as unknown as Record<string, unknown>[],
        [
          { key: "txn_time", title: "时间" },
          { key: "bank_type", title: "银行" },
          { key: "person_name", title: "姓名" },
          { key: "acct_no", title: "账号/卡号" },
          { key: "txn_direction", title: "方向" },
          { key: "amount", title: "金额" },
          { key: "balance", title: "余额" },
          { key: "counterparty_name", title: "对手" },
          { key: "counterparty_account", title: "对手账号" },
          { key: "txn_desc", title: "摘要" },
          { key: "remark", title: "备注" },
        ],
        fileBase,
        "命中明细"
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${fileBase}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success("命中明细已导出");
    } catch (err) {
      message.error((err as Error).message || "导出失败");
    }
  };

  return (
    <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>银行流水分析</Title>
        <Space>
          <span>批次：</span>
          <Select
            style={{ minWidth: 320 }}
            value={batchId}
            onChange={(val) => setBatchId(val)}
            options={batches.map((b) => ({
              value: b.import_batch_id,
              label: `${batchLabel(b)} (${b.file_count} 文件 · ${b.imported_at})`,
            }))}
          />
        </Space>
      </div>
      <Tabs
        defaultActiveKey="custom"
        onChange={onTabChange}
        items={[
          {
            key: "custom",
            label: "自定义筛选",
            children: (
              <div>
                <Form layout="vertical" form={filter}>
                  <Form.Item
                    name="quick_query"
                    label="快速筛选"
                    tooltip="多个关键词用空格隔开，每个关键词会在银行、姓名、卡号、对手、摘要、备注中匹配"
                  >
                    <Input.Search
                      allowClear
                      size="large"
                      placeholder="例如：李芳 建设银行 李军"
                      enterButton="快速筛选"
                      loading={loading}
                      onSearch={() => void runQuery()}
                    />
                  </Form.Item>
                  <Space>
                    <Button type="primary" loading={loading} onClick={runQuery}>查询并生成描述</Button>
                    <Button icon={advancedOpen ? <UpOutlined /> : <DownOutlined />} onClick={() => setAdvancedOpen((open) => !open)}>
                      更多筛选
                    </Button>
                    <Button onClick={() => filter.resetFields()}>重置</Button>
                  </Space>
                  {advancedOpen ? (
                    <div className="bank-advanced-filter">
                      <Row gutter={12}>
                        <Col span={6}>
                          <Form.Item name="bank_type" label="银行">
                            <Select allowClear options={(filterOptions.bank_type || []).map((v) => ({ value: v, label: v }))} />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name="person_name" label="姓名">
                            <Select allowClear showSearch options={(filterOptions.person_name || []).map((v) => ({ value: v, label: v }))} />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name="acct_no" label="卡号">
                            <Select allowClear showSearch options={(filterOptions.acct_no || []).map((v) => ({ value: v, label: v }))} />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name="counterparty_name" label="对手姓名">
                            <Select allowClear showSearch options={(filterOptions.counterparty_name || []).map((v) => ({ value: v, label: v }))} />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name="amount_min" label="金额下限">
                            <InputNumber style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                        <Col span={6}>
                          <Form.Item name="amount_max" label="金额上限">
                            <InputNumber style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                        <AnalysisDateTimeFilterFields dateCol={{ span: 6 }} timeCol={{ span: 6 }} />
                      </Row>
                    </div>
                  ) : null}
                </Form>
                {records && (
                  <>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={6}>
                        <div className="metric-card"><div className="metric-title">交易笔数</div><div className="metric-value">{Number(records.summary.txn_count || 0)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="metric-card"><div className="metric-title">收入总额</div><div className="metric-value metric-primary">{Number(records.summary.in_total || 0).toFixed(2)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="metric-card"><div className="metric-title">支出总额</div><div className="metric-value metric-secondary">{Number(records.summary.out_total || 0).toFixed(2)}</div></div>
                      </Col>
                      <Col span={6}>
                        <div className="metric-card"><div className="metric-title">净额</div><div className="metric-value">{Number(records.summary.net_amount || 0).toFixed(2)}</div></div>
                      </Col>
                    </Row>
                    <div className="app-card bank-anomaly-panel">
                      <div className="bank-section-head">
                        <Title level={5} style={{ margin: 0 }}>
                          <WarningOutlined /> 异常重点
                        </Title>
                        <Tag color="volcano">点击卡片查看明细</Tag>
                      </div>
                      <Row gutter={[12, 12]}>
                        {anomalyCards.map((item) => (
                          <Col xs={24} md={12} xl={6} key={item.key}>
                            <button
                              type="button"
                              className={`bank-anomaly-card${item.value ? " is-hot" : ""}`}
                              onClick={() => openDetail(item.title, item.rows)}
                            >
                              <span>{item.title}</span>
                              <strong>{item.value}</strong>
                              <em>{item.desc}</em>
                            </button>
                          </Col>
                        ))}
                      </Row>
                      {anomalyOption ? (
                        <ReactECharts option={anomalyOption} style={{ height: 220, marginTop: 12 }} />
                      ) : null}
                    </div>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={10}>
                        <Card size="small" title="收支分布">
                          {directionOption && <ReactECharts option={directionOption} style={{ height: 240 }} />}
                        </Card>
                      </Col>
                      <Col span={14}>
                        <Card size="small" title="交易对手排名（按总流量）">
                          {topCounterpartyOption ? (
                            <ReactECharts option={topCounterpartyOption} style={{ height: 240 }} />
                          ) : (
                            <Paragraph style={{ color: "#5b6477", margin: 0 }}>暂无数据</Paragraph>
                          )}
                        </Card>
                      </Col>
                    </Row>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <div className="bank-section-head">
                        <Title level={5} style={{ margin: 0 }}>命中记录（前 200 行）</Title>
                        <Button
                          icon={<DownloadOutlined />}
                          disabled={!records.records.length}
                          onClick={() => void exportMatchedRecords()}
                        >
                          导出Excel
                        </Button>
                      </div>
                      <Table
                        rowKey={(r) => `${r.txn_time}-${r.acct_no}-${r.amount}-${r.counterparty_account}`}
                        size="small"
                        scroll={{ x: "max-content" }}
                        columns={recordColumns}
                        dataSource={records.records.slice(0, 200)}
                        pagination={{ pageSize: 30 }}
                      />
                    </div>
                  </>
                )}
              </div>
            ),
          },
          {
            key: "module",
            label: "固定分析模块",
            children: (
              <div>
                <Form
                  layout="inline"
                  form={moduleParams}
                  initialValues={{ large_amount_threshold: 100000, top_n: 15, repeat_amount_min_count: 3 }}
                >
                  <Form.Item
                    name="large_amount_threshold"
                    label={activeModule === "large_inout" ? "单笔绝对值 ≥" : "大额阈值"}
                    tooltip="金额绝对值高于或等于该数值，就算大额"
                  >
                    <InputNumber min={0} step={10000} addonAfter="元" />
                  </Form.Item>
                  <Form.Item name="top_n" label="排名数量">
                    <InputNumber min={1} max={500} />
                  </Form.Item>
                  <Form.Item name="repeat_amount_min_count" label="重复金额下限">
                    <InputNumber min={2} max={50} />
                  </Form.Item>
                </Form>
                <Space style={{ marginTop: 12 }}>
                  {MODULES.map((m) => (
                    <Button
                      key={m.id}
                      type={activeModule === m.id ? "primary" : "default"}
                      loading={moduleLoading && activeModule === m.id}
                      onClick={() => runModule(m.id)}
                    >
                      {m.name}
                    </Button>
                  ))}
                </Space>
                {moduleLoading && !displayedModuleResult && (
                  <div className="app-card" style={{ marginTop: 16 }}>
                    <Paragraph className="analysis-empty">{activeModuleName} 正在分析...</Paragraph>
                  </div>
                )}
                {displayedModuleResult && (
                  <>
                    <div style={{ marginTop: 16 }}>
                      <div className="bank-section-head">
                        <Title level={5} style={{ margin: 0 }}>
                          {activeModuleName}
                          <Tag style={{ marginLeft: 8 }}>{moduleHits.length} 条命中</Tag>
                        </Title>
                      </div>
                      <Row gutter={16}>
                        <Col xs={24} md={6}>
                          <div className="metric-card"><div className="metric-title">命中笔数</div><div className="metric-value">{moduleSummary.hitCount}</div></div>
                        </Col>
                        <Col xs={24} md={6}>
                          <div className="metric-card"><div className="metric-title">收入合计</div><div className="metric-value metric-primary">{moneyText(moduleSummary.incomeTotal)}</div></div>
                        </Col>
                        <Col xs={24} md={6}>
                          <div className="metric-card"><div className="metric-title">支出合计</div><div className="metric-value metric-secondary">{moneyText(moduleSummary.expenseTotal)}</div></div>
                        </Col>
                        <Col xs={24} md={6}>
                          <div className="metric-card"><div className="metric-title">单笔最高</div><div className="metric-value">{moneyText(moduleSummary.maxAmount)}</div></div>
                        </Col>
                      </Row>
                      {moduleCharts.length > 0 && (
                        <Row gutter={16} style={{ marginTop: 16 }}>
                          {moduleCharts.map((chart) => (
                            <Col xs={24} md={moduleCharts.length > 1 ? 12 : 24} key={chart.title}>
                              <Card size="small" title={chart.title}>
                                {chart.option ? (
                                  <ReactECharts option={chart.option} style={{ height: 280 }} />
                                ) : (
                                  <Paragraph className="analysis-empty">暂无图表数据</Paragraph>
                                )}
                              </Card>
                            </Col>
                          ))}
                        </Row>
                      )}
                    </div>
                    <div className="app-card" style={{ marginTop: 16 }}>
                      <div className="bank-section-head">
                        <Title level={5} style={{ margin: 0 }}>命中明细（前 200 行）</Title>
                        <Space>
                          <Select
                            size="small"
                            value={moduleSortMode}
                            style={{ width: 180 }}
                            onChange={setModuleSortMode}
                            options={[
                              { value: "default", label: "默认顺序" },
                              { value: "abs_desc", label: "按绝对值从大到小" },
                            ]}
                          />
                          <Button
                            icon={<DownloadOutlined />}
                            disabled={!sortedModuleHits.length}
                            onClick={() => void exportModuleHits()}
                          >
                            导出Excel
                          </Button>
                        </Space>
                      </div>
                      <Table
                        size="small"
                        rowKey={(r, idx) => `${idx}`}
                        scroll={{ x: "max-content" }}
                        columns={recordColumns}
                        dataSource={sortedModuleHits.slice(0, 200)}
                        pagination={{ pageSize: 30 }}
                      />
                    </div>
                  </>
                )}
              </div>
            ),
          },
        ]}
      />
      <Modal
        title={`${detailTitle}明细（${detailRows.length} 条）`}
        open={detailRows.length > 0}
        width={980}
        footer={null}
        onCancel={() => {
          setDetailRows([]);
          setDetailTitle("");
        }}
      >
        <Table
          rowKey={(r, idx) => `${idx}-${r.txn_time}-${r.acct_no}-${r.amount}-${r.counterparty_account}`}
          size="small"
          scroll={{ x: "max-content", y: 460 }}
          columns={recordColumns}
          dataSource={detailRows}
          pagination={{ pageSize: 20 }}
        />
      </Modal>
    </Card>
  );
}

export default BankAnalysisPage;
