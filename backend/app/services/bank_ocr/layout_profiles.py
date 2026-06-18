"""Bank layout profiles for OCR table parsing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LayoutProfile:
    """Column and header definitions for one bank OCR layout."""

    profile_id: str
    bank_display_name: str
    bank_keywords: tuple[str, ...]
    table_columns: tuple[str, ...]
    header_fields: tuple[str, ...]
    deposit_column: str | None = None
    withdrawal_column: str | None = None
    # 页眉 OCR 正则：字段名 -> 捕获组 pattern
    header_patterns: dict[str, str] = field(default_factory=dict)


CEB_TXN_V1 = LayoutProfile(
    profile_id="ceb_txn_v1",
    bank_display_name="光大银行",
    bank_keywords=("光大银行", "光大", "ceb", "cebbank"),
    table_columns=(
        "客户账号",
        "交易日期",
        "交易流水号",
        "存入金额",
        "检出金额",
        "账户余额",
        "摘要",
        "对方账号",
        "对方名称",
    ),
    header_fields=("客户姓名", "客户账号", "对账日期", "发卡/折机构"),
    deposit_column="存入金额",
    withdrawal_column="检出金额",
    header_patterns={
        "客户姓名": r"客户姓名[:：]?\s*([^\s客户账号对账日期]+)",
        "客户账号": r"客户账号[:：]?\s*([\d\*xX]+)",
        "对账日期": r"对账日期[:：]?\s*([\d\-]+)",
        "发卡/折机构": r"(?:发卡/折机构|发卡机构)[:：]?\s*(.+?)(?=客户账号|币种|对账日期|$)",
    },
)

CCB_TXN_V1 = LayoutProfile(
    profile_id="ccb_txn_v1",
    bank_display_name="建设银行",
    bank_keywords=("建设银行", "建行", "ccb"),
    table_columns=(
        "客户名称",
        "交易卡号",
        "交易日期",
        "交易时间",
        "借贷方向",
        "币种",
        "交易金额",
        "账户余额",
        "摘要",
        "对方户名",
        "对方账号",
    ),
    header_fields=("客户名称", "证件号码", "卡号/账号", "查询起止日期"),
    header_patterns={
        "客户名称": r"(?:客户名称|账户名称)[:：]?\s*([^\s证件卡号查询]+)",
        "证件号码": r"证件号码[:：]?\s*([\dXx]+)",
        "卡号/账号": r"(?:卡号/账号|交易卡号|账号)[:：]?\s*([\d\*]+)",
        "查询起止日期": r"(?:查询起止日期|起止日期)[:：]?\s*([\d\-—至]+)",
    },
)

ICBC_TXN_V2 = LayoutProfile(
    profile_id="icbc_txn_v2",
    bank_display_name="工商银行",
    bank_keywords=("工商银行", "工行", "icbc"),
    table_columns=(
        "卡号",
        "交易日期",
        "记账时间",
        "借贷标志",
        "交易币种",
        "交易金额",
        "余额",
        "对方卡号/账号",
        "对方账户户名",
        "交易描述",
    ),
    header_fields=("户名", "卡号", "查询区间"),
    header_patterns={
        "户名": r"(?:户名|客户姓名)[:：]?\s*([^\s卡号查询]+)",
        "卡号": r"(?:卡号|账号)[:：]?\s*([\d\*]+)",
        "查询区间": r"(?:查询区间|查询起止日)[:：]?\s*([\d\-—至]+)",
    },
)

ABC_TXN_V1 = LayoutProfile(
    profile_id="abc_txn_v1",
    bank_display_name="农业银行",
    bank_keywords=("农业银行", "农行", "abc"),
    table_columns=(
        "客户账号",
        "交易日期",
        "交易时间",
        "交易金额",
        "对手方户名",
        "对手方账号",
        "摘要",
        "交易行号",
        "交易行名",
    ),
    header_fields=("客户姓名", "客户账号", "查询日期"),
    header_patterns={
        "客户姓名": r"(?:客户姓名|户名)[:：]?\s*([^\s客户账号查询]+)",
        "客户账号": r"(?:客户账号|账号)[:：]?\s*([\d\*]+)",
        "查询日期": r"(?:查询日期|查询区间)[:：]?\s*([\d\-—至]+)",
    },
)

CGB_TXN_V1 = LayoutProfile(
    profile_id="cgb_txn_v1",
    bank_display_name="广发银行",
    bank_keywords=("广发银行", "广发", "cgb"),
    table_columns=(
        "客户名称",
        "账号",
        "交易日期",
        "交易时间",
        "借贷标识",
        "交易金额",
        "摘要中文",
        "对手账号",
        "对手名",
    ),
    header_fields=("客户名称", "账号", "查询期间"),
    header_patterns={
        "客户名称": r"客户名称[:：]?\s*([^\s账号查询]+)",
        "账号": r"账号[:：]?\s*([\d\*]+)",
        "查询期间": r"(?:查询期间|起止日期)[:：]?\s*([\d\-—至]+)",
    },
)

LAYOUT_PROFILES: dict[str, LayoutProfile] = {
    CEB_TXN_V1.profile_id: CEB_TXN_V1,
    CCB_TXN_V1.profile_id: CCB_TXN_V1,
    ICBC_TXN_V2.profile_id: ICBC_TXN_V2,
    ABC_TXN_V1.profile_id: ABC_TXN_V1,
    CGB_TXN_V1.profile_id: CGB_TXN_V1,
}


def list_layout_profiles() -> tuple[LayoutProfile, ...]:
    """Return all registered OCR layout profiles."""
    return tuple(LAYOUT_PROFILES.values())


def resolve_profile(profile_id: str | None = None, bank_name: str = "") -> LayoutProfile:
    """Pick layout profile by id or bank name keywords."""
    if profile_id and profile_id in LAYOUT_PROFILES:
        return LAYOUT_PROFILES[profile_id]
    text = (bank_name or "").lower()
    for profile in LAYOUT_PROFILES.values():
        if any(keyword.lower() in text for keyword in profile.bank_keywords):
            return profile
    return CEB_TXN_V1
