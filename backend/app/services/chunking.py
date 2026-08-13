"""Divide segmentos do Whisper em trechos pesquisáveis com timestamps preservados.

Estratégia: agrupa segmentos consecutivos até ~1100 caracteres, quebrando
preferencialmente em fim de frase, com sobreposição para não perder contexto
na fronteira entre trechos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings

_SENTENCE_END = re.compile(r"[.!?…](\s|$)")


@dataclass
class Chunk:
    seq: int
    start: float
    end: float
    text: str
    chapter: str = ""

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.text) // 4)


def chunk_segments(
    segments: list[dict],
    *,
    target_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[Chunk]:
    target = target_chars or settings.chunk_target_chars
    overlap = overlap_chars or settings.chunk_overlap_chars

    chunks: list[Chunk] = []
    buffer: list[dict] = []
    buffer_len = 0
    seq = 0

    def flush(carry: list[dict] | None = None) -> None:
        nonlocal buffer, buffer_len, seq
        if not buffer:
            return
        text = " ".join(s["text"].strip() for s in buffer).strip()
        if text:
            chunks.append(
                Chunk(
                    seq=seq,
                    start=float(buffer[0]["start"]),
                    end=float(buffer[-1]["end"]),
                    text=text,
                )
            )
            seq += 1
        buffer = list(carry or [])
        buffer_len = sum(len(s["text"]) for s in buffer)

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        buffer.append(seg)
        buffer_len += len(text) + 1

        if buffer_len >= target:
            ends_sentence = bool(_SENTENCE_END.search(text[-3:] + " "))
            if ends_sentence or buffer_len >= target * 1.5:
                # sobreposição: mantém os últimos segmentos até `overlap` chars
                carry: list[dict] = []
                acc = 0
                for s in reversed(buffer):
                    acc += len(s["text"])
                    carry.insert(0, s)
                    if acc >= overlap:
                        break
                flush(carry if overlap > 0 else None)

    flush()
    return chunks


def assign_chapters(chunks: list[Chunk], chapters: list[dict]) -> list[Chunk]:
    """Marca cada trecho com o capítulo correspondente (para citações mais claras)."""
    if not chapters:
        return chunks
    ordered = sorted(chapters, key=lambda c: float(c.get("start", 0)))
    for chunk in chunks:
        current = ""
        for ch in ordered:
            if float(ch.get("start", 0)) <= chunk.start:
                current = ch.get("title", "")
            else:
                break
        chunk.chapter = current
    return chunks


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
