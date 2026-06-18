"""将 PDF / 各类图片统一展开为 OCR 可用的页面 PNG。"""

from __future__ import annotations

from pathlib import Path

from app.services.bank_ocr.upload_formats import (
    PDF_SUFFIXES,
    RASTER_IMAGE_SUFFIXES,
    SUPPORTED_IMAGE_SUFFIXES,
    SUPPORTED_UPLOAD_SUFFIXES,
    VECTOR_IMAGE_SUFFIXES,
    is_supported_upload,
)

__all__ = [
    "SUPPORTED_IMAGE_SUFFIXES",
    "SUPPORTED_UPLOAD_SUFFIXES",
    "expand_upload_to_page_images",
    "is_supported_upload",
]


def _rasterize_svg(source: Path, target: Path, *, dpi: int = 200) -> None:
    """将 SVG 栅格化为 PNG；优先 cairosvg，失败时给出明确提示。"""
    try:
        import cairosvg
    except ImportError as err:
        raise ValueError(
            "当前环境未安装 SVG 栅格化依赖（cairosvg），请使用 PNG/JPEG 等位图，或安装 cairosvg 后重试"
        ) from err
    png_bytes = cairosvg.svg2png(url=str(source), dpi=dpi)
    target.write_bytes(png_bytes)


def _rasterize_image(source: Path, target: Path) -> None:
    """用 Pillow 将栅格图转为 PNG（GIF 取首帧，统一色彩空间）。"""
    from PIL import Image

    with Image.open(source) as img:
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        rgb = img.convert("RGB")
        rgb.save(target, "PNG")


def expand_upload_to_page_images(source_path: str | Path, output_dir: str | Path, *, dpi: int = 200) -> list[str]:
    """把一个上传文件展开为有序页面图片路径（均为 PNG）。"""
    src = Path(source_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()

    if suffix in RASTER_IMAGE_SUFFIXES | VECTOR_IMAGE_SUFFIXES:
        target = output / "page_0001.png"
        if suffix in VECTOR_IMAGE_SUFFIXES:
            _rasterize_svg(src, target, dpi=dpi)
        else:
            _rasterize_image(src, target)
        return [str(target.resolve())]

    if suffix in PDF_SUFFIXES:
        from pdf2image import convert_from_path

        pages = convert_from_path(str(src), dpi=dpi)
        paths: list[str] = []
        for index, page in enumerate(pages, start=1):
            target = output / f"page_{index:04d}.png"
            page.save(str(target), "PNG")
            paths.append(str(target.resolve()))
        return paths

    raise ValueError(f"不支持的文件类型：{src.name}（{suffix or '无后缀'}）")
