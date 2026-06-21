import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  CaseInfo,
  CASE_CHANGED_EVENT,
  emitCaseChanged,
  persistSelectedCaseId,
  resolveSelectedCaseId,
} from "../api";
import WorkflowGuide, { buildWorkflowSteps, DEFAULT_WORKFLOW_SNAPSHOT } from "../components/WorkflowGuide";

const { Title, Paragraph, Text } = Typography;

const SOURCE_TAG: Record<string, string> = {
  bank: "银行",
  commercial: "商务网",
  enterprise: "工商",
  wechat: "微信",
  telecom: "通讯",
};

function CaseManagePage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseInfo | null>(null);
  const [unbound, setUnbound] = useState<BatchInfo[]>([]);
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<{ case_name: string; description: string }>();
  const selectedCaseIdRef = useRef<number | null>(null);

  const selectCase = useCallback((caseId: number | null) => {
    selectedCaseIdRef.current = caseId;
    setSelectedCaseId(caseId);
    persistSelectedCaseId(caseId);
    emitCaseChanged(caseId);
  }, []);

  const refreshCases = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listCases();
      setCases(data.items);
      const nextId = resolveSelectedCaseId(data.items, selectedCaseIdRef.current);
      setSelectedCaseId(nextId);
      selectedCaseIdRef.current = nextId;
      persistSelectedCaseId(nextId);
      emitCaseChanged(nextId);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshDetail = useCallback(async (caseId: number) => {
    try {
      const [detail, unboundData] = await Promise.all([
        api.getCase(caseId),
        api.listUnboundBatches(),
      ]);
      if (selectedCaseIdRef.current !== caseId) return;
      setCaseDetail(detail);
      setUnbound(unboundData.items);
      setSelectedBatchIds([]);
    } catch (err) {
      message.error((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshCases();
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId ?? null;
      if (!nextCaseId || nextCaseId === selectedCaseIdRef.current) return;
      selectedCaseIdRef.current = nextCaseId;
      setSelectedCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  useEffect(() => {
    if (selectedCaseId) {
      void refreshDetail(selectedCaseId);
    } else {
      setCaseDetail(null);
      setUnbound([]);
    }
  }, [selectedCaseId, refreshDetail]);

  const createCase = async () => {
    const values = await createForm.validateFields();
    try {
      const created = await api.createCase(values);
      message.success("案件已创建");
      setCreateOpen(false);
      createForm.resetFields();
      await refreshCases();
      selectCase(created.case_id);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const bindBatches = async () => {
    if (!selectedCaseId || !selectedBatchIds.length) return;
    try {
      await api.bindCaseBatches(selectedCaseId, selectedBatchIds);
      message.success(`已绑定 ${selectedBatchIds.length} 个批次`);
      await refreshDetail(selectedCaseId);
      await refreshCases();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const unbindBatch = async (batchId: string) => {
    if (!selectedCaseId) return;
    try {
      await api.unbindCaseBatch(selectedCaseId, batchId);
      message.success("已解绑批次");
      await refreshDetail(selectedCaseId);
      await refreshCases();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const discover = async () => {
    if (!selectedCaseId) return;
    try {
      message.loading({ content: "正在扫描候选标识…", key: "discover" });
      const result = await api.discoverCaseIdentifiers(selectedCaseId);
      message.success({
        content: `扫描完成：新增 ${result.inserted} 条候选，跳过 ${result.skipped} 条`,
        key: "discover",
      });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "discover" });
    }
  };

  const autoLink = async () => {
    if (!selectedCaseId) return;
    try {
      message.loading({ content: "机器预关联中…", key: "auto-link" });
      const result = await api.autoLinkCase(selectedCaseId, true);
      message.success({
        content: `预关联完成：新建 ${result.persons_created} 人，关联 ${result.links_created} 条，剩余 ${result.unresolved_pending} 条待人工处理`,
        key: "auto-link",
        duration: 6,
      });
    } catch (err) {
      message.error({ content: (err as Error).message, key: "auto-link" });
    }
  };

  const deleteCase = async (caseId: number) => {
    try {
      await api.deleteCase(caseId);
      message.success("案件已删除");
      if (selectedCaseId === caseId) selectCase(null);
      await refreshCases();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const boundColumns = useMemo(
    () => [
      {
        title: "批次编号",
        dataIndex: "import_batch_id",
        render: (val: string) => <code>{val}</code>,
      },
      {
        title: "来源",
        dataIndex: "source_type",
        width: 100,
        render: (val: string) => <Tag>{SOURCE_TAG[val] || val}</Tag>,
      },
      { title: "绑定时间", dataIndex: "bound_at", width: 180 },
      {
        title: "操作",
        key: "actions",
        width: 100,
        render: (_: unknown, row: { import_batch_id: string }) => (
          <Popconfirm title="解绑该批次？" onConfirm={() => void unbindBatch(row.import_batch_id)}>
            <Button size="small" danger>
              解绑
            </Button>
          </Popconfirm>
        ),
      },
    ],
    [selectedCaseId]
  );

  const activeCase = useMemo(
    () => cases.find((item) => item.case_id === selectedCaseId) ?? caseDetail,
    [cases, selectedCaseId, caseDetail]
  );

  const guideSteps = buildWorkflowSteps({
    ...DEFAULT_WORKFLOW_SNAPSHOT,
    caseCount: cases.length,
    batchCount: unbound.length + (caseDetail?.batches?.length ?? 0),
    boundBatchCount: caseDetail?.batch_count ?? caseDetail?.batches?.length ?? 0,
    selectedCaseId,
  });

  return (
    <div>
      <WorkflowGuide steps={guideSteps} currentKey="cases" compact />
      <Card className="app-card" bordered={false}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          案件管理
        </Title>
        <Space wrap>
          <Select
            style={{ minWidth: 220 }}
            placeholder="选择案件"
            value={selectedCaseId ?? undefined}
            onChange={(val) => selectCase(val ?? null)}
            options={cases.map((c) => ({ value: c.case_id, label: `${c.case_name} (${c.batch_count}批)` }))}
            allowClear
            onClear={() => selectCase(null)}
          />
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            新建案件
          </Button>
          {selectedCaseId && (
            <>
              <Button onClick={() => void discover()}>扫描候选标识</Button>
              <Button type="primary" onClick={() => void autoLink()}>机器预关联</Button>
              <Button onClick={() => navigate(`/person-linking?case=${selectedCaseId}`)}>人物关联</Button>
              <Button type="primary" onClick={() => navigate(`/fusion-cockpit?case=${selectedCaseId}&view=analysis&tab=open`)}>
                融合驾驶舱
              </Button>
            </>
          )}
        </Space>
      </div>
      {activeCase && (
        <Paragraph style={{ marginBottom: 16 }}>
          <Text strong>当前案件：</Text>
          <Text>{activeCase.case_name}</Text>
          {activeCase.description ? (
            <Text type="secondary"> · {activeCase.description}</Text>
          ) : null}
        </Paragraph>
      )}
      <Paragraph style={{ color: "#5b6477" }}>
        每个案件独立维护人物库与关联关系。请先将已导入批次绑定到案件，再扫描候选标识并在
        <Link to="/person-linking"> 人物关联 </Link>
        页确认映射。
      </Paragraph>

      <Table
        rowKey="case_id"
        size="small"
        loading={loading}
        dataSource={cases}
        pagination={{ pageSize: 8 }}
        rowClassName={(row) => (row.case_id === selectedCaseId ? "case-row-selected" : "")}
        onRow={(row) => ({
          onClick: () => selectCase(row.case_id),
          style: { cursor: "pointer" },
        })}
        columns={[
          { title: "案件名称", dataIndex: "case_name" },
          { title: "描述", dataIndex: "description", ellipsis: true },
          { title: "批次", dataIndex: "batch_count", width: 72 },
          { title: "状态", dataIndex: "status", width: 88, render: (v: string) => <Tag>{v}</Tag> },
          { title: "更新时间", dataIndex: "updated_at", width: 180 },
          {
            title: "操作",
            key: "actions",
            width: 280,
            render: (_: unknown, row: CaseInfo) => (
              <Space wrap onClick={(event) => event.stopPropagation()}>
                <Button size="small" type={row.case_id === selectedCaseId ? "primary" : "default"} onClick={() => selectCase(row.case_id)}>
                  {row.case_id === selectedCaseId ? "当前选中" : "选中"}
                </Button>
                <Button size="small" onClick={() => navigate(`/person-linking?case=${row.case_id}`)}>
                  关联
                </Button>
                <Button size="small" type="primary" onClick={() => navigate(`/fusion-cockpit?case=${row.case_id}&view=analysis&tab=open`)}>
                  驾驶舱
                </Button>
                <Popconfirm title="删除案件及人物关联？" onConfirm={() => void deleteCase(row.case_id)}>
                  <Button size="small" danger>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {caseDetail && selectedCaseId === caseDetail.case_id && (
        <>
          <Title level={5} style={{ marginTop: 24 }}>
            已绑定批次
          </Title>
          <Table
            rowKey="import_batch_id"
            size="small"
            columns={boundColumns}
            dataSource={caseDetail.batches || []}
            pagination={false}
            locale={{ emptyText: "尚未绑定批次" }}
            style={{ marginBottom: 16 }}
          />
          <Space direction="vertical" style={{ width: "100%" }}>
            <Paragraph style={{ marginBottom: 0 }}>绑定未归属批次（可多选）</Paragraph>
            <Select
              mode="multiple"
              style={{ width: "100%" }}
              placeholder="选择要绑定的批次"
              value={selectedBatchIds}
              onChange={setSelectedBatchIds}
              options={unbound.map((b) => ({
                value: b.import_batch_id,
                label: `${SOURCE_TAG[b.source_type] || b.source_type} · ${batchLabel(b)} · ${b.imported_at}`,
              }))}
            />
            <Button type="primary" disabled={!selectedBatchIds.length} onClick={() => void bindBatches()}>
              绑定到当前案件
            </Button>
          </Space>
        </>
      )}

      <Modal title="新建案件" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => void createCase()}>
        <Form form={createForm} layout="vertical">
          <Form.Item name="case_name" label="案件名称" rules={[{ required: true, message: "请输入案件名称" }]}>
            <Input placeholder="例如：华南机电调查" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="可选说明" />
          </Form.Item>
        </Form>
      </Modal>
      </Card>
    </div>
  );
}

export default CaseManagePage;
