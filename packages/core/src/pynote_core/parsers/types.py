"""Shared loader output."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedPart:
    """One raw unit from a loader — page (PDF), section (DOCX), segment (audio), etc.

    `ordinal` is the loader's 0-based position; the worker writes it through to
    `source_part.ordinal`. `text` may be empty (e.g. image-only PDF page) — that's
    fine; the embedding step will skip it.

    `headings` (RAG_ROADMAP 3.1) is optional structure metadata: dicts with
    `text`, `level` (1 = topmost) and `start` (char offset into `text`),
    ascending by `start`. Loaders that can't detect structure leave it None.
    """

    ordinal: int
    text: str
    page: int | None = None
    bbox: dict[str, Any] | None = field(default=None)
    headings: list[dict[str, Any]] | None = field(default=None)
