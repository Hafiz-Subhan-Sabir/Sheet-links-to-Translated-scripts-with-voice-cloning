"""Ensure yt-dlp + FFmpeg exist; download them automatically when missing."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _BACKEND_DIR / "tools"
_FFMPEG_DIR = _TOOLS_DIR / "ffmpeg"

# Official Windows GPL build (essentials) — used only if nothing else is available
_FFMPEG_WIN_ZIP = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
    "latest/ffmpeg-master-latest-win64-gpl.zip"
)

_ffmpeg_path: Optional[str] = None
_ffprobe_path: Optional[str] = None
_ensured = False


def tools_dir() -> Path:
    _TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    return _TOOLS_DIR


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _configured_ffmpeg_hint() -> Optional[Path]:
    try:
        from app.config import get_settings

        raw = get_settings().ffmpeg_location.strip()
    except Exception:
        raw = (os.environ.get("FFMPEG_LOCATION") or "").strip()
    if not raw:
        return None
    return Path(raw)


def _path_from_hint(hint: Path, exe: str) -> Optional[str]:
    if hint.is_file():
        if hint.name.lower().startswith(exe.replace(".exe", "").lower()):
            return str(hint)
        # Directory-like path pointing at a binary name by mistake
        sibling = hint.with_name(exe)
        if sibling.is_file():
            return str(sibling)
        return str(hint) if exe.startswith("ffmpeg") else None
    candidate = hint / exe
    if candidate.is_file():
        return str(candidate)
    return None


def _bundled_ffmpeg(exe: str) -> Optional[str]:
    for base in (_FFMPEG_DIR, _FFMPEG_DIR / "bin", *_FFMPEG_DIR.glob("ffmpeg-*")):
        candidate = base / exe if base.is_dir() else None
        if candidate and candidate.is_file():
            return str(candidate)
        if base.is_dir():
            nested = base / "bin" / exe
            if nested.is_file():
                return str(nested)
    return None


def _imageio_ffmpeg() -> Optional[str]:
    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).is_file():
            return path
    except Exception as e:
        logger.warning("imageio-ffmpeg unavailable: %s", e)
    return None


def _download_ffmpeg_windows() -> Optional[str]:
    """Download a portable FFmpeg build into backend/tools/ffmpeg."""
    if sys.platform != "win32":
        return None
    tools_dir()
    zip_path = _TOOLS_DIR / "ffmpeg-win64.zip"
    logger.info("Downloading FFmpeg into %s …", _FFMPEG_DIR)
    try:
        urlretrieve(_FFMPEG_WIN_ZIP, zip_path)
        _FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(_FFMPEG_DIR)
        zip_path.unlink(missing_ok=True)
    except Exception as e:
        logger.error("FFmpeg download failed: %s", e)
        return None
    return _bundled_ffmpeg("ffmpeg.exe")


def ensure_yt_dlp() -> None:
    """Import yt-dlp; pip-install into the current interpreter if missing."""
    try:
        import yt_dlp  # noqa: F401

        return
    except ImportError:
        logger.warning("yt-dlp missing — installing with pip…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp>=2024.1.0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import yt_dlp  # noqa: F401


def ensure_ffmpeg() -> str:
    """
    Return path to ffmpeg.exe / ffmpeg.
    Order: config → PATH → backend/tools → imageio-ffmpeg (auto-download) → GitHub zip.
    """
    global _ffmpeg_path
    if _ffmpeg_path and Path(_ffmpeg_path).is_file():
        return _ffmpeg_path

    hint = _configured_ffmpeg_hint()
    if hint:
        found = _path_from_hint(hint, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if found:
            _ffmpeg_path = found
            return found

    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for candidate in (_which("ffmpeg"), _bundled_ffmpeg(exe)):
        if candidate and Path(candidate).is_file():
            _ffmpeg_path = candidate
            return candidate

    # Auto-download via imageio-ffmpeg cache
    img = _imageio_ffmpeg()
    if img:
        _ffmpeg_path = img
        logger.info("Using imageio-ffmpeg binary: %s", img)
        return img

    # Last resort: portable Windows build into tools/
    portable = _download_ffmpeg_windows()
    if portable:
        _ffmpeg_path = portable
        return portable

    raise RuntimeError(
        "FFmpeg not found and auto-download failed. "
        "Install FFmpeg or set FFMPEG_LOCATION in backend/.env"
    )


def ensure_ffprobe() -> str:
    """Return path to ffprobe; fall back near ffmpeg if needed."""
    global _ffprobe_path
    if _ffprobe_path and Path(_ffprobe_path).is_file():
        return _ffprobe_path

    hint = _configured_ffmpeg_hint()
    if hint:
        found = _path_from_hint(hint, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if found:
            _ffprobe_path = found
            return found

    exe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    for candidate in (_which("ffprobe"), _bundled_ffmpeg(exe)):
        if candidate and Path(candidate).is_file():
            _ffprobe_path = candidate
            return candidate

    ffmpeg = Path(ensure_ffmpeg())
    sibling = ffmpeg.with_name(exe)
    if sibling.is_file():
        _ffprobe_path = str(sibling)
        return _ffprobe_path

    # imageio only ships ffmpeg; probing can no-op in callers if missing
    _ffprobe_path = str(sibling)
    return _ffprobe_path


def ensure_media_bins() -> dict[str, str]:
    """Ensure yt-dlp + ffmpeg are available. Safe to call repeatedly."""
    global _ensured
    ensure_yt_dlp()
    ffmpeg = ensure_ffmpeg()
    ffprobe = ensure_ffprobe()
    _ensured = True
    logger.info("Media bins ready — ffmpeg=%s ffprobe=%s", ffmpeg, ffprobe)
    return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}


def ffmpeg_dir_for_ytdlp() -> str:
    """Directory containing ffmpeg, for yt-dlp's ffmpeg_location option."""
    ffmpeg = Path(ensure_ffmpeg())
    return str(ffmpeg.parent)


def _voice_samples_dir() -> Path:
    """Short, stable folder for voice-sample downloads (avoids Windows MAX_PATH issues)."""
    try:
        from app.config import get_settings

        base = Path(get_settings().data_dir)
    except Exception:
        base = _BACKEND_DIR / "data"
    dest = base / "voice_samples"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _safe_filename_stem(title: str, fallback: str = "voice-sample") -> str:
    stem = re.sub(r"[^\w\s\-]", "", title, flags=re.UNICODE).strip()
    stem = re.sub(r"\s+", "-", stem)[:60]
    return stem or fallback


def download_url_as_mp3(url: str, out_dir: Optional[Path] = None) -> Path:
    """Download a video URL as an MP3 file (for voice samples)."""
    ensure_media_bins()
    import yt_dlp

    dest = Path(out_dir) if out_dir else _voice_samples_dir()
    dest.mkdir(parents=True, exist_ok=True)

    # Temp dir keeps paths short on Windows; use video id (not title) for filenames.
    tmp_dir = Path(tempfile.mkdtemp(prefix="vts_dl_", dir=str(dest)))
    outtmpl = str(tmp_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        "quiet": False,
        "no_warnings": True,
        "restrictfilenames": True,
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "ffmpeg_location": ffmpeg_dir_for_ytdlp(),
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
            video_id = (info.get("id") if isinstance(info, dict) else None) or "audio"
            requested = ydl.prepare_filename(info)
        mp3 = Path(requested).with_suffix(".mp3")
        if not mp3.is_file():
            matches = sorted(tmp_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not matches:
                raise RuntimeError(f"MP3 was not created for {url}")
            mp3 = matches[0]

        final = dest / f"{video_id}.mp3"
        if final.exists():
            final.unlink()
        shutil.move(str(mp3), str(final))
        return final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def prepare_voice_sample_from_url(
    url: str,
    *,
    out_dir: Optional[Path] = None,
    start_sec: float = 0.0,
    duration_sec: float = 30.0,
) -> tuple[Path, str]:
    """
    Download audio from a URL and trim a short clip for Fish voice cloning.

    Returns (sample_mp3_path, source_title).
    """
    import subprocess
    import yt_dlp

    ensure_media_bins()
    dest = Path(out_dir) if out_dir else _voice_samples_dir()
    dest.mkdir(parents=True, exist_ok=True)

    # Metadata first (title) then download
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    title = (info.get("title") or info.get("id") or "voice-sample") if isinstance(info, dict) else "voice-sample"
    video_id = (info.get("id") if isinstance(info, dict) else None) or "voice-sample"

    full = download_url_as_mp3(url, dest)
    start = max(0.0, float(start_sec or 0.0))
    duration = max(5.0, min(90.0, float(duration_sec or 30.0)))

    safe_stem = _safe_filename_stem(title, fallback=video_id)
    sample = dest / f"{safe_stem}-sample-{int(start)}s-{int(duration)}s.mp3"

    ffmpeg = ensure_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(full),
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        str(sample),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not sample.is_file():
        raise RuntimeError(
            f"Could not trim voice sample: {(result.stderr or result.stdout or '')[:400]}"
        )
    return sample, str(title)
