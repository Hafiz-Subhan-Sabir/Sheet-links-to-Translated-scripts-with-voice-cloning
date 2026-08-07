import subprocess
import tempfile
from pathlib import Path

import yt_dlp

from app.config import get_settings
from app.services.detect_source import validate_online_url


class VideoError(Exception):
    pass


def _base_ydl_opts() -> dict:
    opts: dict = {"quiet": True, "no_warnings": True}
    ffmpeg = get_settings().ffmpeg_location.strip()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    return opts


def _ffmpeg_binary() -> str:
    ffmpeg = get_settings().ffmpeg_location.strip()
    if ffmpeg:
        p = Path(ffmpeg)
        if p.is_file():
            return str(p)
        candidate = p / "ffmpeg.exe"
        if candidate.is_file():
            return str(candidate)
        return str(p / "ffmpeg.exe")
    return "ffmpeg"


def _ffprobe_binary() -> str:
    ffmpeg = get_settings().ffmpeg_location.strip()
    if ffmpeg:
        p = Path(ffmpeg)
        if p.is_file():
            return str(p.with_name("ffprobe.exe" if p.suffix.lower() == ".exe" else "ffprobe"))
        return str(p / "ffprobe.exe")
    return "ffprobe"


def probe_media_duration(path_str: str) -> float:
    """Return media duration in seconds via ffprobe (accurate for local video files)."""
    path = Path(path_str)
    if not path.exists():
        return 0.0
    try:
        result = subprocess.run(
            [
                _ffprobe_binary(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return max(0.0, float(result.stdout.strip()))
    except Exception:
        pass
    return 0.0


def download_audio_from_url(url: str) -> tuple[str, float]:
    valid, msg = validate_online_url(url)
    if not valid:
        raise VideoError(msg)

    tmp_dir = tempfile.mkdtemp(prefix="vts_audio_")
    out_template = str(Path(tmp_dir) / "audio.%(ext)s")

    ydl_opts = {
        **_base_ydl_opts(),
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "extractaudio": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration = float(info.get("duration") or 0)
    except yt_dlp.utils.DownloadError as e:
        err = str(e).lower()
        if "private" in err:
            raise VideoError("Video is private or unavailable") from e
        if "geo" in err or "region" in err:
            raise VideoError("Video is geo-blocked in your region") from e
        if "sign in" in err or "login" in err:
            raise VideoError("Video requires authentication") from e
        raise VideoError(f"Could not download video: {e}") from e
    except Exception as e:
        raise VideoError(f"Could not reach video URL: {e}") from e

    audio_files = list(Path(tmp_dir).glob("audio.*"))
    if not audio_files:
        raise VideoError("Failed to extract audio from video")

    return str(audio_files[0]), duration


def prepare_local_audio(path_str: str) -> tuple[str, float]:
    path = Path(path_str)
    if not path.exists():
        raise VideoError("File not found at path")

    ext = path.suffix.lower()
    audio_exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
    probed = probe_media_duration(str(path))
    if ext in audio_exts:
        return str(path), probed

    tmp_dir = tempfile.mkdtemp(prefix="vts_local_")
    out_path = str(Path(tmp_dir) / "audio.mp3")

    try:
        result = subprocess.run(
            [
                _ffmpeg_binary(),
                "-y",
                "-i",
                str(path),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "5",
                out_path,
            ],
            capture_output=True,
            text=True,
            timeout=max(120, int(probed * 2) + 30) if probed > 0 else 600,
            check=False,
        )
        if result.returncode != 0:
            raise VideoError(
                f"FFmpeg could not extract audio. Is FFmpeg installed? {result.stderr[:300]}"
            )
        if not Path(out_path).exists():
            raise VideoError("FFmpeg did not produce an audio file")
        return out_path, probed
    except subprocess.TimeoutExpired as e:
        raise VideoError("Audio extraction timed out — file may be too large or corrupt") from e
    except VideoError:
        raise
    except Exception as e:
        raise VideoError(f"Could not prepare audio from file: {e}") from e
