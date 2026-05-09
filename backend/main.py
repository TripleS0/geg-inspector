"""FastAPI backend for the offline desktop Web system."""

import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.application.analysis_use_cases import BankAnalysisUseCase, CommercialRiskUseCase
from app.application.risk_config_use_cases import RiskConfigUseCase
from app.application.bootstrap import bootstrap_database
from app.application.dataset_use_cases import DatasetUseCase
from app.application.export_use_cases import ExportUseCase
from app.application.import_use_cases import EnterpriseImportUseCase, ImportUseCase
from app.application.task_store import TaskStore
from app.runtime_paths import exports_dir, uploads_dir
from app.services.integration.bank.analysis_modules import ModuleParams
from app.services.integration.bank.query_service import BankQueryFilters
from app.services.shared.db.sqlite_client import SqliteClient
from app.services.desensitizer_service import collect_supported_files, process_single_file
from app.services.integration.qichacha_client import (
    column_letter_to_index,
    extract_log_fields,
    fetch_basic_details_by_name,
    normalize_keywords,
    parse_form_keywords_text,
    parse_names_from_excel,
    parse_names_from_txt,
    qichacha_credentials,
    qichacha_response_to_export_row,
    responses_to_excel_bytes,
)


class ImportRequest(BaseModel):
    """Import request using local file paths."""

    file_paths: List[str] = Field(default_factory=list)
    bank_name: str = "默认来源"


class RiskRunRequest(BaseModel):
    """Commercial risk analysis request."""

    enterprise_batch_id: Optional[str] = None


class ExportRequest(BaseModel):
    """Optional output path for exports."""

    output_path: Optional[str] = None


class DesensitizeRequest(BaseModel):
    """Desensitization request using local file or folder paths."""

    file_paths: List[str] = Field(default_factory=list)


class BankFilterRequest(BaseModel):
    """Bank filter payload."""

    bank_type: str = ""
    person_name: str = ""
    acct_no: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""

    def to_filters(self) -> BankQueryFilters:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:  # pragma: no cover - pydantic v1 fallback
            data = self.dict()
        return BankQueryFilters(**data)


class ModuleRequest(BaseModel):
    """Bank fixed-module request."""

    large_amount_threshold: float = 100_000.0
    top_n: int = 15
    repeat_amount_min_count: int = 3
    special_amount_whitelist: List[float] = Field(
        default_factory=lambda: [520.0, 521.0, 1314.0, 666.0, 888.0, 188.0, 288.0]
    )

    def to_params(self) -> ModuleParams:
        return ModuleParams(
            large_amount_threshold=self.large_amount_threshold,
            top_n=self.top_n,
            repeat_amount_min_count=self.repeat_amount_min_count,
            special_amount_whitelist=tuple(self.special_amount_whitelist),
        )


class DeleteRowsRequest(BaseModel):
    """Delete table rows by SQLite rowid."""

    rowids: List[int]


class QichachaExportRowsBody(BaseModel):
    """根据预览结果导出 Excel（不再调用企查查）。"""

    rows: List[Dict[str, Any]] = Field(default_factory=list)
    run_id: Optional[str] = None


class QichachaIngestProfileBody(BaseModel):
    """企查查预览行写入工商主体库。"""

    rows: List[Dict[str, Any]] = Field(default_factory=list)
    run_id: Optional[str] = None


class RiskRulePatchBody(BaseModel):
    """更新单条风险规则。"""

    params: Optional[Dict[str, Any]] = None
    weight: Optional[float] = None
    enabled: Optional[int] = None


def _ensure_r007_rule_row() -> None:
    """旧库可能无 R007，幂等补种。"""
    SqliteClient().execute(
        """
        INSERT OR IGNORE INTO cfg_risk_rule (rule_code, rule_name, enabled, weight, params_json, version)
        VALUES (
            'R007', '协同串标强化', 1, 1.2,
            '{"min_shared_inquiries":3,"min_jaccard":0.8,"min_inquiries_for_jaccard":3,"note":"围标或串标口径重叠且两企业工商法定代表人为同一人"}',
            1
        );
        """
    )


QICHACHA_503_DETAIL = (
    "未配置企查查密钥：请设置环境变量 QICHACHA_APP_KEY / QICHACHA_SECRET_KEY，"
    "或在以下任一 JSON 文件中填写 app_key 与 secret_key（格式见 "
    "app/resources/config/qichacha_config.example.json）："
    "data/qichacha_config.json、app/resources/config/qichacha_config.json、"
    "或临时使用 qichacha_config.example.json（勿将含密钥的示例文件提交 Git）。"
    "环境变量优先。修改后请重启后端。"
)


def _qichacha_skip_header(raw: str) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def require_qichacha_credentials() -> Tuple[str, str]:
    app_key, secret_key = qichacha_credentials()
    if not app_key or not secret_key:
        raise HTTPException(status_code=503, detail=QICHACHA_503_DETAIL)
    return app_key, secret_key


async def parse_qichacha_keywords_from_upload(
    *,
    keywords: Optional[str],
    file: Optional[UploadFile],
    column_index: int,
    column_letter: Optional[str],
    skip_header: str,
) -> Tuple[List[str], str]:
    try:
        manual_list = parse_form_keywords_text(keywords)
    except (ValueError, TypeError, json.JSONDecodeError) as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    file_kws: List[str] = []
    file_kind = "excel"
    tmp_path: Optional[Path] = None
    try:
        if file and (file.filename or "").strip():
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".xlsx", ".xls", ".txt"}:
                raise HTTPException(status_code=400, detail="仅支持上传 .xlsx、.xls 或 .txt")
            body = await file.read()
            if suffix == ".txt":
                file_kws = parse_names_from_txt(body)
                file_kind = "txt"
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(body)
                    tmp_path = Path(tmp.name)
                col_idx = int(column_index)
                if column_letter and str(column_letter).strip():
                    try:
                        col_idx = column_letter_to_index(str(column_letter))
                    except ValueError as err:
                        raise HTTPException(status_code=400, detail=str(err)) from err
                try:
                    file_kws = parse_names_from_excel(
                        tmp_path,
                        column_index=col_idx,
                        skip_header=_qichacha_skip_header(skip_header),
                    )
                except ValueError as err:
                    raise HTTPException(status_code=400, detail=str(err)) from err
    finally:
        if tmp_path is not None and tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)

    has_manual = bool(manual_list)
    has_file = bool(file_kws)
    if not has_manual and not has_file:
        raise HTTPException(status_code=400, detail="请手动输入企业名称或上传名称列表文件")
    if has_manual and has_file:
        input_source = "mixed"
    elif has_file:
        input_source = file_kind
    else:
        input_source = "manual"

    merged = normalize_keywords([*manual_list, *file_kws])
    if not merged:
        raise HTTPException(status_code=400, detail="未解析到任何企业名称")
    return merged, input_source


def execute_qichacha_keyword_queries(
    merged: List[str],
    input_source: str,
    app_key: str,
    secret_key: str,
) -> Tuple[str, List[Dict[str, Any]], List[Tuple[Any, ...]]]:
    run_id = str(uuid.uuid4())
    export_rows: List[Dict[str, Any]] = []
    log_rows: List[Tuple[Any, ...]] = []

    for kw in merged:
        t0 = time.perf_counter()
        err_detail: Optional[str] = None
        data: Optional[Dict[str, Any]] = None
        try:
            data = fetch_basic_details_by_name(kw, app_key=app_key, secret_key=secret_key)
        except Exception as ex:  # noqa: BLE001
            err_detail = str(ex)
            data = {"Status": "error", "Message": err_detail, "OrderNumber": None, "Result": None}

        duration_ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(data, dict):
            err_detail = err_detail or "接口返回非 JSON 对象"
            data = {"Status": "error", "Message": err_detail, "OrderNumber": None, "Result": None}

        export_rows.append(qichacha_response_to_export_row(kw, data))
        api_status, api_message, order_number, matched_name, credit_code = extract_log_fields(
            kw,
            data,
            duration_ms=duration_ms,
            error_detail=err_detail,
        )
        log_rows.append(
            (
                run_id,
                kw,
                input_source,
                api_status,
                api_message,
                order_number,
                matched_name,
                credit_code,
                duration_ms,
                err_detail,
            )
        )

    return run_id, export_rows, log_rows


def persist_qichacha_query_logs(log_rows: List[Tuple[Any, ...]]) -> None:
    if not log_rows:
        return
    db = SqliteClient()
    db.executemany(
        """
        INSERT INTO meta_qichacha_query_log (
            run_id, query_keyword, input_source, api_status, api_message,
            order_number, matched_name, credit_code, duration_ms, error_detail
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        log_rows,
    )


def create_app() -> FastAPI:
    """Create the local FastAPI app."""
    bootstrap_database()
    _ensure_r007_rule_row()
    app = FastAPI(title="DataFusionX Offline Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1",
            "http://localhost",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Run-Id"],
    )

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        client = SqliteClient()
        return {
            "status": "ok",
            "version": app.version,
            "db_path": str(client.db_path),
            "exports_dir": str(exports_dir()),
        }

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> Dict[str, Any]:
        try:
            return TaskStore().get(task_id)
        except KeyError as err:
            raise HTTPException(status_code=404, detail="任务不存在") from err

    def enqueue(background_tasks: BackgroundTasks, task_type: str, func: Callable[[], Dict[str, Any]]) -> Dict[str, str]:
        store = TaskStore()
        task_id = store.create(task_type)

        def runner() -> None:
            task_store = TaskStore()
            try:
                task_store.update(task_id, status="running", progress=10, message="任务执行中")
                result = func()
                task_store.update(task_id, status="succeeded", progress=100, message="任务完成", result=result)
            except Exception as err:  # pragma: no cover - surfaced via task endpoint
                task_store.update(
                    task_id,
                    status="failed",
                    progress=100,
                    message="任务失败",
                    error_message=str(err),
                )

        background_tasks.add_task(runner)
        return {"task_id": task_id}

    def require_files(paths: List[str]) -> List[str]:
        clean = [str(Path(p)) for p in paths if str(p).strip()]
        if not clean:
            raise HTTPException(status_code=400, detail="请提供至少一个文件")
        return clean

    def run_desensitization(paths: List[str]) -> Dict[str, Any]:
        source_paths = [Path(p) for p in paths if str(p).strip()]
        files = collect_supported_files(source_paths)
        if not files:
            raise ValueError("未找到可处理的 .xlsx / .xls / .txt 文件")

        logs: List[str] = []
        outputs: List[str] = []
        success_count = 0
        for file_path in files:
            try:
                source_file, output_file = process_single_file(file_path)
                success_count += 1
                outputs.append(str(output_file))
                logs.append(f"[成功] {source_file} -> {output_file}")
            except Exception as err:
                logs.append(f"[失败] {file_path}，错误：{err}")

        return {
            "total": len(files),
            "success_count": success_count,
            "failed_count": len(files) - success_count,
            "outputs": outputs,
            "logs": logs,
        }

    @app.post("/api/import/enterprise")
    def import_enterprise(
        payload: ImportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        files = require_files(payload.file_paths)
        return enqueue(
            background_tasks,
            "import_enterprise",
            lambda: EnterpriseImportUseCase().import_enterprise_profiles(files).to_dict(),
        )

    @app.post("/api/import/{source_type}")
    def import_by_paths(
        source_type: str,
        payload: ImportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        if source_type not in {"bank", "commercial"}:
            raise HTTPException(status_code=400, detail="source_type 仅支持 bank 或 commercial")
        files = require_files(payload.file_paths)
        return enqueue(
            background_tasks,
            "import_{}".format(source_type),
            lambda: ImportUseCase().import_source(
                file_paths=files,
                bank_name=payload.bank_name,
                source_type=source_type,
            ).to_dict(),
        )

    @app.post("/api/upload/{source_type}")
    async def upload_and_import(
        source_type: str,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        bank_name: str = "默认来源",
    ) -> Dict[str, str]:
        if source_type not in {"bank", "commercial", "enterprise"}:
            raise HTTPException(status_code=400, detail="source_type 仅支持 bank、commercial 或 enterprise")
        task_upload_dir = uploads_dir() / source_type
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []
        for item in files:
            target = task_upload_dir / Path(item.filename or "upload.xlsx").name
            with target.open("wb") as fp:
                shutil.copyfileobj(item.file, fp)
            saved.append(str(target))
        if source_type == "enterprise":
            return enqueue(
                background_tasks,
                "import_enterprise",
                lambda: EnterpriseImportUseCase().import_enterprise_profiles(saved).to_dict(),
            )
        return enqueue(
            background_tasks,
            "import_{}".format(source_type),
            lambda: ImportUseCase().import_source(
                file_paths=saved,
                bank_name=bank_name,
                source_type=source_type,
            ).to_dict(),
        )

    @app.post("/api/desensitize")
    def desensitize_by_paths(
        payload: DesensitizeRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        files = require_files(payload.file_paths)
        return enqueue(
            background_tasks,
            "desensitize",
            lambda: run_desensitization(files),
        )

    @app.post("/api/desensitize/upload")
    async def upload_and_desensitize(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
    ) -> Dict[str, str]:
        task_upload_dir = uploads_dir() / "desensitization"
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []
        for item in files:
            target = task_upload_dir / Path(item.filename or "upload.xlsx").name
            with target.open("wb") as fp:
                shutil.copyfileobj(item.file, fp)
            saved.append(str(target))
        return enqueue(
            background_tasks,
            "desensitize",
            lambda: run_desensitization(saved),
        )

    @app.get("/api/batches")
    def list_batches(
        source_type: Optional[str] = Query(default=None),
        limit: int = Query(default=80, ge=1, le=500),
    ) -> Dict[str, Any]:
        uc = DatasetUseCase()
        if source_type == "enterprise":
            rows = uc.list_enterprise_batches(limit)
        elif source_type in ("bank", "commercial"):
            rows = uc.list_batches(source_type, limit)
        else:
            rows = uc.list_batches_merged(limit)
        return {"items": [row.to_dict() for row in rows]}

    @app.delete("/api/batches/{batch_id}")
    def delete_batch(batch_id: str) -> Dict[str, Any]:
        try:
            return DatasetUseCase().delete_import_batch(batch_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/tables")
    def list_tables() -> Dict[str, Any]:
        return {"items": DatasetUseCase().list_tables()}

    @app.get("/api/tables/{table_name}/preview")
    def preview_table(
        table_name: str,
        limit: int = Query(default=200, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
        source_columns_only: bool = True,
    ) -> Dict[str, Any]:
        return DatasetUseCase().preview_table(
            table_name,
            limit=limit,
            offset=offset,
            source_columns_only=source_columns_only,
        ).to_dict()

    @app.delete("/api/tables/{table_name}/rows")
    def delete_rows(table_name: str, payload: DeleteRowsRequest) -> Dict[str, int]:
        return DatasetUseCase().delete_rows(table_name, payload.rowids)

    @app.delete("/api/tables/{table_name}")
    def drop_table(table_name: str) -> Dict[str, str]:
        return DatasetUseCase().drop_table(table_name)

    @app.get("/api/bank/{batch_id}/filter-options")
    def bank_filter_options(batch_id: str) -> Dict[str, List[str]]:
        return BankAnalysisUseCase().filter_options(batch_id)

    @app.post("/api/bank/{batch_id}/records")
    def bank_records(batch_id: str, payload: BankFilterRequest) -> Dict[str, Any]:
        return BankAnalysisUseCase().query_records(batch_id, payload.to_filters()).to_dict()

    @app.post("/api/bank/{batch_id}/modules/{module_id}")
    def bank_module(batch_id: str, module_id: str, payload: ModuleRequest) -> Dict[str, Any]:
        return BankAnalysisUseCase().run_module(batch_id, module_id, payload.to_params())

    @app.post("/api/commercial/{batch_id}/risk/run")
    def run_risk(
        batch_id: str,
        payload: RiskRunRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        return enqueue(
            background_tasks,
            "commercial_risk",
            lambda: CommercialRiskUseCase().run_full(batch_id, payload.enterprise_batch_id).to_dict(),
        )

    @app.get("/api/commercial/{batch_id}/risk/events")
    def risk_events(batch_id: str, limit: int = Query(default=500, ge=1, le=5000)) -> Dict[str, Any]:
        return {"items": CommercialRiskUseCase().list_events(batch_id, limit)}

    @app.get("/api/commercial/{batch_id}/risk/summary")
    def risk_summary(batch_id: str, limit: int = Query(default=500, ge=1, le=5000)) -> Dict[str, Any]:
        return {"items": CommercialRiskUseCase().list_summary(batch_id, limit)}

    @app.get("/api/commercial/{batch_id}/entity-matches")
    def entity_matches(
        batch_id: str,
        enterprise_batch_id: Optional[str] = Query(default=None),
        limit: int = Query(default=2000, ge=1, le=5000),
    ) -> Dict[str, Any]:
        return {
            "items": CommercialRiskUseCase().list_entity_matches(
                batch_id, enterprise_batch_id, limit
            )
        }

    @app.get("/api/commercial/risk-rules")
    def list_commercial_risk_rules() -> Dict[str, Any]:
        return {"items": RiskConfigUseCase().list_rules()}

    @app.patch("/api/commercial/risk-rules/{rule_code}")
    def patch_commercial_risk_rule(rule_code: str, body: RiskRulePatchBody) -> Dict[str, Any]:
        try:
            return RiskConfigUseCase().patch_rule(
                rule_code,
                params=body.params,
                weight=body.weight,
                enabled=body.enabled,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/qichacha/ingest-profile")
    def qichacha_ingest_profile(payload: QichachaIngestProfileBody) -> Dict[str, Any]:
        if not payload.rows:
            raise HTTPException(status_code=400, detail="rows 不能为空")
        summary = EnterpriseImportUseCase().import_qichacha_flat_rows([dict(r) for r in payload.rows])
        out = dict(summary.to_dict())
        if payload.run_id:
            out["run_id"] = payload.run_id
        return out

    @app.post("/api/export/{source_type}/{batch_id}")
    def export_batch(
        source_type: str,
        batch_id: str,
        payload: ExportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        return enqueue(
            background_tasks,
            "export_{}".format(source_type),
            lambda: ExportUseCase().export_batch(batch_id, source_type, payload.output_path).to_dict(),
        )

    @app.post("/api/export/commercial-risk/{batch_id}")
    def export_risk(
        batch_id: str,
        payload: ExportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        return enqueue(
            background_tasks,
            "export_commercial_risk",
            lambda: ExportUseCase().export_commercial_risk_report(batch_id, payload.output_path).to_dict(),
        )

    @app.post("/api/qichacha/basic-details/query")
    async def qichacha_basic_query(
        keywords: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        column_index: int = Form(0),
        column_letter: Optional[str] = Form(None),
        skip_header: str = Form("0"),
    ) -> Dict[str, Any]:
        app_key, secret_key = require_qichacha_credentials()
        merged, input_source = await parse_qichacha_keywords_from_upload(
            keywords=keywords,
            file=file,
            column_index=column_index,
            column_letter=column_letter,
            skip_header=skip_header,
        )
        run_id, export_rows, log_rows = execute_qichacha_keyword_queries(
            merged, input_source, app_key, secret_key
        )
        persist_qichacha_query_logs(log_rows)
        return {"run_id": run_id, "rows": export_rows, "count": len(export_rows)}

    @app.post("/api/qichacha/basic-details/export")
    def qichacha_basic_export_excel(payload: QichachaExportRowsBody) -> Response:
        if not payload.rows:
            raise HTTPException(status_code=400, detail="没有可导出的数据，请先点击查询")
        blob = responses_to_excel_bytes(payload.rows)
        rid = (payload.run_id or "").strip() or str(uuid.uuid4())
        short = rid[:8] if len(rid) >= 8 else rid
        fname = f"qichacha_basic_{short}.xlsx"
        headers: Dict[str, str] = {"Content-Disposition": f'attachment; filename="{fname}"'}
        if (payload.run_id or "").strip():
            headers["X-Run-Id"] = str(payload.run_id).strip()
        return Response(
            content=blob,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )

    @app.get("/api/qichacha/query-logs")
    def qichacha_query_logs(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        run_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        client = SqliteClient()
        cols = (
            "log_id, run_id, created_at, query_keyword, input_source, api_status, "
            "api_message, order_number, matched_name, credit_code, duration_ms, error_detail"
        )
        keys = [
            "log_id",
            "run_id",
            "created_at",
            "query_keyword",
            "input_source",
            "api_status",
            "api_message",
            "order_number",
            "matched_name",
            "credit_code",
            "duration_ms",
            "error_detail",
        ]
        if run_id and str(run_id).strip():
            rows = client.query_all(
                f"SELECT {cols} FROM meta_qichacha_query_log WHERE run_id = ? "
                "ORDER BY log_id DESC LIMIT ? OFFSET ?",
                (str(run_id).strip(), limit, offset),
            )
        else:
            rows = client.query_all(
                f"SELECT {cols} FROM meta_qichacha_query_log ORDER BY log_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        items = [dict(zip(keys, r)) for r in rows]
        return {"items": items}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=False)
