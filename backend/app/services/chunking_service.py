from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    chunk_index: int
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_markdown(text: str, *, max_chars: int = 1200, overlap: int = 120) -> list[ChunkDraft]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    sections = _split_markdown_sections(normalized)
    pieces: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            pieces.append(section.strip())
        else:
            pieces.extend(_window(section, max_chars=max_chars, overlap=overlap))

    drafts: list[ChunkDraft] = []
    for index, piece in enumerate(part for part in pieces if part.strip()):
        cleaned = piece.strip()
        drafts.append(ChunkDraft(text=cleaned, chunk_index=index, token_count=estimate_tokens(cleaned)))
    return drafts


def _split_markdown_sections(text: str) -> list[str]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(preamble)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(text[match.start() : end].strip())
    return sections


def _window(text: str, *, max_chars: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    safe_overlap = min(overlap, max(0, max_chars // 4))
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split_at = text.rfind("\n\n", start + 1, end)
            if split_at <= start:
                split_at = text.rfind("\n", start + 1, end)
            if split_at > start:
                end = split_at
        if end <= start:
            end = min(len(text), start + max_chars)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        next_start = end - safe_overlap
        start = next_start if next_start > start else end
    return [chunk for chunk in chunks if chunk]
