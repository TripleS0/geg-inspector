"""Fixed multidimensional analysis modules for standardized bank transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.services.integration.bank.query_service import BankQueryService
from app.services.shared.db.sqlite_client import SqliteClient


class AnalysisModuleId:
    """Built-in analysis module identifiers (plain str constants, Py3.8+ compatible)."""

    LARGE_INOUT = "large_inout"
    LARGE_FLOW = "large_flow"
    SPECIAL_AMOUNT = "special_amount"
    SPECIAL_TIME = "special_time"


# chinese-calendar 返回的英文名 → 中文（国务院办公厅放假名称常用说法）
_STATUTORY_HOLIDAY_NAME_ZH: dict[str, str] = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明节",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午节",
    "Mid-autumn Festival": "中秋节",
    "National Day": "国庆节",
}


@dataclass
class ModuleParams:
    """Parameters for fixed analysis modules."""

    large_amount_threshold: float = 100_000.0
    top_n: int = 15
    repeat_amount_min_count: int = 3
    special_amount_whitelist: tuple[float, ...] = (
        520.0,
        521.0,
        1314.0,
        666.0,
        888.0,
        188.0,
        288.0,
    )


@dataclass
class ModuleResult:
    """Output of one module run."""

    module_id: str
    params: ModuleParams
    hit_records: list[dict[str, str]]
    summary: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)
    description: str = ""


def _safe_float(value: str | None) -> float:
    text = (value or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_dt(text: str) -> datetime | None:
    value = (text or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _counterparty_group_key(row: dict[str, str]) -> str:
    acct = (row.get("counterparty_account") or "").strip()
    if acct and acct not in ("未知账号",):
        return f"acct:{acct}"
    name = (row.get("counterparty_name") or "").strip()
    if name and name not in ("未知对手",):
        return f"name:{name}"
    return "unknown"


def _counterparty_display(row: dict[str, str], key: str) -> tuple[str, str]:
    acct = (row.get("counterparty_account") or "").strip()
    name = (row.get("counterparty_name") or "").strip()
    if key.startswith("acct:"):
        return key[5:], name
    if key.startswith("name:"):
        return "", key[5:]
    return acct, name


def filter_large_transactions(records: list[dict[str, str]], threshold: float) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in records:
        if abs(_safe_float(row.get("amount"))) >= threshold:
            out.append(row)
    return out


def aggregate_large_flow(
    large_records: list[dict[str, str]],
    top_n: int,
) -> list[dict[str, Any]]:
    """Aggregate by opponent account (fallback to name)."""
    groups: dict[str, dict[str, Any]] = {}
    for row in large_records:
        key = _counterparty_group_key(row)
        g = groups.setdefault(
            key,
            {
                "group_key": key,
                "counterparty_account": "",
                "counterparty_name": "",
                "in_total": 0.0,
                "out_total": 0.0,
                "count": 0,
            },
        )
        acct_disp, name_disp = _counterparty_display(row, key)
        if not g["counterparty_account"] and acct_disp:
            g["counterparty_account"] = acct_disp
        if not g["counterparty_name"] and name_disp:
            g["counterparty_name"] = name_disp
        amt = abs(_safe_float(row.get("amount")))
        direction = row.get("txn_direction", "")
        if direction == "收入":
            g["in_total"] += amt
        elif direction == "支出":
            g["out_total"] += amt
        g["count"] += 1
    rows: list[dict[str, Any]] = []
    for g in groups.values():
        g["net"] = g["in_total"] - g["out_total"]
        g["volume"] = g["in_total"] + g["out_total"]
        rows.append(g)
    rows.sort(key=lambda x: float(x["volume"]), reverse=True)
    return rows[: max(0, top_n)]


def classify_special_amount(row: dict[str, str], params: ModuleParams, amount_counts: dict[float, int]) -> list[str]:
    """仅金额维度标签（不写时间类）；不读取原始备注。用于规则统计与「特殊金额」模块备注。"""
    tags: list[str] = []
    amt = abs(_safe_float(row.get("amount")))
    if amt <= 0:
        return tags
    rounded = round(amt, 2)
    if rounded in params.special_amount_whitelist:
        tags.append(f"敏感金额：{rounded:g}元（常见示爱/吉利金额等）")
    if amt >= 1000 and amt % 10000 < 0.005:
        tags.append("金额特征：整万元（无角分尾数）")
    elif amt >= 100 and amt % 1000 < 0.005:
        tags.append("金额特征：整千元（无角分尾数）")
    cnt = amount_counts.get(rounded, 0)
    if cnt >= params.repeat_amount_min_count:
        tags.append(f"金额特征：重复金额（本批次内同金额出现≥{params.repeat_amount_min_count}次）")
    return tags


def build_amount_rounded_counts(records: list[dict[str, str]]) -> dict[float, int]:
    counts: dict[float, int] = {}
    for row in records:
        r = round(abs(_safe_float(row.get("amount"))), 2)
        if r <= 0:
            continue
        counts[r] = counts.get(r, 0) + 1
    return counts


@lru_cache(maxsize=1)
def _zhdate_class() -> Any:
    """Lunar calendar helper (CutePandaSh/zhdate, 1900–2100). None if not installed."""
    try:
        from zhdate import ZhDate  # type: ignore[import-not-found]

        return ZhDate
    except ImportError:
        return None


@lru_cache(maxsize=1)
def _chinese_calendar_module() -> Any:
    try:
        import chinese_calendar as cc  # type: ignore[import-not-found]

        return cc
    except ImportError:
        return None


def statutory_holiday_tag(dt: datetime) -> str | None:
    """中国法定节假日（依据 chinese-calendar 库数据）。无库或日期不在支持范围则返回 None。"""
    cc = _chinese_calendar_module()
    if cc is None:
        return None
    d = dt.date()
    try:
        if not cc.is_holiday(d):
            return None
        _ok, en_name = cc.get_holiday_detail(d)
        zh = _STATUTORY_HOLIDAY_NAME_ZH.get(en_name or "", en_name or "法定节假日")
        return (
            f"特殊日期：中国法定节假日·{zh}（当日按国务院公布的放假安排为休息日；"
            f"公历{d.isoformat()}）"
        )
    except Exception:
        return None


def cultural_festival_tags_for_date(dt: datetime) -> list[str]:
    """非国务院固定公历节日、但常用于特殊日期分析的日期（不含元旦，元旦以法定节假日为准）。"""
    tags: list[str] = []
    if dt.month == 2 and dt.day == 14:
        tags.append("特殊日期：西方情人节（每年公历2月14日）")
    if dt.month == 5 and dt.day == 20:
        tags.append("特殊日期：5·20网络情人节（每年公历5月20日）")
    ZhDate = _zhdate_class()
    if ZhDate is not None and 1900 <= dt.year <= 2100:
        try:
            lunar = ZhDate.from_datetime(dt)
        except (TypeError, ValueError, OverflowError):
            lunar = None
        if lunar is not None and lunar.lunar_month == 7 and lunar.lunar_day == 7 and not lunar.leap_month:
            tags.append(
                "特殊日期：七夕节（农历七月初七，按当年农历换算的公历日发生交易；非闰七月初七）"
            )
    return tags


def festival_tags_for_solar_date(dt: datetime) -> list[str]:
    """兼容旧测试入口：法定节假日 + 文化节日。"""
    tags: list[str] = []
    sh = statutory_holiday_tag(dt)
    if sh:
        tags.append(sh)
    tags.extend(cultural_festival_tags_for_date(dt))
    return tags


def classify_special_time(row: dict[str, str]) -> list[str]:
    """特殊时间/日期：深夜、凌晨（凌晨自00:01起）、法定节假日、特定文化日、七夕；不含周末；不读原始备注。"""
    tags: list[str] = []
    dt = _parse_dt(row.get("txn_time", ""))
    if dt is None:
        return tags
    h, m = dt.hour, dt.minute
    tmin = h * 60 + m
    if tmin >= 22 * 60:
        tags.append("特殊时间：深夜时段（当日22:00至24:00）")
    if 1 <= tmin < 6 * 60:
        tags.append("特殊时间：凌晨时段（当日00:01至06:00，不含0点整）")
    sh = statutory_holiday_tag(dt)
    if sh:
        tags.append(sh)
    for t in cultural_festival_tags_for_date(dt):
        if t not in tags:
            tags.append(t)
    return tags


def _join_remark(parts: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "；".join(out)


def row_with_filled_remark(row: dict[str, str], analysis_remark: str) -> dict[str, str]:
    """浅拷贝统一记录，仅覆盖备注为系统分析结论（原始备注不参与展示）。"""
    r = dict(row)
    r["remark"] = analysis_remark.strip()
    return r


def build_custom_filter_analysis_remark(
    row: dict[str, str],
    params: ModuleParams,
    amount_counts: dict[float, int],
) -> str:
    """自定义筛选导出：合并大额、特殊时间/日期、特殊金额等全部规则写入备注。"""
    parts: list[str] = []
    th = params.large_amount_threshold
    if abs(_safe_float(row.get("amount"))) >= th:
        parts.append(f"系统分析：大额交易（单笔绝对金额≥{th:g}元）")
    parts.extend(classify_special_time(row))
    parts.extend(classify_special_amount(row, params, amount_counts))
    return _join_remark(parts)


def run_module(
    import_batch_id: str,
    module_id: str,
    params: ModuleParams | None = None,
    client: SqliteClient | None = None,
) -> ModuleResult:
    """Load batch unified records, apply module rules, summarize and build description."""
    params = params or ModuleParams()
    query = BankQueryService(client)
    all_records = query.query_unified_records(import_batch_id, None)
    extra: dict[str, Any] = {}
    hit_records: list[dict[str, str]] = []

    if module_id == AnalysisModuleId.LARGE_INOUT:
        raw = filter_large_transactions(all_records, params.large_amount_threshold)
        th = params.large_amount_threshold
        for r in raw:
            hit_records.append(
                row_with_filled_remark(
                    r,
                    f"系统分析：大额进出（单笔绝对金额≥{th:g}元，方向：{r.get('txn_direction') or '未知'}）",
                )
            )
        large_in = sum(abs(_safe_float(r.get("amount"))) for r in raw if r.get("txn_direction") == "收入")
        large_out = sum(abs(_safe_float(r.get("amount"))) for r in raw if r.get("txn_direction") == "支出")
        extra["large_in_total"] = large_in
        extra["large_out_total"] = large_out
        extra["large_in_count"] = sum(1 for r in raw if r.get("txn_direction") == "收入")
        extra["large_out_count"] = sum(1 for r in raw if r.get("txn_direction") == "支出")
        extra["threshold"] = params.large_amount_threshold

    elif module_id == AnalysisModuleId.LARGE_FLOW:
        raw = filter_large_transactions(all_records, params.large_amount_threshold)
        th = params.large_amount_threshold
        for r in raw:
            hit_records.append(
                row_with_filled_remark(
                    r,
                    f"系统分析：大额资金流向分析命中（单笔绝对金额≥{th:g}元）",
                )
            )
        flow_rows = aggregate_large_flow(raw, params.top_n)
        extra["flow_top"] = flow_rows
        extra["threshold"] = params.large_amount_threshold

    elif module_id == AnalysisModuleId.SPECIAL_AMOUNT:
        counts = build_amount_rounded_counts(all_records)
        rule_counts: dict[str, int] = {}
        for row in all_records:
            tags = classify_special_amount(row, params, counts)
            if not tags:
                continue
            hit_records.append(row_with_filled_remark(row, _join_remark(tags)))
            for t in tags:
                rule_counts[t] = rule_counts.get(t, 0) + 1
        extra["rule_hit_counts"] = dict(sorted(rule_counts.items(), key=lambda x: -x[1]))

    elif module_id == AnalysisModuleId.SPECIAL_TIME:
        rule_counts: dict[str, int] = {}
        for row in all_records:
            tags = classify_special_time(row)
            if not tags:
                continue
            hit_records.append(row_with_filled_remark(row, _join_remark(tags)))
            for t in tags:
                rule_counts[t] = rule_counts.get(t, 0) + 1
        extra["rule_hit_counts"] = dict(sorted(rule_counts.items(), key=lambda x: -x[1]))

    else:
        raise ValueError(f"Unknown module_id: {module_id}")

    summary = query.summarize(hit_records)
    description = render_module_description(module_id, params, summary, extra, len(all_records))
    return ModuleResult(
        module_id=module_id,
        params=params,
        hit_records=hit_records,
        summary=summary,
        extra=extra,
        description=description,
    )


def render_module_description(
    module_id: str,
    params: ModuleParams,
    summary: dict[str, Any],
    extra: dict[str, Any],
    batch_total_count: int,
) -> str:
    """Human-readable audit text for fixed modules."""
    lines: list[str] = []
    title_map = {
        AnalysisModuleId.LARGE_INOUT: "大额进出分析",
        AnalysisModuleId.LARGE_FLOW: "大额资金流向",
        AnalysisModuleId.SPECIAL_AMOUNT: "特殊金额分析",
        AnalysisModuleId.SPECIAL_TIME: "特殊时间分析",
    }
    title = title_map.get(module_id, module_id)
    lines.append(f"【{title}】")
    lines.append(f"本批次总交易笔数：{batch_total_count}；命中笔数：{int(summary.get('txn_count', 0))}。")

    if module_id in (AnalysisModuleId.LARGE_INOUT, AnalysisModuleId.LARGE_FLOW):
        th = float(extra.get("threshold", params.large_amount_threshold))
        lines.append(f"大额判定阈值：单笔绝对金额 ≥ {th:.2f}。")

    if module_id == AnalysisModuleId.LARGE_INOUT:
        lines.append(
            f"大额收入：{int(extra.get('large_in_count', 0))}笔，合计 {float(extra.get('large_in_total', 0.0)):.2f}；"
            f"大额支出：{int(extra.get('large_out_count', 0))}笔，合计 {float(extra.get('large_out_total', 0.0)):.2f}。"
        )

    if module_id == AnalysisModuleId.LARGE_FLOW:
        top = extra.get("flow_top") or []
        lines.append(f"按对手汇总（Top {len(top)}，按总发生额排序）：")
        for i, row in enumerate(top, 1):
            acct = row.get("counterparty_account") or ""
            name = row.get("counterparty_name") or ""
            lines.append(
                f"  {i}. 对手卡号={acct or '(无)'}，对手名={name or '(无)'}，"
                f"流入 {float(row.get('in_total', 0)):.2f}，流出 {float(row.get('out_total', 0)):.2f}，"
                f"净额 {float(row.get('net', 0)):.2f}，笔数 {int(row.get('count', 0))}。"
            )

    if module_id in (AnalysisModuleId.SPECIAL_AMOUNT, AnalysisModuleId.SPECIAL_TIME):
        rc = extra.get("rule_hit_counts") or {}
        if rc:
            lines.append("规则命中统计（按命中笔数）：")
            for k, v in list(rc.items())[:20]:
                lines.append(f"  · {k}：{v}笔")
        if module_id == AnalysisModuleId.SPECIAL_AMOUNT:
            lines.append(
                f"重复金额判定：同一金额（保留两位）在本批次内出现次数 ≥ {params.repeat_amount_min_count} 即标注。"
            )
        if module_id == AnalysisModuleId.SPECIAL_TIME:
            lines.append(
                "时间规则：深夜22:00–24:00；凌晨00:01–06:00（0点整不计入凌晨）；"
                "中国法定节假日以 chinese-calendar 库为准；另含2·14、5·20、七夕（农历七月初七，zhdate）。"
            )
            if _zhdate_class() is None:
                lines.append("提示：未安装 zhdate 则无法换算七夕对应公历日（pip install zhdate）。")
            if _chinese_calendar_module() is None:
                lines.append("提示：未安装 chinese-calendar 则无法标注法定节假日（pip install chinese-calendar）。")

    lines.append(
        f"命中样本汇总：总收入 {float(summary.get('in_total', 0.0)):.2f}，"
        f"总支出 {float(summary.get('out_total', 0.0)):.2f}，"
        f"净额 {float(summary.get('net_amount', 0.0)):.2f}。"
    )
    lines.append("导出与界面表格中的「备注」列为本次分析自动填写，不保留银行原始备注。")
    return "\n".join(lines)
