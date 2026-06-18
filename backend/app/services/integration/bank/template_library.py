"""Built-in bank transaction template rules and merged user templates."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.shared.db.sqlite_client import SqliteClient


def _n(text: str) -> str:
    """Normalize text for loose matching."""
    return "".join(ch for ch in (text or "") if ch.isalnum()).lower()


@dataclass(frozen=True)
class BankTemplate:
    """Mapping template for one bank transaction sheet."""

    template_id: str
    bank_display_name: str
    bank_keywords: tuple[str, ...]
    sheet_keywords: tuple[str, ...]
    header_row_hint: int | None
    field_map: dict[str, tuple[str, ...]]
    signature_columns: tuple[str, ...] = ()
    user_template_id: str | None = None
    template_type: str = "txn_detail"


_MERGED_TEMPLATE_CACHE: dict[str, tuple[BankTemplate, ...]] = {}


def clear_template_cache() -> None:
    """Invalidate cached merged templates (call after user template CRUD)."""
    _MERGED_TEMPLATE_CACHE.clear()


def list_templates_for_match(client: SqliteClient | None = None) -> tuple[BankTemplate, ...]:
    """Active user templates (priority desc) then built-ins."""
    db = client or SqliteClient()
    key = str(db.db_path.resolve())
    cached = _MERGED_TEMPLATE_CACHE.get(key)
    if cached is not None:
        return cached
    user_templates: list[BankTemplate] = []
    try:
        from app.services.integration.bank.user_bank_template_repository import (
            UserBankTemplateRepository,
            record_to_bank_template,
        )

        repo = UserBankTemplateRepository(db)
        for rec in repo.list_active_ordered():
            user_templates.append(record_to_bank_template(rec))
    except Exception:
        pass
    merged = tuple(user_templates) + BUILTIN_TEMPLATES
    _MERGED_TEMPLATE_CACHE[key] = merged
    return merged


BUILTIN_TEMPLATES: tuple[BankTemplate, ...] = (
    BankTemplate(
        template_id="ccb_account_v1",
        bank_display_name="建设银行",
        bank_keywords=("建设银行", "建行", "ccb"),
        sheet_keywords=("开户信息", "账户信息", "客户信息"),
        header_row_hint=None,
        field_map={
            "acct_no": ("账号", "借记卡主账户账号"),
            "person_name": ("账户名称", "客户名称"),
            "id_no": ("证件号码",),
            "mobile": ("移动电话",),
            "open_date": ("开户日期",),
        },
        signature_columns=("账户名称", "证件号码", "开户日期", "移动电话"),
        template_type="account_profile",
    ),
    BankTemplate(
        template_id="ccb_txn_v1",
        bank_display_name="建设银行",
        bank_keywords=("建设银行", "建行", "ccb"),
        sheet_keywords=("交易明细",),
        header_row_hint=None,
        field_map={
            "person_name": ("客户名称", "账户名称"),
            "acct_no": ("交易卡号", "账号"),
            "counterparty_name": ("对方户名",),
            "counterparty_account": ("对方账号",),
            "txn_date": ("交易日期",),
            "txn_time_raw": ("交易时间",),
            "txn_direction": ("借贷方向",),
            "currency": ("币种",),
            "txn_amount": ("交易金额",),
            "balance": ("账户余额",),
            "summary": ("摘要", "扩充备注"),
            "txn_org_no": ("交易机构号",),
            "txn_org_name": ("交易机构名称",),
        },
        signature_columns=("借贷方向", "交易卡号", "交易日期", "交易时间"),
    ),
    BankTemplate(
        template_id="icbc_txn_v1",
        bank_display_name="工商银行",
        bank_keywords=("工商银行", "工行"),
        sheet_keywords=("sheet1", "明细", "流水"),
        header_row_hint=None,
        field_map={
            "person_name": (),
            "acct_no": ("账号", "卡号"),
            "counterparty_name": ("对方户名",),
            "counterparty_account": ("对方账户", "对方账户/账号", "对方卡号/账号"),
            "txn_time_raw": ("交易时间戳",),
            "txn_direction": ("借贷标志",),
            "currency": ("币种", "交易币种"),
            "txn_amount": ("发生额", "交易金额"),
            "balance": ("余额",),
            "summary": ("注释",),
            "txn_org_no": ("网点号", "地区号"),
            "txn_org_name": ("交易场所简称",),
        },
        signature_columns=("借贷标志", "交易时间", "对方账号", "交易场所简称"),
    ),
    BankTemplate(
        template_id="icbc_txn_v2",
        bank_display_name="工商银行",
        bank_keywords=("工商银行", "工行"),
        sheet_keywords=("sheet1", "明细", "流水"),
        header_row_hint=None,
        field_map={
            "person_name": (),
            "acct_no": ("卡号", "账号"),
            "txn_date": ("交易日期",),
            "txn_time_raw": ("记账时间",),
            "txn_direction": ("借贷标志",),
            "currency": ("交易币种", "币种"),
            "txn_amount": ("交易金额", "发生额"),
            "balance": ("余额",),
            "counterparty_account": ("对方卡号/账号", "对方账户/账号"),
            "counterparty_name": ("对方账户户名", "对方户名"),
            "summary": ("交易描述", "摘要", "注释"),
            "txn_org_no": ("地区号",),
            "txn_org_name": ("交易场所简称",),
        },
        signature_columns=("交易日期", "记账时间", "交易币种", "对方卡号/账号"),
    ),
    BankTemplate(
        template_id="cgb_txn_v1",
        bank_display_name="广发银行",
        bank_keywords=("广发银行", "广发行", "广发"),
        sheet_keywords=("旧核心交易流水",),
        header_row_hint=None,
        field_map={
            "person_name": ("客户名称",),
            "acct_no": ("账号", "卡号"),
            "counterparty_name": ("对手名", "对方行名"),
            "counterparty_account": ("对手账号",),
            "txn_date": ("交易日期",),
            "txn_time_raw": ("交易时间",),
            "txn_direction": ("借贷标识", "借贷标志"),
            "txn_amount": ("交易金额",),
            "summary": ("摘要中文", "备注"),
            "txn_org_no": ("交易行",),
            "txn_org_name": ("交易行",),
        },
        signature_columns=("借贷标识", "对手账号", "摘要中文"),
    ),
    BankTemplate(
        template_id="abc_txn_v1",
        bank_display_name="农业银行",
        bank_keywords=("农业银行", "农行"),
        sheet_keywords=("个人客户明细",),
        header_row_hint=3,
        field_map={
            "person_name": (),
            "acct_no": ("客户账号", "核算账号"),
            "counterparty_name": ("对手方户名",),
            "counterparty_account": ("对手方账号",),
            "txn_date": ("交易日期",),
            "txn_time_raw": ("交易时间",),
            "txn_direction": (),
            "txn_amount": ("交易金额",),
            "summary": ("摘要",),
            "txn_org_no": ("交易行号",),
            "txn_org_name": ("交易行名",),
        },
        signature_columns=("客户账号", "核算账号", "对手方账号", "交易行号"),
    ),
    BankTemplate(
        template_id="ceb_txn_v1",
        bank_display_name="光大银行",
        bank_keywords=("光大银行", "光大", "ceb", "cebbank"),
        sheet_keywords=("交易明细",),
        header_row_hint=None,
        field_map={
            "person_name": ("客户姓名",),
            "acct_no": ("客户账号", "账号", "卡号"),
            "counterparty_name": ("对方名称", "对方户名"),
            "counterparty_account": ("对方账号",),
            "txn_date": ("交易日期",),
            "txn_direction": ("借贷方向",),
            "txn_amount": ("交易金额",),
            "balance": ("账户余额",),
            "summary": ("摘要",),
            "remark": ("交易流水号",),
        },
        signature_columns=("交易日期", "交易流水号", "存入金额", "检出金额", "对方名称"),
    ),
)

ACCOUNT_SHEET_HINTS: tuple[str, ...] = (
    "开户",
    "账户信息",
    "客户信息",
    "客户主档",
    "开户资料",
)

TXN_SHEET_HINTS: tuple[str, ...] = (
    "交易",
    "流水",
    "明细",
    "账单",
)

BANK_HINTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("建设银行", ("建行", "建设银行", "ccb"), ("交易明细", "开户信息")),
    ("工商银行", ("工行", "工商银行", "icbc"), ("sheet1",)),
    ("广发银行", ("广发", "广发行", "广发银行", "cgb"), ("旧核心交易流水", "开户资料")),
    ("农业银行", ("农行", "农业银行", "abc"), ("个人客户明细", "客户信息", "客户主档")),
)


def _type_ok(item: BankTemplate, sheet_type: str | None) -> bool:
    if not sheet_type:
        return True
    return item.template_type == sheet_type


def match_template(
    bank_name: str,
    sheet_name: str,
    *,
    sheet_type: str | None = None,
    client: SqliteClient | None = None,
) -> BankTemplate | None:
    """Find best template by bank/sheet keywords (user templates first)."""
    bank_norm = _n(bank_name)
    sheet_norm = _n(sheet_name)
    templates = list_templates_for_match(client)
    for item in templates:
        if not _type_ok(item, sheet_type):
            continue
        hit_bank = any(_n(k) in bank_norm for k in item.bank_keywords if k)
        hit_sheet = any(_n(k) in sheet_norm for k in item.sheet_keywords if k)
        if hit_bank and hit_sheet:
            return item
    for item in templates:
        if not _type_ok(item, sheet_type):
            continue
        hit_sheet = any(_n(k) in sheet_norm for k in item.sheet_keywords if k)
        if hit_sheet:
            return item
    return None


def find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    """Find raw column name by alias list."""
    if not aliases:
        return None
    lookup = {_n(col): col for col in columns}
    for alias in aliases:
        key = _n(alias)
        if key in lookup:
            return lookup[key]
    for alias in aliases:
        key = _n(alias)
        for norm_col, raw_col in lookup.items():
            if key and key in norm_col:
                return raw_col
    return None


def _extended_bank_hints(client: SqliteClient | None) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    hints: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    try:
        from app.services.integration.bank.user_bank_template_repository import UserBankTemplateRepository

        repo = UserBankTemplateRepository(client or SqliteClient())
        for rec in repo.list_active_ordered():
            hints.append((rec.bank_display_name, tuple(rec.bank_keywords), tuple(rec.sheet_keywords)))
    except Exception:
        pass
    hints.extend(BANK_HINTS)
    return hints


def infer_bank_name(
    file_name: str,
    sheet_names: list[str],
    fallback: str = "银行数据",
    *,
    client: SqliteClient | None = None,
) -> str:
    """Infer bank display name from filename/sheet names."""
    file_norm = _n(file_name)
    sheet_norms = [_n(x) for x in sheet_names if x]
    for bank_display, file_tokens, sheet_tokens in _extended_bank_hints(client):
        if any(_n(t) in file_norm for t in file_tokens):
            return bank_display
        for sheet in sheet_norms:
            if any(_n(t) in sheet for t in sheet_tokens):
                return bank_display
    return fallback or "银行数据"


def match_template_by_columns(
    columns: list[str],
    *,
    sheet_type: str | None = None,
    client: SqliteClient | None = None,
) -> BankTemplate | None:
    """Match template by column signatures."""
    norm_cols = {_n(col) for col in columns if col}
    best: BankTemplate | None = None
    best_score = 0
    for item in list_templates_for_match(client):
        if not _type_ok(item, sheet_type):
            continue
        score = 0
        for sig in item.signature_columns:
            key = _n(sig)
            if not key:
                continue
            if any(key in c for c in norm_cols):
                score += 1
        if score > best_score:
            best = item
            best_score = score
    if best is not None and best_score >= 2:
        return best
    return None


def infer_bank_name_by_columns(
    columns: list[str],
    fallback: str = "银行数据",
    *,
    sheet_type: str | None = None,
    client: SqliteClient | None = None,
) -> str:
    """Infer bank name directly from header columns."""
    template = match_template_by_columns(columns, sheet_type=sheet_type, client=client)
    if template is not None and template.bank_display_name:
        return template.bank_display_name
    norm_cols = {_n(col) for col in columns if col}
    icbc_signs = ("交易时间戳", "借贷标志", "交易币种", "记账时间", "对方卡号账号", "账号对应卡号")
    score = 0
    for sig in icbc_signs:
        key = _n(sig)
        if any(key in col for col in norm_cols):
            score += 1
    if score >= 2:
        return "工商银行"
    return fallback or "银行数据"


def infer_sheet_purpose(sheet_name: str) -> str:
    """Infer schema purpose from sheet name."""
    text = _n(sheet_name)
    if any(_n(x) in text for x in ACCOUNT_SHEET_HINTS):
        return "account_profile"
    if any(_n(x) in text for x in TXN_SHEET_HINTS):
        return "txn_detail"
    return "txn_detail"


def infer_sheet_purpose_by_columns(columns: list[str], fallback: str = "txn_detail") -> str:
    """Infer schema purpose from header columns."""
    norm_cols = {_n(col) for col in columns if col}
    account_signs = (
        "姓名",
        "证件号码",
        "开户日期",
        "账号对应卡号",
    )
    txn_signs = (
        "借贷标志",
        "交易时间戳",
        "交易日期",
        "记账时间",
        "交易金额",
    )
    account_score = 0
    txn_score = 0
    for sig in account_signs:
        key = _n(sig)
        if any(key in c for c in norm_cols):
            account_score += 1
    for sig in txn_signs:
        key = _n(sig)
        if any(key in c for c in norm_cols):
            txn_score += 1
    if account_score >= 2 and account_score >= txn_score:
        return "account_profile"
    if txn_score >= 2:
        return "txn_detail"
    return fallback

