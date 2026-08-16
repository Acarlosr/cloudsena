"""Importação de playlists do YouTube sem baixar o vídeo inteiro.

Filosofia deste módulo, importante pra entender as escolhas abaixo: listar uma
playlist é "olhar a vitrine" (metadados, sem baixar nada). Transcrever um vídeo
baixa só o **áudio** — sempre bem menor que o vídeo — transcreve local com o
mesmo Whisper usado nos cursos baixados, e descarta o áudio depois (mesma
convenção de `data/temp/{video_id}.wav` usada por `services/media.py`, então
`step_transcribe` e `cleanup_temp` funcionam sem precisar saber a origem).

Trade-off aceito conscientemente: não guardamos o vídeo. Isso significa que a
reprodução na interface usa o player embutido do YouTube (iframe), não o
`<video>` local com streaming por Range — ver `components/YouTubePlayer.tsx`
no frontend. Se o vídeo for removido/tornar-se privado no YouTube depois de
transcrito, a transcrição e a busca continuam funcionando; só a reprodução
para de funcionar (comportamento esperado, não um bug).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class YoutubeError(RuntimeError):
    pass


def available() -> bool:
    try:
        import yt_dlp  # noqa: F401

        return True
    except ImportError:
        return False


def _require_yt_dlp():
    if not available():
        raise YoutubeError("yt-dlp não instalado. Rode: pip install yt-dlp")
    import yt_dlp

    return yt_dlp


@dataclass
class PlaylistEntry:
    youtube_id: str
    title: str
    url: str
    duration_seconds: float
    channel: str
    playlist_index: int
    thumbnail: str = ""


def extract_playlist(url: str) -> tuple[str, list[PlaylistEntry]]:
    """Lista os vídeos de uma playlist sem baixar nada (só metadados).

    Retorna (título_da_playlist, entradas). Levanta YoutubeError se a URL não
    resolver — playlist privada, removida, ou não é playlist de verdade.
    """
    yt_dlp = _require_yt_dlp()
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        raise YoutubeError(f"Não foi possível ler a playlist: {exc}") from exc

    if not info:
        raise YoutubeError("Playlist vazia ou inacessível.")

    entries_raw = info.get("entries") or ([info] if info.get("id") else [])
    if not entries_raw:
        raise YoutubeError("Nenhum vídeo encontrado nessa URL.")

    entries: list[PlaylistEntry] = []
    for idx, e in enumerate(entries_raw, start=1):
        if not e or not e.get("id"):
            continue
        entries.append(
            PlaylistEntry(
                youtube_id=e["id"],
                title=e.get("title") or f"Vídeo {e['id']}",
                url=e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
                duration_seconds=float(e.get("duration") or 0),
                channel=e.get("channel") or e.get("uploader") or "",
                playlist_index=idx,
                thumbnail=(e.get("thumbnails") or [{}])[-1].get("url", ""),
            )
        )
    playlist_title = info.get("title") or "Playlist do YouTube"
    return playlist_title, entries


def fetch_video_duration(youtube_id: str) -> float:
    """Consulta metadados de UM vídeo (sem baixar mídia) — usado quando a
    listagem 'achatada' da playlist não trouxe a duração."""
    yt_dlp = _require_yt_dlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={youtube_id}", download=False)
        return float((info or {}).get("duration") or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao consultar duração de %s: %s", youtube_id, exc)
        return 0.0


def download_audio_wav(youtube_id: str, video_pk: int) -> Path:
    """Baixa só a trilha de áudio e converte pra WAV mono 16kHz — o formato que
    o Whisper espera. Usa o mesmo caminho/convenção de `media.extract_audio`
    (`data/temp/{video_pk}.wav`) para que o resto do pipeline (transcrição,
    limpeza) não precise saber se a origem é local ou YouTube."""
    yt_dlp = _require_yt_dlp()
    tmp_dir = settings.data_dir / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_base = tmp_dir / str(video_pk)
    final_wav = tmp_dir / f"{video_pk}.wav"

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_base) + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
        "postprocessor_args": {
            # mono 16kHz — mesma spec de media.extract_audio, ideal pro Whisper.
            "ffmpeg": ["-ac", "1", "-ar", "16000"],
        },
        "ffmpeg_location": settings.ffmpeg_bin if settings.ffmpeg_bin != "ffmpeg" else None,
    }
    opts = {k: v for k, v in opts.items() if v is not None}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={youtube_id}"])
    except Exception as exc:  # noqa: BLE001
        raise YoutubeError(f"Falha ao baixar áudio de {youtube_id}: {exc}") from exc

    if not final_wav.exists():
        raise YoutubeError(f"Áudio baixado mas arquivo esperado não apareceu: {final_wav}")
    return final_wav


_THUMB_QUALITIES = ("maxresdefault", "hqdefault", "mqdefault", "default")


def download_thumbnail(youtube_id: str, video_pk: int) -> str:
    """Baixa a melhor thumbnail disponível direto da CDN do YouTube (não
    precisa do vídeo pra isso). Retorna caminho relativo a data/, mesmo
    contrato de `media.make_thumbnail`."""
    out_dir = settings.data_dir / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video_pk}.jpg"

    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        for quality in _THUMB_QUALITIES:
            url = f"https://i.ytimg.com/vi/{youtube_id}/{quality}.jpg"
            try:
                resp = client.get(url)
                # O YouTube devolve um placeholder cinza 120x90 (respondendo 200)
                # quando a qualidade pedida não existe — filtramos pelo tamanho
                # em bytes, que é bem menor pro placeholder que pra thumbnail real.
                if resp.status_code == 200 and len(resp.content) > 2000:
                    out.write_bytes(resp.content)
                    return f"thumbnails/{out.name}"
            except httpx.HTTPError:
                continue
    log.warning("Nenhuma thumbnail disponível para %s", youtube_id)
    return ""
