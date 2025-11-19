"""Shared helpers for parsing source files into structured text."""
from __future__ import annotations

import html
import re
from pathlib import Path


def read_text(path: Path) -> str:
    """Read UTF-8 text from disk.

    Centralizing file IO makes it easier to swap sources (e.g., cloud storage)
    without touching the parsing functions.
    """

    return path.read_text(encoding="utf-8")


def html_to_text(raw: str) -> str:
    """Convert HTML content into normalized plain text."""

    with_breaks = re.sub(r"(?i)<\s*br\s*/?>", "\n", raw)
    with_breaks = re.sub(r"(?i)</p>", "\n", with_breaks)
    with_breaks = re.sub(r"(?i)</div>", "\n", with_breaks)
    text = re.sub(r"<[^>]+>", " ", with_breaks)
    text = html.unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def clean_amount(raw: str) -> float:
    """Convert euro-formatted strings into floats (handles comma or dot decimals)."""

    normalized = re.sub(r"[€\s]", "", raw)

    # Detect European-style decimals (comma) vs. US-style (dot)
    if re.search(r",\d{2}$", normalized):
        normalized = normalized.replace(".", "")
        normalized = normalized.replace(",", ".")
    else:
        normalized = normalized.replace(",", "")

    return float(normalized)
