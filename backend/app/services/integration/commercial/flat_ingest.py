"""Parse flat old/new commercial-network export sheets into canonical rows."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_BID_CODE_PATTERN = re.compile(r"^Q[A-Za-z0-9]+$")
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?$")

WIN_STATUSES = frozenset({"已中标", "已预中标", "部分中标", "部分预中标"})


def is_win_status(status: Any) -> bool:
    """Treat partial/full pre-win and win statuses as won."""
    text = _to_text(status)
    if not text:
        return False
    if text in WIN_STATUSES:
        return True
    normalized = text.replace(" ", "")
    return normalized in WIN_STATUSES


def normalize_header(name: Any) -> str:
    """Normalize column header text for matching."""
    text = "" if name is None else str(name).strip()
    if text.lower() == "nan":
        return ""
    return text.replace("（", "(").replace("）", ")")


def detect_flat_format(df: pd.DataFrame | None) -> str | None:
    """Return ``old`` / ``new`` when the sheet is a flat commercial export."""
    if df is None or df.empty:
        return None
    headers = {normalize_header(value) for value in df.iloc[0].tolist()}
    headers.discard("")
    if "寻源单号" in headers:
        return "new"
    if "项目编码" in headers:
        return "old"
    return None


def _to_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.lower() in {"nan", "null", "none"}:
        return ""
    return text


def _to_amount(value: Any) -> float:
    text = _to_text(value)
    if not text:
        return 0.0
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return 0.0


def _format_amount(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _promote_header(df: pd.DataFrame) -> pd.DataFrame:
    """Use the first row as column names and return body rows."""
    raw_headers = [normalize_header(value) for value in df.iloc[0].tolist()]
    headers: list[str] = []
    seen: dict[str, int] = {}
    for idx, header in enumerate(raw_headers):
        if not header:
            header = f"__col_{idx}"
        count = seen.get(header, 0)
        seen[header] = count + 1
        if count:
            header = f"{header}_{count + 1}"
        headers.append(header)
    body = df.iloc[1:].copy()
    body.columns = headers[: body.shape[1]]
    return body.reset_index(drop=True)


def _pick_column(columns: list[str], *candidates: str) -> str | None:
    normalized = {normalize_header(name): name for name in columns}
    for candidate in candidates:
        key = normalize_header(candidate)
        if key in normalized:
            return normalized[key]
    return None


def _cell(row: pd.Series, column: str | None) -> str:
    if not column or column not in row.index:
        return ""
    return _to_text(row[column])


def _looks_like_bid_code(value: Any) -> bool:
    return bool(_BID_CODE_PATTERN.match(_to_text(value)))


def _looks_like_datetime(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    if _DATETIME_PATTERN.match(text):
        return True
    return "datetime" in text.lower()


def _looks_like_company_name(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    if _looks_like_bid_code(text) or _looks_like_datetime(text):
        return False
    if text.replace(".", "", 1).isdigit():
        return False
    return True


def _bid_code_header_index(headers: list[str]) -> int | None:
    for idx, header in enumerate(headers):
        if normalize_header(header) == "投标编号":
            return idx
    return None


def _realign_new_format_values(values: list[Any], headers: list[str]) -> list[Any]:
    """Fix rows where a multi-cell title shifts columns after 寻源单号."""
    bid_header_idx = _bid_code_header_index(headers)
    if bid_header_idx is None:
        return values

    bid_idx = next((idx for idx, value in enumerate(values) if _looks_like_bid_code(value)), None)
    if bid_idx is None or bid_idx == bid_header_idx:
        return values

    extra = bid_idx - bid_header_idx
    if extra <= 0:
        return values

    title = "".join(_to_text(value) for value in values[1 : 1 + extra + 1])
    return [values[0], title, *values[1 + extra + 1 :]]


def _realign_new_format_row(row: pd.Series, headers: list[str]) -> pd.Series:
    realigned = _realign_new_format_values(row.tolist(), headers)
    if len(realigned) < len(headers):
        realigned.extend([""] * (len(headers) - len(realigned)))
    return pd.Series(realigned[: len(headers)], index=headers, dtype=object)


def _format_source_ref(source_file: str, source_sheet: str, excel_row: int) -> str:
    parts = [part for part in (_to_text(source_file), _to_text(source_sheet)) if part]
    if not parts:
        return f"第{excel_row}行"
    return f"{' / '.join(parts)} / 第{excel_row}行"


def _empty_record(output_columns: list[str]) -> dict[str, str]:
    return {column: "" for column in output_columns}


def _build_winners_by_project(body: pd.DataFrame, project_col: str, status_col: str, company_col: str) -> dict[str, list[str]]:
    winners: dict[str, list[str]] = {}
    for _, row in body.iterrows():
        project_code = _cell(row, project_col)
        if not project_code:
            continue
        status = _cell(row, status_col)
        company = _cell(row, company_col)
        if not is_win_status(status) or not company:
            continue
        bucket = winners.setdefault(project_code, [])
        if company not in bucket:
            bucket.append(company)
    return winners


def _build_winner_by_inquiry(body: pd.DataFrame, inquiry_col: str, winner_col: str) -> dict[str, str]:
    winner_map: dict[str, str] = {}
    for _, row in body.iterrows():
        inquiry_no = _cell(row, inquiry_col)
        if not inquiry_no:
            continue
        winner = _cell(row, winner_col)
        if not winner or not _looks_like_company_name(winner):
            continue
        current = winner_map.get(inquiry_no, "")
        if not current or (not _looks_like_company_name(current) and _looks_like_company_name(winner)):
            winner_map[inquiry_no] = winner
    return winner_map


def parse_old_commercial_sheet(
    df: pd.DataFrame,
    *,
    purchaser: str,
    output_columns: list[str],
    source_file: str = "",
    source_sheet: str = "",
) -> list[dict[str, str]]:
    """Parse flat old commercial-network rows grouped by project code."""
    body = _promote_header(df)
    columns = [str(col) for col in body.columns]
    project_col = _pick_column(columns, "项目编码")
    company_col = _pick_column(columns, "供应商名称")
    status_col = _pick_column(columns, "中标状态")
    if not project_col or not company_col or not status_col:
        return []

    quote_col = _pick_column(columns, "报价金额(元)", "报价金额（元）")
    title_col = _pick_column(columns, "项目名称")
    type_col = _pick_column(columns, "项目类型")
    budget_col = _pick_column(columns, "项目预算(元)", "项目预算（元）")
    deadline_col = _pick_column(columns, "投标截止时间")
    handler_col = _pick_column(columns, "经办人")
    bid_code_col = _pick_column(columns, "投标编码")
    supplier_code_col = _pick_column(columns, "供应商编码")

    winners_by_project = _build_winners_by_project(body, project_col, status_col, company_col)
    records: list[dict[str, str]] = []

    for excel_row, (_, row) in enumerate(body.iterrows(), start=2):
        project_code = _cell(row, project_col)
        company_name = _cell(row, company_col)
        if not project_code or not company_name:
            continue

        status = _cell(row, status_col)
        quote_amount = _to_amount(_cell(row, quote_col))
        quote_text = _format_amount(quote_amount) if quote_amount > 0 else _cell(row, quote_col)
        winners = winners_by_project.get(project_code, [])
        title = _cell(row, title_col)
        won = is_win_status(status)

        record = _empty_record(output_columns)
        record.update(
            {
                "数据来源": _format_source_ref(source_file, source_sheet, excel_row),
                "询价单号": project_code,
                "摘要": title,
                "采购单位": purchaser,
                "寻源策略": _cell(row, type_col),
                "报价截止时间": _cell(row, deadline_col),
                "状态": status,
                "预估含税总额": _cell(row, budget_col),
                "中标供应商": "、".join(winners),
                "备注": _compose_remark(
                    handler=_cell(row, handler_col),
                    bid_code=_cell(row, bid_code_col),
                    supplier_code=_cell(row, supplier_code_col),
                ),
                "序号": "1",
                "物资编码/来源采购申请代码--物资描述": title,
                "公司名称": company_name,
                "总价(元)": quote_text,
                "含税合计总价(元)": quote_text,
            }
        )
        if won:
            record["中标金额(元)"] = _format_amount(quote_amount)
        records.append(record)

    return records


def parse_new_commercial_sheet(
    df: pd.DataFrame,
    *,
    purchaser: str,
    output_columns: list[str],
    source_file: str = "",
    source_sheet: str = "",
) -> list[dict[str, str]]:
    """Parse flat new commercial-network rows grouped by sourcing inquiry number."""
    body = _promote_header(df)
    columns = [str(col) for col in body.columns]
    inquiry_col = _pick_column(columns, "寻源单号")
    company_col = _pick_column(columns, "投标单位")
    winner_col = _pick_column(columns, "中标单位")
    if not inquiry_col or not company_col:
        return []

    status_col = _pick_column(columns, "中标状态", "状态")
    title_col = _pick_column(columns, "寻源标题")
    scope_col = _pick_column(columns, "寻源范围")
    category_col = _pick_column(columns, "寻源类别")
    budget_col = _pick_column(columns, "项目预算(元)", "项目预算（元）", "项目预算")
    quote_col = _pick_column(columns, "投标价格(元)", "投标价格（元）")
    win_price_col = _pick_column(columns, "中标价格(元)", "中标价格（元）")
    deadline_col = _pick_column(columns, "投标截止时间")
    handler_col = _pick_column(columns, "经办人")
    bid_code_col = _pick_column(columns, "投标编号")

    headers = [str(col) for col in body.columns]
    realigned_rows = [_realign_new_format_row(row, headers) for _, row in body.iterrows()]
    body = pd.DataFrame(realigned_rows, columns=headers)

    winner_by_inquiry = _build_winner_by_inquiry(body, inquiry_col, winner_col)
    records: list[dict[str, str]] = []

    for excel_row, (_, row) in enumerate(body.iterrows(), start=2):
        inquiry_no = _cell(row, inquiry_col)
        company_name = _cell(row, company_col)
        if not inquiry_no or not _looks_like_company_name(company_name):
            continue

        winner = winner_by_inquiry.get(inquiry_no, "")
        if winner and not _looks_like_company_name(winner):
            winner = ""
        status = _cell(row, status_col) if status_col else ""
        quote_amount = _to_amount(_cell(row, quote_col))
        quote_text = _format_amount(quote_amount) if quote_amount > 0 else _cell(row, quote_col)
        title = _cell(row, title_col)
        won = is_win_status(status) or (bool(winner) and company_name == winner)
        display_status = status if status else ("已中标" if won else "未中标")

        record = _empty_record(output_columns)
        record.update(
            {
                "数据来源": _format_source_ref(source_file, source_sheet, excel_row),
                "询价单号": inquiry_no,
                "摘要": title,
                "采购单位": purchaser,
                "询价类别": _cell(row, category_col),
                "寻源范围": _cell(row, scope_col),
                "报价截止时间": _cell(row, deadline_col),
                "状态": display_status,
                "预估含税总额": _cell(row, budget_col),
                "中标供应商": winner,
                "备注": _compose_remark(
                    handler=_cell(row, handler_col),
                    bid_code=_cell(row, bid_code_col),
                ),
                "序号": "1",
                "物资编码/来源采购申请代码--物资描述": title,
                "公司名称": company_name,
                "总价(元)": quote_text,
                "含税合计总价(元)": quote_text,
            }
        )
        if won:
            win_amount = quote_amount if quote_amount > 0 else _to_amount(_cell(row, win_price_col))
            record["中标金额(元)"] = _format_amount(win_amount)
        records.append(record)

    return records


def _compose_remark(*, handler: str = "", bid_code: str = "", supplier_code: str = "") -> str:
    parts: list[str] = []
    if handler:
        parts.append(f"经办人:{handler}")
    if bid_code:
        parts.append(f"投标编码:{bid_code}")
    if supplier_code:
        parts.append(f"供应商编码:{supplier_code}")
    return "; ".join(parts)


__all__ = [
    "WIN_STATUSES",
    "detect_flat_format",
    "is_win_status",
    "normalize_header",
    "parse_new_commercial_sheet",
    "parse_old_commercial_sheet",
]
