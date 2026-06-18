import { useEffect, useMemo, useState } from "react";
import { Button, Card, Modal, Space, Table, Tooltip, Typography, message } from "antd";
import { useSearchParams } from "react-router-dom";
import { api, TablePreview } from "../api";

const { Title, Paragraph } = Typography;

/** 列表展示用列名：去掉技术前缀，避免界面出现过多英文片段 */
function displayColumnTitle(raw: string): string {
  const trimmed = raw.replace(/^src_/i, "").trim();
  return trimmed || raw;
}

function PreviewCell({ value }: { value: unknown }) {
  const text = value === null || value === undefined ? "" : String(value);
  if (!text) {
    return <span className="tables-preview-cell tables-preview-cell--empty">—</span>;
  }
  return (
    <Tooltip
      title={<div className="tables-preview-tooltip">{text}</div>}
      placement="topLeft"
      overlayStyle={{ maxWidth: 520 }}
      mouseEnterDelay={0.35}
    >
      <span className="tables-preview-cell">{text}</span>
    </Tooltip>
  );
}

function TablesPage() {
  const [searchParams] = useSearchParams();
  const [tables, setTables] = useState<string[]>([]);
  const [activeTable, setActiveTable] = useState<string>("");
  const [preview, setPreview] = useState<TablePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedRowIds, setSelectedRowIds] = useState<number[]>([]);
  const [highlightRowId, setHighlightRowId] = useState<number | null>(null);
  const [tableBodyHeight, setTableBodyHeight] = useState(420);

  const urlTable = searchParams.get("table") || "";
  const urlHighlight = searchParams.get("highlight");

  useEffect(() => {
    const update = () => setTableBodyHeight(Math.max(260, Math.floor(window.innerHeight - 292)));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const refreshTables = async () => {
    try {
      const data = await api.listTables();
      setTables(data.items);
      const preferred = urlTable && data.items.includes(urlTable) ? urlTable : activeTable;
      if (data.items.length > 0 && (!preferred || !data.items.includes(preferred))) {
        setActiveTable(data.items[0]);
      } else if (preferred) {
        setActiveTable(preferred);
      }
      if (data.items.length === 0) {
        setActiveTable("");
        setPreview(null);
      }
      if (urlHighlight) {
        const parsed = Number(urlHighlight);
        if (!Number.isNaN(parsed)) setHighlightRowId(parsed);
      }
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const loadPreview = async (table: string) => {
    if (!table) return;
    setLoading(true);
    try {
      const data = await api.previewTable(table, 200, 0);
      setPreview(data);
      setSelectedRowIds([]);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshTables();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadPreview(activeTable);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTable]);

  const columns = useMemo(() => {
    if (!preview) return [];
    return preview.columns.map((col, idx) => {
      const title = displayColumnTitle(col);
      const isNarrow =
        /单号|编号|id|时间|日期|类别|策略|状态|金额|数量/i.test(title) && title.length <= 12;
      return {
        title,
        dataIndex: idx,
        key: col,
        width: isNarrow ? 112 : 160,
        minWidth: isNarrow ? 96 : 140,
        render: (val: unknown) => <PreviewCell value={val} />,
      };
    });
  }, [preview]);

  const dataSource = useMemo(() => {
    if (!preview) return [] as Array<Record<string, unknown> & { __key: number }>;
    return preview.rows.map((row, rowIdx) => {
      const item: Record<string, unknown> & { __key: number } = { __key: preview.rowids[rowIdx] };
      row.forEach((cell, colIdx) => {
        item[colIdx] = cell;
      });
      return item;
    });
  }, [preview]);

  const handleDeleteRows = async () => {
    if (!activeTable || selectedRowIds.length === 0) return;
    Modal.confirm({
      title: `确认删除 ${selectedRowIds.length} 行？`,
      content: "删除操作不可恢复，请确认。",
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.deleteRows(activeTable, selectedRowIds);
          message.success("已删除");
          await loadPreview(activeTable);
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  };

  const handleDropTable = () => {
    if (!activeTable) return;
    Modal.confirm({
      title: `确认删除整张表 ${activeTable}？`,
      content: "将清空该表的所有行和登记信息，标准层历史数据保留。",
      okText: "删除整张表",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.dropTable(activeTable);
          message.success("已删除");
          setActiveTable("");
          setPreview(null);
          await refreshTables();
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  };

  return (
    <Card className="app-card" bordered={false}>
      <Title level={4} style={{ marginBottom: 8 }}>数据表浏览</Title>
      <Paragraph style={{ color: "#5b6477", marginBottom: 16 }}>
        左侧为已登记的用户上传数据表（一般为「文件名_工作表名」），右侧预览只展示业务列。长文本可悬停查看全文。
      </Paragraph>
      <div className="tables-browser-layout">
        <aside className="tables-browser-sider" aria-label="数据表列表">
          <div className="tables-browser-sider-head">
            <Button size="small" onClick={refreshTables}>
              刷新
            </Button>
          </div>
          <div className="tables-browser-list">
            {tables.length === 0 && <div className="tables-browser-empty">暂无已导入数据表</div>}
            {tables.map((name) => (
              <button
                key={name}
                type="button"
                className={`tables-browser-list-item${name === activeTable ? " is-active" : ""}`}
                onClick={() => setActiveTable(name)}
              >
                {name}
              </button>
            ))}
          </div>
        </aside>
        <div className="tables-browser-main">
          <div className="tables-browser-toolbar">
            <Space wrap size={[8, 8]}>
              <Button onClick={() => loadPreview(activeTable)} disabled={!activeTable}>
                刷新预览
              </Button>
              <Button danger onClick={handleDeleteRows} disabled={selectedRowIds.length === 0}>
                删除选中行（{selectedRowIds.length}）
              </Button>
              <Button danger onClick={handleDropTable} disabled={!activeTable}>
                删除整张表
              </Button>
            </Space>
            {preview ? (
              <div className="tables-browser-meta">
                <span className="tables-browser-meta-label">当前表</span>
                <span className="tables-browser-meta-value" title={preview.table_name}>
                  {preview.table_name}
                </span>
                <span className="tables-browser-meta-stat">
                  总行数 <strong>{preview.total_rows}</strong>
                </span>
                <span className="tables-browser-meta-stat">
                  本页预览 <strong>{preview.rows.length}</strong> 行
                </span>
              </div>
            ) : null}
          </div>
          <div className="tables-browser-table-shell">
            <Table
              className="tables-browser-table"
              rowKey="__key"
              size="small"
              loading={loading}
              scroll={{ x: "max-content", y: tableBodyHeight }}
              columns={columns}
              dataSource={dataSource}
              rowClassName={(record) =>
                highlightRowId !== null && record.__key === highlightRowId ? "tables-row-highlight" : ""
              }
              rowSelection={{
                selectedRowKeys: selectedRowIds,
                onChange: (keys) => setSelectedRowIds(keys.map((k) => Number(k))),
              }}
              pagination={{ pageSize: 50, showSizeChanger: false }}
            />
          </div>
        </div>
      </div>
    </Card>
  );
}

export default TablesPage;
