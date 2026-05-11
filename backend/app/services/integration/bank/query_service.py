"""Filtered query, statistics and description rendering for bank records."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.services.shared.db.sqlite_client import SqliteClient


@dataclass
class BankQueryFilters:
    bank_type: str = ""
    person_name: str = ""
    acct_no: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount_min: float | None = None
    amount_max: float | None = None
    start_time: str = ""
    end_time: str = ""
    day_time_start: str = ""
    day_time_end: str = ""


class BankQueryService:
    """Provide reusable query + stats + description capability."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._ensure_desc_templates()

    def query_unified_records(self, import_batch_id: str, filters: BankQueryFilters | None = None) -> list[dict[str, str]]:
        filters = filters or BankQueryFilters()
        sql = [
            """
            SELECT
                t.source_name AS data_source,
                t.bank_name AS bank_type,
                CASE
                    WHEN TRIM(COALESCE(t.person_name, '')) <> '' THEN t.person_name
                    ELSE COALESCE(a.person_name, '')
                END AS person_name,
                t.acct_no AS acct_no,
                t.txn_time AS txn_time,
                t.txn_direction AS txn_direction,
                COALESCE(NULLIF(t.currency, ''), 'CNY') AS currency,
                t.txn_amount AS amount,
                t.balance AS balance,
                t.counterparty_name AS counterparty_name,
                t.counterparty_account AS counterparty_account,
                t.summary AS txn_desc,
                t.remark AS remark
            FROM std_bank_txn t
            LEFT JOIN (
                SELECT acct_no, MAX(person_name) AS person_name
                FROM std_bank_account
                WHERE person_name IS NOT NULL AND TRIM(person_name) <> ''
                GROUP BY acct_no
                HAVING COUNT(DISTINCT person_name)=1
            ) a ON a.acct_no=t.acct_no
            WHERE t.import_batch_id=?
              AND NOT (
                TRIM(COALESCE(t.acct_no, ''))=''
                AND TRIM(COALESCE(t.txn_time, ''))=''
                AND TRIM(COALESCE(t.txn_amount, ''))=''
                AND (
                  COALESCE(t.person_name, '') LIKE '%数据截至%'
                  OR COALESCE(t.person_name, '') LIKE '%非实时数据%'
                  OR COALESCE(t.person_name, '') LIKE '%生产系统为准%'
                  OR COALESCE(t.person_name, '') LIKE '%综合查控平台%'
                  OR COALESCE(t.summary, '') LIKE '%数据截至%'
                  OR COALESCE(t.summary, '') LIKE '%非实时数据%'
                  OR COALESCE(t.remark, '') LIKE '%数据截至%'
                  OR COALESCE(t.remark, '') LIKE '%非实时数据%'
                )
              )
            """
        ]
        params: list[Any] = [import_batch_id]
        self._append_filters(sql, params, filters)
        sql.append(" ORDER BY t.txn_time, t.std_id")

        rows = self._client.query_all("".join(sql), tuple(params))
        output: list[dict[str, str]] = []
        for row in rows:
            output.append(
                {
                    "data_source": "" if row[0] is None else str(row[0]),
                    "bank_type": "" if row[1] is None else str(row[1]),
                    "person_name": "" if row[2] is None else str(row[2]),
                    "acct_no": "" if row[3] is None else str(row[3]),
                    "txn_time": "" if row[4] is None else str(row[4]),
                    "txn_direction": "" if row[5] is None else str(row[5]),
                    "currency": "" if row[6] is None else str(row[6]),
                    "amount": "" if row[7] is None else str(row[7]),
                    "balance": "" if row[8] is None else str(row[8]),
                    "counterparty_name": "" if row[9] is None else str(row[9]),
                    "counterparty_account": "" if row[10] is None else str(row[10]),
                    "txn_desc": "" if row[11] is None else str(row[11]),
                    "remark": "" if row[12] is None else str(row[12]),
                }
            )
        if filters.day_time_start and filters.day_time_end:
            output = [
                row
                for row in output
                if self._match_day_time(row.get("txn_time", ""), filters.day_time_start, filters.day_time_end)
            ]
        return output

    def get_filter_options(self, import_batch_id: str) -> dict[str, list[str]]:
        """Return distinct options for dialog dropdowns in current batch."""
        rows = self._client.query_all(
            """
            SELECT DISTINCT
                TRIM(COALESCE(t.bank_name, '')) AS bank_type,
                TRIM(
                    CASE
                        WHEN TRIM(COALESCE(t.person_name, '')) <> '' THEN t.person_name
                        ELSE COALESCE(a.person_name, '')
                    END
                ) AS person_name,
                TRIM(COALESCE(t.acct_no, '')) AS acct_no,
                TRIM(COALESCE(t.counterparty_name, '')) AS counterparty_name,
                TRIM(COALESCE(t.counterparty_account, '')) AS counterparty_account
            FROM std_bank_txn t
            LEFT JOIN (
                SELECT acct_no, MAX(person_name) AS person_name
                FROM std_bank_account
                WHERE import_batch_id=?
                  AND person_name IS NOT NULL
                  AND TRIM(person_name) <> ''
                GROUP BY acct_no
            ) a ON a.acct_no=t.acct_no
            WHERE t.import_batch_id=?
              AND NOT (
                TRIM(COALESCE(t.acct_no, ''))=''
                AND TRIM(COALESCE(t.txn_time, ''))=''
                AND TRIM(COALESCE(t.txn_amount, ''))=''
                AND (
                  COALESCE(t.person_name, '') LIKE '%数据截至%'
                  OR COALESCE(t.person_name, '') LIKE '%非实时数据%'
                  OR COALESCE(t.person_name, '') LIKE '%生产系统为准%'
                  OR COALESCE(t.person_name, '') LIKE '%综合查控平台%'
                  OR COALESCE(t.summary, '') LIKE '%数据截至%'
                  OR COALESCE(t.summary, '') LIKE '%非实时数据%'
                  OR COALESCE(t.remark, '') LIKE '%数据截至%'
                  OR COALESCE(t.remark, '') LIKE '%非实时数据%'
                )
              )
            """,
            (import_batch_id, import_batch_id),
        )
        options = {
            "bank_type": set(),
            "person_name": set(),
            "acct_no": set(),
            "counterparty_name": set(),
            "counterparty_account": set(),
        }
        for row in rows:
            values = {
                "bank_type": row[0],
                "person_name": row[1],
                "acct_no": row[2],
                "counterparty_name": row[3],
                "counterparty_account": row[4],
            }
            for key, value in values.items():
                text = "" if value is None else str(value).strip()
                if text:
                    options[key].add(text)
        return {key: sorted(vals) for key, vals in options.items()}

    def summarize(self, records: list[dict[str, str]]) -> dict[str, Any]:
        count = len(records)
        in_total = 0.0
        out_total = 0.0
        by_currency: dict[str, float] = {}
        persons = set()
        counterparties = set()
        cp_amounts: dict[str, float] = {}
        time_period_stats: dict[str, int] = {"凌晨": 0, "白天": 0, "夜间": 0}
        remark_tag_stats: dict[str, int] = {}
        for row in records:
            amt = self._safe_float(row.get("amount", ""))
            direction = row.get("txn_direction", "")
            currency = (row.get("currency", "") or "CNY").upper()
            if direction == "收入":
                in_total += abs(amt)
            elif direction == "支出":
                out_total += abs(amt)
            by_currency[currency] = by_currency.get(currency, 0.0) + abs(amt)
            if row.get("person_name"):
                persons.add(row["person_name"])
            if row.get("counterparty_name"):
                counterparties.add(row["counterparty_name"])
                cp = row["counterparty_name"]
                cp_amounts[cp] = cp_amounts.get(cp, 0.0) + abs(amt)
            period = self._infer_time_period(row.get("txn_time", ""))
            if period:
                time_period_stats[period] = time_period_stats.get(period, 0) + 1
            for tag in self._extract_remark_tags(row.get("remark", "")):
                remark_tag_stats[tag] = remark_tag_stats.get(tag, 0) + 1
        top_counterparties = sorted(cp_amounts.items(), key=lambda x: x[1], reverse=True)[:5]
        total_cp_amount = sum(cp_amounts.values())
        top1_ratio = (top_counterparties[0][1] / total_cp_amount) if total_cp_amount and top_counterparties else 0.0
        top3_amount = sum(x[1] for x in top_counterparties[:3])
        top3_ratio = (top3_amount / total_cp_amount) if total_cp_amount else 0.0
        top_remark_tags = sorted(remark_tag_stats.items(), key=lambda x: x[1], reverse=True)[:8]
        return {
            "txn_count": count,
            "in_total": in_total,
            "out_total": out_total,
            "total_amount": in_total + out_total,
            "net_amount": in_total - out_total,
            "currency_breakdown": by_currency,
            "person_count": len(persons),
            "counterparty_count": len(counterparties),
            "top_counterparties": top_counterparties,
            "counterparty_concentration": {
                "top1_ratio": top1_ratio,
                "top3_ratio": top3_ratio,
                "total_counterparty_amount": total_cp_amount,
            },
            "time_period_stats": time_period_stats,
            "remark_tag_stats": top_remark_tags,
        }

    def render_description(self, filters: BankQueryFilters, summary: dict[str, Any]) -> str:
        tag = self._select_template_tag(filters)
        rows = self._client.query_all(
            "SELECT template_text FROM meta_desc_template WHERE template_tag=? AND is_active=1 LIMIT 1;",
            (tag,),
        )
        template = rows[0][0] if rows else "{start_time}到{end_time}期间共{txn_count}笔交易，总金额{total_amount}。"
        start_time = filters.start_time or "起始时间未限定"
        end_time = filters.end_time or "结束时间未限定"
        text = str(template).format(
            bank_type=filters.bank_type or "全部银行",
            person_name=filters.person_name or "全部主体",
            acct_no=filters.acct_no or "全部卡号",
            counterparty_name=filters.counterparty_name or "全部对手",
            counterparty_acct=filters.counterparty_account or "全部对手卡号",
            start_time=start_time,
            end_time=end_time,
            txn_count=summary.get("txn_count", 0),
            total_amount=f"{float(summary.get('total_amount', 0.0)):.2f}",
            currency_breakdown=self._format_currency_breakdown(summary.get("currency_breakdown", {})),
        )
        detail = (
            f"交易总览：共{int(summary.get('txn_count', 0))}笔，"
            f"总金额{float(summary.get('total_amount', 0.0)):.2f}；"
            f"收入{float(summary.get('in_total', 0.0)):.2f}，"
            f"支出{float(summary.get('out_total', 0.0)):.2f}，"
            f"净额{float(summary.get('net_amount', 0.0)):.2f}。"
        )
        subject_detail = (
            f"主体/对手：涉及主体{int(summary.get('person_count', 0))}个，"
            f"对手方{int(summary.get('counterparty_count', 0))}个。"
        )
        top_counter = self._format_top_counterparties(summary.get("top_counterparties", []))
        concentration = summary.get("counterparty_concentration", {})
        concentration_text = (
            f"对手集中度：Top1占比{float(concentration.get('top1_ratio', 0.0))*100:.2f}%，"
            f"Top3占比{float(concentration.get('top3_ratio', 0.0))*100:.2f}%。"
        )
        time_dist = self._format_time_period_stats(summary.get("time_period_stats", {}))
        remark_dist = self._format_remark_tag_stats(summary.get("remark_tag_stats", []))
        filter_phrase = self._build_filter_phrase(filters)
        return "\n".join(
            [
                f"筛选条件：{filter_phrase}",
                text,
                detail,
                subject_detail,
                f"币种明细：{self._format_currency_breakdown(summary.get('currency_breakdown', {}))}",
                concentration_text,
                f"主要对手：{top_counter}",
                f"时间分布：{time_dist}",
                f"异常标签：{remark_dist}",
            ]
        )

    def _append_filters(self, sql_parts: list[str], params: list[Any], filters: BankQueryFilters) -> None:
        if filters.bank_type:
            sql_parts.append(" AND COALESCE(t.bank_name, '') LIKE ?")
            params.append(f"%{filters.bank_type}%")
        if filters.person_name:
            sql_parts.append(
                " AND (COALESCE(t.person_name, '') LIKE ? OR EXISTS (SELECT 1 FROM std_bank_account a2 "
                "WHERE a2.acct_no=t.acct_no AND COALESCE(a2.person_name,'') LIKE ?))"
            )
            like = f"%{filters.person_name}%"
            params.extend([like, like])
        if filters.acct_no:
            sql_parts.append(" AND COALESCE(t.acct_no, '') LIKE ?")
            params.append(f"%{filters.acct_no}%")
        if filters.counterparty_name:
            sql_parts.append(" AND COALESCE(t.counterparty_name, '') LIKE ?")
            params.append(f"%{filters.counterparty_name}%")
        if filters.counterparty_account:
            sql_parts.append(" AND COALESCE(t.counterparty_account, '') LIKE ?")
            params.append(f"%{filters.counterparty_account}%")
        if filters.amount_min is not None:
            sql_parts.append(" AND ABS(CAST(COALESCE(NULLIF(t.txn_amount, ''), '0') AS REAL)) >= ?")
            params.append(float(filters.amount_min))
        if filters.amount_max is not None:
            sql_parts.append(" AND ABS(CAST(COALESCE(NULLIF(t.txn_amount, ''), '0') AS REAL)) <= ?")
            params.append(float(filters.amount_max))
        if filters.start_time:
            sql_parts.append(" AND COALESCE(t.txn_time, '') >= ?")
            params.append(filters.start_time)
        if filters.end_time:
            sql_parts.append(" AND COALESCE(t.txn_time, '') <= ?")
            params.append(filters.end_time)

    def _select_template_tag(self, filters: BankQueryFilters) -> str:
        if filters.person_name and (filters.acct_no or filters.counterparty_name or filters.counterparty_account):
            return "by_person_card_counterparty_time"
        if filters.person_name:
            return "by_person_time"
        if filters.amount_min is not None or filters.amount_max is not None:
            return "by_amount_time"
        return "by_time_only"

    def _ensure_desc_templates(self) -> None:
        defaults = {
            "by_time_only": "在{start_time}到{end_time}期间，共发生{txn_count}笔交易，总金额{total_amount}，分币种：{currency_breakdown}。",
            "by_person_time": "姓名为{person_name}的主体，在{start_time}到{end_time}期间共发生{txn_count}笔交易，累计金额{total_amount}，分币种：{currency_breakdown}。",
            "by_person_card_counterparty_time": "姓名为{person_name}的主体，在{start_time}到{end_time}期间通过{acct_no}与{counterparty_name}（{counterparty_acct}）往来{total_amount}，共{txn_count}笔，分币种：{currency_breakdown}。",
            "by_amount_time": "在{start_time}到{end_time}期间，按金额条件筛选命中{txn_count}笔交易，总金额{total_amount}，分币种：{currency_breakdown}。",
        }
        for tag, text in defaults.items():
            self._client.execute(
                """
                INSERT INTO meta_desc_template(template_tag, template_text, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(template_tag) DO NOTHING;
                """,
                (tag, text),
            )

    def _safe_float(self, value: str) -> float:
        text = (value or "").strip().replace(",", "")
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _format_currency_breakdown(self, mapping: dict[str, float]) -> str:
        if not mapping:
            return "无"
        items = sorted(mapping.items(), key=lambda x: x[0])
        return "；".join([f"币种{k}，金额{v:.2f}" for k, v in items])

    def _format_top_counterparties(self, pairs: list[tuple[str, float]]) -> str:
        if not pairs:
            return "无"
        return "；".join([f"{name}：{amt:.2f}" for name, amt in pairs])

    def _format_time_period_stats(self, stats: dict[str, int]) -> str:
        if not stats:
            return "无"
        order = ("凌晨", "白天", "夜间")
        parts = [f"{k}{int(stats.get(k, 0))}笔" for k in order]
        return "，".join(parts)

    def _format_remark_tag_stats(self, tags: list[tuple[str, int]]) -> str:
        if not tags:
            return "无明显异常标签"
        return "；".join([f"{name}({count})" for name, count in tags])

    def _build_filter_phrase(self, filters: BankQueryFilters) -> str:
        parts: list[str] = []
        if filters.bank_type:
            parts.append(f"银行类型={filters.bank_type}")
        if filters.person_name:
            parts.append(f"姓名={filters.person_name}")
        if filters.acct_no:
            parts.append(f"卡号={filters.acct_no}")
        if filters.counterparty_name:
            parts.append(f"对手名={filters.counterparty_name}")
        if filters.counterparty_account:
            parts.append(f"对手卡号={filters.counterparty_account}")
        if filters.amount_min is not None or filters.amount_max is not None:
            parts.append(f"金额区间={filters.amount_min if filters.amount_min is not None else '-∞'}~{filters.amount_max if filters.amount_max is not None else '+∞'}")
        if filters.start_time or filters.end_time:
            parts.append(f"时间段={filters.start_time or '不限'}至{filters.end_time or '不限'}")
        if filters.day_time_start and filters.day_time_end:
            parts.append(f"日内时段={filters.day_time_start}至{filters.day_time_end}")
        return "，".join(parts) if parts else "未设置条件（全量）"

    def _match_day_time(self, txn_time: str, start_hms: str, end_hms: str) -> bool:
        raw = (txn_time or "").strip()
        if not raw:
            return False
        match = re.search(r"(\d{2})[:\.-](\d{2})[:\.-](\d{2})", raw)
        if not match:
            return False
        t = f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
        if start_hms <= end_hms:
            return start_hms <= t <= end_hms
        return t >= start_hms or t <= end_hms

    def _infer_time_period(self, txn_time: str) -> str:
        raw = (txn_time or "").strip()
        if not raw:
            return ""
        match = re.search(r"(\d{2})[:\.-](\d{2})[:\.-](\d{2})", raw)
        if not match:
            return ""
        hour = int(match.group(1))
        if 0 <= hour < 6:
            return "凌晨"
        if 6 <= hour < 18:
            return "白天"
        return "夜间"

    def _extract_remark_tags(self, remark: str) -> list[str]:
        text = (remark or "").strip()
        if not text:
            return []
        return [x.strip() for x in text.split(";") if x.strip()]
