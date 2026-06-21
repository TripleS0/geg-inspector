import { useCallback, useMemo, useState } from "react";
import { Button, Descriptions, Drawer, Table, Tag, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import { api, FusionRecord, RecordDetailResponse } from "../../api";
import { formatFusionAmount, graphRecordTypeLabel } from "../../utils/graphRecordUtils";

const { Title } = Typography;

const RECORD_TYPE_COLORS: Record<string, string> = {
  bank_txn: "#e85d45",
  wechat: "#52c41a",
  telecom: "#1890ff",
  enterprise: "#722ed1",
  commercial: "#fa8c16",
};

export function useFusionRecordDrawers(caseId: number | null) {
  const navigate = useNavigate();
  const [listOpen, setListOpen] = useState(false);
  const [listTitle, setListTitle] = useState("");
  const [listMeta, setListMeta] = useState<Record<string, string>>({});
  const [listRecords, setListRecords] = useState<FusionRecord[]>([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState<FusionRecord | null>(null);
  const [rawDetail, setRawDetail] = useState<RecordDetailResponse | null>(null);
  const [rawLoading, setRawLoading] = useState(false);

  const openRecords = useCallback((title: string, records: FusionRecord[], meta: Record<string, string> = {}) => {
    setListTitle(title);
    setListMeta(meta);
    setListRecords(records);
    setListOpen(true);
  }, []);

  const openDetail = useCallback((record: FusionRecord) => {
    setDetailRecord(record);
    setRawDetail(null);
    setDetailOpen(true);
  }, []);

  const loadRawDetail = useCallback(async () => {
    if (!caseId || !detailRecord?.source_ref) return;
    setRawLoading(true);
    try {
      const data = await api.recordDetail(caseId, detailRecord.source_ref);
      setRawDetail(data);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setRawLoading(false);
    }
  }, [caseId, detailRecord]);

  const gotoRawTable = useCallback(() => {
    if (!rawDetail) return;
    const pk = rawDetail.pk as { raw_id?: number };
    if (rawDetail.layer === "raw" && pk.raw_id) {
      navigate(`/tables?table=${encodeURIComponent(rawDetail.table)}&highlight=${pk.raw_id}`);
    } else {
      navigate(`/tables?table=${encodeURIComponent(rawDetail.table)}`);
    }
  }, [navigate, rawDetail]);

  const recordColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "record_type",
        width: 96,
        render: (v: string) => (
          <Tag color={RECORD_TYPE_COLORS[v] || "default"}>{graphRecordTypeLabel(v)}</Tag>
        ),
      },
      { title: "时间", dataIndex: "time", width: 158, render: (v: string | null) => v || "—" },
      { title: "摘要", dataIndex: "summary", ellipsis: true },
      { title: "对手/关联", dataIndex: "counterparty", ellipsis: true, width: 140 },
      {
        title: "金额/时长",
        dataIndex: "amount",
        width: 110,
        render: (v: number | null, row: FusionRecord) =>
          row.record_type === "telecom" ? `${v ?? 0} 秒` : formatFusionAmount(v),
      },
    ],
    []
  );

  const drawers = (
    <>
      <Drawer title={listTitle || "详情数据"} width={640} placement="right" open={listOpen} onClose={() => setListOpen(false)}>
        {Object.keys(listMeta).length > 0 && (
          <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
            {Object.entries(listMeta).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {v}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
        <Table
          rowKey={(_, idx) => `graph-record-${idx}`}
          size="small"
          columns={recordColumns}
          dataSource={listRecords}
          onRow={(row) => ({ onClick: () => openDetail(row), className: "cockpit-record-row" })}
          pagination={{ pageSize: 8, showTotal: (t) => `共 ${t} 条` }}
          locale={{ emptyText: "暂无可展示的明细记录" }}
        />
      </Drawer>

      <Drawer
        title="记录详情"
        width={580}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        extra={
          <Button loading={rawLoading} onClick={() => void loadRawDetail()}>
            查看原始数据
          </Button>
        }
      >
        {detailRecord && (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="类型">
                <Tag color={RECORD_TYPE_COLORS[detailRecord.record_type]}>
                  {graphRecordTypeLabel(detailRecord.record_type)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标题">{detailRecord.title}</Descriptions.Item>
              <Descriptions.Item label="时间">{detailRecord.time || "—"}</Descriptions.Item>
              <Descriptions.Item label="金额/时长">
                {detailRecord.record_type === "telecom"
                  ? `${detailRecord.amount ?? 0} 秒`
                  : formatFusionAmount(detailRecord.amount)}
              </Descriptions.Item>
              <Descriptions.Item label="对手/关联">{detailRecord.counterparty || "—"}</Descriptions.Item>
              <Descriptions.Item label="摘要">{detailRecord.summary || "—"}</Descriptions.Item>
            </Descriptions>
            {rawDetail && (
              <>
                <Title level={5} style={{ marginTop: 16 }}>
                  原始字段
                </Title>
                <Descriptions column={1} size="small" bordered>
                  {Object.entries(rawDetail.fields || {}).map(([key, val]) => (
                    <Descriptions.Item key={key} label={key}>
                      {val === null || val === undefined ? "—" : String(val)}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
                <Button type="primary" style={{ marginTop: 12 }} onClick={gotoRawTable}>
                  定位原始数据
                </Button>
              </>
            )}
          </>
        )}
      </Drawer>
    </>
  );

  return { openRecords, drawers };
}
