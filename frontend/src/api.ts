export interface BatchInfo {
  import_batch_id: string;
  source_type: string;
  file_count: number;
  imported_at: string;
  batch_name?: string;
}

export function batchLabel(batch: Pick<BatchInfo, "import_batch_id" | "batch_name">): string {
  const name = batch.batch_name?.trim();
  if (name) return name;
  return `${batch.import_batch_id.slice(0, 8)}…`;
}

export interface TablePreview {
  table_name: string;
  columns: string[];
  rowids: number[];
  rows: unknown[][];
  total_rows: number;
}

export interface BankFilter {
  bank_type?: string;
  person_name?: string;
  acct_no?: string;
  counterparty_name?: string;
  counterparty_account?: string;
  amount_min?: number | null;
  amount_max?: number | null;
  start_time?: string;
  end_time?: string;
  day_time_start?: string;
  day_time_end?: string;
}

export interface BankRecordsResponse {
  records: Array<Record<string, string>>;
  summary: Record<string, unknown>;
  description: string;
}

export interface ModuleParams {
  large_amount_threshold?: number;
  top_n?: number;
  repeat_amount_min_count?: number;
  special_amount_whitelist?: number[];
}

export interface CommercialAnalysisFilter {
  company_name?: string;
  purchaser?: string;
  inquiry_no?: string;
  winner?: string;
  amount_min?: number | null;
  amount_max?: number | null;
  only_winners?: boolean;
}

export interface CommercialAnalysisRecord {
  source: string;
  inquiry_no: string;
  purchaser: string;
  company_name: string;
  winner: string;
  is_winner: boolean;
  win_amount: number;
  item_name: string;
  quote_price: string;
  quantity: string;
  remark: string;
}

export interface CommercialAnalysisResponse {
  records: CommercialAnalysisRecord[];
  summary: {
    record_count: number;
    inquiry_count: number;
    company_count: number;
    winner_company_count: number;
    total_win_amount: number;
    company_summary: Array<Record<string, unknown>>;
    purchaser_summary: Array<Record<string, unknown>>;
    fund_links: Array<Record<string, unknown>>;
    top_company_amounts: Array<[string, number]>;
    top_purchaser_amounts: Array<[string, number]>;
  };
  description: string;
}

export interface WechatAnalysisFilter {
  user_name?: string;
  debit_credit_type?: string;
  counterparty_name?: string;
  business_type?: string;
  purpose_type?: string;
  amount_min?: number | null;
  amount_max?: number | null;
  start_time?: string;
  end_time?: string;
  day_time_start?: string;
  day_time_end?: string;
  remark?: string;
  income_types?: string[];
  expense_types?: string[];
}

export interface WechatAnalysisRecord {
  source: string;
  user_id: string;
  txn_no: string;
  user_name: string;
  debit_credit_type: string;
  business_type: string;
  purpose_type: string;
  txn_time: string;
  amount_yuan: number;
  balance_yuan: number;
  counterparty_name: string;
  counterparty_bank_name: string;
  remark1: string;
  remark2: string;
}

export interface WechatAnalysisResponse {
  records: WechatAnalysisRecord[];
  summary: {
    record_count: number;
    in_total: number;
    out_total: number;
    net_total: number;
    type_counts: Record<string, number>;
    top_counterparties: Array<[string, number]>;
    top_purpose_types: Array<[string, number]>;
    top_business_types: Array<[string, number]>;
    income_types: string[];
    expense_types: string[];
  };
  description: string;
}

export interface TelecomAnalysisFilter {
  local_phone?: string;
  peer_phone?: string;
  call_type?: string;
  bill_type?: string;
  direction?: string;
  local_carrier?: string;
  peer_carrier?: string;
  peer_location?: string;
  local_location?: string;
  duration_min?: number | null;
  duration_max?: number | null;
  start_time?: string;
  end_time?: string;
  day_time_start?: string;
  day_time_end?: string;
}

export interface TelecomPeerRanking {
  local_phone: string;
  peer_phone: string;
  call_count: number;
  total_duration_sec: number;
  outbound_count: number;
  inbound_count: number;
  first_call_time: string;
  last_call_time: string;
}

export interface TelecomAnalysisRecord {
  source: string;
  record_id: string;
  call_type: string;
  bill_type: string;
  direction: string;
  local_phone_display: string;
  peer_phone_display: string;
  local_carrier: string;
  peer_carrier: string;
  local_location: string;
  peer_location: string;
  call_time: string;
  duration_sec: number;
  group_name: string;
  group_no: string;
}

export interface TelecomAnalysisResponse {
  records: TelecomAnalysisRecord[];
  summary: {
    record_count: number;
    total_duration_sec: number;
    total_duration_min: number;
    direction_counts: Record<string, number>;
    call_type_counts: Record<string, number>;
    peer_location_counts: Record<string, number>;
    peer_carrier_counts: Record<string, number>;
    hourly_distribution: Array<{ hour: number; count: number }>;
    daily_distribution: Array<{ date: string; count: number }>;
    peer_ranking: TelecomPeerRanking[];
    top_peer_locations: Array<[string, number]>;
    top_peer_carriers: Array<[string, number]>;
  };
  description: string;
}

export interface RiskEvent {
  event_id: number;
  rule_code: string;
  rule_name: string;
  risk_level: string;
  risk_score: number;
  enterprise_name: string;
  inquiry_no: string;
  evidence_json: string;
  created_at: string;
}

export interface RiskSummary {
  summary_id: number;
  enterprise_name: string;
  total_score: number;
  hit_count: number;
  risk_level: string;
  detail_json: string;
  created_at: string;
}

export interface TaskStatus {
  task_id: string;
  task_type: string;
  status: "pending" | "running" | "succeeded" | "failed";
  progress: number;
  message: string;
  result: Record<string, unknown>;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface BankOcrRow {
  row_id?: number;
  page_index: number;
  row_index: number;
  cells: Record<string, string>;
  confidence: Record<string, number>;
  is_edited?: boolean;
}

export interface BankOcrJob {
  job_id: string;
  status: string;
  bank_name: string;
  batch_name: string;
  layout_profile_id: string;
  table_columns: string[];
  header_fields: string[];
  page_count: number;
  header: Record<string, string>;
  error_message: string;
  created_at: string;
  updated_at: string;
  commit_mode?: "raw";
  pages: Array<{
    page_id: number;
    page_index: number;
    ocr_status: string;
    width: number;
    height: number;
  }>;
  rows: BankOcrRow[];
}

export interface BankOcrProfile {
  profile_id: string;
  bank_display_name: string;
  table_columns: string[];
  header_fields: string[];
}

export interface HealthInfo {
  status: string;
  version: string;
  db_path: string;
  exports_dir: string;
}

export interface QichachaQueryResult {
  run_id: string;
  rows: Record<string, unknown>[];
  count: number;
}

export interface QichachaIngestResult {
  import_batch_id: string;
  source_type: string;
  files_total: number;
  rows_total: number;
  failed_files: number;
  run_id?: string;
}

export interface EntityMatchRow {
  match_id: number;
  inquiry_no: string;
  biz_company_name: string;
  biz_company_name_norm: string;
  enterprise_id: number;
  enterprise_name: string;
  match_score: number;
  match_method: string;
  credit_code: string;
  legal_person: string;
  enterprise_import_batch_id: string;
}

export interface RiskRuleItem {
  rule_code: string;
  rule_name: string;
  enabled: number;
  weight: number;
  params: Record<string, unknown>;
  version: number;
}

export interface QichachaLogItem {
  log_id: number;
  run_id: string;
  created_at: string;
  query_keyword: string;
  input_source: string;
  api_status: string | null;
  api_message: string | null;
  order_number: string | null;
  matched_name: string | null;
  credit_code: string | null;
  duration_ms: number | null;
  error_detail: string | null;
}

export type BankTemplateType = "account_profile" | "txn_detail";

export interface UserBankTemplate {
  id?: number;
  template_id?: string;
  display_name: string;
  template_type: BankTemplateType;
  bank_display_name: string;
  bank_keywords: string[];
  sheet_keywords: string[];
  field_map: Record<string, string[]>;
  signature_columns: string[];
  header_row_0based?: number | null;
  match_priority: number;
  template_group_id?: string | null;
  direction_rules: Record<string, string>;
  datetime_patterns?: Record<string, unknown> | null;
  is_active?: number;
  created_at?: string;
  updated_at?: string;
}

export interface BankTemplateAnalyzeResult {
  file_name: string;
  sheet_name: string;
  template_type: BankTemplateType;
  header_row_selected_0based: number;
  header_row_candidates: Array<{ row_0based: number; score: number }>;
  source_headers: string[];
  suggested_mapping: Record<string, string>;
  direction_distinct_values: string[];
  datetime_analysis: { merged_preview?: string[] };
  sample_row_count: number;
  preview_columns: string[];
  preview_grid: string[][];
  input_kind?: "excel" | "ocr";
  ocr_page_meta?: Record<string, string>;
}

export interface CaseInfo {
  case_id: number;
  case_name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  batch_count: number;
  batches?: CaseBatchInfo[];
}

export interface CaseBatchInfo {
  import_batch_id: string;
  source_type: string;
  bound_at: string;
}

export interface PersonLink {
  link_id: number;
  identifier_type: string;
  identifier_value: string;
  identifier_norm: string;
  source_type: string;
  source_ref: Record<string, unknown>;
  created_at: string;
}

export interface PersonInfo {
  person_id: number;
  case_id: number;
  display_name: string;
  role_tag: string;
  notes: string;
  created_at: string;
  updated_at: string;
  links: PersonLink[];
}

export interface IdentifierCandidate {
  candidate_id: number;
  identifier_type: string;
  identifier_norm: string;
  display_value: string;
  source_type: string;
  source_batch_id: string;
  source_ref: Record<string, unknown>;
  review_status: string;
  created_at: string;
}

export interface FusionRecord {
  record_type: string;
  title: string;
  time: string | null;
  amount: number | null;
  counterparty: string;
  summary: string;
  source_ref: Record<string, unknown>;
  direction?: string;
  batch_id?: string;
  role_hint?: string;
}

export interface PersonCockpitResponse {
  profile: Record<string, unknown>;
  kpis: Record<string, number>;
  charts: Record<string, unknown>;
  records_by_type: Record<string, FusionRecord[]>;
  summary_text: string;
}

export interface RelationCockpitResponse {
  person_a: { person_id: number; display_name: string };
  person_b: { person_id: number; display_name: string };
  direct_records: FusionRecord[];
  indirect_relations: Array<{ relation_type: string; title: string; detail: string }>;
  charts: Record<string, unknown>;
  summary_text: string;
}

export interface AnchorCockpitResponse {
  anchor: { type: string; value: string; norm: string; label: string };
  linked_persons: Array<{ person_id: number; display_name: string; role_tag: string }>;
  enterprise_roles?: {
    enterprise_name: string;
    legal_person: string;
    shareholders: string[];
    key_persons: string[];
  } | null;
  commercial_roles?: {
    purchaser_count: number;
    winner_count: number;
    bid_company_count: number;
  } | null;
  kpis: Record<string, number>;
  charts: Record<string, unknown>;
  records_by_type: Record<string, FusionRecord[]>;
  summary_text: string;
}

export interface AnchorSuggestItem {
  identifier_type: string;
  display_value: string;
  identifier_norm: string;
  person_id?: number | null;
  person_name?: string;
  source: string;
}

export interface RecordDetailResponse {
  layer: string;
  table: string;
  pk: Record<string, unknown>;
  fields: Record<string, unknown>;
  raw_payload: unknown;
}

export const CASE_STORAGE_KEY = "datafusionx.selectedCaseId";
export const CASE_CHANGED_EVENT = "datafusionx.caseChanged";

export function resolveSelectedCaseId(
  cases: Array<{ case_id: number }>,
  preferredId?: number | null
): number | null {
  const storedRaw = localStorage.getItem(CASE_STORAGE_KEY);
  const storedId = storedRaw ? Number(storedRaw) : null;
  const candidate = preferredId ?? storedId;
  if (candidate && cases.some((item) => item.case_id === candidate)) return candidate;
  return cases[0]?.case_id ?? null;
}

export function persistSelectedCaseId(caseId: number | null) {
  if (caseId != null) {
    localStorage.setItem(CASE_STORAGE_KEY, String(caseId));
  } else {
    localStorage.removeItem(CASE_STORAGE_KEY);
  }
}

export function emitCaseChanged(caseId: number | null) {
  window.dispatchEvent(new CustomEvent(CASE_CHANGED_EVENT, { detail: { caseId } }));
}

export const IDENTIFIER_TYPE_LABELS: Record<string, string> = {
  person_name: "姓名",
  phone: "手机号",
  wechat_name: "微信名",
  bank_card: "银行卡号",
  bank_acct: "银行账号",
  id_no: "身份证号",
  enterprise_name: "企业名称",
};

const API_BASE = (() => {
  const fromGlobal = (window as unknown as { DATAFUSIONX_API_BASE?: string }).DATAFUSIONX_API_BASE;
  if (fromGlobal) return fromGlobal.replace(/\/$/, "");
  if (typeof import.meta !== "undefined" && (import.meta as ImportMeta).env?.VITE_API_BASE) {
    return ((import.meta as ImportMeta).env.VITE_API_BASE as string).replace(/\/$/, "");
  }
  return "";
})();

async function http<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = (data?.detail as string) || JSON.stringify(data);
    } catch (err) {
      // keep default detail
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => http<HealthInfo>("/api/health"),

  listBatches: (sourceType?: string) =>
    http<{ items: BatchInfo[] }>(
      `/api/batches${sourceType ? `?source_type=${encodeURIComponent(sourceType)}` : ""}`
    ),

  deleteBatch: (batchId: string) =>
    http<{ status: string; import_batch_id: string; source_type: string }>(
      `/api/batches/${encodeURIComponent(batchId)}`,
      { method: "DELETE" }
    ),

  renameBatch: (batchId: string, batchName: string) =>
    http<BatchInfo>(`/api/batches/${encodeURIComponent(batchId)}`, {
      method: "PATCH",
      body: JSON.stringify({ batch_name: batchName }),
    }),

  importByPaths: (
    sourceType: "bank" | "commercial" | "enterprise" | "wechat" | "telecom",
    filePaths: string[],
    bankName: string,
    batchName?: string
  ) =>
    http<{ task_id: string }>(`/api/import/${sourceType}`, {
      method: "POST",
      body: JSON.stringify({
        file_paths: filePaths,
        bank_name: bankName,
        batch_name: batchName?.trim() || undefined,
      }),
    }),

  uploadFiles: async (
    sourceType: "bank" | "commercial" | "enterprise" | "wechat" | "telecom",
    files: File[],
    bankName: string,
    batchName?: string
  ) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    if (batchName?.trim()) {
      form.append("batch_name", batchName.trim());
    }
    const url = `${API_BASE}/api/upload/${sourceType}?bank_name=${encodeURIComponent(bankName)}`;
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${text}`);
    }
    return (await res.json()) as { task_id: string };
  },

  uploadBankOcr: async (
    files: File[],
    bankName: string,
    batchName?: string,
    layoutProfileId = "ceb_txn_v1"
  ) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    if (batchName?.trim()) {
      form.append("batch_name", batchName.trim());
    }
    form.append("layout_profile_id", layoutProfileId);
    form.append("bank_name", bankName);
    const res = await fetch(`${API_BASE}/api/bank-ocr/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${text}`);
    }
    return (await res.json()) as { task_id: string };
  },

  listBankOcrJobs: (status?: string) =>
    http<{ items: BankOcrJob[] }>(`/api/bank-ocr/jobs${status ? `?status=${encodeURIComponent(status)}` : ""}`),

  getBankOcrJob: (jobId: string) => http<BankOcrJob>(`/api/bank-ocr/jobs/${encodeURIComponent(jobId)}`),

  bankOcrPageImageUrl: (jobId: string, pageIndex: number) =>
    `${API_BASE}/api/bank-ocr/jobs/${encodeURIComponent(jobId)}/pages/${pageIndex}/image`,

  saveBankOcrRows: (jobId: string, rows: BankOcrRow[]) =>
    http<BankOcrJob>(`/api/bank-ocr/jobs/${encodeURIComponent(jobId)}/rows`, {
      method: "PUT",
      body: JSON.stringify({ rows }),
    }),

  saveBankOcrHeader: (jobId: string, header: Record<string, string>) =>
    http<BankOcrJob>(`/api/bank-ocr/jobs/${encodeURIComponent(jobId)}/header`, {
      method: "PUT",
      body: JSON.stringify({ header }),
    }),

  commitBankOcrJob: (jobId: string) =>
    http<{ task_id: string }>(`/api/bank-ocr/jobs/${encodeURIComponent(jobId)}/commit`, { method: "POST" }),

  deleteBankOcrJob: (jobId: string) =>
    http<{ job_id: string; deleted: boolean }>(`/api/bank-ocr/jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
    }),

  listBankOcrProfiles: () =>
    http<{ items: BankOcrProfile[]; supported_formats?: string[]; format_hint?: string }>(
      "/api/bank-ocr/profiles"
    ),

  desensitizeByPaths: (filePaths: string[]) =>
    http<{ task_id: string }>("/api/desensitize", {
      method: "POST",
      body: JSON.stringify({ file_paths: filePaths }),
    }),

  uploadDesensitizationFiles: async (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const res = await fetch(`${API_BASE}/api/desensitize/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${text}`);
    }
    return (await res.json()) as { task_id: string };
  },

  task: (taskId: string) => http<TaskStatus>(`/api/tasks/${taskId}`),

  listTables: () => http<{ items: string[] }>("/api/tables"),

  previewTable: (table: string, limit = 200, offset = 0) =>
    http<TablePreview>(
      `/api/tables/${encodeURIComponent(table)}/preview?limit=${limit}&offset=${offset}`
    ),

  deleteRows: (table: string, rowids: number[]) =>
    http<{ deleted: number }>(`/api/tables/${encodeURIComponent(table)}/rows`, {
      method: "DELETE",
      body: JSON.stringify({ rowids }),
    }),

  dropTable: (table: string) =>
    http<{ status: string }>(`/api/tables/${encodeURIComponent(table)}`, { method: "DELETE" }),

  bankFilterOptions: (batchId: string) =>
    http<Record<string, string[]>>(`/api/bank/${encodeURIComponent(batchId)}/filter-options`),

  bankRecords: (batchId: string, filters: BankFilter) =>
    http<BankRecordsResponse>(`/api/bank/${encodeURIComponent(batchId)}/records`, {
      method: "POST",
      body: JSON.stringify(filters),
    }),

  bankModule: (batchId: string, moduleId: string, params: ModuleParams) =>
    http<Record<string, unknown>>(
      `/api/bank/${encodeURIComponent(batchId)}/modules/${encodeURIComponent(moduleId)}`,
      { method: "POST", body: JSON.stringify(params) }
    ),

  commercialAnalysisFilterOptions: (batchId: string) =>
    http<Record<string, string[]>>(`/api/commercial/${encodeURIComponent(batchId)}/analysis/filter-options`),

  commercialAnalysisRecords: (batchId: string, filters: CommercialAnalysisFilter) =>
    http<CommercialAnalysisResponse>(`/api/commercial/${encodeURIComponent(batchId)}/analysis/records`, {
      method: "POST",
      body: JSON.stringify(filters),
    }),

  wechatAnalysisFilterOptions: (batchId: string) =>
    http<Record<string, string[]>>(`/api/wechat/${encodeURIComponent(batchId)}/analysis/filter-options`),

  wechatAnalysisRecords: (batchId: string, filters: WechatAnalysisFilter) =>
    http<WechatAnalysisResponse>(`/api/wechat/${encodeURIComponent(batchId)}/analysis/records`, {
      method: "POST",
      body: JSON.stringify(filters),
    }),

  telecomAnalysisFilterOptions: (batchId: string) =>
    http<Record<string, string[]>>(`/api/telecom/${encodeURIComponent(batchId)}/analysis/filter-options`),

  telecomAnalysisRecords: (batchId: string, filters: TelecomAnalysisFilter) =>
    http<TelecomAnalysisResponse>(`/api/telecom/${encodeURIComponent(batchId)}/analysis/records`, {
      method: "POST",
      body: JSON.stringify(filters),
    }),

  runRisk: (batchId: string, enterpriseBatchId?: string) =>
    http<{ task_id: string }>(`/api/commercial/${encodeURIComponent(batchId)}/risk/run`, {
      method: "POST",
      body: JSON.stringify({ enterprise_batch_id: enterpriseBatchId || null }),
    }),

  riskEvents: (batchId: string, limit = 500) =>
    http<{ items: RiskEvent[] }>(
      `/api/commercial/${encodeURIComponent(batchId)}/risk/events?limit=${limit}`
    ),

  riskSummary: (batchId: string, limit = 500) =>
    http<{ items: RiskSummary[] }>(
      `/api/commercial/${encodeURIComponent(batchId)}/risk/summary?limit=${limit}`
    ),

  exportBatch: (sourceType: "bank" | "commercial" | "wechat" | "telecom", batchId: string, outputPath?: string) =>
    http<{ task_id: string }>(`/api/export/${sourceType}/${encodeURIComponent(batchId)}`, {
      method: "POST",
      body: JSON.stringify({ output_path: outputPath || null }),
    }),

  exportRiskReport: (batchId: string, outputPath?: string) =>
    http<{ task_id: string }>(`/api/export/commercial-risk/${encodeURIComponent(batchId)}`, {
      method: "POST",
      body: JSON.stringify({ output_path: outputPath || null }),
    }),

  exportCommercialAnalysisReport: (batchId: string, outputPath?: string) =>
    http<{ task_id: string }>(`/api/export/commercial-analysis/${encodeURIComponent(batchId)}`, {
      method: "POST",
      body: JSON.stringify({ output_path: outputPath || null }),
    }),

  qichachaQueryLogs: (limit = 100, offset = 0, runId?: string) =>
    http<{ items: QichachaLogItem[] }>(
      `/api/qichacha/query-logs?limit=${limit}&offset=${offset}${
        runId ? `&run_id=${encodeURIComponent(runId)}` : ""
      }`
    ),

  ingestQichachaProfile: (rows: Record<string, unknown>[], runId?: string | null) =>
    http<QichachaIngestResult>("/api/qichacha/ingest-profile", {
      method: "POST",
      body: JSON.stringify({ rows, run_id: runId || null }),
    }),

  entityMatches: (batchId: string, enterpriseBatchId?: string, limit = 2000) =>
    http<{ items: EntityMatchRow[] }>(
      `/api/commercial/${encodeURIComponent(batchId)}/entity-matches?limit=${limit}${
        enterpriseBatchId ? `&enterprise_batch_id=${encodeURIComponent(enterpriseBatchId)}` : ""
      }`
    ),

  listRiskRules: () => http<{ items: RiskRuleItem[] }>("/api/commercial/risk-rules"),

  patchRiskRule: (
    ruleCode: string,
    body: { params?: Record<string, unknown>; weight?: number; enabled?: number }
  ) =>
    http<RiskRuleItem & { params: Record<string, unknown> }>(
      `/api/commercial/risk-rules/${encodeURIComponent(ruleCode)}`,
      { method: "PATCH", body: JSON.stringify(body) }
    ),

  listBankTemplates: () => http<{ items: UserBankTemplate[] }>("/api/bank-templates"),

  createBankTemplate: (body: UserBankTemplate) =>
    http<UserBankTemplate>("/api/bank-templates", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteBankTemplate: (templateId: string) =>
    http<{ status: string; template_id: string }>(`/api/bank-templates/${encodeURIComponent(templateId)}`, {
      method: "DELETE",
    }),

  clearBankTemplateMappings: (templateFingerprint: string) =>
    http<{ status: string; template_fingerprint: string }>("/api/bank-templates/fingerprint-mappings/clear", {
      method: "POST",
      body: JSON.stringify({ template_fingerprint: templateFingerprint }),
    }),

  listCases: () => http<{ items: CaseInfo[] }>("/api/cases"),

  createCase: (body: { case_name: string; description?: string; status?: string }) =>
    http<CaseInfo>("/api/cases", { method: "POST", body: JSON.stringify(body) }),

  getCase: (caseId: number) => http<CaseInfo>(`/api/cases/${caseId}`),

  updateCase: (caseId: number, body: { case_name?: string; description?: string; status?: string }) =>
    http<CaseInfo>(`/api/cases/${caseId}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteCase: (caseId: number) =>
    http<{ status: string; case_id: string }>(`/api/cases/${caseId}`, { method: "DELETE" }),

  listUnboundBatches: () => http<{ items: BatchInfo[] }>("/api/cases/unbound-batches"),

  batchCaseMap: () => http<{ items: Record<string, { case_id: number; case_name: string }> }>("/api/cases/batch-map"),

  bindCaseBatches: (caseId: number, importBatchIds: string[]) =>
    http<{ items: CaseBatchInfo[] }>(`/api/cases/${caseId}/batches`, {
      method: "POST",
      body: JSON.stringify({ import_batch_ids: importBatchIds }),
    }),

  unbindCaseBatch: (caseId: number, batchId: string) =>
    http<{ status: string; import_batch_id: string }>(
      `/api/cases/${caseId}/batches/${encodeURIComponent(batchId)}`,
      { method: "DELETE" }
    ),

  discoverCaseIdentifiers: (caseId: number) =>
    http<{ case_id: number; inserted: number; skipped: number }>(`/api/cases/${caseId}/discover`, {
      method: "POST",
    }),

  autoLinkCase: (caseId: number, rediscover = true) =>
    http<{
      case_id: number;
      persons_created: number;
      links_created: number;
      skipped: number;
      unresolved_pending: number;
      person_names: string[];
    }>(`/api/cases/${caseId}/auto-link?rediscover=${rediscover ? "true" : "false"}`, {
      method: "POST",
    }),

  listCasePersons: (caseId: number) => http<{ items: PersonInfo[] }>(`/api/cases/${caseId}/persons`),

  createCasePerson: (caseId: number, body: { display_name: string; role_tag?: string; notes?: string }) =>
    http<PersonInfo>(`/api/cases/${caseId}/persons`, { method: "POST", body: JSON.stringify(body) }),

  updateCasePerson: (
    caseId: number,
    personId: number,
    body: { display_name?: string; role_tag?: string; notes?: string }
  ) =>
    http<PersonInfo>(`/api/cases/${caseId}/persons/${personId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteCasePerson: (caseId: number, personId: number) =>
    http<{ status: string; person_id: string }>(`/api/cases/${caseId}/persons/${personId}`, {
      method: "DELETE",
    }),

  listCaseCandidates: (caseId: number, reviewStatus = "pending") =>
    http<{ items: IdentifierCandidate[] }>(
      `/api/cases/${caseId}/candidates?review_status=${encodeURIComponent(reviewStatus)}`
    ),

  linkCaseCandidate: (
    caseId: number,
    candidateId: number,
    body: { person_id?: number; display_name?: string; role_tag?: string }
  ) =>
    http<PersonInfo>(`/api/cases/${caseId}/candidates/${candidateId}/link`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  markCaseCandidateNoMatch: (caseId: number, candidateId: number) =>
    http<{ status: string; candidate_id: string }>(
      `/api/cases/${caseId}/candidates/${candidateId}/no-match`,
      { method: "POST" }
    ),

  addPersonManualLink: (
    caseId: number,
    personId: number,
    body: { identifier_type: string; identifier_value: string }
  ) =>
    http<PersonInfo>(`/api/cases/${caseId}/persons/${personId}/links`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  removePersonLink: (caseId: number, personId: number, linkId: number) =>
    http<{ status: string; link_id: string }>(
      `/api/cases/${caseId}/persons/${personId}/links/${linkId}`,
      { method: "DELETE" }
    ),

  personCockpit: (caseId: number, personId: number) =>
    http<PersonCockpitResponse>(`/api/cases/${caseId}/cockpit/person/${personId}`),

  relationCockpit: (caseId: number, personA: number, personB: number) =>
    http<RelationCockpitResponse>(
      `/api/cases/${caseId}/cockpit/relation?person_a=${personA}&person_b=${personB}`
    ),

  anchorCockpit: (caseId: number, value: string, type = "auto") =>
    http<AnchorCockpitResponse>(
      `/api/cases/${caseId}/cockpit/anchor?${new URLSearchParams({ value, type }).toString()}`
    ),

  suggestAnchors: (caseId: number, q: string, limit = 20, type = "auto") =>
    http<{ items: AnchorSuggestItem[] }>(
      `/api/cases/${caseId}/cockpit/suggest?${new URLSearchParams({
        q,
        type,
        limit: String(limit),
      }).toString()}`
    ),

  recordDetail: (caseId: number, sourceRef: Record<string, unknown>) =>
    http<RecordDetailResponse>(
      `/api/cases/${caseId}/records/detail?ref=${encodeURIComponent(JSON.stringify(sourceRef))}`
    ),
};

export async function analyzeBankTemplateSample(params: {
  file: File;
  sheetName: string;
  templateType: BankTemplateType;
  bankNameHint?: string;
  headerRow0based?: number | null;
}): Promise<BankTemplateAnalyzeResult> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("sheet_name", params.sheetName);
  form.append("template_type", params.templateType);
  form.append("bank_name_hint", params.bankNameHint || "银行数据");
  if (params.headerRow0based !== null && params.headerRow0based !== undefined) {
    form.append("header_row_0based", String(params.headerRow0based));
  }
  const res = await fetch(`${API_BASE}/api/bank-templates/analyze-sample`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data?.detail || JSON.stringify(data);
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as BankTemplateAnalyzeResult;
}

export async function analyzeBankTemplateOcrSample(params: {
  file: File;
  templateType: BankTemplateType;
  bankNameHint?: string;
  layoutProfileId?: string;
}): Promise<BankTemplateAnalyzeResult> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("template_type", params.templateType);
  form.append("bank_name_hint", params.bankNameHint || "银行数据");
  if (params.layoutProfileId) {
    form.append("layout_profile_id", params.layoutProfileId);
  }
  const res = await fetch(`${API_BASE}/api/bank-templates/analyze-ocr-sample`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data?.detail || JSON.stringify(data);
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as BankTemplateAnalyzeResult;
}

export async function listBankTemplateSampleSheets(file: File): Promise<string[]> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/bank-templates/analyze-sample/sheets`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data?.detail || JSON.stringify(data);
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  const data = (await res.json()) as { sheets?: string[] };
  return data.sheets || [];
}

export async function queryQichachaBasicDetails(params: {
  keywordsText?: string;
  file?: File | null;
  columnIndex?: number;
  columnLetter?: string;
  skipHeader?: boolean;
}): Promise<QichachaQueryResult> {
  const form = new FormData();
  if (params.keywordsText?.trim()) {
    form.append("keywords", params.keywordsText.trim());
  }
  if (params.file) {
    form.append("file", params.file);
  }
  form.append("column_index", String(params.columnIndex ?? 0));
  if (params.columnLetter?.trim()) {
    form.append("column_letter", params.columnLetter.trim());
  }
  form.append("skip_header", params.skipHeader ? "1" : "0");
  const res = await fetch(`${API_BASE}/api/qichacha/basic-details/query`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data?.detail || JSON.stringify(data);
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as QichachaQueryResult;
}

export async function exportQichachaExcelFromRows(
  rows: Record<string, unknown>[],
  runId?: string | null
): Promise<{ blob: Blob; runId: string | null }> {
  const res = await fetch(`${API_BASE}/api/qichacha/basic-details/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, run_id: runId || null }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: string };
      detail = data?.detail || JSON.stringify(data);
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  const hdr = res.headers.get("X-Run-Id");
  const blob = await res.blob();
  return { blob, runId: hdr || runId || null };
}

export async function pollTask(taskId: string, onProgress?: (task: TaskStatus) => void): Promise<TaskStatus> {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const status = await api.task(taskId);
        onProgress?.(status);
        if (status.status === "succeeded") {
          resolve(status);
          return;
        }
        if (status.status === "failed") {
          reject(new Error(status.error_message || status.message));
          return;
        }
        setTimeout(tick, 800);
      } catch (err) {
        reject(err);
      }
    };
    void tick();
  });
}
