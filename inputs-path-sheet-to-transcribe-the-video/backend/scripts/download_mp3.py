"""Download a YouTube/video URL as MP3 for voice cloning samples.

Usage:
  python -m scripts.download_mp3 "https://www.youtube.com/watch?v=..."
  python -m scripts.download_mp3 "URL" --out D:\\samples
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python -m scripts.download_mp3` from backend/
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.media_bins import download_url_as_mp3, ensure_media_bins


def main() -> int:
    parser = argparse.ArgumentParser(description="Download video audio as MP3")
    parser.add_argument("url", help="YouTube or other video URL")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output folder (default: backend/tools/voice_samples)",
    )
    args = parser.parse_args()

    print("Checking yt-dlp + FFmpeg (auto-download if missing)…")
    bins = ensure_media_bins()
    print(f"  ffmpeg:  {bins['ffmpeg']}")
    print(f"  ffprobe: {bins['ffprobe']}")

    print(f"Downloading MP3 from:\n  {args.url}")
    path = download_url_as_mp3(args.url, args.out)
    print(f"Saved:\n  {path}")
    print("Upload this file on the Voice tab -> New voice from sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
