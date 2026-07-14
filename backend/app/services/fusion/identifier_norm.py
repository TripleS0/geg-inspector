"""Identifier normalization for fusion linking."""

from __future__ import annotations

import json
import re

from app.services.integration.commercial.ic_ingest_service import normalize_enterprise_name
from app.services.integration.telecom.phone_utils import normalize_phone

_DIGITS = re.compile(r"\D+")
_BANK_ACCOUNT_SEPARATOR = "|"
_BANK_ALIASES = {
    "工商银行": "工商银行",
    "工行": "工商银行",
    "ICBC": "工商银行",
    "建设银行": "建设银行",
    "建行": "建设银行",
    "CCB": "建设银行",
    "农业银行": "农业银行",
    "农行": "农业银行",
    "ABC": "农业银行",
    "广发银行": "广发银行",
    "广发": "广发银行",
    "广发行": "广发银行",
    "CGB": "广发银行",
}


def normalize_identifier(identifier_type: str, value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if identifier_type == "phone":
        return normalize_phone(text)
    if identifier_type in {"bank_card", "bank_acct"}:
        return _DIGITS.sub("", text)
    if identifier_type == "id_no":
        return text.upper().replace(" ", "")
    if identifier_type == "enterprise_name":
        return normalize_enterprise_name(text)
    if identifier_type in {"person_name", "wechat_name"}:
        return text.replace(" ", "")
    return text


def normalize_bank_name(value: str) -> str:
    key = "".join((value or "").strip().upper().split())
    return _BANK_ALIASES.get(key, key)


def normalize_scoped_bank_account(bank_name: str, value: str) -> str:
    account = normalize_identifier("bank_acct", value)
    bank = normalize_bank_name(bank_name)
    if not account:
        return ""
    return f"{bank}{_BANK_ACCOUNT_SEPARATOR}{account}" if bank else account


def split_scoped_bank_account(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if _BANK_ACCOUNT_SEPARATOR not in text:
        return "", normalize_identifier("bank_acct", text)
    bank, account = text.split(_BANK_ACCOUNT_SEPARATOR, 1)
    return normalize_bank_name(bank), normalize_identifier("bank_acct", account)


def parse_person_names_from_json_field(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text or text in {"[]", "{}"}:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _split_person_text(text)
    if isinstance(data, list):
        names: list[str] = []
        for item in data:
            if isinstance(item, str):
                names.extend(_split_person_text(item))
            elif isinstance(item, dict):
                for key in ("name", "person_name", "姓名"):
                    val = item.get(key)
                    if val:
                        names.extend(_split_person_text(str(val)))
        return names
    if isinstance(data, str):
        return _split_person_text(data)
    return []


_ROLE_ONLY = frozenset(
    {"财务负责人", "监事", "法人", "股东", "总经理", "执行董事", "负责人", "董事", "经理"}
)


def _split_person_text(text: str) -> list[str]:
    parts = re.split(r"[、,，;；/|（）()]+", text)
    out: list[str] = []
    for part in parts:
        name = part.strip()
        if not name:
            continue
        name = re.sub(r"（.*?）|\(.*?\)|持股.*$|监事.*$|法人.*$", "", name).strip()
        if name and len(name) <= 20 and name not in _ROLE_ONLY:
            out.append(name)
    return out


__all__ = [
    "normalize_bank_name",
    "normalize_identifier",
    "normalize_scoped_bank_account",
    "parse_person_names_from_json_field",
    "split_scoped_bank_account",
]
