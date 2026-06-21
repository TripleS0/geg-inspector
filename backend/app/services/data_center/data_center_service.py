"""Data center: unified record listing, deletion and dashboard statistics."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.shared.db.sqlite_client import SqliteClient

SOURCE_LABELS: dict[str, str] = {
    "bank": "银行流水",
    "wechat": "微信转账",
    "telecom": "通讯话单",
    "commercial": "商务网",
    "enterprise": "工商信息",
}


class DataCenterService:
    def __init__(self, client: SqliteClient) -> None:
        self._client = client

    def _case_batch_ids(self, case_id: int) -> list[str]:
        rows = self._client.query_all(
            "SELECT import_batch_id FROM rel_case_batch WHERE case_id=?;",
            (case_id,),
        )
        return [str(row[0]) for row in rows]

    def _batch_clause(self, case_id: int | None, batch_id: str | None) -> tuple[str, list[Any]]:
        if batch_id:
            return "AND import_batch_id=?", [batch_id.strip()]
        if case_id:
            batch_ids = self._case_batch_ids(case_id)
            if not batch_ids:
                return "AND 1=0", []
            placeholders = ",".join("?" * len(batch_ids))
            return f"AND import_batch_id IN ({placeholders})", batch_ids
        return "", []

    def list_records(
        self,
        *,
        case_id: int | None = None,
        batch_id: str | None = None,
        source_type: str | None = None,
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        batch_clause, batch_params = self._batch_clause(case_id, batch_id)
        kw = (keyword or "").strip()
        lim = max(1, min(int(limit), 200))
        off = max(0, int(offset))
        st = (source_type or "all").strip()

        txn_kw_clause = ""
        txn_kw_params: list[Any] = []
        ent_kw_clause = ""
        ent_kw_params: list[Any] = []
        if kw:
            like = f"%{kw}%"
            txn_kw_clause = """
                AND (
                    COALESCE(counterparty_name, '') LIKE ?
                    OR COALESCE(person_name, '') LIKE ?
                    OR COALESCE(summary, '') LIKE ?
                    OR COALESCE(source_name, '') LIKE ?
                    OR COALESCE(import_batch_id, '') LIKE ?
                )
            """
            txn_kw_params = [like, like, like, like, like]
            ent_kw_clause = """
                AND (
                    enterprise_name LIKE ?
                    OR source_file_name LIKE ?
                    OR import_batch_id LIKE ?
                )
            """
            ent_kw_params = [like, like, like]

        include_txn = st in ("all", "bank", "wechat", "telecom", "commercial")
        include_ent = st in ("all", "enterprise")
        txn_src_clause = ""
        txn_src_params: list[Any] = []
        if st not in ("all", "enterprise"):
            txn_src_clause = "AND source_type=?"
            txn_src_params = [st]

        parts: list[str] = []
        params: list[Any] = []
        if include_txn:
            parts.append(
                f"""
                SELECT 'txn' AS record_kind, std_id AS record_id, source_type, import_batch_id,
                       COALESCE(counterparty_name, person_name, summary, '—') AS content,
                       COALESCE(txn_time, standardized_at, '') AS record_date,
                       COALESCE(source_name, '') AS source_file,
                       COALESCE(NULLIF(txn_time, ''), standardized_at, '') AS sort_key
                FROM std_bank_txn
                WHERE 1=1 {batch_clause} {txn_src_clause} {txn_kw_clause}
                """
            )
            params.extend(batch_params + txn_src_params + txn_kw_params)
        if include_ent:
            parts.append(
                f"""
                SELECT 'enterprise' AS record_kind, enterprise_id AS record_id, 'enterprise' AS source_type,
                       import_batch_id, enterprise_name AS content,
                       COALESCE(establish_date, imported_at, '') AS record_date,
                       source_file_name AS source_file,
                       COALESCE(NULLIF(establish_date, ''), imported_at, '') AS sort_key
                FROM std_enterprise_profile
                WHERE 1=1 {batch_clause} {ent_kw_clause}
                """
            )
            params.extend(batch_params + ent_kw_params)

        if not parts:
            return {"items": [], "total": 0, "limit": lim, "offset": off}

        union_sql = " UNION ALL ".join(parts)
        rows = self._client.query_all(
            f"""
            SELECT record_kind, record_id, source_type, import_batch_id, content, record_date, source_file
            FROM ({union_sql})
            ORDER BY sort_key DESC, record_id DESC
            LIMIT ? OFFSET ?;
            """,
            tuple(params + [lim, off]),
        )

        items = [
            {
                "record_kind": str(row[0]),
                "record_id": int(row[1]),
                "source_type": str(row[2]),
                "source_type_label": SOURCE_LABELS.get(str(row[2]), str(row[2])),
                "import_batch_id": str(row[3]),
                "content": str(row[4]),
                "record_date": self._format_date(str(row[5])),
                "source_file": str(row[6]) or "—",
            }
            for row in rows
        ]

        total = self._count_total(
            batch_clause,
            batch_params,
            include_txn,
            include_ent,
            txn_src_clause,
            txn_src_params,
            txn_kw_clause,
            txn_kw_params,
            ent_kw_clause,
            ent_kw_params,
        )
        return {"items": items, "total": total, "limit": lim, "offset": off}

    def _count_total(
        self,
        batch_clause: str,
        batch_params: list[Any],
        include_txn: bool,
        include_ent: bool,
        txn_src_clause: str,
        txn_src_params: list[Any],
        txn_kw_clause: str,
        txn_kw_params: list[Any],
        ent_kw_clause: str,
        ent_kw_params: list[Any],
    ) -> int:
        total = 0
        if include_txn:
            rows = self._client.query_all(
                f"SELECT COUNT(*) FROM std_bank_txn WHERE 1=1 {batch_clause} {txn_src_clause} {txn_kw_clause};",
                tuple(batch_params + txn_src_params + txn_kw_params),
            )
            total += int(rows[0][0]) if rows else 0
        if include_ent:
            rows = self._client.query_all(
                f"SELECT COUNT(*) FROM std_enterprise_profile WHERE 1=1 {batch_clause} {ent_kw_clause};",
                tuple(batch_params + ent_kw_params),
            )
            total += int(rows[0][0]) if rows else 0
        return total

    def delete_records(self, items: list[dict[str, Any]]) -> dict[str, int]:
        deleted = 0
        for item in items:
            kind = str(item.get("record_kind") or "")
            rid = int(item.get("record_id") or 0)
            if not rid:
                continue
            if kind == "txn":
                self._client.execute("DELETE FROM std_bank_txn WHERE std_id=?;", (rid,))
                deleted += 1
            elif kind == "enterprise":
                self._client.execute(
                    "DELETE FROM rel_biz_enterprise_match WHERE enterprise_id=?;",
                    (rid,),
                )
                self._client.execute(
                    "DELETE FROM std_enterprise_profile WHERE enterprise_id=?;",
                    (rid,),
                )
                deleted += 1
        return {"deleted": deleted}

    def get_dashboard(self, case_id: int | None = None) -> dict[str, Any]:
        batch_clause, batch_params = self._batch_clause(case_id, None)

        overview = self._overview_stats(batch_clause, batch_params, case_id)
        source_distribution = self._source_distribution(batch_clause, batch_params)
        timeline = self._timeline_series(batch_clause, batch_params)
        batch_ranking = self._batch_ranking(batch_clause, batch_params)
        person_ranking = self._person_ranking(batch_clause, batch_params, case_id)
        event_distribution = self._event_distribution(case_id) if case_id else []

        return {
            "case_id": case_id,
            "overview": overview,
            "source_distribution": source_distribution,
            "timeline": timeline,
            "batch_ranking": batch_ranking,
            "person_ranking": person_ranking,
            "event_distribution": event_distribution,
        }

    def _overview_stats(
        self,
        batch_clause: str,
        batch_params: list[Any],
        case_id: int | None,
    ) -> dict[str, int]:
        txn_rows = self._client.query_all(
            f"SELECT COUNT(*) FROM std_bank_txn WHERE 1=1 {batch_clause};",
            tuple(batch_params),
        )
        ent_rows = self._client.query_all(
            f"SELECT COUNT(*) FROM std_enterprise_profile WHERE 1=1 {batch_clause};",
            tuple(batch_params),
        )
        batch_count = 0
        if case_id:
            batch_count = len(self._case_batch_ids(case_id))
        else:
            meta = self._client.query_all(
                "SELECT COUNT(DISTINCT import_batch_id) FROM meta_bank_files;"
            )
            ent = self._client.query_all(
                "SELECT COUNT(DISTINCT import_batch_id) FROM std_enterprise_profile;"
            )
            batch_count = int(meta[0][0] if meta else 0) + int(ent[0][0] if ent else 0)

        case_rows = self._client.query_all("SELECT COUNT(*) FROM std_case;")
        person_count = 0
        if case_id:
            p_rows = self._client.query_all(
                "SELECT COUNT(*) FROM std_person WHERE case_id=?;",
                (case_id,),
            )
            person_count = int(p_rows[0][0]) if p_rows else 0

        return {
            "record_count": int(txn_rows[0][0] if txn_rows else 0) + int(ent_rows[0][0] if ent_rows else 0),
            "txn_count": int(txn_rows[0][0] if txn_rows else 0),
            "enterprise_count": int(ent_rows[0][0] if ent_rows else 0),
            "batch_count": batch_count,
            "case_count": int(case_rows[0][0] if case_rows else 0),
            "person_count": person_count,
        }

    def _source_distribution(
        self,
        batch_clause: str,
        batch_params: list[Any],
    ) -> list[dict[str, Any]]:
        rows = self._client.query_all(
            f"""
            SELECT source_type, COUNT(*) AS cnt
            FROM std_bank_txn
            WHERE 1=1 {batch_clause}
            GROUP BY source_type
            ORDER BY cnt DESC;
            """,
            tuple(batch_params),
        )
        items = [
            {
                "source_type": str(row[0]),
                "label": SOURCE_LABELS.get(str(row[0]), str(row[0])),
                "count": int(row[1]),
            }
            for row in rows
        ]
        ent_rows = self._client.query_all(
            f"SELECT COUNT(*) FROM std_enterprise_profile WHERE 1=1 {batch_clause};",
            tuple(batch_params),
        )
        ent_count = int(ent_rows[0][0]) if ent_rows else 0
        if ent_count:
            items.append({"source_type": "enterprise", "label": SOURCE_LABELS["enterprise"], "count": ent_count})
        return items

    def _timeline_series(
        self,
        batch_clause: str,
        batch_params: list[Any],
    ) -> dict[str, Any]:
        rows = self._client.query_all(
            f"""
            SELECT substr(COALESCE(NULLIF(txn_time, ''), standardized_at), 1, 7) AS month_key,
                   source_type,
                   COUNT(*) AS cnt
            FROM std_bank_txn
            WHERE 1=1 {batch_clause}
              AND COALESCE(NULLIF(txn_time, ''), standardized_at, '') <> ''
            GROUP BY month_key, source_type
            HAVING month_key IS NOT NULL AND length(month_key) >= 7
            ORDER BY month_key;
            """,
            tuple(batch_params),
        )
        months: list[str] = []
        series_map: dict[str, dict[str, int]] = defaultdict(dict)
        for row in rows:
            month = str(row[0])
            st = str(row[1])
            cnt = int(row[2])
            if month not in months:
                months.append(month)
            series_map[st][month] = cnt

        ent_rows = self._client.query_all(
            f"""
            SELECT substr(COALESCE(NULLIF(establish_date, ''), imported_at), 1, 7) AS month_key,
                   COUNT(*) AS cnt
            FROM std_enterprise_profile
            WHERE 1=1 {batch_clause}
              AND COALESCE(NULLIF(establish_date, ''), imported_at, '') <> ''
            GROUP BY month_key
            HAVING month_key IS NOT NULL AND length(month_key) >= 7
            ORDER BY month_key;
            """,
            tuple(batch_params),
        )
        for row in ent_rows:
            month = str(row[0])
            cnt = int(row[1])
            if month not in months:
                months.append(month)
            series_map.setdefault("enterprise", {})[month] = cnt

        months.sort()
        series: list[dict[str, Any]] = []
        for st, month_counts in series_map.items():
            series.append(
                {
                    "source_type": st,
                    "label": SOURCE_LABELS.get(st, st),
                    "data": [month_counts.get(m, 0) for m in months],
                }
            )
        return {"months": months, "series": series}

    def _batch_ranking(
        self,
        batch_clause: str,
        batch_params: list[Any],
        *,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        rows = self._client.query_all(
            f"""
            SELECT import_batch_id, source_type, COUNT(*) AS cnt
            FROM std_bank_txn
            WHERE 1=1 {batch_clause}
            GROUP BY import_batch_id, source_type
            ORDER BY cnt DESC
            LIMIT ?;
            """,
            tuple(batch_params + [limit]),
        )
        name_map = self._batch_name_map([str(row[0]) for row in rows])
        return [
            {
                "import_batch_id": str(row[0]),
                "batch_name": name_map.get(str(row[0]), str(row[0])[:8] + "…"),
                "source_type": str(row[1]),
                "source_type_label": SOURCE_LABELS.get(str(row[1]), str(row[1])),
                "count": int(row[2]),
            }
            for row in rows
        ]

    def _batch_name_map(self, batch_ids: list[str]) -> dict[str, str]:
        if not batch_ids:
            return {}
        placeholders = ",".join("?" * len(batch_ids))
        rows = self._client.query_all(
            f"SELECT import_batch_id, batch_name FROM meta_import_batch WHERE import_batch_id IN ({placeholders});",
            tuple(batch_ids),
        )
        return {str(row[0]): str(row[1]) for row in rows if str(row[1]).strip()}

    def _person_ranking(
        self,
        batch_clause: str,
        batch_params: list[Any],
        case_id: int | None,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        transfer_rows = self._client.query_all(
            f"""
            SELECT COALESCE(NULLIF(counterparty_name, ''), person_name, '未知') AS name,
                   COUNT(*) AS cnt
            FROM std_bank_txn
            WHERE 1=1 {batch_clause}
              AND source_type IN ('bank', 'wechat', 'commercial')
              AND COALESCE(NULLIF(counterparty_name, ''), person_name, '') <> ''
            GROUP BY name
            ORDER BY cnt DESC
            LIMIT ?;
            """,
            tuple(batch_params + [limit * 2]),
        )
        call_rows = self._client.query_all(
            f"""
            SELECT COALESCE(NULLIF(counterparty_name, ''), person_name, '未知') AS name,
                   COUNT(*) AS cnt
            FROM std_bank_txn
            WHERE 1=1 {batch_clause}
              AND source_type = 'telecom'
              AND COALESCE(NULLIF(counterparty_name, ''), person_name, '') <> ''
            GROUP BY name
            ORDER BY cnt DESC
            LIMIT ?;
            """,
            tuple(batch_params + [limit * 2]),
        )

        transfer_map = {str(row[0]): int(row[1]) for row in transfer_rows}
        call_map = {str(row[0]): int(row[1]) for row in call_rows}
        names = set(transfer_map) | set(call_map)

        if case_id:
            person_rows = self._client.query_all(
                "SELECT display_name FROM std_person WHERE case_id=?;",
                (case_id,),
            )
            for row in person_rows:
                names.add(str(row[0]))

        ranked: list[dict[str, Any]] = []
        for name in names:
            transfer_count = transfer_map.get(name, 0)
            call_count = call_map.get(name, 0)
            score = transfer_count + call_count
            if score <= 0:
                continue
            ranked.append(
                {
                    "person_name": name,
                    "transfer_count": transfer_count,
                    "call_count": call_count,
                    "total_score": score,
                }
            )
        ranked.sort(key=lambda x: x["total_score"], reverse=True)
        return ranked[:limit]

    def _event_distribution(self, case_id: int) -> list[dict[str, Any]]:
        try:
            from app.services.fusion.fusion_event_service import FusionEventService

            result = FusionEventService(self._client).scan_events(case_id)
            by_type = result.get("summary", {}).get("by_event_type", {})
            return [
                {"event_type": k, "count": int(v)}
                for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)
            ]
        except Exception:
            return []

    @staticmethod
    def _format_date(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "—"
        text = text.replace("T", " ").replace("/", ".")
        m = re.match(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", text)
        if m:
            return f"{m.group(1)}.{int(m.group(2))}.{int(m.group(3))}"
        if len(text) >= 10:
            return text[:10].replace("-", ".")
        return text
