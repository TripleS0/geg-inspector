"""Fusion model catalog for case-level model management and event scanning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FusionModelDef:
    key: str
    name: str
    category: str
    category_label: str
    description: str
    event_type_label: str
    param_schema: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    default_enabled: bool = True


BANK_MODULE_KEYS = (
    "bank_large_inout",
    "bank_large_flow",
    "bank_special_amount",
    "bank_special_time",
)

WECHAT_MODULE_KEYS = (
    "wechat_large_inout",
    "wechat_large_flow",
    "wechat_special_amount",
    "wechat_special_time",
)

COMMERCIAL_MODULE_KEYS = (
    "commercial_large_win",
    "commercial_repeat_winner",
)

RISK_RULE_KEYS = (
    "risk_R001",
    "risk_R002",
    "risk_R003",
    "risk_R004",
    "risk_R005",
    "risk_R006",
    "risk_R007",
    "risk_R008",
)

_CO_BID_DEFAULT_PARAMS: dict[str, Any] = {
    "min_shared_inquiries": 3,
    "min_co_rate": 0.25,
    "min_rotating_exclusive_wins": 4,
    "min_alternation_score": 0.55,
    "note": "陪标关联分析：高频陪标与轮流中标判定阈值",
}

_DEFAULT_TXN_PARAMS: dict[str, Any] = {
    "large_amount_threshold": 100_000.0,
    "top_n": 15,
    "repeat_amount_min_count": 3,
    "special_amount_whitelist": [520.0, 521.0, 1314.0, 666.0, 888.0, 188.0, 288.0],
}


def _txn_model(
    key: str,
    name: str,
    category: str,
    category_label: str,
    description: str,
    event_type_label: str,
) -> FusionModelDef:
    return FusionModelDef(
        key=key,
        name=name,
        category=category,
        category_label=category_label,
        description=description,
        event_type_label=event_type_label,
        param_schema=("large_amount_threshold", "top_n", "repeat_amount_min_count", "special_amount_whitelist"),
        default_params=dict(_DEFAULT_TXN_PARAMS),
    )


FUSION_MODEL_CATALOG: tuple[FusionModelDef, ...] = (
    _txn_model(
        "bank_large_inout",
        "大额进出",
        "bank",
        "银行流水分析",
        "按阈值识别大额收支交易",
        "大额转账",
    ),
    _txn_model(
        "bank_large_flow",
        "大额资金流向",
        "bank",
        "银行流水分析",
        "按交易对手统计大额资金流向排名",
        "大额资金流向",
    ),
    _txn_model(
        "bank_special_amount",
        "特殊金额",
        "bank",
        "银行流水分析",
        "敏感金额、整数金额、重复金额",
        "特殊金额",
    ),
    _txn_model(
        "bank_special_time",
        "特殊时间",
        "bank",
        "银行流水分析",
        "深夜、凌晨、节假日等特殊时段交易",
        "特殊日子转账",
    ),
    _txn_model(
        "wechat_large_inout",
        "大额进出",
        "wechat",
        "微信转账分析",
        "按阈值识别微信大额转账",
        "大额转账",
    ),
    _txn_model(
        "wechat_large_flow",
        "大额资金流向",
        "wechat",
        "微信转账分析",
        "按交易对手统计微信大额流向",
        "大额资金流向",
    ),
    _txn_model(
        "wechat_special_amount",
        "特殊金额",
        "wechat",
        "微信转账分析",
        "敏感金额、整数金额、重复金额",
        "特殊金额",
    ),
    _txn_model(
        "wechat_special_time",
        "特殊时间",
        "wechat",
        "微信转账分析",
        "深夜、凌晨、节假日等特殊时段转账",
        "特殊日子转账",
    ),
    FusionModelDef(
        key="commercial_large_win",
        name="大额中标",
        category="commercial",
        category_label="商务网分析",
        description="识别中标金额超过阈值的项目",
        event_type_label="大额中标",
        param_schema=("large_amount_threshold",),
        default_params={"large_amount_threshold": 500_000.0},
    ),
    FusionModelDef(
        key="commercial_repeat_winner",
        name="重复中标",
        category="commercial",
        category_label="商务网分析",
        description="同一企业多次中标的异常模式",
        event_type_label="重复中标",
        param_schema=("min_win_count",),
        default_params={"min_win_count": 3},
    ),
    FusionModelDef(
        key="risk_R001",
        name="围标疑似",
        category="risk",
        category_label="风险分析 · 围串标",
        description="同一批项目中多家企业高频共同参标",
        event_type_label="围标",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R002",
        name="串标疑似",
        category="risk",
        category_label="风险分析 · 围串标",
        description="企业对在多个项目中高度同步出现",
        event_type_label="串标",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R003",
        name="陪标疑似",
        category="risk",
        category_label="风险分析 · 围串标",
        description="长期少中标且频繁与同一中标方同场",
        event_type_label="陪标",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R004",
        name="关联关系异常",
        category="risk",
        category_label="风险分析 · 围串标",
        description="同一询价下工商主体法定代表人相同",
        event_type_label="关联异常",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R005",
        name="报价异常",
        category="risk",
        category_label="风险分析 · 围串标",
        description="同一询价多家含税单价离散度过低",
        event_type_label="报价异常",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R006",
        name="轮流中标",
        category="risk",
        category_label="风险分析 · 围串标",
        description="连续多单中标方在固定小集合内轮换",
        event_type_label="轮流中标",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R007",
        name="协同串标强化",
        category="risk",
        category_label="风险分析 · 围串标",
        description="围标或串标口径重叠且两企业工商法定代表人为同一人",
        event_type_label="围标",
        default_enabled=True,
    ),
    FusionModelDef(
        key="risk_R008",
        name="陪标关联分析",
        category="commercial",
        category_label="商务网分析",
        description="商务网分析页「陪标关联分析」：高频陪标、轮流中标判定阈值",
        event_type_label="陪标关联",
        param_schema=(
            "min_shared_inquiries",
            "min_co_rate",
            "min_rotating_exclusive_wins",
            "min_alternation_score",
        ),
        default_params=dict(_CO_BID_DEFAULT_PARAMS),
        default_enabled=True,
    ),
)

CATALOG_BY_KEY: dict[str, FusionModelDef] = {item.key: item for item in FUSION_MODEL_CATALOG}

MODULE_ID_BY_KEY: dict[str, str] = {
    "bank_large_inout": "large_inout",
    "bank_large_flow": "large_flow",
    "bank_special_amount": "special_amount",
    "bank_special_time": "special_time",
    "wechat_large_inout": "large_inout",
    "wechat_large_flow": "large_flow",
    "wechat_special_amount": "special_amount",
    "wechat_special_time": "special_time",
}

RISK_CODE_BY_KEY: dict[str, str] = {key: key.replace("risk_", "") for key in RISK_RULE_KEYS}
