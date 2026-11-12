"""Sentence-aware text chunking (spec 4.6, 5.4).

Chunks always end on a sentence boundary when possible, never split a paragraph
silently, and remember where paragraphs end so the right pause can be inserted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ABBREV = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "inc", "ltd",
           "co", "no", "fig", "approx", "e.g", "i.e", "u.s", "u.k", "a.m", "p.m", "mt"}
_BOUNDARY = re.compile(r"""([.!?…]+["'”’)\]]*)\s+""")
_CJK_BOUNDARY = re.compile(r"[。！？]+[」』”’）]*")
_CJK_END = "。！？」』”’）"
_PARA_SPLIT = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    paragraph_end: bool


def _is_abbrev(fragment: str) -> bool:
    words = fragment.split()
    if not words:
        return True
    last = words[-1].rstrip(".!?…\"'”’)]").lower()
    if last in _ABBREV:
        return fragment.rstrip().endswith(".")
    return bool(re.fullmatch(r"[A-Z]\.", words[-1]))


def split_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(paragraph):
        cand = paragraph[start:m.end(1)]
        if _is_abbrev(cand):
            continue  # "Dr. Smith" is not a sentence end
        out.append(cand.strip())
        start = m.end()
    rest = paragraph[start:].strip()
    if rest:
        out.append(rest)
    # CJK full stops are not followed by spaces
    final: list[str] = []
    for s in out:
        pos = 0
        for m in _CJK_BOUNDARY.finditer(s):
            if m.end() < len(s):
                final.append(s[pos:m.end()].strip())
                pos = m.end()
        tail = s[pos:].strip()
        if tail:
            final.append(tail)
    return [s for s in final if s]


def _split_long(sentence: str, limit: int) -> list[str]:
    """Break an over-long sentence at clause punctuation, then spaces, then hard."""
    parts: list[str] = []
    s = sentence.strip()
    while len(s) > limit:
        window = s[:limit]
        cut = max(window.rfind(", "), window.rfind("; "), window.rfind(": "),
                  window.rfind(" — "), window.rfind("、"), window.rfind("，"))
        if cut < limit * 0.4:
            cut = window.rfind(" ")
        if cut < limit * 0.4:
            cut = limit - 1  # no usable break (e.g. unspaced CJK): hard cut
        parts.append(s[:cut + 1].strip())
        s = s[cut + 1:].strip()
    if s:
        parts.append(s)
    return parts


def _join(a: str, b: str) -> str:
    return (a + b) if a and a[-1] in _CJK_END else f"{a} {b}"


def chunk_text(text: str, max_chars: int = 500, first_chars: int | None = None) -> list[Chunk]:
    """Split ``text`` (already normalised) into ordered chunks.

    The first chunk is kept shorter so audio is ready sooner (lower first-audio latency).
    """
    first_chars = min(first_chars or max_chars, max_chars)
    chunks: list[Chunk] = []
    paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]

    for p in paragraphs:
        p = re.sub(r"\s*\n\s*", " ", p)  # single line breaks flow as spaces
        pieces: list[str] = []
        for sentence in split_sentences(p):
            limit = first_chars if not chunks and not pieces else max_chars
            pieces.extend(_split_long(sentence, limit) if len(sentence) > limit else [sentence])

        current = ""
        para_chunks: list[str] = []
        for piece in pieces:
            limit = first_chars if (not chunks and not para_chunks) else max_chars
            candidate = _join(current, piece) if current else piece
            if current and len(candidate) > limit:
                para_chunks.append(current)
                current = piece
            else:
                current = candidate
        if current:
            para_chunks.append(current)

        for i, t in enumerate(para_chunks):
            chunks.append(Chunk(index=len(chunks), text=t, paragraph_end=(i == len(para_chunks) - 1)))
    return chunks
