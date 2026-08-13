"""Camada FFmpeg: probe, thumbnails, extração de áudio e frames."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    codec: str = ""
    size: int = 0
    has_audio: bool = False
    audio_language: str = ""


def ffmpeg_available() -> bool:
    return shutil.which(settings.ffmpeg_bin) is not None


def ffprobe_available() -> bool:
    return shutil.which(settings.ffprobe_bin) is not None


def _run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    log.debug("exec: %s", " ".join(cmd[:8]))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise MediaError(f"{cmd[0]} falhou ({proc.returncode}): {proc.stderr[-600:]}")
    return proc


def probe(path: Path) -> MediaInfo:
    if not ffprobe_available():
        raise MediaError("ffprobe não encontrado. Instale o FFmpeg.")
    proc = _run(
        [
            settings.ffprobe_bin,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=120,
    )
    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format", {})
    info = MediaInfo(
        duration=float(fmt.get("duration", 0) or 0),
        size=int(fmt.get("size", 0) or 0),
    )
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not info.width:
            info.width = int(stream.get("width", 0) or 0)
            info.height = int(stream.get("height", 0) or 0)
            info.codec = stream.get("codec_name", "")
        elif stream.get("codec_type") == "audio":
            info.has_audio = True
            info.audio_language = (stream.get("tags") or {}).get("language", "")
    return info


def make_thumbnail(video_path: Path, video_id: int, at_seconds: float | None = None) -> str:
    """Gera thumbnail JPEG. Retorna caminho relativo a data/."""
    out_dir = settings.data_dir / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video_id}.jpg"

    if at_seconds is None:
        try:
            at_seconds = max(3.0, probe(video_path).duration * 0.12)
        except Exception:  # noqa: BLE001
            at_seconds = 5.0

    _run(
        [
            settings.ffmpeg_bin,
            "-y", "-loglevel", "error",
            "-ss", f"{at_seconds:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", f"scale={settings.thumbnail_width}:-2",
            "-q:v", "3",
            str(out),
        ],
        timeout=180,
    )
    return f"thumbnails/{out.name}"


def extract_audio(video_path: Path, video_id: int) -> Path:
    """Extrai áudio mono 16 kHz WAV — formato ideal para o Whisper."""
    tmp_dir = settings.data_dir / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / f"{video_id}.wav"
    _run(
        [
            settings.ffmpeg_bin,
            "-y", "-loglevel", "error",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out),
        ],
        timeout=7200,
    )
    return out


def extract_frames(video_path: Path, video_id: int, every_seconds: int = 30) -> list[tuple[float, Path]]:
    """Extrai frames periódicos para análise visual (slides, código na tela)."""
    out_dir = settings.data_dir / "frames" / str(video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            settings.ffmpeg_bin,
            "-y", "-loglevel", "error",
            "-i", str(video_path),
            "-vf", f"fps=1/{every_seconds},scale=1280:-2",
            "-q:v", "4",
            str(out_dir / "frame_%05d.jpg"),
        ],
        timeout=7200,
    )
    frames = sorted(out_dir.glob("frame_*.jpg"))
    return [(idx * every_seconds, p) for idx, p in enumerate(frames)]


def cleanup_temp(video_id: int) -> None:
    tmp = settings.data_dir / "temp" / f"{video_id}.wav"
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:  # pragma: no cover
            log.warning("Não foi possível remover %s", tmp)
