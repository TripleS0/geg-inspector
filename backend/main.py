"""FastAPI backend for the offline desktop Web system."""

import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.application.analysis_use_cases import (
    BankAnalysisUseCase,
    CommercialAnalysisUseCase,
    CommercialRiskUseCase,
    TelecomAnalysisUseCase,
    WechatAnalysisUseCase,
)
from app.application.case_use_cases import CaseUseCase
from app.application.fusion_use_cases import FusionUseCase
from app.application.risk_config_use_cases import RiskConfigUseCase
from app.application.bootstrap import bootstrap_database
from app.application.data_center_use_cases import DataCenterUseCase
from app.application.dataset_use_cases import DatasetUseCase
from app.application.export_use_cases import ExportUseCase
from app.application.bank_ocr_use_cases import BankOcrUseCase
from app.application.import_use_cases import EnterpriseImportUseCase, ImportUseCase
from app.application.task_store import TaskStore
from app.runtime_paths import exports_dir, uploads_dir
from app.services.integration.bank.analysis_modules import ModuleParams
from app.services.integration.bank.bank_template_wizard_service import (
    BankTemplateWizardService,
    validate_field_map,
)
from app.services.bank_ocr.bank_template_ocr_service import BankTemplateOcrAnalyzeService
from app.services.bank_ocr.upload_formats import SUPPORTED_UPLOAD_SUFFIXES, UPLOAD_FORMAT_HINT
from app.services.integration.bank.mapping_service import BankMappingService
from app.services.integration.bank.query_service import BankQueryFilters
from app.services.integration.commercial.analysis_service import CommercialAnalysisFilters
from app.services.integration.commercial.co_bid_analysis_service import CoBidAnalysisParams
from app.services.integration.telecom.analysis_service import TelecomAnalysisFilters
from app.services.integration.wechat.analysis_service import WechatAnalysisFilters
from app.services.integration.bank.user_bank_template_repository import UserBankTemplateRepository
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
    batch_name: Optional[str] = None


class BatchRenamePayload(BaseModel):
    """Rename an import batch display name."""

    batch_name: str = Field(..., min_length=1, max_length=120)


class RiskRunRequest(BaseModel):
    """Commercial risk analysis request."""

    enterprise_batch_id: Optional[str] = None


class ExportRequest(BaseModel):
    """Optional output path for exports."""

    output_path: Optional[str] = None


class DesensitizeRequest(BaseModel):
    """Desensitization request using local file or folder paths."""

    file_paths: List[str] = Field(default_factory=list)


class BankOcrRowsPayload(BaseModel):
    """Proofread OCR rows payload."""

    rows: List[Dict[str, Any]] = Field(default_factory=list)


class BankOcrHeaderPayload(BaseModel):
    """Proofread OCR header payload."""

    header: Dict[str, Any] = Field(default_factory=dict)


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


class CommercialAnalysisFilterRequest(BaseModel):
    """Commercial bid analysis filter payload."""

    company_name: str = ""
    purchaser: str = ""
    inquiry_no: str = ""
    winner: str = ""
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    participation_min: Optional[int] = None
    only_winners: bool = False
    start_time: str = ""
    end_time: str = ""

    def to_filters(self) -> CommercialAnalysisFilters:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:  # pragma: no cover - pydantic v1 fallback
            data = self.dict()
        return CommercialAnalysisFilters(**data)


class CommercialCoBidAnalysisRequest(BaseModel):
    """Co-bidding pattern analysis for a target company."""

    company_name: str = ""
    purchaser: str = ""
    start_time: str = ""
    end_time: str = ""

    def to_params(self) -> CoBidAnalysisParams:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:  # pragma: no cover - pydantic v1 fallback
            data = self.dict()
        return CoBidAnalysisParams(**data)


class WechatAnalysisFilterRequest(BaseModel):
    """WeChat transfer analysis filter payload."""

    user_name: str = ""
    debit_credit_type: str = ""
    counterparty_name: str = ""
    business_type: str = ""
    purpose_type: str = ""
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""
    remark: str = ""
    income_types: List[str] = Field(default_factory=lambda: ["入"])
    expense_types: List[str] = Field(default_factory=lambda: ["出"])

    def to_filters(self) -> WechatAnalysisFilters:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:  # pragma: no cover - pydantic v1 fallback
            data = self.dict()
        return WechatAnalysisFilters(
            user_name=data.get("user_name", ""),
            debit_credit_type=data.get("debit_credit_type", ""),
            counterparty_name=data.get("counterparty_name", ""),
            business_type=data.get("business_type", ""),
            purpose_type=data.get("purpose_type", ""),
            amount_min=data.get("amount_min"),
            amount_max=data.get("amount_max"),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            day_time_start=data.get("day_time_start", ""),
            day_time_end=data.get("day_time_end", ""),
            remark=data.get("remark", ""),
            income_types=tuple(data.get("income_types") or ["入"]),
            expense_types=tuple(data.get("expense_types") or ["出"]),
        )


class GraphExploreAnchorPayload(BaseModel):
    """Graph exploration anchor."""

    type: str = "person"
    value: str


class GraphExplorePayload(BaseModel):
    """Graph exploration request payload."""

    anchors: List[GraphExploreAnchorPayload] = Field(default_factory=list)
    display_level: int = Field(default=2, ge=1, le=10)
    unlimited: bool = False
    relation_types: List[str] = Field(default_factory=list)
    min_weight: int = Field(default=1, ge=1, le=100)
    max_nodes: int = Field(default=500, ge=1, le=1000)
    max_edges: int = Field(default=1500, ge=1, le=3000)
    include_sample_records: bool = True


class GraphSelectionDetailPayload(BaseModel):
    """Graph node/edge detail and chart stats request."""

    kind: str
    node_id: str = ""
    source: str = ""
    target: str = ""
    edge_type: str = ""
    date_from: str = ""
    date_to: str = ""


class TelecomAnalysisFilterRequest(BaseModel):
    """Telecom CDR analysis filter payload."""

    local_phone: str = ""
    peer_phone: str = ""
    call_type: str = ""
    bill_type: str = ""
    direction: str = ""
    local_carrier: str = ""
    peer_carrier: str = ""
    peer_location: str = ""
    local_location: str = ""
    duration_min: Optional[int] = None
    duration_max: Optional[int] = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""

    def to_filters(self) -> TelecomAnalysisFilters:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:  # pragma: no cover - pydantic v1 fallback
            data = self.dict()
        return TelecomAnalysisFilters(
            local_phone=data.get("local_phone", ""),
            peer_phone=data.get("peer_phone", ""),
            call_type=data.get("call_type", ""),
            bill_type=data.get("bill_type", ""),
            direction=data.get("direction", ""),
            local_carrier=data.get("local_carrier", ""),
            peer_carrier=data.get("peer_carrier", ""),
            peer_location=data.get("peer_location", ""),
            local_location=data.get("local_location", ""),
            duration_min=data.get("duration_min"),
            duration_max=data.get("duration_max"),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            day_time_start=data.get("day_time_start", ""),
            day_time_end=data.get("day_time_end", ""),
        )


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


class CasePayload(BaseModel):
    case_name: str
    description: str = ""
    status: str = "active"


class CasePatchPayload(BaseModel):
    case_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class CaseBindBatchesPayload(BaseModel):
    import_batch_ids: List[str] = Field(default_factory=list)


class PersonPayload(BaseModel):
    display_name: str
    role_tag: str = "unknown"
    notes: str = ""


class PersonPatchPayload(BaseModel):
    display_name: Optional[str] = None
    role_tag: Optional[str] = None
    notes: Optional[str] = None


class PersonLinkCandidatePayload(BaseModel):
    person_id: Optional[int] = None
    display_name: Optional[str] = None
    role_tag: str = "unknown"


class ManualLinkPayload(BaseModel):
    identifier_type: str
    identifier_value: str


class FusionModelUpdateItem(BaseModel):
    model_key: str
    enabled: bool = True
    params: Dict[str, Any] = Field(default_factory=dict)


class FusionModelSavePayload(BaseModel):
    items: List[FusionModelUpdateItem] = Field(default_factory=list)


class DataCenterRecordDeleteItem(BaseModel):
    record_kind: str
    record_id: int
    raw_table: Optional[str] = None


class DataCenterDeletePayload(BaseModel):
    items: List[DataCenterRecordDeleteItem] = Field(default_factory=list)


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


class UserBankTemplatePayload(BaseModel):
    """创建/更新用户银行模板。"""

    display_name: str = Field(..., min_length=1)
    template_type: str = Field(..., description="account_profile 或 txn_detail")
    bank_display_name: str = Field(..., min_length=1)
    bank_keywords: List[str] = Field(default_factory=list)
    sheet_keywords: List[str] = Field(default_factory=list)
    field_map: Dict[str, List[str]] = Field(default_factory=dict)
    signature_columns: List[str] = Field(default_factory=list)
    header_row_0based: Optional[int] = None
    match_priority: int = 0
    template_group_id: Optional[str] = None
    direction_rules: Dict[str, str] = Field(default_factory=dict)
    datetime_patterns: Optional[Dict[str, Any]] = None
    template_id: Optional[str] = None


class UserBankTemplatePatchBody(BaseModel):
    """部分更新用户银行模板。"""

    display_name: Optional[str] = None
    template_type: Optional[str] = None
    bank_display_name: Optional[str] = None
    bank_keywords: Optional[List[str]] = None
    sheet_keywords: Optional[List[str]] = None
    field_map: Optional[Dict[str, List[str]]] = None
    signature_columns: Optional[List[str]] = None
    header_row_0based: Optional[int] = None
    match_priority: Optional[int] = None
    template_group_id: Optional[str] = None
    direction_rules: Optional[Dict[str, str]] = None
    datetime_patterns: Optional[Dict[str, Any]] = None
    is_active: Optional[int] = None


class ClearFingerprintMappingsBody(BaseModel):
    """清除某指纹下的字段映射，便于重新标准化时重新种子映射。"""

    template_fingerprint: str = Field(..., min_length=8)


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


def _ensure_r008_rule_row() -> None:
    """旧库可能无 R008（陪标关联分析阈值），幂等补种。"""
    SqliteClient().execute(
        """
        INSERT OR IGNORE INTO cfg_risk_rule (rule_code, rule_name, enabled, weight, params_json, version)
        VALUES (
            'R008', '陪标关联分析', 1, 1.0,
            '{"min_shared_inquiries":3,"min_co_rate":0.25,"max_target_win_rate":0.15,"min_both_lose_rate":0.5,"min_other_win_rate":0.5,"min_rotating_exclusive_wins":4,"min_alternation_score":0.55,"note":"陪标关联分析页面判定阈值"}',
            1
        );
        """
    )


QICHACHA_503_DETAIL = (
    "未配置企查查密钥：请设置环境变量 QICHACHA_APP_KEY / QICHACHA_SECRET_KEY，"
    "或在以下任一 JSON 文件中填写 app_key 与 secret_key（格式见 "
    "backend/app/resources/config/qichacha_config.example.json）："
    "data/qichacha_config.json、backend/app/resources/config/qichacha_config.json、"
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
    _ensure_r008_rule_row()
    app = FastAPI(title="DataFusionX Offline Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1",
            "http://localhost",
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
            lambda: EnterpriseImportUseCase().import_enterprise_profiles(
                files,
                batch_name=payload.batch_name,
            ).to_dict(),
        )

    @app.post("/api/import/{source_type}")
    def import_by_paths(
        source_type: str,
        payload: ImportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        if source_type not in {"bank", "commercial", "wechat", "telecom"}:
            raise HTTPException(status_code=400, detail="source_type 仅支持 bank、commercial、wechat 或 telecom")
        files = require_files(payload.file_paths)
        return enqueue(
            background_tasks,
            "import_{}".format(source_type),
            lambda: ImportUseCase().import_source(
                file_paths=files,
                bank_name=payload.bank_name,
                source_type=source_type,
                batch_name=payload.batch_name,
            ).to_dict(),
        )

    @app.post("/api/upload/{source_type}")
    async def upload_and_import(
        source_type: str,
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        bank_name: str = "默认来源",
        batch_name: Optional[str] = Form(default=None),
    ) -> Dict[str, str]:
        if source_type not in {"bank", "commercial", "enterprise", "wechat", "telecom"}:
            raise HTTPException(status_code=400, detail="source_type 仅支持 bank、commercial、enterprise、wechat 或 telecom")
        task_upload_dir = uploads_dir() / source_type
        saved: List[str] = []
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        for item in files:
            original = Path(item.filename or "upload.xlsx").name
            target = task_upload_dir / f"{uuid.uuid4().hex}_{original}"
            with target.open("wb") as fp:
                shutil.copyfileobj(item.file, fp)
            saved.append(str(target))
        if source_type == "enterprise":
            return enqueue(
                background_tasks,
                "import_enterprise",
                lambda: EnterpriseImportUseCase().import_enterprise_profiles(
                    saved,
                    batch_name=batch_name,
                ).to_dict(),
            )
        return enqueue(
            background_tasks,
            "import_{}".format(source_type),
            lambda: ImportUseCase().import_source(
                file_paths=saved,
                bank_name=bank_name,
                source_type=source_type,
                batch_name=batch_name,
            ).to_dict(),
        )

    @app.get("/api/bank-ocr/profiles")
    def list_bank_ocr_profiles() -> Dict[str, Any]:
        payload = BankOcrUseCase().list_profiles()
        payload["supported_formats"] = sorted(SUPPORTED_UPLOAD_SUFFIXES)
        payload["format_hint"] = UPLOAD_FORMAT_HINT
        return payload

    @app.get("/api/bank-ocr/jobs")
    def list_bank_ocr_jobs(status: Optional[str] = Query(default=None)) -> Dict[str, Any]:
        return BankOcrUseCase().list_jobs(status=status)

    @app.get("/api/bank-ocr/jobs/{job_id}")
    def get_bank_ocr_job(job_id: str) -> Dict[str, Any]:
        try:
            return BankOcrUseCase().get_job(job_id)
        except ValueError as err:
            raise HTTPException(status_code=404, detail=str(err)) from err

    @app.get("/api/bank-ocr/jobs/{job_id}/pages/{page_index}/image")
    def get_bank_ocr_page_image(job_id: str, page_index: int) -> FileResponse:
        from app.services.bank_ocr.draft_repository import BankOcrDraftRepository

        image_path = BankOcrDraftRepository(SqliteClient()).get_page_image_path(job_id, page_index)
        if not image_path or not Path(image_path).is_file():
            raise HTTPException(status_code=404, detail="页面图片不存在")
        media_type = "image/png"
        suffix = Path(image_path).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif suffix == ".webp":
            media_type = "image/webp"
        return FileResponse(image_path, media_type=media_type)

    @app.put("/api/bank-ocr/jobs/{job_id}/rows")
    def save_bank_ocr_rows(job_id: str, payload: BankOcrRowsPayload) -> Dict[str, Any]:
        try:
            return BankOcrUseCase().save_rows(job_id, payload.rows)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.put("/api/bank-ocr/jobs/{job_id}/header")
    def save_bank_ocr_header(job_id: str, payload: BankOcrHeaderPayload) -> Dict[str, Any]:
        try:
            return BankOcrUseCase().save_header(job_id, payload.header)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/bank-ocr/jobs/{job_id}/commit")
    def commit_bank_ocr_job(job_id: str, background_tasks: BackgroundTasks) -> Dict[str, str]:
        return enqueue(
            background_tasks,
            "bank_ocr_commit",
            lambda: BankOcrUseCase().commit(job_id),
        )

    @app.delete("/api/bank-ocr/jobs/{job_id}")
    def delete_bank_ocr_job(job_id: str) -> Dict[str, Any]:
        try:
            return BankOcrUseCase().delete_job(job_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/bank-ocr/upload")
    async def upload_bank_ocr(
        background_tasks: BackgroundTasks,
        files: List[UploadFile] = File(...),
        bank_name: str = Form(default="光大银行"),
        batch_name: Optional[str] = Form(default=None),
        layout_profile_id: Optional[str] = Form(default="ceb_txn_v1"),
    ) -> Dict[str, str]:
        task_upload_dir = uploads_dir() / "bank_ocr" / "incoming"
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        saved: List[str] = []
        for item in files:
            suffix = Path(item.filename or "upload.png").suffix.lower()
            if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的文件类型：{suffix or '无后缀'}。{UPLOAD_FORMAT_HINT}",
                )
            target = task_upload_dir / f"{uuid.uuid4().hex}_{Path(item.filename or 'upload.png').name}"
            with target.open("wb") as fp:
                shutil.copyfileobj(item.file, fp)
            saved.append(str(target))
        return enqueue(
            background_tasks,
            "bank_ocr_upload",
            lambda: BankOcrUseCase().process_upload(
                upload_paths=saved,
                bank_name=bank_name,
                batch_name=batch_name or "",
                layout_profile_id=layout_profile_id,
            ),
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
            original = Path(item.filename or "upload.xlsx").name
            target = task_upload_dir / f"{uuid.uuid4().hex}_{original}"
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
        elif source_type in ("bank", "commercial", "wechat", "telecom"):
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

    @app.patch("/api/batches/{batch_id}")
    def rename_batch(batch_id: str, payload: BatchRenamePayload) -> Dict[str, Any]:
        try:
            row = DatasetUseCase().rename_batch(batch_id, payload.batch_name)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return row.to_dict()

    @app.get("/api/cases")
    def list_cases() -> Dict[str, Any]:
        rows = CaseUseCase().list_cases()
        return {
            "items": [
                {
                    "case_id": r.case_id,
                    "case_name": r.case_name,
                    "description": r.description,
                    "status": r.status,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "batch_count": r.batch_count,
                }
                for r in rows
            ]
        }

    @app.post("/api/cases")
    def create_case(payload: CasePayload) -> Dict[str, Any]:
        try:
            case = CaseUseCase().create_case(
                case_name=payload.case_name,
                description=payload.description,
                status=payload.status,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {
            "case_id": case.case_id,
            "case_name": case.case_name,
            "description": case.description,
            "status": case.status,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "batch_count": case.batch_count,
        }

    @app.get("/api/cases/unbound-batches")
    def list_unbound_batches() -> Dict[str, Any]:
        return {"items": CaseUseCase().list_unbound_batches()}

    @app.get("/api/cases/batch-map")
    def batch_case_map() -> Dict[str, Any]:
        return {"items": CaseUseCase().batch_case_map()}

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: int) -> Dict[str, Any]:
        case = CaseUseCase().get_case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        batches = CaseUseCase().list_case_batches(case_id)
        return {
            "case_id": case.case_id,
            "case_name": case.case_name,
            "description": case.description,
            "status": case.status,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "batch_count": case.batch_count,
            "batches": [
                {
                    "import_batch_id": b.import_batch_id,
                    "source_type": b.source_type,
                    "bound_at": b.bound_at,
                }
                for b in batches
            ],
        }

    @app.patch("/api/cases/{case_id}")
    def patch_case(case_id: int, payload: CasePatchPayload) -> Dict[str, Any]:
        try:
            case = CaseUseCase().update_case(
                case_id,
                case_name=payload.case_name,
                description=payload.description,
                status=payload.status,
            )
        except ValueError as err:
            raise HTTPException(status_code=404 if "不存在" in str(err) else 400, detail=str(err)) from err
        return {
            "case_id": case.case_id,
            "case_name": case.case_name,
            "description": case.description,
            "status": case.status,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
            "batch_count": case.batch_count,
        }

    @app.delete("/api/cases/{case_id}")
    def delete_case(case_id: int) -> Dict[str, str]:
        CaseUseCase().delete_case(case_id)
        return {"status": "deleted", "case_id": str(case_id)}

    @app.post("/api/cases/{case_id}/batches")
    def bind_case_batches(case_id: int, payload: CaseBindBatchesPayload) -> Dict[str, Any]:
        try:
            batches = CaseUseCase().bind_batches(case_id, payload.import_batch_ids)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {
            "items": [
                {
                    "import_batch_id": b.import_batch_id,
                    "source_type": b.source_type,
                    "bound_at": b.bound_at,
                }
                for b in batches
            ]
        }

    @app.delete("/api/cases/{case_id}/batches/{batch_id}")
    def unbind_case_batch(case_id: int, batch_id: str) -> Dict[str, str]:
        CaseUseCase().unbind_batch(case_id, batch_id)
        return {"status": "unbound", "import_batch_id": batch_id}

    @app.post("/api/cases/{case_id}/discover")
    def discover_case_identifiers(case_id: int) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        return FusionUseCase().discover(case_id)

    @app.post("/api/cases/{case_id}/auto-link")
    def auto_link_case_identifiers(
        case_id: int,
        rediscover: bool = Query(default=True),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            return FusionUseCase().auto_link(case_id, rediscover=rediscover)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/persons")
    def list_case_persons(case_id: int) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        return {"items": FusionUseCase().list_persons(case_id)}

    @app.post("/api/cases/{case_id}/persons")
    def create_case_person(case_id: int, payload: PersonPayload) -> Dict[str, Any]:
        try:
            return FusionUseCase().create_person(
                case_id,
                display_name=payload.display_name,
                role_tag=payload.role_tag,
                notes=payload.notes,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/persons/{person_id}")
    def get_case_person(case_id: int, person_id: int) -> Dict[str, Any]:
        try:
            return FusionUseCase().get_person(case_id, person_id)
        except ValueError as err:
            raise HTTPException(status_code=404, detail=str(err)) from err

    @app.patch("/api/cases/{case_id}/persons/{person_id}")
    def patch_case_person(case_id: int, person_id: int, payload: PersonPatchPayload) -> Dict[str, Any]:
        try:
            return FusionUseCase().update_person(
                case_id,
                person_id,
                display_name=payload.display_name,
                role_tag=payload.role_tag,
                notes=payload.notes,
            )
        except ValueError as err:
            raise HTTPException(status_code=404 if "不存在" in str(err) else 400, detail=str(err)) from err

    @app.delete("/api/cases/{case_id}/persons/{person_id}")
    def delete_case_person(case_id: int, person_id: int) -> Dict[str, str]:
        FusionUseCase().delete_person(case_id, person_id)
        return {"status": "deleted", "person_id": str(person_id)}

    @app.get("/api/cases/{case_id}/candidates")
    def list_case_candidates(
        case_id: int,
        review_status: str = Query(default="pending"),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        return {"items": FusionUseCase().list_candidates(case_id, review_status=review_status)}

    @app.post("/api/cases/{case_id}/candidates/{candidate_id}/link")
    def link_case_candidate(
        case_id: int,
        candidate_id: int,
        payload: PersonLinkCandidatePayload,
    ) -> Dict[str, Any]:
        try:
            if payload.person_id is not None:
                return FusionUseCase().link_candidate(case_id, candidate_id, payload.person_id)
            return FusionUseCase().link_candidate_new_person(
                case_id,
                candidate_id,
                display_name=payload.display_name,
                role_tag=payload.role_tag,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/cases/{case_id}/candidates/{candidate_id}/no-match")
    def mark_case_candidate_no_match(case_id: int, candidate_id: int) -> Dict[str, str]:
        try:
            FusionUseCase().mark_candidate_no_match(case_id, candidate_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {"status": "no_match", "candidate_id": str(candidate_id)}

    @app.post("/api/cases/{case_id}/persons/{person_id}/links")
    def add_case_person_link(case_id: int, person_id: int, payload: ManualLinkPayload) -> Dict[str, Any]:
        try:
            return FusionUseCase().add_manual_link(
                case_id,
                person_id,
                identifier_type=payload.identifier_type,
                identifier_value=payload.identifier_value,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.delete("/api/cases/{case_id}/persons/{person_id}/links/{link_id}")
    def delete_case_person_link(case_id: int, person_id: int, link_id: int) -> Dict[str, str]:
        try:
            FusionUseCase().remove_link(case_id, person_id, link_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {"status": "deleted", "link_id": str(link_id)}

    @app.get("/api/cases/{case_id}/cockpit/person/{person_id}")
    def case_person_cockpit(case_id: int, person_id: int) -> Dict[str, Any]:
        try:
            return FusionUseCase().person_cockpit(case_id, person_id)
        except ValueError as err:
            raise HTTPException(status_code=404 if "不存在" in str(err) else 400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/cockpit/relation")
    def case_relation_cockpit(
        case_id: int,
        person_a: int = Query(...),
        person_b: int = Query(...),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            return FusionUseCase().relation_cockpit(case_id, person_a, person_b)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/cockpit/anchor")
    def case_anchor_cockpit(
        case_id: int,
        value: str = Query(..., min_length=1),
        type: str = Query(default="auto"),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            return FusionUseCase().anchor_cockpit(case_id, type, value)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/cockpit/suggest")
    def case_anchor_suggest(
        case_id: int,
        q: str = Query(default=""),
        type: str = Query(default="auto"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        return FusionUseCase().suggest_anchors(case_id, q, limit=limit, anchor_type=type)

    @app.post("/api/cases/{case_id}/graph/explore")
    def case_graph_explore(case_id: int, payload: GraphExplorePayload) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            return FusionUseCase().explore_graph(case_id, data)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/cases/{case_id}/graph/selection-detail")
    def case_graph_selection_detail(case_id: int, payload: GraphSelectionDetailPayload) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            return FusionUseCase().graph_selection_detail(case_id, data)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/records/detail")
    def case_record_detail(case_id: int, ref: str = Query(...)) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            return FusionUseCase().record_detail(ref)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/cases/{case_id}/fusion/models")
    def list_fusion_models(case_id: int) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        return FusionUseCase().list_fusion_models(case_id)

    @app.put("/api/cases/{case_id}/fusion/models")
    def save_fusion_models(case_id: int, payload: FusionModelSavePayload) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        updates = [
            {"model_key": item.model_key, "enabled": item.enabled, "params": item.params}
            for item in payload.items
        ]
        return FusionUseCase().save_fusion_models(case_id, updates)

    @app.get("/api/cases/{case_id}/fusion/events")
    def scan_fusion_events(
        case_id: int,
        start_date: str = Query(default=""),
        end_date: str = Query(default=""),
        keyword: str = Query(default=""),
        event_type: str = Query(default=""),
    ) -> Dict[str, Any]:
        if CaseUseCase().get_case(case_id) is None:
            raise HTTPException(status_code=404, detail="案件不存在")
        try:
            return FusionUseCase().scan_fusion_events(
                case_id,
                start_date=start_date,
                end_date=end_date,
                keyword=keyword,
                event_type=event_type,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/data-center/records")
    def data_center_records(
        case_id: Optional[int] = Query(default=None),
        batch_id: Optional[str] = Query(default=None),
        source_type: Optional[str] = Query(default=None),
        keyword: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> Dict[str, Any]:
        return DataCenterUseCase().list_records(
            case_id=case_id,
            batch_id=batch_id,
            source_type=source_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    @app.delete("/api/data-center/records")
    def data_center_delete_records(payload: DataCenterDeletePayload) -> Dict[str, int]:
        try:
            items = [item.model_dump() for item in payload.items]
            return DataCenterUseCase().delete_records(items)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.get("/api/data-center/dashboard")
    def data_center_dashboard(
        case_id: Optional[int] = Query(default=None),
    ) -> Dict[str, Any]:
        return DataCenterUseCase().get_dashboard(case_id)

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

    @app.get("/api/commercial/{batch_id}/analysis/filter-options")
    def commercial_analysis_filter_options(batch_id: str) -> Dict[str, List[str]]:
        return CommercialAnalysisUseCase().filter_options(batch_id)

    @app.post("/api/commercial/{batch_id}/analysis/records")
    def commercial_analysis_records(
        batch_id: str,
        payload: CommercialAnalysisFilterRequest,
    ) -> Dict[str, Any]:
        return CommercialAnalysisUseCase().query_records(batch_id, payload.to_filters())

    @app.post("/api/commercial/{batch_id}/analysis/co-bidding")
    def commercial_co_bid_analysis(
        batch_id: str,
        payload: CommercialCoBidAnalysisRequest,
    ) -> Dict[str, Any]:
        return CommercialAnalysisUseCase().analyze_co_bidding(batch_id, payload.to_params())

    @app.get("/api/wechat/{batch_id}/analysis/filter-options")
    def wechat_analysis_filter_options(batch_id: str) -> Dict[str, List[str]]:
        return WechatAnalysisUseCase().filter_options(batch_id)

    @app.post("/api/wechat/{batch_id}/analysis/records")
    def wechat_analysis_records(
        batch_id: str,
        payload: WechatAnalysisFilterRequest,
    ) -> Dict[str, Any]:
        return WechatAnalysisUseCase().query_records(batch_id, payload.to_filters())

    @app.get("/api/telecom/{batch_id}/analysis/filter-options")
    def telecom_analysis_filter_options(batch_id: str) -> Dict[str, List[str]]:
        return TelecomAnalysisUseCase().filter_options(batch_id)

    @app.post("/api/telecom/{batch_id}/analysis/records")
    def telecom_analysis_records(
        batch_id: str,
        payload: TelecomAnalysisFilterRequest,
    ) -> Dict[str, Any]:
        return TelecomAnalysisUseCase().query_records(batch_id, payload.to_filters())

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

    @app.post("/api/export/commercial-analysis/{batch_id}")
    def export_commercial_analysis(
        batch_id: str,
        payload: ExportRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, str]:
        return enqueue(
            background_tasks,
            "export_commercial_analysis",
            lambda: ExportUseCase().export_commercial_analysis_report(batch_id, payload.output_path).to_dict(),
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

    def _user_tpl_dict(rec: Any) -> Dict[str, Any]:
        return {
            "id": rec.id,
            "template_id": rec.template_id,
            "display_name": rec.display_name,
            "template_type": rec.template_type,
            "bank_display_name": rec.bank_display_name,
            "bank_keywords": rec.bank_keywords,
            "sheet_keywords": rec.sheet_keywords,
            "field_map": rec.field_map,
            "signature_columns": rec.signature_columns,
            "header_row_0based": rec.header_row_0based,
            "match_priority": rec.match_priority,
            "template_group_id": rec.template_group_id,
            "direction_rules": rec.direction_rules,
            "datetime_patterns": rec.datetime_patterns,
            "is_active": rec.is_active,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }

    def _validate_direction_rules(rules: Dict[str, str]) -> None:
        allowed = {"收入", "支出", "未知"}
        for k, v in rules.items():
            if v not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"借贷规则值须为 收入/支出/未知，收到: {k} -> {v}",
                )

    @app.get("/api/bank-templates")
    def list_user_bank_templates(
        group_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        repo = UserBankTemplateRepository()
        rows = repo.list_all()
        if group_id and str(group_id).strip():
            gid = str(group_id).strip()
            rows = [r for r in rows if (r.template_group_id or "") == gid]
        return {"items": [_user_tpl_dict(r) for r in rows]}

    @app.post("/api/bank-templates/analyze-sample")
    async def analyze_bank_template_sample(
        file: UploadFile = File(...),
        sheet_name: str = Form(""),
        template_type: str = Form(...),
        bank_name_hint: str = Form("银行数据"),
        header_row_0based: Optional[str] = Form(None),
    ) -> Dict[str, Any]:
        if template_type not in ("account_profile", "txn_detail"):
            raise HTTPException(status_code=400, detail="template_type 无效")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xlsx", ".xls"}:
            raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls")
        body = await file.read()
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(body)
                tmp_path = Path(tmp.name)
            hdr: Optional[int] = None
            if header_row_0based is not None and str(header_row_0based).strip() != "":
                try:
                    hdr = int(str(header_row_0based).strip())
                except ValueError as err:
                    raise HTTPException(status_code=400, detail="header_row_0based 须为整数") from err
            wiz = BankTemplateWizardService()
            result = wiz.analyze(
                file_path=tmp_path,
                sheet_name=sheet_name.strip(),
                template_type=template_type,
                bank_name_hint=bank_name_hint.strip() or "银行数据",
                header_row_0based=hdr,
            )
            return result
        finally:
            if tmp_path is not None and tmp_path.is_file():
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    pass

    @app.post("/api/bank-templates/analyze-ocr-sample")
    async def analyze_bank_template_ocr_sample(
        file: UploadFile = File(...),
        template_type: str = Form(...),
        bank_name_hint: str = Form("银行数据"),
        layout_profile_id: Optional[str] = Form(None),
    ) -> Dict[str, Any]:
        if template_type not in ("account_profile", "txn_detail"):
            raise HTTPException(status_code=400, detail="template_type 无效")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"不支持的样本格式。{UPLOAD_FORMAT_HINT}")
        body = await file.read()
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".png") as tmp:
                tmp.write(body)
                tmp_path = Path(tmp.name)
            svc = BankTemplateOcrAnalyzeService()
            return svc.analyze(
                file_path=tmp_path,
                template_type=template_type,
                bank_name_hint=bank_name_hint.strip() or "银行数据",
                layout_profile_id=(layout_profile_id or "").strip() or None,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        except FileNotFoundError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        finally:
            if tmp_path is not None and tmp_path.is_file():
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    pass

    @app.post("/api/bank-templates/analyze-sample/sheets")
    async def list_sheets_for_analyze(file: UploadFile = File(...)) -> Dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xlsx", ".xls"}:
            raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls")
        body = await file.read()
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(body)
                tmp_path = Path(tmp.name)
            wiz = BankTemplateWizardService()
            names = wiz.list_sheet_names(tmp_path)
            return {"sheets": names}
        finally:
            if tmp_path is not None and tmp_path.is_file():
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    pass

    @app.post("/api/bank-templates/fingerprint-mappings/clear")
    def clear_fingerprint_mappings(payload: ClearFingerprintMappingsBody) -> Dict[str, Any]:
        BankMappingService().clear_field_mappings(payload.template_fingerprint.strip())
        return {"status": "ok", "template_fingerprint": payload.template_fingerprint.strip()}

    @app.get("/api/bank-templates/{template_id}")
    def get_user_bank_template(template_id: str) -> Dict[str, Any]:
        repo = UserBankTemplateRepository()
        rec = repo.get_by_template_id(template_id)
        if not rec:
            raise HTTPException(status_code=404, detail="模板不存在")
        return _user_tpl_dict(rec)

    @app.post("/api/bank-templates")
    def create_user_bank_template(payload: UserBankTemplatePayload) -> Dict[str, Any]:
        if payload.template_type not in ("account_profile", "txn_detail"):
            raise HTTPException(status_code=400, detail="template_type 无效")
        try:
            validate_field_map(payload.template_type, payload.field_map)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        if payload.template_type == "txn_detail":
            fm = payload.field_map
            if "acct_no" not in fm or not fm.get("acct_no"):
                raise HTTPException(status_code=400, detail="流水模板须映射 acct_no")
            if "txn_amount" not in fm or not fm.get("txn_amount"):
                raise HTTPException(status_code=400, detail="流水模板须映射 txn_amount")
            if not (fm.get("txn_time_raw") or fm.get("txn_date")):
                raise HTTPException(status_code=400, detail="流水模板须映射 txn_time_raw 或 txn_date")
        else:
            if "acct_no" not in payload.field_map or not payload.field_map.get("acct_no"):
                raise HTTPException(status_code=400, detail="开户模板须映射 acct_no")
            if "person_name" not in payload.field_map or not payload.field_map.get("person_name"):
                raise HTTPException(status_code=400, detail="开户模板须映射 person_name")
        _validate_direction_rules(payload.direction_rules)
        repo = UserBankTemplateRepository()
        tid = repo.create(
            display_name=payload.display_name.strip(),
            template_type=payload.template_type,
            bank_display_name=payload.bank_display_name.strip(),
            bank_keywords=[str(x).strip() for x in payload.bank_keywords if str(x).strip()],
            sheet_keywords=[str(x).strip() for x in payload.sheet_keywords if str(x).strip()],
            field_map={k: [str(x) for x in v] for k, v in payload.field_map.items()},
            signature_columns=payload.signature_columns,
            header_row_0based=payload.header_row_0based,
            match_priority=payload.match_priority,
            template_group_id=(payload.template_group_id or "").strip() or None,
            direction_rules=payload.direction_rules,
            datetime_patterns=payload.datetime_patterns,
            template_id=(payload.template_id or "").strip() or None,
        )
        rec = repo.get_by_template_id(tid)
        return _user_tpl_dict(rec) if rec else {"template_id": tid}

    @app.patch("/api/bank-templates/{template_id}")
    def patch_user_bank_template(template_id: str, payload: UserBankTemplatePatchBody) -> Dict[str, Any]:
        repo = UserBankTemplateRepository()
        existing = repo.get_by_template_id(template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="模板不存在")
        if payload.template_type is not None and payload.template_type not in ("account_profile", "txn_detail"):
            raise HTTPException(status_code=400, detail="template_type 无效")
        if payload.field_map is not None:
            tt = payload.template_type or existing.template_type
            try:
                validate_field_map(tt, payload.field_map)
            except ValueError as err:
                raise HTTPException(status_code=400, detail=str(err)) from err
        if payload.direction_rules is not None:
            _validate_direction_rules(payload.direction_rules)
        repo.update(
            template_id,
            display_name=payload.display_name,
            template_type=payload.template_type,
            bank_display_name=payload.bank_display_name,
            bank_keywords=payload.bank_keywords,
            sheet_keywords=payload.sheet_keywords,
            field_map=payload.field_map,
            signature_columns=payload.signature_columns,
            header_row_0based=payload.header_row_0based,
            match_priority=payload.match_priority,
            template_group_id=payload.template_group_id,
            direction_rules=payload.direction_rules,
            datetime_patterns=payload.datetime_patterns,
            is_active=payload.is_active,
        )
        rec = repo.get_by_template_id(template_id)
        return _user_tpl_dict(rec) if rec else {}

    @app.delete("/api/bank-templates/{template_id}")
    def delete_user_bank_template(template_id: str) -> Dict[str, str]:
        repo = UserBankTemplateRepository()
        if not repo.delete(template_id):
            raise HTTPException(status_code=404, detail="模板不存在")
        return {"status": "deleted", "template_id": template_id}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=False)
