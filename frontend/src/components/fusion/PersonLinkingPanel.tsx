import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  BankOutlined,
  IdcardOutlined,
  MobileOutlined,
  PartitionOutlined,
  PlusOutlined,
  ScanOutlined,
  ThunderboltOutlined,
  UserOutlined,
  WechatOutlined,
} from "@ant-design/icons";
import {
  api,
  IDENTIFIER_TYPE_LABELS,
  IdentifierCandidate,
  PersonInfo,
  PersonLink,
} from "../../api";

const { Title, Paragraph, Text } = Typography;

const ROLE_LABELS: Record<string, string> = {
  subject: "主体",
  linked: "关联人",
  unknown: "未知",
};

const MATRIX_COLUMNS: Array<{ key: string; label: string; types: string[] }> = [
  { key: "phone", label: "手机号", types: ["phone"] },
  { key: "wechat", label: "微信号", types: ["wechat_name"] },
  { key: "bank", label: "银行卡/账号", types: ["bank_card", "bank_acct"] },
  { key: "id_no", label: "身份证", types: ["id_no"] },
  { key: "enterprise", label: "关联企业", types: ["enterprise_name"] },
];

const TYPE_FILTER_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "person_name", label: "姓名" },
  { value: "phone", label: "手机" },
  { value: "wechat_name", label: "微信" },
  { value: "bank_card", label: "银行卡" },
  { value: "bank_acct", label: "银行账号" },
  { value: "id_no", label: "身份证" },
  { value: "enterprise_name", label: "企业" },
];

function linksByTypes(links: PersonLink[], types: string[]) {
  return links.filter((l) => types.includes(l.identifier_type));
}

function IdentifierTags({ links, onRemove }: { links: PersonLink[]; onRemove?: (linkId: number) => void }) {
  if (!links.length) return <Text type="secondary">—</Text>;
  return (
    <Space size={[4, 4]} wrap>
      {links.map((link) => (
        <Tag
          key={link.link_id}
          className="link-matrix-tag"
          closable={!!onRemove}
          onClose={(e) => {
            e.preventDefault();
            onRemove?.(link.link_id);
          }}
        >
          {link.identifier_value}
        </Tag>
      ))}
    </Space>
  );
}

export interface PersonLinkingPanelProps {
  caseId: number;
  embedded?: boolean;
  wizardMode?: boolean;
  initialAutoSetup?: boolean;
  onEnterCockpit?: () => void;
  onStatsChange?: (stats: { personCount: number; linkedCount: number; pendingCount: number }) => void;
}

function PersonLinkingPanel({
  caseId,
  embedded = false,
  wizardMode = false,
  initialAutoSetup = false,
  onEnterCockpit,
  onStatsChange,
}: PersonLinkingPanelProps) {
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [candidates, setCandidates] = useState<IdentifierCandidate[]>([]);
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [candidateSearch, setCandidateSearch] = useState("");
  const [linkTargets, setLinkTargets] = useState<Record<number, number | "new">>({});
  const [manualOpen, setManualOpen] = useState(false);
  const [manualPersonId, setManualPersonId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [manualForm] = Form.useForm<{ identifier_type: string; identifier_value: string }>();
  const [createForm] = Form.useForm<{ display_name: string; role_tag: string }>();

  const refreshPersons = useCallback(async (id: number) => {
    const data = await api.listCasePersons(id);
    setPersons(data.items);
  }, []);

  const refreshCandidates = useCallback(async (id: number) => {
    const data = await api.listCaseCandidates(id, "pending");
    setCandidates(data.items);
    setLinkTargets({});
  }, []);

  useEffect(() => {
    void refreshPersons(caseId).catch((err) => message.error((err as Error).message));
    void refreshCandidates(caseId).catch((err) => message.error((err as Error).message));
  }, [caseId, refreshCandidates, refreshPersons]);

  useEffect(() => {
    if (!initialAutoSetup) return;
    let active = true;
    void (async () => {
      try {
        message.loading({ content: "正在扫描并预关联人物标识…", key: "link-setup" });
        await api.discoverCaseIdentifiers(caseId);
        await api.autoLinkCase(caseId, true);
        if (!active) return;
        await refreshPersons(caseId);
        await refreshCandidates(caseId);
        message.success({ content: "已完成初始扫描与机器预关联，请核对下方结果", key: "link-setup" });
      } catch (err) {
        if (active) {
          message.error({ content: (err as Error).message, key: "link-setup" });
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [caseId, initialAutoSetup, refreshCandidates, refreshPersons]);

  const discover = async () => {
    try {
      const result = await api.discoverCaseIdentifiers(caseId);
      message.success(`扫描完成：新增 ${result.inserted} 条候选`);
      await refreshCandidates(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const autoLink = async () => {
    try {
      message.loading({ content: "机器预关联中…", key: "auto-link" });
      const result = await api.autoLinkCase(caseId, true);
      message.success({
        content: `预关联完成：新建 ${result.persons_created} 人，关联 ${result.links_created} 条标识，剩余待处理 ${result.unresolved_pending} 条`,
        key: "auto-link",
        duration: 6,
      });
      await refreshPersons(caseId);
      await refreshCandidates(caseId);
    } catch (err) {
      message.error({ content: (err as Error).message, key: "auto-link" });
    }
  };

  const linkCandidateToPerson = async (candidate: IdentifierCandidate, target: number | "new") => {
    try {
      if (target === "new") {
        await api.linkCaseCandidate(caseId, candidate.candidate_id, {
          display_name: candidate.display_value,
          role_tag: "unknown",
        });
      } else {
        await api.linkCaseCandidate(caseId, candidate.candidate_id, { person_id: target });
      }
      message.success("已关联");
      await refreshPersons(caseId);
      await refreshCandidates(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const markNoMatch = async (candidate: IdentifierCandidate) => {
    try {
      await api.markCaseCandidateNoMatch(caseId, candidate.candidate_id);
      message.success("已标记为无对应");
      await refreshCandidates(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const createPerson = async () => {
    const values = await createForm.validateFields();
    try {
      await api.createCasePerson(caseId, values);
      message.success("人物已创建");
      setCreateOpen(false);
      createForm.resetFields();
      await refreshPersons(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const addManualLink = async () => {
    if (!manualPersonId) return;
    const values = await manualForm.validateFields();
    try {
      await api.addPersonManualLink(caseId, manualPersonId, values);
      message.success("已添加标识");
      setManualOpen(false);
      manualForm.resetFields();
      await refreshPersons(caseId);
      await refreshCandidates(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const removeLink = async (personId: number, linkId: number) => {
    try {
      await api.removePersonLink(caseId, personId, linkId);
      message.success("已移除");
      await refreshPersons(caseId);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  const personOptions = useMemo(
    () => [
      ...persons.map((p) => ({ value: p.person_id, label: p.display_name })),
      { value: "new" as const, label: "+ 新建人物并关联" },
    ],
    [persons]
  );

  const filteredCandidates = useMemo(() => {
    return candidates.filter((c) => {
      if (typeFilter !== "all" && c.identifier_type !== typeFilter) return false;
      if (candidateSearch.trim()) {
        const q = candidateSearch.trim().toLowerCase();
        return c.display_value.toLowerCase().includes(q) || c.identifier_type.includes(q);
      }
      return true;
    });
  }, [candidates, typeFilter, candidateSearch]);

  const matrixColumns = useMemo(
    () => [
      {
        title: "姓名",
        key: "name",
        width: 120,
        fixed: "left" as const,
        render: (_: unknown, row: PersonInfo) => (
          <Space direction="vertical" size={0}>
            <Text strong>{row.display_name}</Text>
            <Tag className="link-role-tag">{ROLE_LABELS[row.role_tag] || row.role_tag}</Tag>
          </Space>
        ),
      },
      ...MATRIX_COLUMNS.map((col) => ({
        title: col.label,
        key: col.key,
        render: (_: unknown, row: PersonInfo) => (
          <IdentifierTags
            links={linksByTypes(row.links, col.types)}
            onRemove={(linkId) => void removeLink(row.person_id, linkId)}
          />
        ),
      })),
      {
        title: "操作",
        key: "actions",
        width: 88,
        fixed: "right" as const,
        render: (_: unknown, row: PersonInfo) => (
          <Button
            size="small"
            type="link"
            onClick={() => {
              setManualPersonId(row.person_id);
              setManualOpen(true);
            }}
          >
            添加
          </Button>
        ),
      },
    ],
    [caseId]
  );

  const candidateColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "identifier_type",
        width: 100,
        render: (v: string) => <Tag color="volcano">{IDENTIFIER_TYPE_LABELS[v] || v}</Tag>,
      },
      {
        title: "标识值",
        dataIndex: "display_value",
        ellipsis: true,
        render: (v: string) => <Text code className="link-candidate-value">{v}</Text>,
      },
      {
        title: "来源",
        width: 100,
        render: (_: unknown, row: IdentifierCandidate) => (
          <Tooltip title={`批次 ${row.source_batch_id}`}>
            <Tag>{row.source_type || "—"}</Tag>
          </Tooltip>
        ),
      },
      {
        title: "关联到人物",
        key: "link",
        width: 200,
        render: (_: unknown, row: IdentifierCandidate) => (
          <Select
            size="small"
            style={{ width: "100%" }}
            placeholder="选择姓名"
            allowClear
            showSearch
            optionFilterProp="label"
            value={linkTargets[row.candidate_id]}
            options={personOptions}
            onChange={(val) => setLinkTargets((prev) => ({ ...prev, [row.candidate_id]: val }))}
          />
        ),
      },
      {
        title: "操作",
        key: "actions",
        width: 160,
        render: (_: unknown, row: IdentifierCandidate) => {
          const target = linkTargets[row.candidate_id];
          return (
            <Space size={4}>
              <Button
                size="small"
                type="primary"
                disabled={target === undefined}
                onClick={() => target !== undefined && void linkCandidateToPerson(row, target)}
              >
                确认关联
              </Button>
              <Button size="small" danger type="link" onClick={() => void markNoMatch(row)}>
                无对应
              </Button>
            </Space>
          );
        },
      },
    ],
    [linkTargets, personOptions, caseId]
  );

  const stats = useMemo(() => {
    const linked = persons.reduce((sum, p) => sum + p.links.length, 0);
    return { personCount: persons.length, linkedCount: linked, pendingCount: candidates.length };
  }, [persons, candidates]);

  useEffect(() => {
    onStatsChange?.(stats);
  }, [onStatsChange, stats]);

  const canEnterCockpit = stats.personCount > 0 && stats.linkedCount > 0;

  return (
    <div className={`person-linking-panel${embedded ? " embedded" : ""}${wizardMode ? " wizard-mode" : ""}`}>
      <Card className={`app-card link-hero${embedded ? " link-hero-embedded" : ""}`} bordered={false}>
        <div className="link-hero-inner">
          <div>
            <Title level={4} style={{ margin: 0, color: "#fff" }}>
              人物标识关联
            </Title>
            <Paragraph style={{ margin: "6px 0 0", color: "rgba(255,255,255,0.85)", maxWidth: 720 }}>
              按「姓名 · 手机 · 微信 · 银行卡」建立一人多标识关联矩阵，从候选池选择归属人物后用于融合分析。
            </Paragraph>
          </div>
          <Space wrap className="link-hero-actions">
            <Button icon={<ScanOutlined />} onClick={() => void discover()}>
              扫描候选
            </Button>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => void autoLink()}>
              机器预关联
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建人物
            </Button>
          </Space>
        </div>
        <Row gutter={12} className="link-stats-row">
          {[
            { icon: <UserOutlined />, label: "已建人物", value: stats.personCount },
            { icon: <IdcardOutlined />, label: "已关联标识", value: stats.linkedCount },
            { icon: <MobileOutlined />, label: "待处理候选", value: stats.pendingCount },
          ].map((item) => (
            <Col xs={8} key={item.label}>
              <div className="link-stat-pill">
                <span className="link-stat-icon">{item.icon}</span>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {onEnterCockpit ? (
        <div className="link-enter-cockpit-bar">
          <div className="link-enter-cockpit-copy">
            <Text strong className="link-enter-cockpit-title">核对完成，进入融合分析</Text>
            <Text type="secondary" className="link-enter-cockpit-desc">
              已建 {stats.personCount} 人 · 已关联 {stats.linkedCount} 条标识
              {stats.pendingCount > 0 ? ` · 仍有 ${stats.pendingCount} 条待处理（可稍后在驾驶舱继续）` : ""}
            </Text>
          </div>
          <Button
            type="primary"
            size="large"
            className="link-enter-cockpit-btn"
            icon={<PartitionOutlined />}
            disabled={!canEnterCockpit}
            onClick={onEnterCockpit}
          >
            进入融合分析驾驶舱
          </Button>
        </div>
      ) : null}

      <Card className="app-card link-section" bordered={false} title="关联结果矩阵（一人可多卡号 / 多手机号 / 多微信号）">
        <Table
          rowKey="person_id"
          size="small"
          columns={matrixColumns}
          dataSource={persons}
          pagination={false}
          scroll={{ x: 960 }}
          locale={{ emptyText: "暂无人物，请先新建人物或从下方候选池关联" }}
        />
      </Card>

      <Card
        className="app-card link-section"
        bordered={false}
        title={
          <Space>
            <span>待关联候选池</span>
            <Tag color="orange">{filteredCandidates.length}</Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索标识值"
              style={{ width: 180 }}
              value={candidateSearch}
              onChange={(e) => setCandidateSearch(e.target.value)}
            />
            <Segmented
              size="small"
              value={typeFilter}
              onChange={(v) => setTypeFilter(String(v))}
              options={TYPE_FILTER_OPTIONS}
            />
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          每一行选择要关联的<strong>姓名</strong>，点击「确认关联」；一人可绑定多个手机号、微信号、银行卡号。无需对应时选「无对应」。
        </Paragraph>
        <Table
          rowKey="candidate_id"
          size="small"
          columns={candidateColumns}
          dataSource={filteredCandidates}
          pagination={{ pageSize: 12, showSizeChanger: true, pageSizeOptions: ["12", "24", "48"] }}
          scroll={{ x: 860 }}
          locale={{ emptyText: "暂无待处理候选，请先扫描或执行机器预关联" }}
        />
      </Card>

      <Modal title="新建人物" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => void createPerson()}>
        <Form form={createForm} layout="vertical" initialValues={{ role_tag: "unknown" }}>
          <Form.Item name="display_name" label="姓名" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input prefix={<UserOutlined />} placeholder="如：张伟" />
          </Form.Item>
          <Form.Item name="role_tag" label="角色">
            <Select options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="手动添加标识"
        open={manualOpen}
        onCancel={() => {
          setManualOpen(false);
          setManualPersonId(null);
        }}
        onOk={() => void addManualLink()}
      >
        <Form form={manualForm} layout="vertical">
          <Form.Item label="关联人物">
            <Select
              value={manualPersonId ?? undefined}
              onChange={setManualPersonId}
              options={persons.map((p) => ({ value: p.person_id, label: p.display_name }))}
              placeholder="选择人物"
            />
          </Form.Item>
          <Form.Item name="identifier_type" label="类型" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "phone", label: "手机号" },
                { value: "wechat_name", label: "微信号" },
                { value: "bank_card", label: "银行卡号" },
                { value: "bank_acct", label: "银行账号" },
                { value: "id_no", label: "身份证" },
                { value: "person_name", label: "姓名/别名" },
                { value: "enterprise_name", label: "企业名称" },
              ]}
            />
          </Form.Item>
          <Form.Item name="identifier_value" label="值" rules={[{ required: true }]}>
            <Input
              prefix={
                manualForm.getFieldValue("identifier_type") === "wechat_name" ? (
                  <WechatOutlined />
                ) : manualForm.getFieldValue("identifier_type")?.includes("bank") ? (
                  <BankOutlined />
                ) : (
                  <MobileOutlined />
                )
              }
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default PersonLinkingPanel;
