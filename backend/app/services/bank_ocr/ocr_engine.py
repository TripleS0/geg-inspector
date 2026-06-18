"""PaddleOCR engine wrapper with lazy initialization."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.services.bank_ocr.image_preprocess import enhance_for_ocr, load_image_bgr


def _configure_model_home() -> None:
    model_dir = os.environ.get("PADDLE_OCR_MODEL_DIR") or os.environ.get("PADDLEOCR_HOME")
    if model_dir:
        path = Path(model_dir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.environ["PADDLEOCR_HOME"] = str(path)


@lru_cache(maxsize=1)
def get_text_engine() -> Any:
    """Return a cached PaddleOCR instance for plain text recognition."""
    _configure_model_home()
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, use_gpu=False)


@lru_cache(maxsize=1)
def get_structure_engine() -> Any:
    """Return a cached PPStructure instance for table recognition."""
    _configure_model_home()
    from paddleocr import PPStructure

    return PPStructure(show_log=False, use_gpu=False, lang="ch", table=True, ocr=True)


def recognize_page_text(image_path: str, *, top_ratio: float = 0.28) -> list[tuple[str, float]]:
    """Recognize text lines from the top portion of a page."""
    image = enhance_for_ocr(load_image_bgr(image_path))
    height = image.shape[0]
    top = image[: max(1, int(height * top_ratio))]
    engine = get_text_engine()
    raw = engine.ocr(top, cls=True) or []
    lines: list[tuple[str, float]] = []
    for block in raw:
        if not block:
            continue
        for item in block:
            if not item or len(item) < 2:
                continue
            text = str(item[1][0] or "").strip()
            score = float(item[1][1] or 0.0)
            if text:
                lines.append((text, score))
    return lines


def recognize_page_table(image_path: str) -> list[dict[str, Any]]:
    """Run PP-Structure table recognition on one page image."""
    image = enhance_for_ocr(load_image_bgr(image_path))
    engine = get_structure_engine()
    result = engine(image)
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def read_image_size(image_path: str) -> tuple[int, int]:
    image = load_image_bgr(image_path)
    height, width = image.shape[:2]
    return width, height
