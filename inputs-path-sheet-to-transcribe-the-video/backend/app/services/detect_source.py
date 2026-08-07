import os
import re
from pathlib import Path
from urllib.parse import urlparse

ONLINE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
)

LOCAL_EXTENSIONS = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".wav", ".m4a")


def _normalize(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _is_online(value: str) -> bool:
    lower = value.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return True
    if lower.startswith("www."):
        return True
    return any(domain in lower for domain in ONLINE_DOMAINS)


def _is_bare_filename(value: str) -> bool:
    """A filename without a directory — not a valid server path unless uploaded."""
    if "/" in value or "\\" in value:
        return False
    if re.match(r"^[a-zA-Z]:", value):
        return False
    return bool(Path(value).suffix)


def _is_local(value: str) -> bool:
    lower = value.lower()
    if lower.startswith("file://"):
        return True
    if re.match(r"^[a-zA-Z]:\\", value):
        return True
    if value.startswith("\\\\"):
        return True
    if value.startswith("/") and not value.startswith("//"):
        return True
    if any(lower.endswith(ext) for ext in LOCAL_EXTENSIONS):
        return not _is_bare_filename(value)
    return False


def detect_source(value: str) -> dict:
    """Detect whether input is a local file path or online video URL."""
    normalized = _normalize(value)
    if not normalized:
        return {
            "type": None,
            "normalized": "",
            "valid": False,
            "message": "Please enter a video path or URL",
        }

    online = _is_online(normalized)
    local = _is_local(normalized)

    if online and local:
        return {
            "type": None,
            "normalized": normalized,
            "valid": False,
            "message": "Input is ambiguous — please confirm local file or online URL",
        }

    if online:
        if normalized.startswith("www."):
            normalized = f"https://{normalized}"
        return {"type": "online", "normalized": normalized, "valid": True, "message": None}

    if local:
        if normalized.lower().startswith("file://"):
            normalized = normalized[7:]
            if normalized.startswith("/") and re.match(r"^/[A-Za-z]:", normalized):
                normalized = normalized[1:]
        return {"type": "local", "normalized": normalized, "valid": True, "message": None}

    return {
        "type": None,
        "normalized": normalized,
        "valid": False,
        "message": "Could not detect source type — use a valid path or URL",
    }


def validate_local_path(path_str: str) -> tuple[bool, str]:
    if _is_bare_filename(path_str):
        return (
            False,
            "Use Pick file to upload, or paste the full path (e.g. C:\\Videos\\clip.mp4)",
        )
    path = Path(path_str)
    if not path.exists():
        return False, f"File not found: {path_str}"
    if not path.is_file():
        return False, "Path is not a file"
    ext = path.suffix.lower()
    if ext not in LOCAL_EXTENSIONS:
        return False, f"Unsupported file format: {ext}"
    return True, ""


def validate_online_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Invalid URL scheme"
    if not parsed.netloc:
        return False, "Could not reach video URL"
    return True, ""


def _default_search_roots() -> list[Path]:
    roots: list[Path] = []
    home = Path.home()
    for name in ("Downloads", "Desktop", "Videos", "Documents"):
        candidate = home / name
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def find_local_files_by_name(filename: str, *, max_results: int = 8, max_depth: int = 5) -> list[str]:
    """Find local video files by filename under common user folders (instant pick-file flow)."""
    name = Path(filename.strip().strip('"')).name
    if not name:
        return []

    matches: list[str] = []
    seen: set[str] = set()

    def consider(path: Path) -> bool:
        if not path.is_file() or path.suffix.lower() not in LOCAL_EXTENSIONS:
            return False
        resolved = str(path.resolve())
        if resolved in seen:
            return False
        seen.add(resolved)
        matches.append(resolved)
        return len(matches) >= max_results

    for root in _default_search_roots():
        try:
            direct = root / name
            if direct.is_file() and consider(direct):
                return matches

            for child in root.iterdir():
                if not child.is_dir():
                    continue
                nested = child / name
                if nested.is_file() and consider(nested):
                    return matches

            for dirpath, dirnames, filenames in os.walk(root):
                rel = Path(dirpath).relative_to(root)
                if len(rel.parts) > max_depth:
                    dirnames.clear()
                    continue
                if name in filenames and consider(Path(dirpath) / name):
                    return matches
        except OSError:
            continue

    return matches
