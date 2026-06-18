"""Phone number normalization helpers for telecom analysis."""

from __future__ import annotations

import re

_DIGITS_ONLY = re.compile(r"\D+")


def normalize_phone(value: str) -> str:
    """Normalize carrier phone values for comparison (86136... -> 13609047915)."""
    text = (value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    digits = _DIGITS_ONLY.sub("", text)
    if not digits:
        return ""
    if digits.startswith("0086") and len(digits) > 11:
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    if len(digits) > 11:
        digits = digits[-11:]
    return digits


def is_mobile_phone(value: str) -> bool:
    """Return True for a normalized mainland mobile number."""
    digits = normalize_phone(value)
    return len(digits) == 11 and digits.startswith("1")


def display_phone(value: str) -> str:
    """Prefer normalized 11-digit display when possible."""
    normalized = normalize_phone(value)
    return normalized or (value or "").strip()


__all__ = ["display_phone", "is_mobile_phone", "normalize_phone"]
