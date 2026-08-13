"""Transcrição com faster-whisper (GPU local) — padrão do modo privado.

O modelo é carregado uma única vez por processo e reaproveitado entre vídeos.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_model = None
_model_lock = threading.Lock()
_model_key: tuple[str, str, str] | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    confidence: float = 0.0


@dataclass
class TranscriptionResult:
    language: str
    duration: float
    segments: list[Segment]
    model: str
    engine: str = "faster-whisper"

    @property
    def confidence(self) -> float:
        if not self.segments:
            return 0.0
        return sum(s.confidence for s in self.segments) / len(self.segments)

    @property
    def plain_text(self) -> str:
        return "\n".join(s.text.strip() for s in self.segments if s.text.strip())

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "duration": self.duration,
            "model": self.model,
            "engine": self.engine,
            "confidence": self.confidence,
            "segments": [asdict(s) for s in self.segments],
        }


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _resolve_device() -> tuple[str, str]:
    device = settings.whisper_device
    compute = settings.whisper_compute_type
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # noqa: BLE001
            device = "cpu"
    if device == "cpu" and compute == "float16":
        compute = "int8"
    return device, compute


def get_model():
    """Carrega (uma vez) o modelo faster-whisper."""
    global _model, _model_key
    if not whisper_available():
        raise RuntimeError(
            "faster-whisper não instalado. Rode: pip install faster-whisper"
        )
    device, compute = _resolve_device()
    key = (settings.whisper_model, device, compute)
    with _model_lock:
        if _model is None or _model_key != key:
            from faster_whisper import WhisperModel

            log.info(
                "Carregando Whisper '%s' em %s (%s)...", settings.whisper_model, device, compute
            )
            _model = WhisperModel(
                settings.whisper_model,
                device=device,
                compute_type=compute,
                download_root=str(settings.data_dir / "models"),
            )
            _model_key = key
            log.info("Whisper pronto.")
    return _model


def transcribe(
    audio_path: Path,
    *,
    language: str | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> TranscriptionResult:
    import math

    model = get_model()
    lang = language or settings.transcription_language or None

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=lang,
        beam_size=settings.whisper_beam_size,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
        condition_on_previous_text=False,
    )

    total = float(getattr(info, "duration", 0.0) or 0.0)
    segments: list[Segment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        avg_lp = getattr(seg, "avg_logprob", None)
        conf = float(math.exp(avg_lp)) if avg_lp is not None else 0.0
        segments.append(
            Segment(start=float(seg.start), end=float(seg.end), text=text, confidence=conf)
        )
        if on_progress and total > 0:
            on_progress(min(0.99, float(seg.end) / total), text[:80])

    return TranscriptionResult(
        language=getattr(info, "language", lang or ""),
        duration=total,
        segments=segments,
        model=settings.whisper_model,
    )


def save_transcript(video_id: int, result: TranscriptionResult) -> tuple[str, str]:
    """Grava JSON com timestamps + TXT legível. Retorna caminhos relativos a data/."""
    out_dir = settings.data_dir / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{video_id}.json"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    txt_path = out_dir / f"{video_id}.txt"
    lines = [f"[{_ts(s.start)}] {s.text}" for s in result.segments]
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    return f"transcripts/{json_path.name}", f"transcripts/{txt_path.name}"


def load_transcript(rel_path: str) -> dict:
    path = settings.data_dir / rel_path
    if not path.exists():
        return {"segments": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
