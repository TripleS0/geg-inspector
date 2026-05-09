"""企查查 ECIV4 GetBasicDetailsByName 代理、名称解析与 Excel 导出。"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.runtime_paths import data_dir, project_root

QICHACHA_BASIC_URL = "https://api.qichacha.com/ECIV4/GetBasicDetailsByName"
QICHACHA_CONFIG_FILENAME = "qichacha_config.json"


def qichacha_config_file_path() -> Path:
    """推荐：可写 data 目录下的配置文件（目录默认已被 .gitignore 忽略）。"""
    return data_dir() / QICHACHA_CONFIG_FILENAME


def _credentials_from_json_file(path: Path) -> Tuple[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(raw, dict):
        return "", ""
    key = str(raw.get("app_key") or raw.get("QICHACHA_APP_KEY") or "").strip()
    secret = str(raw.get("secret_key") or raw.get("QICHACHA_SECRET_KEY") or "").strip()
    return key, secret


def _credential_json_paths() -> List[Path]:
    """按顺序尝试的配置文件路径（环境变量未设置时使用，先到先得）。"""
    cfg = project_root() / "app" / "resources" / "config"
    return [
        data_dir() / QICHACHA_CONFIG_FILENAME,
        cfg / QICHACHA_CONFIG_FILENAME,
        cfg / "qichacha_config.example.json",
    ]


def qichacha_credentials() -> Tuple[str, str]:
    """读取 AppKey 与 SecretKey：优先环境变量，再依次尝试多个 JSON 配置文件。"""
    key = (os.environ.get("QICHACHA_APP_KEY") or "").strip()
    secret = (os.environ.get("QICHACHA_SECRET_KEY") or "").strip()
    if key and secret:
        return key, secret

    for path in _credential_json_paths():
        k, s = _credentials_from_json_file(path)
        if k and s:
            return k, s
    return "", ""


def build_qichacha_headers(app_key: str, secret_key: str) -> Dict[str, str]:
    """生成 Timespan、Token（MD5 大写）请求头。"""
    timespan = str(int(time.time()))
    raw = f"{app_key}{timespan}{secret_key}"
    token = hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
    return {"Timespan": timespan, "Token": token}


def column_letter_to_index(letter: str) -> int:
    """A -> 0, B -> 1, …"""
    s = (letter or "").strip().upper()
    if not s or not re.match(r"^[A-Z]+$", s):
        raise ValueError("列字母无效，请使用 A–Z…")
    idx = 0
    for ch in s:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def normalize_keywords(raw: List[str]) -> List[str]:
    """strip、去空、去重（保序）。"""
    seen: set[str] = set()
    out: List[str] = []
    for item in raw:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def parse_form_keywords_text(raw: Optional[str]) -> List[str]:
    """表单或 JSON 数组字符串 -> 名称列表。"""
    if not raw or not str(raw).strip():
        return []
    t = str(raw).strip()
    if t.startswith("["):
        data = json.loads(t)
        if not isinstance(data, list):
            raise ValueError("keywords 的 JSON 须为数组")
        return [str(x).strip() for x in data if str(x).strip()]
    return parse_keywords_from_text(t)


def parse_keywords_from_text(text: str) -> List[str]:
    """多行或逗号分隔的名称列表。"""
    parts: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "，" in line or "," in line:
            for seg in re.split(r"[，,]+", line):
                t = seg.strip()
                if t:
                    parts.append(t)
        else:
            parts.append(line)
    return parts


def parse_names_from_txt(content: bytes) -> List[str]:
    """UTF-8 文本，每行一名。"""
    text = content.decode("utf-8-sig")
    return parse_keywords_from_text(text)


def parse_names_from_excel(
    path: Path,
    *,
    column_index: int = 0,
    skip_header: bool = False,
) -> List[str]:
    """首张工作表单列，自上而下每行一个企业名称。"""
    import pandas as pd

    suffix = path.suffix.lower()
    engine: Optional[str] = None
    if suffix == ".xls":
        engine = "xlrd"
    df = pd.read_excel(path, sheet_name=0, header=None, dtype=str, engine=engine)
    if df.empty:
        return []
    if column_index < 0 or column_index >= len(df.columns):
        raise ValueError("列索引超出表格范围")
    col = df.iloc[:, column_index]
    values = col.tolist()
    if skip_header and values:
        values = values[1:]
    raw: List[str] = []
    for v in values:
        if v is None or (isinstance(v, float) and str(v) == "nan"):
            continue
        s = str(v).strip()
        if s:
            raw.append(s)
    return raw


def fetch_basic_details_by_name(
    keyword: str,
    *,
    app_key: str,
    secret_key: str,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """调用企查查接口，返回 JSON 字典。"""
    headers = build_qichacha_headers(app_key, secret_key)
    q = urllib.parse.urlencode({"key": app_key, "keyword": keyword})
    url = f"{QICHACHA_BASIC_URL}?{q}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"企查查 HTTP {err.code}: {detail}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"企查查请求失败: {err}") from err
    return json.loads(body)


def flatten_result_body(result: Any) -> Dict[str, Any]:
    """将 Result 对象展平为单层 dict（嵌套 dict 用下划线连接键；列表 JSON 字符串）。"""
    import pandas as pd

    if not isinstance(result, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in result.items():
        if v is None:
            out[k] = None
        elif isinstance(v, dict):
            sub = pd.json_normalize([v], sep="_").to_dict(orient="records")
            if sub:
                for sk, sv in sub[0].items():
                    out[f"{k}_{sk}"] = sv
        elif isinstance(v, list):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    return out


def qichacha_response_to_export_row(query_keyword: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """单次 API 响应 -> 导出表一行。"""
    row: Dict[str, Any] = {"query_keyword": query_keyword}
    row["qcc_Status"] = data.get("Status")
    row["qcc_Message"] = data.get("Message")
    row["qcc_OrderNumber"] = data.get("OrderNumber")
    status = str(data.get("Status") or "")
    result = data.get("Result")
    if status != "200" or not isinstance(result, dict):
        row["error_message"] = data.get("Message") or data.get("error") or "无 Result 或查询失败"
        return row
    flat = flatten_result_body(result)
    row.update(flat)
    return row


def responses_to_excel_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """多行字典 -> xlsx 字节。"""
    import pandas as pd

    if not rows:
        df = pd.DataFrame([{"提示": "没有可导出的数据"}])
    else:
        df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="工商信息")
    return buf.getvalue()


def extract_log_fields(
    query_keyword: str,
    data: Optional[Dict[str, Any]],
    *,
    duration_ms: int,
    error_detail: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """从响应中提取日志字段：api_status, api_message, order_number, matched_name, credit_code。"""
    if data is None:
        return None, None, None, None, None
    api_status = str(data.get("Status")) if data.get("Status") is not None else None
    api_message = str(data.get("Message")) if data.get("Message") is not None else None
    order_number = str(data.get("OrderNumber")) if data.get("OrderNumber") is not None else None
    result = data.get("Result")
    matched = None
    credit = None
    if isinstance(result, dict):
        if result.get("Name") is not None:
            matched = str(result.get("Name"))
        if result.get("CreditCode") is not None:
            credit = str(result.get("CreditCode"))
    return api_status, api_message, order_number, matched, credit
