from app.services.detect_source import validate_online_url
from app.services.media_bins import ensure_yt_dlp
from app.services.video import VideoError


def get_video_preview(url: str) -> dict:
    valid, msg = validate_online_url(url)
    if not valid:
        raise VideoError(msg)

    ensure_yt_dlp()
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise VideoError(f"Could not fetch video info: {e}") from e

    return {
        "title": info.get("title") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": float(info.get("duration") or 0),
        "uploader": info.get("uploader") or "",
    }
