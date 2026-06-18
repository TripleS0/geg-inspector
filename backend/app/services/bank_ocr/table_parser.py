"""Parse OCR table output into structured bank rows."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

from app.services.bank_ocr.layout_profiles import LayoutProfile

_AMOUNT_RE = re.compile(r"^-?[\d,]+(?:\.\d{1,2})?$")
_DATE_RE = re.compile(r"^\d{8}$")


class _TableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_row is not None:
            self._current_row.append(_clean_cell("".join(self._cell_parts)))
            self._cell_parts = []
        elif tag == "tr" and self._current_row is not None:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_row is not None:
            self._cell_parts.append(data)


def _normalize_header_key(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _clean_cell(text: str) -> str:
    value = unescape(str(text or "")).replace("\n", " ").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _match_column_name(header: str, profile: LayoutProfile) -> str | None:
    normalized = _normalize_header_key(header)
    for column in profile.table_columns:
        if _normalize_header_key(column) == normalized:
            return column
        if column in header or header in column:
            return column
    aliases = {
        "支出金额": "检出金额",
        "借方发生额": "检出金额",
        "贷方发生额": "存入金额",
    }
    return aliases.get(normalized)


def parse_header_fields(lines: list[tuple[str, float]], profile: LayoutProfile) -> dict[str, str]:
    """Extract header metadata from OCR text lines."""
    joined = " ".join(text for text, _ in lines)
    header: dict[str, str] = {field: "" for field in profile.header_fields}
    patterns = {
        "客户姓名": r"客户姓名[:：]?\s*([^\s客户账号对账日期]+)",
        "客户账号": r"客户账号[:：]?\s*([\d\*xX]+)",
        "对账日期": r"对账日期[:：]?\s*([\d\-]+)",
        "发卡/折机构": r"(?:发卡/折机构|发卡机构)[:：]?\s*(.+?)(?=客户账号|币种|对账日期|$)",
    }
    for field, pattern in patterns.items():
        if field not in profile.header_fields:
            continue
        match = re.search(pattern, joined)
        if match:
            header[field] = match.group(1).strip()
    return header


def parse_table_html_raw(html: str) -> tuple[list[str], list[dict[str, str]], list[dict[str, float]]]:
    """Parse HTML table using OCR header row as-is (raw columns, no bank profile mapping)."""
    parser = _TableHtmlParser()
    parser.feed(html or "")
    grid = parser.rows
    if len(grid) < 2:
        return [], [], []

    headers = _dedupe_headers([cell.strip() or f"列{index + 1}" for index, cell in enumerate(grid[0])])
    parsed_rows: list[dict[str, str]] = []
    confidences: list[dict[str, float]] = []
    for row in grid[1:]:
        if not any(cell.strip() for cell in row):
            continue
        if _looks_like_header_repeat(row, headers):
            continue
        record = {column: "" for column in headers}
        confidence = {column: 0.85 for column in headers}
        for index, cell in enumerate(row):
            if index >= len(headers):
                break
            column = headers[index]
            record[column] = cell.strip()
            confidence[column] = _score_cell(column, cell.strip())
        if any(record.values()):
            parsed_rows.append(record)
            confidences.append(confidence)
    return headers, parsed_rows, confidences


def parse_structure_result_raw(
    structure_items: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, str]], list[dict[str, float]]]:
    """Parse PP-Structure output into raw column names and row dicts."""
    best_headers: list[str] = []
    all_rows: list[dict[str, str]] = []
    all_conf: list[dict[str, float]] = []
    for item in structure_items:
        if str(item.get("type") or "") != "table":
            continue
        res = item.get("res") or {}
        html = res.get("html") if isinstance(res, dict) else ""
        headers, rows, conf = parse_table_html_raw(str(html or ""))
        if len(headers) > len(best_headers):
            best_headers = headers
        all_rows.extend(rows)
        all_conf.extend(conf)
    if best_headers:
        normalized_rows: list[dict[str, str]] = []
        normalized_conf: list[dict[str, float]] = []
        for row, conf in zip(all_rows, all_conf):
            record = {column: str(row.get(column) or "") for column in best_headers}
            confidence = {column: float(conf.get(column, 0.85)) for column in best_headers}
            normalized_rows.append(record)
            normalized_conf.append(confidence)
        return best_headers, normalized_rows, normalized_conf
    return [], all_rows, all_conf


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for header in headers:
        base = header or "列"
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base}_{count}")
    return result


def _looks_like_header_repeat(row: list[str], headers: list[str]) -> bool:
    normalized_headers = {_normalize_header_key(item) for item in headers if item}
    hits = sum(1 for cell in row if _normalize_header_key(cell) in normalized_headers)
    return hits >= max(2, len(headers) // 2)


def parse_table_html(html: str, profile: LayoutProfile) -> tuple[list[dict[str, str]], list[dict[str, float]]]:
    """Parse PP-Structure HTML table into row dicts and confidence maps."""
    parser = _TableHtmlParser()
    parser.feed(html or "")
    rows = parser.rows
    if not rows:
        return [], []

    header_cells = rows[0]
    column_map: list[str | None] = [_match_column_name(cell, profile) for cell in header_cells]
    if not any(column_map):
        column_map = list(profile.table_columns[: len(header_cells)])

    parsed_rows: list[dict[str, str]] = []
    confidences: list[dict[str, float]] = []
    for row in rows[1:]:
        cells = row
        if not any(cells):
            continue
        if all(_normalize_header_key(cell) in profile.table_columns for cell in cells if cell):
            continue
        record = {column: "" for column in profile.table_columns}
        confidence = {column: 0.85 for column in profile.table_columns}
        for index, cell in enumerate(cells):
            if index >= len(column_map):
                break
            column = column_map[index]
            if not column:
                continue
            record[column] = cell
            confidence[column] = _score_cell(column, cell)
        if _looks_like_data_row(record, profile):
            parsed_rows.append(record)
            confidences.append(confidence)
    return parsed_rows, confidences


def parse_structure_result(
    structure_items: list[dict[str, Any]],
    profile: LayoutProfile,
) -> tuple[list[dict[str, str]], list[dict[str, float]]]:
    """Parse PP-Structure output list into rows."""
    all_rows: list[dict[str, str]] = []
    all_conf: list[dict[str, float]] = []
    for item in structure_items:
        if str(item.get("type") or "") != "table":
            continue
        res = item.get("res") or {}
        html = res.get("html") if isinstance(res, dict) else ""
        rows, conf = parse_table_html(str(html or ""), profile)
        all_rows.extend(rows)
        all_conf.extend(conf)
    return all_rows, all_conf


def merge_deposit_withdrawal(record: dict[str, str], profile: LayoutProfile) -> dict[str, str]:
    """Convert separate deposit/withdrawal columns into unified import columns."""
    merged = dict(record)
    deposit = _normalize_amount_text(record.get(profile.deposit_column or "", ""))
    withdrawal = _normalize_amount_text(record.get(profile.withdrawal_column or "", ""))
    if deposit and not withdrawal:
        merged["交易金额"] = deposit
        merged["借贷方向"] = "收入"
    elif withdrawal and not deposit:
        merged["交易金额"] = withdrawal
        merged["借贷方向"] = "支出"
    elif deposit and withdrawal:
        merged["交易金额"] = deposit or withdrawal
        merged["借贷方向"] = "收入" if deposit else "支出"
    return merged


def _normalize_amount_text(value: str) -> str:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "—"}:
        return ""
    if _AMOUNT_RE.match(text.replace(",", "")):
        return text
    return text


def _score_cell(column: str, value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if column == "交易日期" and _DATE_RE.match(text):
        return 0.95
    if column in {"存入金额", "检出金额", "账户余额"} and _AMOUNT_RE.match(text.replace(",", "")):
        return 0.92
    if column == "客户账号" and re.search(r"\d{6,}", text):
        return 0.9
    if len(text) >= 2:
        return 0.78
    return 0.55


def _looks_like_data_row(record: dict[str, str], profile: LayoutProfile) -> bool:
    if record.get("交易日期") and _DATE_RE.match(record["交易日期"]):
        return True
    if record.get(profile.deposit_column or "") or record.get(profile.withdrawal_column or ""):
        return True
    if record.get("摘要"):
        return True
    return False
