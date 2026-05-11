"""Analysis use cases for bank and commercial data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.application.bootstrap import bootstrap_database
from app.services.integration.bank.analysis_modules import ModuleParams, run_module
from app.services.integration.bank.query_service import BankQueryFilters, BankQueryService
from app.services.integration.commercial.analysis_service import (
    CommercialAnalysisFilters,
    CommercialAnalysisService,
)
from app.services.integration.commercial.risk_rule_service import CommercialRiskAnalysisService
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass(frozen=True)
class BankRecordsResult:
    """Filtered bank records plus summary text."""

    records: list[dict[str, str]]
    summary: dict[str, Any]
    description: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RiskRunResult:
    """Commercial risk run counts."""

    import_batch_id: str
    event_count: int
    summary_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BankAnalysisUseCase:
    """Expose bank query, summary and fixed module analysis."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)
        self._query = BankQueryService(self._client)

    def filter_options(self, batch_id: str) -> dict[str, list[str]]:
        """Return dropdown options for a batch."""
        return self._query.get_filter_options(batch_id)

    def query_records(self, batch_id: str, filters: BankQueryFilters | None = None) -> BankRecordsResult:
        """Return filtered bank records and rendered summary."""
        active_filters = filters or BankQueryFilters()
        records = self._query.query_unified_records(batch_id, active_filters)
        summary = self._query.summarize(records)
        description = self._query.render_description(active_filters, summary)
        return BankRecordsResult(records=records, summary=summary, description=description)

    def run_module(
        self,
        batch_id: str,
        module_id: str,
        params: ModuleParams | None = None,
    ) -> dict[str, object]:
        """Run a fixed bank analysis module."""
        result = run_module(batch_id, module_id, params, self._client)
        return {
            "module_id": result.module_id,
            "params": asdict(result.params),
            "hit_records": result.hit_records,
            "summary": result.summary,
            "extra": result.extra,
            "description": result.description,
        }


class CommercialRiskUseCase:
    """Run and read commercial risk analysis results."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)

    def run_full(self, batch_id: str, enterprise_batch_id: str | None = None) -> RiskRunResult:
        """Run all enabled commercial risk rules."""
        events, summaries = CommercialRiskAnalysisService(self._client).run_full(batch_id, enterprise_batch_id)
        return RiskRunResult(batch_id, events, summaries)

    def list_events(self, batch_id: str, limit: int = 500) -> list[dict[str, object]]:
        """Return recent risk events for a commercial batch."""
        rows = self._client.query_all(
            """
            SELECT event_id, rule_code, rule_name, risk_level, risk_score,
                   enterprise_name, inquiry_no, evidence_json, created_at
            FROM ana_risk_event
            WHERE import_batch_id=?
            ORDER BY event_id DESC
            LIMIT ?;
            """,
            (batch_id, max(1, min(int(limit), 5000))),
        )
        keys = [
            "event_id",
            "rule_code",
            "rule_name",
            "risk_level",
            "risk_score",
            "enterprise_name",
            "inquiry_no",
            "evidence_json",
            "created_at",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def list_summary(self, batch_id: str, limit: int = 500) -> list[dict[str, object]]:
        """Return risk summaries for a commercial batch."""
        rows = self._client.query_all(
            """
            SELECT summary_id, enterprise_name, total_score, hit_count,
                   risk_level, detail_json, created_at
            FROM ana_risk_summary
            WHERE import_batch_id=?
            ORDER BY total_score DESC, hit_count DESC
            LIMIT ?;
            """,
            (batch_id, max(1, min(int(limit), 5000))),
        )
        keys = [
            "summary_id",
            "enterprise_name",
            "total_score",
            "hit_count",
            "risk_level",
            "detail_json",
            "created_at",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def list_entity_matches(
        self,
        batch_id: str,
        enterprise_import_batch_id: Optional[str] = None,
        limit: int = 2000,
    ) -> list[dict[str, object]]:
        """商务公司名称与工商主体匹配明细（依赖已跑过匹配/风险）。"""
        lim = max(1, min(int(limit), 5000))
        eb = (enterprise_import_batch_id or "").strip()
        if eb:
            rows = self._client.query_all(
                """
                SELECT m.match_id, m.inquiry_no, m.biz_company_name, m.biz_company_name_norm,
                       m.enterprise_id, m.enterprise_name, m.match_score, m.match_method,
                       IFNULL(p.credit_code,''), IFNULL(p.legal_person,''), p.import_batch_id
                FROM rel_biz_enterprise_match m
                JOIN std_enterprise_profile p ON p.enterprise_id = m.enterprise_id
                WHERE m.import_batch_id=? AND p.import_batch_id=?
                ORDER BY m.match_id DESC LIMIT ?;
                """,
                (batch_id, eb, lim),
            )
        else:
            rows = self._client.query_all(
                """
                SELECT m.match_id, m.inquiry_no, m.biz_company_name, m.biz_company_name_norm,
                       m.enterprise_id, m.enterprise_name, m.match_score, m.match_method,
                       IFNULL(p.credit_code,''), IFNULL(p.legal_person,''), p.import_batch_id
                FROM rel_biz_enterprise_match m
                JOIN std_enterprise_profile p ON p.enterprise_id = m.enterprise_id
                WHERE m.import_batch_id=?
                ORDER BY m.match_id DESC LIMIT ?;
                """,
                (batch_id, lim),
            )
        keys = [
            "match_id",
            "inquiry_no",
            "biz_company_name",
            "biz_company_name_norm",
            "enterprise_id",
            "enterprise_name",
            "match_score",
            "match_method",
            "credit_code",
            "legal_person",
            "enterprise_import_batch_id",
        ]
        return [dict(zip(keys, row)) for row in rows]


class CommercialAnalysisUseCase:
    """Expose commercial bid query and statistics."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = bootstrap_database(client)
        self._service = CommercialAnalysisService(self._client)

    def filter_options(self, batch_id: str) -> dict[str, list[str]]:
        return self._service.filter_options(batch_id)

    def query_records(
        self,
        batch_id: str,
        filters: CommercialAnalysisFilters | None = None,
    ) -> dict[str, object]:
        return self._service.query_records(batch_id, filters)
