"""Text preprocessing helpers."""

from __future__ import annotations


def normalize_text(text: str) -> str:
    return " ".join(text.split())
