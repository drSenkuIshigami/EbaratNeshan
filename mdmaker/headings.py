"""Heading and list markers shared by PDF and DOCX conversion."""

from __future__ import annotations

import re

_LEVEL_IN_TEXT = re.compile(r"عنوان\s*سطح\s*([1-7۱-۷])")
_HASH_LEAD = re.compile(r"^(#{1,7})\s+")
_BANG_LEAD = re.compile(r"^(!{2,7})\s+")
_DASH_LEAD = re.compile(r"^(-{1,6})\s+")
_CHAPTER = re.compile(r"^فصل\s+")
_QUOTE_LINE = re.compile(r'^["«»\s]+$')
_BULLET_LEAD = re.compile(r"^[•●·o○◦▪▫]\s*")
_NUMBER_LEAD = re.compile(r"^((?:\d+\.)+\d+|\d+\.)\s+")
_DOT_LEAD = re.compile(r"^\.\s+")  # RTL-smashed "1. "

_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def to_en_digit(ch: str) -> str:
    return ch.translate(_EN_DIGITS)


def heading_level_from_style(style: str) -> int | None:
    m = re.search(r"(?:heading\s*|عنوان\s*)(\d+)", style or "", re.I)
    if m:
        return min(7, int(m.group(1)))
    return None


def heading_level_from_text(text: str) -> int | None:
    raw = text.strip()
    if not raw:
        return None
    m = _LEVEL_IN_TEXT.search(raw)
    if m:
        return int(to_en_digit(m.group(1)))
    m = _HASH_LEAD.match(raw)
    if m:
        return len(m.group(1))
    m = _BANG_LEAD.match(raw)
    if m:
        n = len(m.group(1))
        return min(7, n + 1) if n >= 4 else n
    m = _DASH_LEAD.match(raw)
    if m and _LEVEL_IN_TEXT.search(raw):
        return min(7, len(m.group(1)) + 1)
    return None


def heading_level_from_size(text: str, size: float, body_size: float) -> int | None:
    level = heading_level_from_text(text)
    if level:
        return level
    if len(text) < 90 and size >= body_size * 1.22:
        if size >= body_size * 1.28:
            return 1
        return 2
    return None


def clean_heading_text(text: str) -> str:
    raw = text.strip()
    raw = _CHAPTER.sub("", raw)
    raw = _HASH_LEAD.sub("", raw)
    raw = _BANG_LEAD.sub("", raw)
    if _LEVEL_IN_TEXT.search(raw):
        raw = _DASH_LEAD.sub("", raw)
    return raw.strip() or text.strip()


def atx(level: int, text: str) -> str:
    n = max(1, min(7, level))
    title = clean_heading_text(text)
    return f"{'#' * n} {title}"


def is_noise_line(text: str) -> bool:
    return bool(_QUOTE_LINE.fullmatch(text.strip()))


def looks_numbered(text: str) -> bool:
    return bool(_NUMBER_LEAD.match(text.strip()))


def is_smashed_number(text: str) -> bool:
    return bool(_DOT_LEAD.match(text.strip()))


def smashed_number_body(text: str) -> str:
    return _DOT_LEAD.sub("", text.strip()).strip()


def list_item(text: str, x0: float | None = None) -> str | None:
    raw = text.strip()
    if not raw:
        return None
    bullet = _BULLET_LEAD.match(raw)
    if bullet:
        depth = _indent_from_x(x0)
        if raw.lstrip().startswith(("o ", "○ ", "◦ ")):
            depth = max(depth, 1)
        body = _BULLET_LEAD.sub("", raw).strip()
        return ("  " * depth) + "- " + body
    if _DOT_LEAD.match(raw):
        return None
    num = _NUMBER_LEAD.match(raw)
    if num:
        marker = num.group(1).rstrip(".")
        depth = marker.count(".")
        return ("  " * depth) + raw
    return None


def _indent_from_x(x0: float | None) -> int:
    if x0 is None:
        return 0
    if x0 >= 370:
        return 0
    if x0 >= 310:
        return 1
    return 2
