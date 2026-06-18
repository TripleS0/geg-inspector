"""Built-in carrier CDR column mapping templates."""

from __future__ import annotations

from dataclasses import dataclass


CANONICAL_COLUMNS: tuple[str, ...] = (
    "序号",
    "通信记录唯一标识",
    "通话类型",
    "话单类型",
    "本机号码",
    "本机IMSI号",
    "本机IMEI号",
    "本机RAC号",
    "本机LAC号",
    "本机基站ID",
    "本机CELLID",
    "本机归属运营商",
    "本机通话所在地",
    "对方号码",
    "对方IMSI号",
    "对方IMEI号",
    "对方RAC号",
    "对方LAC号",
    "对方基站ID",
    "对方CELLID",
    "对方归属运营商",
    "对方通话所在地",
    "对方号码归属地",
    "前转主叫号码",
    "呼叫开始时间",
    "呼叫时长",
    "是否群内呼叫",
    "群组编号",
    "群组名称",
    "短信发送接收时间",
)

REQUIRED_COLUMNS = frozenset({"本机号码", "对方号码"})


@dataclass(frozen=True)
class CarrierTemplate:
    """Column mapping template for one carrier export layout."""

    template_id: str
    carrier_name: str
    carrier_keywords: tuple[str, ...]
    sheet_keywords: tuple[str, ...]
    field_map: dict[str, tuple[str, ...]]
    signature_columns: tuple[str, ...]
    required_columns: frozenset[str] = REQUIRED_COLUMNS


def _identity_map() -> dict[str, tuple[str, ...]]:
    return {col: (col,) for col in CANONICAL_COLUMNS}


BUILTIN_TEMPLATES: tuple[CarrierTemplate, ...] = (
    CarrierTemplate(
        template_id="mobile_gd_v1",
        carrier_name="中国移动",
        carrier_keywords=("移动", "CMCC", "广东移动"),
        sheet_keywords=("运营商话单信息", "话单", "CDR", "通信详单"),
        field_map=_identity_map(),
        signature_columns=(
            "本机号码",
            "对方号码",
            "呼叫开始时间",
            "话单类型",
            "本机归属运营商",
        ),
    ),
    CarrierTemplate(
        template_id="unicom_std_v1",
        carrier_name="中国联通",
        carrier_keywords=("联通", "CUCC", "广东联通"),
        sheet_keywords=("运营商话单信息", "联通话单", "CDR"),
        field_map=_identity_map(),
        signature_columns=("本机号码", "对方号码", "呼叫开始时间", "对方归属运营商"),
    ),
    CarrierTemplate(
        template_id="telecom_std_v1",
        carrier_name="中国电信",
        carrier_keywords=("电信", "CTCC", "广东电信"),
        sheet_keywords=("运营商话单信息", "电信话单", "CDR"),
        field_map=_identity_map(),
        signature_columns=("本机号码", "对方号码", "呼叫开始时间", "对方归属运营商"),
    ),
)


def _normalize_header(value: str) -> str:
    return (value or "").strip()


def _score_template(template: CarrierTemplate, sheet_name: str, headers: set[str]) -> int:
    score = 0
    sheet = (sheet_name or "").strip()
    for keyword in template.sheet_keywords:
        if keyword and keyword in sheet:
            score += 8
            break
    for col in template.signature_columns:
        if col in headers:
            score += 3
    for canonical, aliases in template.field_map.items():
        if canonical in headers:
            score += 1
            continue
        if any(alias in headers for alias in aliases):
            score += 1
    for keyword in template.carrier_keywords:
        if keyword and keyword in sheet:
            score += 2
    return score


def match_carrier_template(
    sheet_name: str,
    headers: list[str],
    *,
    carrier_hint: str = "",
) -> CarrierTemplate | None:
    """Pick the best matching carrier template for one sheet."""
    normalized_headers = {_normalize_header(h) for h in headers if _normalize_header(h)}
    if not normalized_headers:
        return None

    hint = (carrier_hint or "").strip()
    if hint:
        for template in BUILTIN_TEMPLATES:
            if template.template_id == hint:
                return template

    best: CarrierTemplate | None = None
    best_score = 0
    for template in BUILTIN_TEMPLATES:
        score = _score_template(template, sheet_name, normalized_headers)
        if score > best_score:
            best = template
            best_score = score
    if best_score < 6:
        return None
    return best


def get_template_by_id(template_id: str) -> CarrierTemplate | None:
    key = (template_id or "").strip()
    for template in BUILTIN_TEMPLATES:
        if template.template_id == key:
            return template
    return None


__all__ = [
    "BUILTIN_TEMPLATES",
    "CANONICAL_COLUMNS",
    "CarrierTemplate",
    "REQUIRED_COLUMNS",
    "get_template_by_id",
    "match_carrier_template",
]
