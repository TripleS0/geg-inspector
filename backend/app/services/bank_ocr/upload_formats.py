"""银行 OCR 上传文件格式：统一白名单与扩展名说明。"""

from __future__ import annotations

# 栅格图片（经 Pillow 归一化为 PNG 后送 OCR）
RASTER_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".gif",
    }
)

# 矢量图（先栅格化再 OCR）
VECTOR_IMAGE_SUFFIXES: frozenset[str] = frozenset({".svg"})

# 多页文档
PDF_SUFFIXES: frozenset[str] = frozenset({".pdf"})

SUPPORTED_IMAGE_SUFFIXES: frozenset[str] = RASTER_IMAGE_SUFFIXES | VECTOR_IMAGE_SUFFIXES

SUPPORTED_UPLOAD_SUFFIXES: frozenset[str] = SUPPORTED_IMAGE_SUFFIXES | PDF_SUFFIXES

# 供前端 <input accept> 使用
UPLOAD_ACCEPT_ATTR = ",".join(sorted(SUPPORTED_UPLOAD_SUFFIXES))

# 人类可读说明（导入页提示）
UPLOAD_FORMAT_HINT = (
    "支持 PNG、JPEG、BMP、TIFF、WebP、GIF、SVG 及多页 PDF；"
    "矢量 SVG 会自动转为位图后识别"
)


def is_supported_upload(path: str) -> bool:
    """判断上传文件后缀是否在 OCR 白名单内。"""
    from pathlib import Path

    return Path(path).suffix.lower() in SUPPORTED_UPLOAD_SUFFIXES


def format_label(suffix: str) -> str:
    """将后缀转为展示用标签。"""
    mapping = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
        ".webp": "WebP",
        ".gif": "GIF",
        ".svg": "SVG",
        ".pdf": "PDF",
    }
    return mapping.get(suffix.lower(), suffix.lstrip(".").upper())
