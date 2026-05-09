"""Data desensitization service functions reused by UI pages."""

from __future__ import annotations

import io
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List, Tuple

if TYPE_CHECKING:
    import pandas as pd

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".txt"}

NAME_PATTERN = re.compile(r"(?<![\u4e00-\u9fa5])([\u4e00-\u9fa5]{2,4})(?![\u4e00-\u9fa5])")
CARD_PATTERN = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")
COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉"
    "岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧"
    "尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵"
    "席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝"
    "管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉龚程邢滑裴陆荣翁"
    "荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全"
    "郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿"
    "白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶"
    "堵冉宰郦雍璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦"
    "艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越"
    "夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆"
    "红游竺权逯盖益桓公"
)
NON_NAME_TOKENS = {"收入", "支出", "交易类型", "询价单", "采购单", "备件"}


def _require_pandas():
    """Import pandas lazily and provide friendly dependency error."""
    try:
        import pandas as pd  # type: ignore
    except ImportError as err:
        raise ValueError("缺少依赖 pandas，请先执行: pip install -r requirements.txt") from err
    return pd


def mask_name(name: str) -> str:
    """Mask a Chinese name by keeping first character."""
    if len(name) <= 1:
        return name
    return name[0] + "*" * (len(name) - 1)


def mask_bank_card(card_number: str) -> str:
    """Mask bank card number keeping first 6 and last 4 digits."""
    if len(card_number) < 10:
        return card_number
    return f"{card_number[:6]}{'*' * (len(card_number) - 10)}{card_number[-4:]}"


def desensitize_text(text: str) -> str:
    """Apply bank-card and name masking to a plain text."""
    masked = CARD_PATTERN.sub(lambda m: mask_bank_card(m.group(1)), text)
    return NAME_PATTERN.sub(_mask_name_if_likely_person, masked)


def _mask_name_if_likely_person(match: re.Match[str]) -> str:
    """Reduce false positives for common business words."""
    token = match.group(1)
    if token in NON_NAME_TOKENS:
        return token
    if token and token[0] in COMMON_SURNAMES:
        return mask_name(token)
    return token


def collect_supported_files(input_paths: Iterable[Path]) -> List[Path]:
    """Collect all supported files from files or folders recursively."""
    result: List[Path] = []
    for source in input_paths:
        path = source.expanduser()
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            result.append(path)
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    result.append(child)

    seen: set[str] = set()
    unique_files: List[Path] = []
    for file_path in result:
        norm = str(file_path.resolve())
        if norm not in seen:
            seen.add(norm)
            unique_files.append(file_path)
    return unique_files


def process_single_file(file_path: Path) -> Tuple[Path, Path]:
    """Desensitize one file and return source/output tuple."""
    suffix = file_path.suffix.lower()
    if suffix == ".txt":
        return file_path, process_txt_file(file_path)
    if suffix in {".xlsx", ".xls"}:
        return file_path, process_excel_file(file_path)
    raise ValueError(f"不支持的文件类型: {suffix}")


def build_output_path(src_file: Path) -> Path:
    """Build output path under sibling folder named 脱敏结果."""
    output_dir = src_file.parent / "脱敏结果"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"脱敏_{src_file.stem}{src_file.suffix}"


def process_txt_file(src_file: Path) -> Path:
    """Process one txt file with encoding fallback."""
    output_file = build_output_path(src_file)
    encodings = ["utf-8", "utf-8-sig", "gbk"]
    content: list[str] | None = None
    for encoding in encodings:
        try:
            with src_file.open("r", encoding=encoding) as file:
                content = file.readlines()
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        raise ValueError("无法读取文本文件编码。")

    with output_file.open("w", encoding="utf-8") as file:
        for line in content:
            file.write(desensitize_text(line))
    return output_file


def process_excel_file(src_file: Path) -> Path:
    """Process one excel file and keep original extension."""
    pd = _require_pandas()
    output_file = build_output_path(src_file)
    suffix = src_file.suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        workbook = pd.read_excel(src_file, sheet_name=None, dtype=object, engine=engine)
    except Exception as err:
        if suffix == ".xls":
            html_tables = _try_read_html_tables(src_file)
            if html_tables:
                workbook = {f"Sheet{i + 1}": df for i, df in enumerate(html_tables)}
            else:
                raise ValueError(f"Excel 格式错误（{src_file.suffix}）: {err}") from err
        else:
            raise ValueError(f"Excel 格式错误（{src_file.suffix}）: {err}") from err

    masked_workbook: dict[str, pd.DataFrame] = {}
    for sheet_name, dataframe in workbook.items():
        masked = dataframe.copy()
        for column in masked.columns:
            masked[column] = masked[column].apply(
                lambda value: desensitize_text(str(value)) if pd.notna(value) else value
            )
        masked_workbook[sheet_name] = masked

    if suffix == ".xls":
        _write_xls_html_file(masked_workbook, output_file)
    else:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            for sheet_name, dataframe in masked_workbook.items():
                dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return output_file


def _try_read_html_tables(src_file: Path):
    """Try reading HTML-table based xls export files."""
    pd = _require_pandas()
    for encoding in ["utf-8", "utf-8-sig", "gbk", "gb18030", "latin1"]:
        try:
            raw_text = src_file.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        if "<table" not in raw_text.lower():
            continue
        try:
            return pd.read_html(io.StringIO(raw_text))
        except Exception:
            fallback = _parse_html_tables_with_stdlib(raw_text)
            if fallback:
                return fallback
    return []


class _SimpleHTMLTableParser(HTMLParser):
    """Simple standard-library HTML table parser."""

    def __init__(self) -> None:
        """Initialize parser state."""
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: List[List[str]] = []
        self._current_row: List[str] = []
        self._cell_buffer: List[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        """Handle start tags and update parse state."""
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_buffer = []
        elif self._in_cell and tag == "br":
            self._cell_buffer.append("\n")

    def handle_data(self, data: str) -> None:
        """Collect current cell text."""
        if self._in_cell:
            self._cell_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Handle end tags and flush table content."""
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(unescape("".join(self._cell_buffer)).strip())
            self._in_cell = False
            self._cell_buffer = []
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False
            self._current_table = []


def _parse_html_tables_with_stdlib(raw_text: str):
    """Parse html tables without external parser dependency."""
    pd = _require_pandas()
    parser = _SimpleHTMLTableParser()
    try:
        parser.feed(raw_text)
        parser.close()
    except Exception:
        return []

    result: List[pd.DataFrame] = []
    for table in parser.tables:
        if not table:
            continue
        max_columns = max(len(row) for row in table)
        normalized = [row + [""] * (max_columns - len(row)) for row in table]
        result.append(pd.DataFrame(normalized))
    return result


def _write_xls_html_file(workbook, output_file: Path) -> None:
    """Write xls-compatible html table output."""
    pd = _require_pandas()

    def escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    parts = ['<html><head><meta charset="utf-8"></head><body>']
    for index, (sheet_name, dataframe) in enumerate(workbook.items()):
        if index > 0:
            parts.append('<div style="page-break-before: always;"></div>')
        parts.append(f"<h3>{escape_html(str(sheet_name))}</h3>")
        parts.append('<table border="1" cellspacing="0" cellpadding="3">')
        if len(dataframe.columns) > 0:
            parts.append("<tr>")
            for column in dataframe.columns:
                parts.append(f"<th>{escape_html(str(column))}</th>")
            parts.append("</tr>")
        for _, row in dataframe.iterrows():
            parts.append("<tr>")
            for cell in row:
                text = "" if pd.isna(cell) else str(cell)
                parts.append(f"<td>{escape_html(text)}</td>")
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    output_file.write_text("".join(parts), encoding="utf-8")
