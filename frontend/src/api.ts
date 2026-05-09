export interface BatchInfo {
  import_batch_id: string;
  source_type: string;
  file_count: number;
  imported_at: string;
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

  importByPaths: (sourceType: "bank" | "commercial" | "enterprise", filePaths: string[], bankName: string) =>
    http<{ task_id: string }>(`/api/import/${sourceType}`, {
      method: "POST",
      body: JSON.stringify({ file_paths: filePaths, bank_name: bankName }),
    }),

  uploadFiles: async (
    sourceType: "bank" | "commercial" | "enterprise",
    files: File[],
    bankName: string
  ) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const url = `${API_BASE}/api/upload/${sourceType}?bank_name=${encodeURIComponent(bankName)}`;
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${text}`);
    }
    return (await res.json()) as { task_id: string };
  },

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

  exportBatch: (sourceType: "bank" | "commercial", batchId: string, outputPath?: string) =>
    http<{ task_id: string }>(`/api/export/${sourceType}/${encodeURIComponent(batchId)}`, {
      method: "POST",
      body: JSON.stringify({ output_path: outputPath || null }),
    }),

  exportRiskReport: (batchId: string, outputPath?: string) =>
    http<{ task_id: string }>(`/api/export/commercial-risk/${encodeURIComponent(batchId)}`, {
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
};

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
