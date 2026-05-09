"""Match commercial bid supplier names to enterprise profiles (Qichacha import)."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.integration.commercial.export_service import CommercialExportService
from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class EntityMatchResult:
    commercial_batch_id: str
    enterprise_batch_id: str
    matched_pairs: int


class EntityMatchService:
    """Link 商务网「公司名称」到 std_enterprise_profile。"""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def rebuild_matches(
        self,
        commercial_batch_id: str,
        enterprise_import_batch_id: str | None = None,
    ) -> EntityMatchResult:
        """Clear and rebuild rel_biz_enterprise_match for one commercial batch."""
        export_svc = CommercialExportService(self._client)
        rows = export_svc._load_commercial_rows(commercial_batch_id)
        filled = _fill_forward_commercial(rows)
        profiles = self._load_profiles(enterprise_import_batch_id)
        self._client.execute(
            "DELETE FROM rel_biz_enterprise_match WHERE import_batch_id=?;",
            (commercial_batch_id,),
        )
        seen: set[tuple[str, str]] = set()
        inserted = 0
        ent_batch = enterprise_import_batch_id or ""
        for row in filled:
            inquiry = (row.get("询价单号") or "").strip()
            company = (row.get("公司名称") or "").strip()
            if not company:
                continue
            key = (inquiry, company)
            if key in seen:
                continue
            seen.add(key)
            cnorm = normalize_enterprise_name(company)
            if not cnorm:
                continue
            best = self._pick_best_profile(cnorm, profiles)
            if best is None:
                continue
            eid, ename, escore, method, eb = best
            self._client.execute(
                """
                INSERT INTO rel_biz_enterprise_match(
                    import_batch_id, inquiry_no, biz_company_name, biz_company_name_norm,
                    enterprise_id, enterprise_name, match_score, match_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    commercial_batch_id,
                    inquiry,
                    company,
                    cnorm,
                    eid,
                    ename,
                    escore,
                    f"{method};enterprise_batch={eb}",
                ),
            )
            inserted += 1
        return EntityMatchResult(
            commercial_batch_id=commercial_batch_id,
            enterprise_batch_id=ent_batch,
            matched_pairs=inserted,
        )

    def _load_profiles(
        self, enterprise_import_batch_id: str | None
    ) -> list[tuple[int, str, str, str, str]]:
        """Return (enterprise_id, name, name_norm, legal_person, source_batch)."""
        if enterprise_import_batch_id:
            q = """
            SELECT enterprise_id, enterprise_name, enterprise_name_norm, IFNULL(legal_person,''), import_batch_id
            FROM std_enterprise_profile
            WHERE import_batch_id=?
            ORDER BY enterprise_id;
            """
            raw = self._client.query_all(q, (enterprise_import_batch_id,))
        else:
            q = """
            SELECT enterprise_id, enterprise_name, enterprise_name_norm, IFNULL(legal_person,''), import_batch_id
            FROM std_enterprise_profile
            ORDER BY imported_at DESC, enterprise_id DESC;
            """
            raw = self._client.query_all(q)
        out: list[tuple[int, str, str, str, str]] = []
        for row in raw:
            out.append((int(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4])))
        return out

    def _pick_best_profile(
        self,
        company_norm: str,
        profiles: list[tuple[int, str, str, str, str]],
    ) -> tuple[int, str, float, str, str] | None:
        best: tuple[int, str, float, str, str] | None = None
        for eid, ename, enorm, _lp, eb in profiles:
            score = 0.0
            method = ""
            if company_norm == enorm:
                score, method = 1.0, "名称规范化完全匹配"
            elif company_norm in enorm or enorm in company_norm:
                score, method = 0.88, "名称包含关系"
            if score == 0:
                continue
            if best is None or score > best[2] or (score == best[2] and eid > best[0]):
                best = (eid, ename, score, method, eb)
        return best


def _fill_forward_commercial(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fill empty 询价单号/公司名称 from previous row (与导出展示逻辑一致)."""
    out: list[dict[str, str]] = []
    last_inquiry = ""
    last_company = ""
    for r in rows:
        d = dict(r)
        inq = (d.get("询价单号") or "").strip()
        co = (d.get("公司名称") or "").strip()
        if inq:
            last_inquiry = inq
        else:
            d["询价单号"] = last_inquiry
        if co:
            last_company = co
        else:
            d["公司名称"] = last_company
        out.append(d)
    return out


__all__ = ["EntityMatchService", "EntityMatchResult"]
