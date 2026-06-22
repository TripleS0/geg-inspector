import { useCallback, useEffect, useMemo, useState, type Key } from "react";
import {
  Button,
  Card,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { CloudUploadOutlined, DeleteOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  api,
  BatchInfo,
  batchLabel,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  CaseInfo,
  DataCenterRecord,
} from "../api";

const { Paragraph, Text } = Typography;

const SOURCE_OPTIONS = [
  { value: "all", label: "全部类型" },
  { value: "bank", label: "银行流水" },
  { value: "wechat", label: "微信转账" },
  { value: "telecom", label: "通讯话单" },
  { value: "commercial", label: "商务网" },
  { value: "enterprise", label: "工商信息" },
];

const SOURCE_TAG_COLORS: Record<string, string> = {
  bank: "blue",
  wechat: "orange",
  telecom: "cyan",
  commercial: "purple",
  enterprise: "green",
};

function DataManagePage() {
  const navigate = useNavigate();
  const [records, setRecords] = useState<DataCenterRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sourceType, setSourceType] = useState("all");
  const [batchId, setBatchId] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [batches, setBatches] = useState<BatchInfo[]>([]);
  const [batchCaseMap, setBatchCaseMap] = useState<Record<string, { case_id: number; case_name: string }>>({});
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(
    () => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null
  );
  const [deleteCaseModalOpen, setDeleteCaseModalOpen] = useState(false);
  const [deleteCaseId, setDeleteCaseId] = useState<number | null>(null);
  const [deleteBatchModalOpen, setDeleteBatchModalOpen] = useState(false);
  const [deleteBatchTarget, setDeleteBatchTarget] = useState<string>("");

  const rowKey = (row: DataCenterRecord) =>
    row.record_kind === "raw" && row.raw_table
      ? `raw:${row.raw_table}:${row.record_id}`
      : `${row.record_kind}:${row.record_id}`;

  const fetchMeta = useCallback(async () => {
    try {
      const [caseData, batchData, mapData] = await Promise.all([
        api.listCases(),
        api.listBatches(),
        api.batchCaseMap(),
      ]);
      setCases(caseData.items);
      setBatches(batchData.items);
      setBatchCaseMap(mapData.items);
      const stored = Number(localStorage.getItem(CASE_STORAGE_KEY)) || null;
      setSelectedCaseId(
        stored && caseData.items.some((item) => item.case_id === stored)
          ? stored
          : caseData.items[0]?.case_id ?? null
      );
    } catch (err) {
      message.error((err as Error).message);
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listDataCenterRecords({
        case_id: selectedCaseId ?? undefined,
        batch_id: batchId,
        source_type: sourceType === "all" ? undefined : sourceType,
        keyword,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setRecords(data.items);
      setTotal(data.total);
      setSelectedRowKeys([]);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedCaseId, batchId, sourceType, keyword, page, pageSize]);

  useEffect(() => {
    void fetchMeta();
  }, [fetchMeta]);

  useEffect(() => {
    void fetchRecords();
  }, [fetchRecords]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number }>).detail?.caseId ?? null;
      setSelectedCaseId(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, []);

  const deleteSelected = async () => {
    if (!selectedRowKeys.length) {
      message.warning("请先选择要删除的数据");
      return;
    }
    const items = records
      .filter((row) => selectedRowKeys.includes(rowKey(row)))
      .map((row) => ({
        record_kind: row.record_kind,
        record_id: row.record_id,
        ...(row.raw_table ? { raw_table: row.raw_table } : {}),
      }));
    try {
      const result = await api.deleteDataCenterRecords(items);
      message.success(`已删除 ${result.deleted} 条数据`);
      void fetchRecords();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const deleteOne = async (row: DataCenterRecord) => {
    try {
      await api.deleteDataCenterRecords([
        {
          record_kind: row.record_kind,
          record_id: row.record_id,
          ...(row.raw_table ? { raw_table: row.raw_table } : {}),
        },
      ]);
      message.success("已删除");
      void fetchRecords();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const confirmDeleteBatch = async () => {
    if (!deleteBatchTarget) return;
    try {
      await api.deleteBatch(deleteBatchTarget);
      message.success("已删除该批次及相关数据");
      setDeleteBatchModalOpen(false);
      setDeleteBatchTarget("");
      void fetchMeta();
      void fetchRecords();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const confirmDeleteCase = async () => {
    if (!deleteCaseId) return;
    try {
      await api.deleteCase(deleteCaseId);
      message.success("已删除案件");
      setDeleteCaseModalOpen(false);
      setDeleteCaseId(null);
      void fetchMeta();
      void fetchRecords();
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const caseBatches = useMemo(() => {
    if (!selectedCaseId) return batches;
    return batches.filter((batch) => batchCaseMap[batch.import_batch_id]?.case_id === selectedCaseId);
  }, [batches, batchCaseMap, selectedCaseId]);

  const deletableBatches = useMemo(
    () => batches.filter((batch) => !batchCaseMap[batch.import_batch_id]),
    [batches, batchCaseMap]
  );

  const columns = useMemo(
    () => [
      {
        title: "数据 ID",
        key: "record_id",
        width: 88,
        render: (_: unknown, row: DataCenterRecord) => (
          <Text code>{String(row.record_id).padStart(3, "0")}</Text>
        ),
      },
      {
        title: "数据类型",
        dataIndex: "source_type_label",
        width: 110,
        render: (_: string, row: DataCenterRecord) => (
          <Tag color={SOURCE_TAG_COLORS[row.source_type] || "default"}>{row.source_type_label}</Tag>
        ),
      },
      { title: "数据内容", dataIndex: "content", ellipsis: true },
      { title: "日期", dataIndex: "record_date", width: 120 },
      { title: "原文件名", dataIndex: "source_file", ellipsis: true, width: 180 },
      {
        title: "操作",
        key: "actions",
        width: 80,
        render: (_: unknown, row: DataCenterRecord) => (
          <Popconfirm
            title="确定删除该条数据？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => void deleteOne(row)}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        ),
      },
    ],
    []
  );

  const recordTab = (
    <div>
      <div className="data-manage-toolbar">
        <Space wrap>
          <span>模糊搜索：</span>
          <Input.Search
            allowClear
            placeholder="搜索内容、文件名、批次…"
            style={{ width: 260 }}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onSearch={(val) => {
              setKeyword(val.trim());
              setPage(1);
            }}
          />
          <Select
            style={{ width: 130 }}
            value={sourceType}
            options={SOURCE_OPTIONS}
            onChange={(val) => {
              setSourceType(val);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="按批次筛选"
            style={{ width: 200 }}
            value={batchId}
            options={caseBatches.map((batch) => ({
              value: batch.import_batch_id,
              label: batchLabel(batch),
            }))}
            onChange={(val) => {
              setBatchId(val);
              setPage(1);
            }}
          />
        </Space>
        <Space>
          <Popconfirm
            title={`确定批量删除 ${selectedRowKeys.length} 条数据？`}
            description="删除后不可恢复"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={!selectedRowKeys.length}
            onConfirm={() => void deleteSelected()}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!selectedRowKeys.length}>
              批量删除
            </Button>
          </Popconfirm>
          <Button type="primary" icon={<CloudUploadOutlined />} onClick={() => navigate("/fusion-cockpit/new")}>
            导入新数据
          </Button>
        </Space>
      </div>
      <Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {selectedCaseId
          ? `当前展示案件「${cases.find((c) => c.case_id === selectedCaseId)?.case_name ?? ""}」关联批次下的标准化数据。`
          : "未选择案件时展示全部数据。可在顶部切换当前案件以限定范围。"}
      </Paragraph>
      <Table
        rowKey={rowKey}
        rowSelection={{
          selectedRowKeys,
          onChange: setSelectedRowKeys,
        }}
        columns={columns}
        dataSource={records}
        loading={loading}
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (count) => `共 ${count} 条`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />
    </div>
  );

  const batchTab = (
    <div>
      <Paragraph type="secondary">
        删除整批导入数据（含 raw/std 行与元数据）。已绑定案件的批次需先在案件中解绑。
      </Paragraph>
      <Table
        rowKey="import_batch_id"
        size="small"
        dataSource={batches}
        pagination={{ pageSize: 10 }}
        columns={[
          {
            title: "批次名称",
            key: "name",
            render: (_: unknown, row: BatchInfo) => batchLabel(row),
          },
          {
            title: "来源",
            dataIndex: "source_type",
            width: 110,
            render: (val: string) => SOURCE_OPTIONS.find((o) => o.value === val)?.label || val,
          },
          {
            title: "所属案件",
            key: "case",
            width: 140,
            render: (_: unknown, row: BatchInfo) => {
              const mapped = batchCaseMap[row.import_batch_id];
              return mapped ? mapped.case_name : <Tag>未归属</Tag>;
            },
          },
          { title: "条数", dataIndex: "file_count", width: 80 },
          { title: "导入时间", dataIndex: "imported_at", width: 180 },
          {
            title: "操作",
            key: "actions",
            width: 100,
            render: (_: unknown, row: BatchInfo) => {
              const bound = batchCaseMap[row.import_batch_id];
              if (bound) {
                return (
                  <Button
                    size="small"
                    danger
                    disabled
                    title={`已绑定案件「${bound.case_name}」，请先解绑`}
                  >
                    删除批次
                  </Button>
                );
              }
              return (
                <Button
                  size="small"
                  danger
                  onClick={() => {
                    setDeleteBatchTarget(row.import_batch_id);
                    setDeleteBatchModalOpen(true);
                  }}
                >
                  删除批次
                </Button>
              );
            },
          },
        ]}
      />
    </div>
  );

  const caseTab = (
    <div>
      <Paragraph type="secondary">
        删除案件将解除批次绑定并清除人物、标识候选与融合配置，不会删除原始导入批次数据。
      </Paragraph>
      <Table
        rowKey="case_id"
        size="small"
        dataSource={cases}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "案件名称", dataIndex: "case_name" },
          { title: "状态", dataIndex: "status", width: 90 },
          { title: "批次数", dataIndex: "batch_count", width: 80 },
          { title: "创建时间", dataIndex: "created_at", width: 180 },
          {
            title: "操作",
            key: "actions",
            width: 100,
            render: (_: unknown, row: CaseInfo) => (
              <Button
                size="small"
                danger
                onClick={() => {
                  setDeleteCaseId(row.case_id);
                  setDeleteCaseModalOpen(true);
                }}
              >
                删除案件
              </Button>
            ),
          },
        ]}
      />
    </div>
  );

  return (
    <div className="data-manage-page">
      <Card className="app-card" bordered={false}>
        <Tabs
          items={[
            { key: "records", label: "数据记录", children: recordTab },
            { key: "batches", label: "批次删除", children: batchTab },
            { key: "cases", label: "案件删除", children: caseTab },
          ]}
        />
      </Card>

      <Modal
        title="删除批次"
        open={deleteBatchModalOpen}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        onCancel={() => setDeleteBatchModalOpen(false)}
        onOk={() => void confirmDeleteBatch()}
      >
        <Paragraph>
          确定删除批次「{batchLabel({ import_batch_id: deleteBatchTarget })}」？
          将移除该批在库中的全部业务数据与元数据，不可恢复。
        </Paragraph>
        {deletableBatches.length === 0 && deleteBatchTarget && batchCaseMap[deleteBatchTarget] ? (
          <Paragraph type="danger">该批次已绑定案件，无法直接删除。</Paragraph>
        ) : null}
      </Modal>

      <Modal
        title="删除案件"
        open={deleteCaseModalOpen}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        onCancel={() => setDeleteCaseModalOpen(false)}
        onOk={() => void confirmDeleteCase()}
      >
        <Paragraph>
          确定删除案件「{cases.find((c) => c.case_id === deleteCaseId)?.case_name ?? ""}」？
          案件关联的人物与配置将被清除，原始导入数据保留。
        </Paragraph>
      </Modal>
    </div>
  );
}

export default DataManagePage;
