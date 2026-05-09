"""Configurable risk rules for commercial bid data + enterprise profiles."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

from app.services.integration.commercial.entity_match_service import EntityMatchService
from app.services.integration.commercial.export_service import CommercialExportService
from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.shared.db.sqlite_client import SqliteClient


def _norm_company(text: str) -> str:
    """与工商匹配、rel 表 biz_company_name_norm 一致。"""
    return normalize_enterprise_name(text)


def _safe_float(text: str) -> float:
    t = (text or "").strip().replace(",", "")
    if not t:
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def _fill_forward(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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


class CommercialRiskAnalysisService:
    """Run R001–R006 heuristics and persist ana_risk_* rows."""

    def __init__(self, client: SqliteClient | None = None) -> None:
        self._client = client or SqliteClient()

    def run_full(
        self,
        commercial_batch_id: str,
        enterprise_import_batch_id: str | None = None,
    ) -> tuple[int, int]:
        """Rebuild entity matches, clear old risk rows, run rules. Returns (events, summaries)."""
        EntityMatchService(self._client).rebuild_matches(
            commercial_batch_id, enterprise_import_batch_id
        )
        self._client.execute("DELETE FROM ana_risk_event WHERE import_batch_id=?;", (commercial_batch_id,))
        self._client.execute("DELETE FROM ana_risk_summary WHERE import_batch_id=?;", (commercial_batch_id,))

        rules = self._load_rules()
        export_svc = CommercialExportService(self._client)
        raw_rows = export_svc._load_commercial_rows(commercial_batch_id)
        rows = _fill_forward(raw_rows)

        ctx = self._build_context(rows)
        legal_map = self._load_legal_by_company_norm(commercial_batch_id)

        for code, name, weight, params in rules:
            if code == "R001":
                self._rule_r001(commercial_batch_id, name, weight, params, ctx)
            elif code == "R002":
                self._rule_r002(commercial_batch_id, name, weight, params, ctx)
            elif code == "R003":
                self._rule_r003(commercial_batch_id, name, weight, params, ctx)
            elif code == "R004":
                self._rule_r004(commercial_batch_id, name, weight, params, ctx, legal_map)
            elif code == "R005":
                self._rule_r005(commercial_batch_id, name, weight, params, ctx)
            elif code == "R006":
                self._rule_r006(commercial_batch_id, name, weight, params, ctx)

        self._build_summaries(commercial_batch_id, ctx)
        ev_ct = int(
            self._client.query_all(
                "SELECT COUNT(*) FROM ana_risk_event WHERE import_batch_id=?;",
                (commercial_batch_id,),
            )[0][0]
        )
        sm_ct = int(
            self._client.query_all(
                "SELECT COUNT(*) FROM ana_risk_summary WHERE import_batch_id=?;",
                (commercial_batch_id,),
            )[0][0]
        )
        return ev_ct, sm_ct

    def _load_rules(self) -> list[tuple[str, str, float, dict[str, Any]]]:
        rows = self._client.query_all(
            """
            SELECT rule_code, rule_name, weight, params_json
            FROM cfg_risk_rule WHERE enabled=1 ORDER BY rule_code;
            """
        )
        out: list[tuple[str, str, float, dict[str, Any]]] = []
        for r in rows:
            try:
                params = json.loads(r[3] or "{}")
            except json.JSONDecodeError:
                params = {}
            out.append((str(r[0]), str(r[1]), float(r[2]), params))
        return out

    def _build_context(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        inquiry_companies: dict[str, set[str]] = defaultdict(set)
        company_inquiries: dict[str, set[str]] = defaultdict(set)
        company_display_name: dict[str, str] = {}
        inquiry_winner: dict[str, str] = {}
        inquiry_winner_amount: dict[str, float] = {}
        inquiry_company_prices: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        ordered_inquiries: list[str] = []

        seen_inq_order: list[str] = []
        for row in rows:
            inq = (row.get("询价单号") or "").strip()
            co = (row.get("公司名称") or "").strip()
            if inq and inq not in seen_inq_order:
                seen_inq_order.append(inq)
            win_raw = (row.get("中标供应商") or "").strip()
            if inq and win_raw:
                wn = _norm_company(win_raw)
                if wn:
                    inquiry_winner[inq] = wn
                    win_amt = _safe_float(row.get("中标金额(元)", ""))
                    if win_amt > 0 and inq not in inquiry_winner_amount:
                        inquiry_winner_amount[inq] = win_amt
            if inq and co:
                cn = _norm_company(co)
                if cn:
                    inquiry_companies[inq].add(cn)
                    company_inquiries[cn].add(inq)
                    if cn not in company_display_name:
                        company_display_name[cn] = co
                    px = _safe_float(row.get("含税单价(元)", ""))
                    if px > 0:
                        inquiry_company_prices[inq][cn].append(px)

        return {
            "inquiry_companies": inquiry_companies,
            "company_inquiries": company_inquiries,
            "company_display_name": company_display_name,
            "inquiry_winner": inquiry_winner,
            "inquiry_winner_amount": inquiry_winner_amount,
            "inquiry_company_prices": inquiry_company_prices,
            "ordered_inquiries": seen_inq_order,
        }

    def _load_legal_by_company_norm(self, commercial_batch_id: str) -> dict[str, str]:
        rows = self._client.query_all(
            """
            SELECT m.biz_company_name_norm, IFNULL(p.legal_person,'')
            FROM rel_biz_enterprise_match m
            JOIN std_enterprise_profile p ON p.enterprise_id = m.enterprise_id
            WHERE m.import_batch_id=?;
            """,
            (commercial_batch_id,),
        )
        out: dict[str, str] = {}
        for cn, lp in rows:
            c = str(cn or "").strip()
            legal = str(lp or "").strip()
            if c and legal:
                out[c] = legal
        return out

    def _insert_event(
        self,
        batch_id: str,
        code: str,
        title: str,
        weight: float,
        enterprise_norm: str,
        inquiry: str,
        evidence: dict[str, Any],
    ) -> None:
        base_score = 50.0 * float(weight)
        level = "medium"
        if base_score >= 70:
            level = "high"
        elif base_score < 35:
            level = "low"
        self._client.execute(
            """
            INSERT INTO ana_risk_event(
                import_batch_id, rule_code, rule_name, risk_level, risk_score,
                enterprise_name, inquiry_no, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                batch_id,
                code,
                title,
                level,
                base_score,
                enterprise_norm,
                inquiry or "",
                json.dumps(evidence, ensure_ascii=False),
            ),
        )

    def _rule_r001(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        min_shared = int(params.get("min_shared_inquiries", 3))
        inquiry_companies: dict[str, set[str]] = ctx["inquiry_companies"]
        companies = sorted({c for s in inquiry_companies.values() for c in s})
        for i, a in enumerate(companies):
            for b in companies[i + 1 :]:
                shared = len(ctx["company_inquiries"][a] & ctx["company_inquiries"][b])
                if shared >= min_shared:
                    ev = {
                        "口径": "两企业在不少于N个询价中同时出现（参标集合交集）",
                        "阈值N": min_shared,
                        "实际共同询价数": shared,
                        "企业A": a,
                        "企业B": b,
                    }
                    self._insert_event(batch_id, "R001", title, weight, a, "", ev)
                    self._insert_event(batch_id, "R001", title, weight, b, "", ev)

    def _rule_r002(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        min_inq = int(params.get("min_inquiries", 3))
        min_j = float(params.get("min_pair_overlap_ratio", 0.8))
        company_inquiries: dict[str, set[str]] = ctx["company_inquiries"]
        companies = [c for c in company_inquiries if len(company_inquiries[c]) >= min_inq]
        for i, a in enumerate(companies):
            for b in companies[i + 1 :]:
                sa, sb = company_inquiries[a], company_inquiries[b]
                inter = len(sa & sb)
                uni = len(sa | sb)
                if uni == 0:
                    continue
                jaccard = inter / uni
                if jaccard >= min_j:
                    ev = {
                        "口径": "两企业参标询价集合的 Jaccard 相似度",
                        "阈值": min_j,
                        "Jaccard": round(jaccard, 4),
                        "企业A": a,
                        "企业B": b,
                    }
                    self._insert_event(batch_id, "R002", title, weight, a, "", ev)
                    self._insert_event(batch_id, "R002", title, weight, b, "", ev)

    def _rule_r003(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        min_part = int(params.get("min_participations", 4))
        max_win_rate = float(params.get("max_win_rate", 0.15))
        min_co = int(params.get("min_co_winner_hits", 3))
        inquiry_winner: dict[str, str] = ctx["inquiry_winner"]
        company_inquiries: dict[str, set[str]] = ctx["company_inquiries"]
        for c, inquiries in company_inquiries.items():
            if len(inquiries) < min_part:
                continue
            wins = 0
            co_winner_counts: dict[str, int] = defaultdict(int)
            for inq in inquiries:
                w = inquiry_winner.get(inq, "")
                if w and (c == w or c in w or w in c):
                    wins += 1
                elif w:
                    co_winner_counts[w] += 1
            rate = wins / max(len(inquiries), 1)
            if rate > max_win_rate:
                continue
            best_w, best_n = "", 0
            for w, n in co_winner_counts.items():
                if n > best_n:
                    best_w, best_n = w, n
            if best_n < min_co:
                continue
            ev = {
                "口径": "参标次数多但中标占比低，且多次与同一中标方同场",
                "参标询价数": len(inquiries),
                "中标率": round(rate, 4),
                "中标率阈值": max_win_rate,
                "陪跑对象中标方(规范化)": best_w,
                "同场次数": best_n,
            }
            self._insert_event(batch_id, "R003", title, weight, c, "", ev)

    def _rule_r004(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
        legal_map: dict[str, str],
    ) -> None:
        inquiry_companies: dict[str, set[str]] = ctx["inquiry_companies"]
        for inq, cset in inquiry_companies.items():
            legals: dict[str, list[str]] = defaultdict(list)
            for c in cset:
                lp = legal_map.get(c, "")
                if lp:
                    legals[lp].append(c)
            for lp, group in legals.items():
                if len(group) < 2:
                    continue
                ev = {
                    "口径": "同一询价下多家参标主体工商法定代表人相同（依赖工商导入与名称匹配）",
                    "询价单号": inq,
                    "法定代表人": lp,
                    "涉及企业(规范化)": group,
                }
                for c in group:
                    self._insert_event(batch_id, "R004", title, weight, c, inq, ev)

    def _rule_r005(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        min_sup = int(params.get("min_suppliers_with_price", 3))
        max_cv = float(params.get("max_cv", 0.02))
        prices_map: dict[str, dict[str, list[float]]] = ctx["inquiry_company_prices"]
        for inq, cmap in prices_map.items():
            vals: list[float] = []
            for _cn, plist in cmap.items():
                if plist:
                    vals.append(sum(plist) / len(plist))
            if len(vals) < min_sup:
                continue
            mean = statistics.mean(vals)
            if mean <= 0:
                continue
            cv = (statistics.pstdev(vals) / mean) if len(vals) >= 2 else 0.0
            if cv <= max_cv:
                ev = {
                    "口径": "同一询价下多家含税单价均值离散系数过低",
                    "询价单号": inq,
                    "供应商数": len(vals),
                    "离散系数CV": round(cv, 6),
                    "CV阈值": max_cv,
                    "单价样本": [round(x, 4) for x in vals[:20]],
                }
                self._insert_event(batch_id, "R005", title, weight, "询价项目", inq, ev)

    def _rule_r006(
        self,
        batch_id: str,
        title: str,
        weight: float,
        params: dict[str, Any],
        ctx: dict[str, Any],
    ) -> None:
        win_need = int(params.get("min_distinct_winners", 3))
        window = int(params.get("window_size", 5))
        ordered: list[str] = ctx["ordered_inquiries"]
        winners: list[str] = []
        for inq in ordered:
            winners.append(ctx["inquiry_winner"].get(inq, ""))
        for i in range(len(winners)):
            chunk = winners[i : i + window]
            if len(chunk) < window:
                break
            distinct = {w for w in chunk if w}
            if len(distinct) >= win_need:
                ev = {
                    "口径": "连续多单中标方在固定集合内轮换（按询价单顺序窗口）",
                    "窗口": window,
                    "窗口内不同中标方数": len(distinct),
                    "中标方序列片段": chunk,
                    "对应询价单号": ordered[i : i + window],
                }
                self._insert_event(batch_id, "R006", title, weight, "轮换模式", ordered[i], ev)

    def _build_summaries(self, batch_id: str, ctx: dict[str, Any]) -> None:
        rows = self._client.query_all(
            """
            SELECT enterprise_name, rule_code, risk_score
            FROM ana_risk_event WHERE import_batch_id=?;
            """,
            (batch_id,),
        )
        company_inquiries: dict[str, set[str]] = ctx["company_inquiries"]
        company_display_name: dict[str, str] = ctx["company_display_name"]
        inquiry_winner: dict[str, str] = ctx["inquiry_winner"]
        inquiry_winner_amount: dict[str, float] = ctx["inquiry_winner_amount"]
        by_ent: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_score": 0.0, "hit_count": 0, "by_rule": defaultdict(int)}
        )
        for ent, code, score in rows:
            e = str(ent or "")
            c = str(code or "")
            sc = float(score or 0)
            if not e:
                continue
            by_ent[e]["total_score"] += sc
            by_ent[e]["hit_count"] += 1
            by_ent[e]["by_rule"][c] += 1
        all_entities = set(by_ent.keys()) | set(company_inquiries.keys())
        for ent in all_entities:
            data = by_ent[ent]
            total = float(data["total_score"])
            hits = int(data["hit_count"])
            inquiries = company_inquiries.get(ent, set())
            participation_count = len(inquiries)
            win_count = 0
            win_amount = 0.0
            for inq in inquiries:
                w = inquiry_winner.get(inq, "")
                if w and (w == ent or w in ent or ent in w):
                    win_count += 1
                    win_amount += float(inquiry_winner_amount.get(inq, 0.0))
            level = "low"
            if total >= 120 or hits >= 6:
                level = "high"
            elif total >= 60 or hits >= 3:
                level = "medium"
            detail = {
                "by_rule": {k: int(v) for k, v in dict(data["by_rule"]).items()},
                "participation_count": participation_count,
                "win_count": win_count,
                "win_amount": round(win_amount, 2),
            }
            self._client.execute(
                """
                INSERT INTO ana_risk_summary(
                    import_batch_id, enterprise_name, total_score, hit_count, risk_level, detail_json
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    batch_id,
                    company_display_name.get(ent, ent),
                    total,
                    hits,
                    level,
                    json.dumps(detail, ensure_ascii=False),
                ),
            )


__all__ = ["CommercialRiskAnalysisService"]
