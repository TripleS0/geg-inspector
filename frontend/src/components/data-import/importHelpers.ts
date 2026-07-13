import { SOURCE_LABELS, SourceType } from "./constants";

export function buildReadableLogs(result: Record<string, unknown>): string[] {
  const sourceType = String(result.source_type || "");
  const importBatchId = String(result.import_batch_id || "");
  const batchName = String(result.batch_name || "");
  const filesTotal = Number(result.files_total || 0);
  const failedFiles = Number(result.failed_files || 0);
  const rowsTotal = Number(result.rows_total || 0);
  const sheetsTotal = Number(result.sheets_total || 0);
  const newTemplates = Number(result.new_templates || 0);
  const standardizedRows = Number(result.standardized_rows || 0);

  const sourceLabel = SOURCE_LABELS[sourceType as SourceType] || sourceType || "未知来源";
  const logs: string[] = [];
  logs.push(`来源类型：${sourceLabel}`);
  if (importBatchId) {
    logs.push(`导入批次：${batchName || importBatchId}`);
  }
  logs.push(`已处理文件：${filesTotal} 个`);
  logs.push(`失败文件：${failedFiles} 个`);
  if (sheetsTotal > 0) {
    logs.push(`识别工作表：${sheetsTotal} 个`);
  }
  if (rowsTotal > 0) {
    logs.push(`入库总行数：${rowsTotal} 行`);
  }
  if (sourceType === "commercial" && filesTotal > 1) {
    logs.push(`本批次已整合 ${filesTotal} 个文件，分析与导出按批次统一处理`);
  }
  if (sourceType === "commercial") {
    logs.push("提示：如需把文件追加到已有批次，请到「批次管理」选择目标批次后导入");
  }
  if (newTemplates > 0) {
    logs.push(`新增模板：${newTemplates} 个`);
  }
  if (standardizedRows > 0) {
    logs.push(`标准化写入：${standardizedRows} 行`);
  }
  logs.push(failedFiles === 0 ? "处理状态：全部成功" : "处理状态：部分文件失败，请检查文件格式和日志");
  return logs;
}
