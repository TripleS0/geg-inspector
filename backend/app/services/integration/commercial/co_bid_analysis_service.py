"""Co-bidding pattern analysis for a target company in commercial bid data."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.integration.commercial.analysis_service import (
    CommercialAnalysisFilters,
    CommercialAnalysisService,
)
from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.shared.db.sqlite_client import SqliteClient

_DEFAULT_THRESHOLDS: dict[str, float | int] = {
    "min_shared_inquiries": 3,
    "min_co_rate": 0.25,
    "min_rotating_exclusive_wins": 4,
    "min_alternation_score": 0.55,
}


@dataclass(frozen=True)
class CoBidAnalysisParams:
    company_name: str = ""
    purchaser: str = ""
    start_time: str = ""
    end_time: str = ""


def _norm(text: str) -> str:
    return normalize_enterprise_name(text)


def _alternation_score(sequence: list[str]) -> float:
    """Return ratio of adjacent pairs that differ (0–1)."""
    if len(sequence) < 2:
        return 0.0
    flips = sum(1 for i in range(1, len(sequence)) if sequence[i] != sequence[i - 1])
    return flips / (len(sequence) - 1)


def load_co_bid_thresholds(client: SqliteClient | None = None) -> dict[str, float | int]:
    """Load R008 thresholds from cfg_risk_rule (configured in 模型管理)."""
    db = client or SqliteClient()
    rows = db.query_all(
        "SELECT enabled, params_json FROM cfg_risk_rule WHERE rule_code='R008' LIMIT 1;"
    )
    thresholds = dict(_DEFAULT_THRESHOLDS)
    if not rows:
        return thresholds
    enabled, params_json = rows[0]
    if not int(enabled or 0):
        return thresholds
    try:
        params = json.loads(params_json or "{}")
    except json.JSONDecodeError:
        params = {}
    for key, default in _DEFAULT_THRESHOLDS.items():
        raw = params.get(key, default)
        try:
            thresholds[key] = int(raw) if key.endswith("_wins") or key == "min_shared_inquiries" else float(raw)
        except (TypeError, ValueError):
            thresholds[key] = default
    return thresholds


class CommercialCoBidAnalysisService:
    """Analyze co-bidding companions and suspicious patterns for one company."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()
        self._analysis = CommercialAnalysisService(self._client)

    def analyze(self, commercial_batch_id: str, params: CoBidAnalysisParams) -> dict[str, Any]:
        keyword = (params.company_name or "").strip()
        if not keyword:
            return self._empty_result("", "请指定要分析的企业名称")

        thresholds = load_co_bid_thresholds(self._client)
        filters = CommercialAnalysisFilters(
            purchaser=params.purchaser,
            start_time=params.start_time,
            end_time=params.end_time,
        )
        records = [
            r
            for r in self._analysis._load_records(commercial_batch_id)
            if self._analysis._match_filters(r, filters)
        ]
        if not records:
            return self._empty_result(keyword, "当前批次无可用记录")

        ctx = self._build_inquiry_context(records)
        target_norm, target_display, suggestions = self._resolve_target(keyword, ctx["company_display"])
        if not target_norm:
            hint = ""
            if suggestions:
                hint = f"是否要找：{'、'.join(suggestions[:5])}"
            return self._empty_result(
                keyword,
                f"未找到名称匹配「{keyword}」的企业。{hint}".strip(),
            )

        target_inquiries = sorted(
            ctx["company_inquiries"].get(target_norm, set()),
            key=lambda inq: (ctx["inquiry_time"].get(inq, ""), inq),
        )
        if not target_inquiries:
            return self._empty_result(target_display, "该企业无参标记录")

        min_shared = max(1, int(thresholds["min_shared_inquiries"]))
        target_wins = ctx["company_wins"].get(target_norm, set())
        companions = self._analyze_companions(
            target_norm=target_norm,
            target_display=target_display,
            target_inquiries=target_inquiries,
            target_wins=target_wins,
            ctx=ctx,
            thresholds=thresholds,
            min_shared=min_shared,
        )
        inquiries_out = self._build_inquiry_details(target_norm, target_inquiries, ctx)
        graph = self._build_graph(target_norm, target_display, companions)

        return {
            "target_company": target_display,
            "target_company_norm": target_norm,
            "participation_count": len(target_inquiries),
            "win_count": len(target_wins & set(target_inquiries)),
            "description": self._render_description(target_display, companions, len(target_inquiries)),
            "thresholds": thresholds,
            "inquiries": inquiries_out,
            "companions": companions,
            "graph": graph,
        }

    def _empty_result(self, company: str, message: str) -> dict[str, Any]:
        return {
            "target_company": company,
            "target_company_norm": "",
            "participation_count": 0,
            "win_count": 0,
            "description": message,
            "thresholds": load_co_bid_thresholds(self._client),
            "inquiries": [],
            "companions": [],
            "graph": {"nodes": [], "links": [], "categories": []},
        }

    def _build_inquiry_context(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        inquiry_companies: dict[str, set[str]] = defaultdict(set)
        company_inquiries: dict[str, set[str]] = defaultdict(set)
        company_display: dict[str, str] = {}
        inquiry_winners: dict[str, set[str]] = defaultdict(set)
        company_wins: dict[str, set[str]] = defaultdict(set)
        inquiry_meta: dict[str, dict[str, str]] = {}
        inquiry_time: dict[str, str] = {}

        for row in records:
            inquiry = str(row.get("inquiry_no") or "").strip()
            company = str(row.get("company_name") or "").strip()
            if not inquiry or not company:
                continue
            cn = _norm(company)
            if not cn:
                continue
            inquiry_companies[inquiry].add(cn)
            company_inquiries[cn].add(inquiry)
            company_display.setdefault(cn, company)
            inquiry_meta.setdefault(
                inquiry,
                {
                    "inquiry_no": inquiry,
                    "purchaser": str(row.get("purchaser") or ""),
                    "item_name": str(row.get("item_name") or ""),
                    "inquiry_time": str(row.get("inquiry_time") or ""),
                },
            )
            t = str(row.get("inquiry_time") or "").strip()
            if t and not inquiry_time.get(inquiry):
                inquiry_time[inquiry] = t
            if bool(row.get("is_winner")):
                inquiry_winners[inquiry].add(cn)
                company_wins[cn].add(inquiry)

        return {
            "inquiry_companies": inquiry_companies,
            "company_inquiries": company_inquiries,
            "company_display": company_display,
            "inquiry_winners": inquiry_winners,
            "company_wins": company_wins,
            "inquiry_meta": inquiry_meta,
            "inquiry_time": inquiry_time,
        }

    def _resolve_target(
        self,
        keyword: str,
        company_display: dict[str, str],
    ) -> tuple[str, str, list[str]]:
        keyword = keyword.strip()
        if not keyword:
            return "", "", []
        kw_norm = _norm(keyword)
        kw_lower = keyword.lower()

        scored: list[tuple[int, str, str]] = []
        for cn, name in company_display.items():
            name_lower = name.lower()
            score = 0
            if name == keyword:
                score = 100
            elif kw_norm and cn == kw_norm:
                score = 95
            elif keyword in name or name in keyword:
                score = 85
            elif kw_lower in name_lower or name_lower in kw_lower:
                score = 75
            elif kw_norm and (kw_norm in cn or cn in kw_norm):
                score = 65
            if score:
                scored.append((score, cn, name))

        if not scored:
            return "", "", []

        scored.sort(key=lambda item: (-item[0], len(item[2]), item[2]))
        best_cn, best_name = scored[0][1], scored[0][2]
        suggestions = [name for _score, cn, name in scored[1:8] if cn != best_cn]
        return best_cn, best_name, suggestions

    def _analyze_companions(
        self,
        *,
        target_norm: str,
        target_display: str,
        target_inquiries: list[str],
        target_wins: set[str],
        ctx: dict[str, Any],
        thresholds: dict[str, float | int],
        min_shared: int,
    ) -> list[dict[str, Any]]:
        inquiry_companies: dict[str, set[str]] = ctx["inquiry_companies"]
        inquiry_winners: dict[str, set[str]] = ctx["inquiry_winners"]
        company_display: dict[str, str] = ctx["company_display"]
        inquiry_time: dict[str, str] = ctx["inquiry_time"]

        min_co_rate = float(thresholds["min_co_rate"])
        min_rotating_wins = int(thresholds["min_rotating_exclusive_wins"])
        min_alt_score = float(thresholds["min_alternation_score"])

        partner_stats: dict[str, dict[str, Any]] = {}
        target_total = len(target_inquiries)

        for inq in target_inquiries:
            participants = inquiry_companies.get(inq, set())
            winners = inquiry_winners.get(inq, set())
            target_won = target_norm in winners
            for partner_norm in participants:
                if partner_norm == target_norm:
                    continue
                stat = partner_stats.setdefault(
                    partner_norm,
                    {
                        "shared_inquiries": 0,
                        "target_wins_together": 0,
                        "partner_wins_together": 0,
                        "both_lose_together": 0,
                        "other_wins_together": 0,
                        "exclusive_win_sequence": [],
                        "shared_inquiry_nos": [],
                    },
                )
                stat["shared_inquiries"] += 1
                stat["shared_inquiry_nos"].append(inq)
                partner_won = partner_norm in winners
                if target_won and partner_won:
                    stat["target_wins_together"] += 1
                    stat["partner_wins_together"] += 1
                elif target_won:
                    stat["target_wins_together"] += 1
                elif partner_won:
                    stat["partner_wins_together"] += 1
                elif winners:
                    stat["other_wins_together"] += 1
                else:
                    stat["both_lose_together"] += 1

                if len(winners) == 1 and (target_norm in winners or partner_norm in winners):
                    winner = next(iter(winners))
                    stat["exclusive_win_sequence"].append(
                        (inquiry_time.get(inq, ""), inq, winner)
                    )

        companions: list[dict[str, Any]] = []
        for partner_norm, stat in partner_stats.items():
            shared = int(stat["shared_inquiries"])
            if shared < min_shared:
                continue
            co_rate = round(shared / max(target_total, 1), 4)
            both_lose_rate = round(stat["both_lose_together"] / shared, 4)
            target_win_rate = round(stat["target_wins_together"] / shared, 4)
            partner_win_rate = round(stat["partner_wins_together"] / shared, 4)
            other_win_rate = round(stat["other_wins_together"] / shared, 4)

            patterns: list[str] = []
            pattern_detail: dict[str, Any] = {}

            if shared >= min_shared and co_rate >= min_co_rate:
                patterns.append("高频陪标")
                pattern_detail["high_co_bid"] = {"shared": shared, "co_rate": co_rate}

            seq_items = sorted(stat["exclusive_win_sequence"], key=lambda x: (x[0], x[1]))
            win_seq = [item[2] for item in seq_items]
            alt_score = _alternation_score(win_seq)
            distinct_winners = {w for w in win_seq if w}
            if (
                len(win_seq) >= min_rotating_wins
                and len(distinct_winners) == 2
                and target_norm in distinct_winners
                and partner_norm in distinct_winners
                and alt_score >= min_alt_score
            ):
                patterns.append("轮流中标")
                pattern_detail["rotating_win"] = {
                    "alternation_score": round(alt_score, 4),
                    "exclusive_win_count": len(win_seq),
                    "win_sequence": [
                        {
                            "inquiry_no": item[1],
                            "winner_norm": item[2],
                            "winner": company_display.get(item[2], item[2]),
                        }
                        for item in seq_items
                    ],
                }

            companions.append(
                {
                    "company_name": company_display.get(partner_norm, partner_norm),
                    "company_norm": partner_norm,
                    "shared_inquiries": shared,
                    "co_rate": co_rate,
                    "target_wins_together": stat["target_wins_together"],
                    "partner_wins_together": stat["partner_wins_together"],
                    "both_lose_together": stat["both_lose_together"],
                    "other_wins_together": stat["other_wins_together"],
                    "target_win_rate_together": target_win_rate,
                    "partner_win_rate_together": partner_win_rate,
                    "both_lose_rate_together": both_lose_rate,
                    "patterns": patterns,
                    "pattern_detail": pattern_detail,
                    "shared_inquiry_nos": stat["shared_inquiry_nos"],
                }
            )

        companions.sort(
            key=lambda row: (
                -len(row["patterns"]),
                -row["shared_inquiries"],
                -row["co_rate"],
            )
        )
        return companions

    def _build_inquiry_details(
        self,
        target_norm: str,
        target_inquiries: list[str],
        ctx: dict[str, Any],
    ) -> list[dict[str, Any]]:
        company_display: dict[str, str] = ctx["company_display"]
        out: list[dict[str, Any]] = []
        for inq in target_inquiries:
            meta = ctx["inquiry_meta"].get(inq, {})
            participants = ctx["inquiry_companies"].get(inq, set())
            winners = ctx["inquiry_winners"].get(inq, set())
            out.append(
                {
                    "inquiry_no": inq,
                    "purchaser": meta.get("purchaser", ""),
                    "item_name": meta.get("item_name", ""),
                    "inquiry_time": meta.get("inquiry_time", ""),
                    "participants": [company_display.get(c, c) for c in sorted(participants)],
                    "participant_count": len(participants),
                    "winners": [company_display.get(w, w) for w in sorted(winners)],
                    "target_won": target_norm in winners,
                }
            )
        return out

    def _build_graph(
        self,
        target_norm: str,
        target_display: str,
        companions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        categories = [
            {"name": "分析目标"},
            {"name": "陪标关联"},
            {"name": "可疑模式"},
        ]
        nodes = [
            {
                "id": target_norm,
                "name": target_display,
                "category": 0,
                "symbolSize": 56,
                "value": 0,
            }
        ]
        links: list[dict[str, Any]] = []
        for comp in companions[:30]:
            partner_norm = str(comp["company_norm"])
            has_pattern = bool(comp["patterns"])
            nodes.append(
                {
                    "id": partner_norm,
                    "name": str(comp["company_name"]),
                    "category": 2 if has_pattern else 1,
                    "symbolSize": 28 + min(int(comp["shared_inquiries"]), 20),
                    "value": int(comp["shared_inquiries"]),
                    "patterns": comp["patterns"],
                }
            )
            links.append(
                {
                    "source": target_norm,
                    "target": partner_norm,
                    "value": int(comp["shared_inquiries"]),
                    "label": {
                        "show": True,
                        "formatter": "、".join(comp["patterns"]) or f"{comp['shared_inquiries']}次同场",
                    },
                    "lineStyle": {
                        "width": 1 + min(int(comp["shared_inquiries"]) // 2, 8),
                        "type": "dashed" if has_pattern else "solid",
                    },
                }
            )
        return {"nodes": nodes, "links": links, "categories": categories}

    def _render_description(
        self,
        target: str,
        companions: list[dict[str, Any]],
        participation: int,
    ) -> str:
        flagged = [c for c in companions if c["patterns"]]
        if not companions:
            return f"「{target}」共参与 {participation} 个询价项目，未发现满足阈值的高频同场企业。"
        if not flagged:
            return (
                f"「{target}」共参与 {participation} 个询价项目，"
                f"发现 {len(companions)} 家高频同场企业，暂未触发高频陪标/轮流中标模式。"
            )
        names = "、".join(c["company_name"] for c in flagged[:5])
        return (
            f"「{target}」共参与 {participation} 个询价项目，"
            f"{len(flagged)} 家同场企业存在可疑模式（{names}）。"
            "项目唯一标识已统一为询价单号（旧网=项目编码，新网=寻源单号）。"
        )
