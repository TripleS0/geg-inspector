"""Image preprocessing helpers for bank OCR."""

from __future__ import annotations

from typing import Any


def _cv2() -> Any:
    import cv2

    return cv2


def _numpy() -> Any:
    import numpy as np

    return np


def load_image_bgr(path: str) -> Any:
    """Load an image file as a BGR numpy array."""
    cv2 = _cv2()
    image = cv2.imread(path)
    if image is None:
        raise ValueError(f"无法读取图片：{path}")
    return image


def remove_red_stamp(image_bgr: Any) -> Any:
    """Reduce red watermark/stamp interference while keeping dark text."""
    cv2 = _cv2()
    np = _numpy()
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 70, 50])
    upper_red2 = np.array([180, 255, 255])
    mask = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
    cleaned = image_bgr.copy()
    cleaned[mask > 0] = (255, 255, 255)
    return cleaned


def enhance_for_ocr(image_bgr: Any) -> Any:
    """Apply red removal and contrast enhancement."""
    cv2 = _cv2()
    cleaned = remove_red_stamp(image_bgr)
    gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def save_preprocessed(image_bgr: Any, output_path: str) -> str:
    """Write preprocessed image to disk."""
    _cv2().imwrite(output_path, image_bgr)
    return output_path
