import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Card, Input, Modal, Popconfirm, Segmented, Select, Space, Table, Tag, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import { api, BatchInfo, batchLabel, CASE_CHANGED_EVENT, CASE_STORAGE_KEY, pollTask } from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";

const { Title, Paragraph } = Typography;

type Source = "all" | "bank" | "commercial" | "enterprise" | "wechat" | "telecom";

const SOURCE_LABELS: Record<Source, string> = {
  all: "全部",
  bank: "银行",
  commercial: "商务网",
  enterprise: "工商",
  wechat: "微信",
  telecom: "通讯",
};

const SOURCE_TAG_LABELS: Record<string, string> = {
  bank: "银行流水",
  commercial: "商务网",
  enterprise: "工商信息",
  wechat: "微信流水",
  telecom: "运营商话单",
};

function BatchesPage() {
  const [filter, setFilter] = useState<Source>("all");
  const [items, setItems] = useState<BatchInfo[]>([]);
  const [batchCaseMap, setBatchCaseMap] = useState<Record<string, { case_id: number; case_name: string }>>({});
  const [cases, setCases] = useState<Array<{ case_id: number; case_name: string; batch_count: number }>>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(() => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null);
  const [bindModalOpen, setBindModalOpen] = useState(false);
  const [bindBatchId, setBindBatchId] = useState<string>("");
  const [bindCaseId, setBindCaseId] = useState<number | null>(null);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameBatchId, setRenameBatchId] = useState<string>("");
  const [renameValue, setRenameValue] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const [mergeModalOpen, setMergeModalOpen] = useState(false);
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [mergeName, setMergeName] = useState("");
  const [mergeSaving, setMergeSaving] = useState(false);
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [data, mapData, caseData] = await Promise.all([
        api.listBatches(filter === "all" ? undefined : filter),
        api.batchCaseMap(),
        api.listCases(),
      ]);
      setItems(data.items);
      setBatchCaseMap(mapData.items);
      setCases(caseData.items.map((c) => ({ case_id: c.case_id, case_name: c.case_name, batch_count: c.batch_count })));
      const stored = Number(localStorage.getItem(CASE_STORAGE_KEY)) || null;
      setSelectedCaseId(stored && caseData.items.some((item) => item.case_id === stored) ? stored : caseData.items[0]?.case_id ?? null);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId;
      if (nextCaseId) setSelectedCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  const exportRow = async (row: BatchInfo) => {
    if (row.source_type !== "bank" && row.source_type !== "commercial" && row.source_type !== "wechat" && row.source_type !== "telecom") {
      message.info("当前类型暂不支持一键导出");
      return;
    }
    try {
      message.loading({ content: "正在生成电子表格…", key: "export-task" });
      const { task_id } = await api.exportBatch(row.source_type, row.import_batch_id);
      const status = await pollTask(task_id);
      message.success({ content: `导出完成：${(status.result as { output_path?: string }).output_path}`, key: "export-task", duration: 5 });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "export-task" });
    }
  };

  const deleteRow = async (row: BatchInfo) => {
    try {
      await api.deleteBatch(row.import_batch_id);
      setItems((prev) => prev.filter((item) => item.import_batch_id !== row.import_batch_id));
      message.success("已删除该批次及相关数据");
      void fetchData();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const openBindModal = (batchId: string) => {
    setBindBatchId(batchId);
    setBindCaseId(cases[0]?.case_id ?? null);
    setBindModalOpen(true);
  };

  const confirmBind = async () => {
    if (!bindCaseId || !bindBatchId) return;
    try {
      await api.bindCaseBatches(bindCaseId, [bindBatchId]);
      message.success("已加入案件");
      setSelectedCaseId(bindCaseId);
      localStorage.setItem(CASE_STORAGE_KEY, String(bindCaseId));
      window.dispatchEvent(new CustomEvent(CASE_CHANGED_EVENT, { detail: { caseId: bindCaseId } }));
      setBindModalOpen(false);
      void fetchData();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const openRenameModal = (row: BatchInfo) => {
    setRenameBatchId(row.import_batch_id);
    setRenameValue(row.batch_name?.trim() || batchLabel(row));
    setRenameModalOpen(true);
  };

  const confirmRename = async () => {
    const name = renameValue.trim();
    if (!name) {
      message.warning("请输入批次名称");
      return;
    }
    setRenameSaving(true);
    try {
      const updated = await api.renameBatch(renameBatchId, name);
      setItems((prev) =>
        prev.map((item) =>
          item.import_batch_id === updated.import_batch_id
            ? { ...item, batch_name: updated.batch_name }
            : item
        )
      );
      message.success("批次名称已更新");
      setRenameModalOpen(false);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setRenameSaving(false);
    }
  };

  const commercialSelected = useMemo(
    () =>
      items.filter(
        (row) => selectedBatchIds.includes(row.import_batch_id) && row.source_type === "commercial",
      ),
    [items, selectedBatchIds],
  );

  const openMergeModal = () => {
    if (commercialSelected.length < 2) {
      message.warning("请至少选择 2 个商务网批次进行合并");
      return;
    }
    const target = commercialSelected[0];
    setMergeTargetId(target.import_batch_id);
    setMergeName(target.batch_name?.trim() || batchLabel(target));
    setMergeModalOpen(true);
  };

  const confirmMerge = async () => {
    if (commercialSelected.length < 2) return;
    const targetId = mergeTargetId || commercialSelected[0].import_batch_id;
    const sourceIds = commercialSelected
      .map((row) => row.import_batch_id)
      .filter((id) => id !== targetId);
    if (!sourceIds.length) {
      message.warning("请选择一个不同的目标批次");
      return;
    }
    setMergeSaving(true);
    try {
      await api.mergeBatches(targetId, sourceIds, mergeName.trim() || undefined);
      message.success("批次已合并，可在商务网分析中统一查看");
      setMergeModalOpen(false);
      setSelectedBatchIds([]);
      void fetchData();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setMergeSaving(false);
    }
  };

  const selectedCase = cases.find((item) => item.case_id === selectedCaseId) ?? null;
  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount: items.length,
    boundBatchCount: selectedCase?.batch_count ?? 0,
    selectedCaseId,
  });

  const columns = useMemo(
    () => [
      {
        title: "批次名称",
        key: "batch_name",
        render: (_: unknown, row: BatchInfo) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{batchLabel(row)}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              <code>{row.import_batch_id.slice(0, 8)}…</code>
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: "来源",
        dataIndex: "source_type",
        width: 120,
        render: (val: string) => (
          <Tag
            color={
              val === "bank"
                ? "blue"
                : val === "commercial"
                  ? "purple"
                  : val === "wechat"
                    ? "orange"
                    : val === "telecom"
                      ? "cyan"
                      : val === "enterprise"
                      ? "green"
                      : "default"
            }
          >
            {SOURCE_TAG_LABELS[val] || val}
          </Tag>
        ),
      },
      {
        title: "所属案件",
        key: "case",
        width: 140,
        render: (_: unknown, row: BatchInfo) => {
          const mapped = batchCaseMap[row.import_batch_id];
          if (mapped) {
            return (
              <Button type="link" size="small" onClick={() => navigate(`/cases`)}>
                {mapped.case_name}
              </Button>
            );
          }
          return <Tag>未归属</Tag>;
        },
      },
      { title: "条数", dataIndex: "file_count", width: 88 },
      {
        title: "包含来源",
        key: "source_labels",
        ellipsis: true,
        render: (_: unknown, row: BatchInfo) => row.source_labels?.trim() || "—",
      },
      { title: "最近导入时间", dataIndex: "imported_at", width: 200 },
      {
        title: "操作",
        key: "actions",
        width: 520,
        render: (_: unknown, row: BatchInfo) => (
          <Space wrap>
            <Button size="small" onClick={() => openRenameModal(row)}>
              重命名
            </Button>
            {!batchCaseMap[row.import_batch_id] && (
              <Button size="small" onClick={() => openBindModal(row.import_batch_id)}>
                加入案件
              </Button>
            )}
            {row.source_type === "bank" && (
              <Button size="small" type="primary" onClick={() => navigate(`/bank?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                银行分析
              </Button>
            )}
            {row.source_type === "wechat" && (
              <Button size="small" type="primary" onClick={() => navigate(`/wechat-analysis?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                微信分析
              </Button>
            )}
            {row.source_type === "telecom" && (
              <Button size="small" type="primary" onClick={() => navigate(`/telecom-analysis?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                通讯分析
              </Button>
            )}
            {row.source_type === "commercial" && (
              <>
                <Button
                  size="small"
                  type="primary"
                  onClick={() => navigate(`/commercial-analysis?batch=${encodeURIComponent(row.import_batch_id)}`)}
                >
                  商务网分析
                </Button>
                <Button size="small" onClick={() => navigate(`/risk?batch=${encodeURIComponent(row.import_batch_id)}`)}>
                  风险分析
                </Button>
              </>
            )}
            {row.source_type === "enterprise" && (
              <Button
                size="small"
                type="primary"
                onClick={() => navigate(`/risk?enterpriseBatch=${encodeURIComponent(row.import_batch_id)}`)}
              >
                关联风险
              </Button>
            )}
            <Button size="small" onClick={() => void exportRow(row)}>
              导出电子表格
            </Button>
            {!batchCaseMap[row.import_batch_id] ? (
            <Popconfirm
              title="确定删除该批次？"
              description="将删除本批 raw/std 与元数据；商务网还会清除匹配与风险结果；工商会清除主体及依赖的匹配行。不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => void deleteRow(row)}
            >
              <Button size="small" danger>
                删除批次
              </Button>
            </Popconfirm>
            ) : (
              <Button
                size="small"
                danger
                disabled
                title={`已绑定案件「${batchCaseMap[row.import_batch_id].case_name}」，请先在案件管理中解绑`}
                onClick={() =>
                  message.warning(
                    `该批次已绑定案件「${batchCaseMap[row.import_batch_id].case_name}」，请先在案件管理中解绑后再删除`
                  )
                }
              >
                删除批次
              </Button>
            )}
          </Space>
        ),
      },
    ],
    [navigate, fetchData, batchCaseMap, cases]
  );

  return (
    <div>
      <WorkflowGuide steps={guideSteps} currentKey="batches" compact />
      <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>批次管理</Title>
        <Space>
          {(filter === "commercial" || filter === "all") && (
            <Button
              type="primary"
              disabled={commercialSelected.length < 2}
              onClick={openMergeModal}
            >
              合并商务网批次（{commercialSelected.length}）
            </Button>
          )}
          <Segmented
            options={(Object.keys(SOURCE_LABELS) as Source[]).map((key) => ({ value: key, label: SOURCE_LABELS[key] }))}
            value={filter}
            onChange={(val) => setFilter(val as Source)}
          />
          <Button onClick={fetchData}>刷新</Button>
        </Space>
      </div>
      <Paragraph style={{ color: "#5b6477" }}>
        「全部」包含银行、商务网、微信、通讯话单与工商（企查查/工商库）批次，按导入时间混合排序。商务网可将金湾、珠海等多个发电厂批次勾选后合并为一个批次再分析。
      </Paragraph>
      <Table
        rowKey="import_batch_id"
        rowSelection={
          filter === "commercial" || filter === "all"
            ? {
                selectedRowKeys: selectedBatchIds,
                onChange: (keys) => setSelectedBatchIds(keys.map(String)),
                getCheckboxProps: (row: BatchInfo) => ({
                  disabled: row.source_type !== "commercial",
                }),
              }
            : undefined
        }
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 10 }}
        size="small"
      />
      <Modal
        title="修改批次名称"
        open={renameModalOpen}
        confirmLoading={renameSaving}
        onCancel={() => setRenameModalOpen(false)}
        onOk={() => void confirmRename()}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text type="secondary">批次编号：{renameBatchId}</Typography.Text>
          <Input
            value={renameValue}
            maxLength={120}
            placeholder="请输入批次名称"
            onChange={(event) => setRenameValue(event.target.value)}
          />
        </Space>
      </Modal>
      <Modal
        title="加入案件"
        open={bindModalOpen}
        onCancel={() => setBindModalOpen(false)}
        onOk={() => void confirmBind()}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text type="secondary">批次：{batchLabel({ import_batch_id: bindBatchId })}</Typography.Text>
          <Select
            style={{ width: "100%" }}
            placeholder="选择案件"
            value={bindCaseId ?? undefined}
            onChange={setBindCaseId}
            options={cases.map((c) => ({ value: c.case_id, label: c.case_name }))}
          />
          {!cases.length && (
            <Button type="link" onClick={() => navigate("/cases")}>
              尚无案件，去创建
            </Button>
          )}
        </Space>
      </Modal>
      <Modal
        title="合并商务网批次"
        open={mergeModalOpen}
        confirmLoading={mergeSaving}
        onCancel={() => setMergeModalOpen(false)}
        onOk={() => void confirmMerge()}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            将选中的 {commercialSelected.length} 个批次合并为一个，合并后可在商务网分析中统一统计金湾、珠海等所有采购单位数据。
          </Typography.Text>
          <div>
            <Typography.Text>目标批次（保留）</Typography.Text>
            <Select
              style={{ width: "100%", marginTop: 8 }}
              value={mergeTargetId || undefined}
              onChange={setMergeTargetId}
              options={commercialSelected.map((row) => ({
                value: row.import_batch_id,
                label: `${batchLabel(row)}${row.source_labels ? ` · ${row.source_labels}` : ""}`,
              }))}
            />
          </div>
          <div>
            <Typography.Text>合并后批次名称</Typography.Text>
            <Input
              style={{ marginTop: 8 }}
              value={mergeName}
              maxLength={120}
              placeholder="如：2024年商务网询价"
              onChange={(event) => setMergeName(event.target.value)}
            />
          </div>
        </Space>
      </Modal>
      </Card>
    </div>
  );
}

export default BatchesPage;
