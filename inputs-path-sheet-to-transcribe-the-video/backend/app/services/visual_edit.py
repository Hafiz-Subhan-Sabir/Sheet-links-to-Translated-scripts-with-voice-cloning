"""Script → timed visual beats → AI stills → rough MP4 + CapCut edit pack."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import get_settings
from app.services.media_bins import ensure_ffmpeg, ensure_ffprobe, ensure_media_bins
from app.services.studio_llm import StudioLLMError, llm_complete

logger = logging.getLogger(__name__)

WORDS_PER_SEC = 2.5  # ~150 wpm narration
TARGET_BEAT_SEC = 4.0
MIN_BEAT_SEC = 3.0
MAX_BEAT_SEC = 5.0
MAX_BEATS = 36
ProgressCb = Callable[[str, float], None]


@dataclass
class VisualBeat:
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    narration: str
    visual_type: str  # ai_image | broll | text_card | screen
    image_prompt: str
    on_screen_text: str
    camera_move: str
    edit_note: str
    image_filename: Optional[str] = None


class VisualEditError(Exception):
    pass


def edit_packs_dir() -> Path:
    settings = get_settings()
    dest = Path(settings.data_dir) / "edit_packs"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def resolve_voice_mp3(filename: Optional[str]) -> Optional[Path]:
    if not filename:
        return None
    safe = Path(filename).name
    if safe != filename or ".." in filename or not safe.lower().endswith(".mp3"):
        return None
    from app.services.voice_clone import resolve_voice_output_dir

    out_dir = resolve_voice_output_dir().resolve()
    path = (out_dir / safe).resolve()
    if not str(path).startswith(str(out_dir)) or not path.is_file():
        return None
    return path


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                ensure_ffprobe(),
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
            return max(0.1, float(result.stdout.strip()))
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)
    return 0.0


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _estimate_duration(text: str) -> float:
    words = len(re.findall(r"\w+", text))
    return max(MIN_BEAT_SEC, words / WORDS_PER_SEC)


def _chunk_into_beats(text: str, audio_duration: Optional[float] = None) -> list[dict[str, Any]]:
    sentences = _split_sentences(text)
    if not sentences:
        raise VisualEditError("Script is empty")

    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        candidate = f"{buf} {sentence}".strip() if buf else sentence
        dur = _estimate_duration(candidate)
        if buf and dur > MAX_BEAT_SEC:
            chunks.append(buf)
            buf = sentence
        else:
            buf = candidate
            if _estimate_duration(buf) >= TARGET_BEAT_SEC:
                chunks.append(buf)
                buf = ""
    if buf:
        chunks.append(buf)

    # Merge leftover tiny chunks into previous; also fold very short openers forward
    merged: list[str] = []
    for chunk in chunks:
        if merged and _estimate_duration(chunk) < MIN_BEAT_SEC:
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    # If first beat is a tiny hook ("Stop scrolling."), attach next sentence
    if len(merged) >= 2 and _estimate_duration(merged[0]) < MIN_BEAT_SEC:
        merged[0] = f"{merged[0]} {merged[1]}".strip()
        merged.pop(1)

    if len(merged) > MAX_BEATS:
        # Fold overflow into last allowed beat
        head = merged[: MAX_BEATS - 1]
        tail = " ".join(merged[MAX_BEATS - 1 :])
        merged = head + [tail]

    raw_durs = [_estimate_duration(c) for c in merged]
    total_est = sum(raw_durs) or 1.0
    target_total = audio_duration if audio_duration and audio_duration > 1 else total_est
    scale = target_total / total_est

    beats: list[dict[str, Any]] = []
    cursor = 0.0
    for i, chunk in enumerate(merged):
        dur = max(MIN_BEAT_SEC, min(8.0, raw_durs[i] * scale))
        if i == len(merged) - 1 and audio_duration and audio_duration > cursor:
            dur = max(MIN_BEAT_SEC, audio_duration - cursor)
        start = cursor
        end = cursor + dur
        beats.append(
            {
                "index": i + 1,
                "start_sec": round(start, 2),
                "end_sec": round(end, 2),
                "duration_sec": round(dur, 2),
                "narration": chunk,
            }
        )
        cursor = end
    return beats


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict) and isinstance(data.get("beats"), list):
            return [x for x in data["beats"] if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    raise VisualEditError("AI did not return valid visual beat JSON")


def enrich_beats_with_llm(base_beats: list[dict[str, Any]]) -> list[VisualBeat]:
    payload = [
        {"index": b["index"], "narration": b["narration"], "duration_sec": b["duration_sec"]}
        for b in base_beats
    ]
    system = (
        "You are a YouTube editor. For each narration beat, invent a concrete visual. "
        "Return ONLY a JSON array (no markdown). Each item must have: "
        "index (number), visual_type (ai_image|broll|text_card|screen), "
        "image_prompt (English, photoreal or clean 3D, ABSOLUTELY NO text/letters/logos/watermarks, 16:9), "
        "on_screen_text (max 6 words or empty — this is captions, not in the image), "
        "camera_move (push_in|static|pan|zoom_out), "
        "edit_note (one short CapCut tip)."
    )
    user = (
        "Create visuals for these timed beats. Keep image_prompt specific and filmable.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        raw = llm_complete(system, user, max_tokens=6000, temperature=0.55)
        enriched = {int(item.get("index") or 0): item for item in _parse_json_array(raw)}
    except (StudioLLMError, VisualEditError, ValueError, TypeError) as e:
        logger.warning("LLM visual enrich failed, using heuristics: %s", e)
        enriched = {}

    beats: list[VisualBeat] = []
    for b in base_beats:
        extra = enriched.get(int(b["index"]), {})
        narration = b["narration"]
        prompt = str(extra.get("image_prompt") or "").strip()
        if not prompt:
            prompt = (
                f"Cinematic 16:9 still for YouTube B-roll about: {narration[:160]}. "
                "Photoreal, natural light, no text, no watermark, no logos."
            )
        vtype = str(extra.get("visual_type") or "ai_image").strip().lower()
        if vtype not in {"ai_image", "broll", "text_card", "screen"}:
            vtype = "ai_image"
        beats.append(
            VisualBeat(
                index=int(b["index"]),
                start_sec=float(b["start_sec"]),
                end_sec=float(b["end_sec"]),
                duration_sec=float(b["duration_sec"]),
                narration=narration,
                visual_type=vtype,
                image_prompt=prompt,
                on_screen_text=str(extra.get("on_screen_text") or "")[:80],
                camera_move=str(extra.get("camera_move") or "push_in"),
                edit_note=str(extra.get("edit_note") or "Cut on the keyword; keep captions big."),
            )
        )
    return beats


def _download_bytes(url: str, timeout: float = 90.0) -> bytes:
    req = Request(url, headers={"User-Agent": "VoltScriptVisualEdit/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data:
        raise VisualEditError("Empty image download")
    return data


def generate_still(prompt: str, dest: Path) -> Path:
    """Generate a still. Default: free Pollinations. Optional OpenAI if OPENAI_IMAGE_MODEL is set."""
    settings = get_settings()
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean_prompt = (
        f"{prompt.strip()} "
        "No text, no letters, no watermarks, no logos, no UI, cinematic 16:9."
    )

    def _placeholder() -> Path:
        ensure_ffmpeg()
        subprocess.run(
            [
                ensure_ffmpeg(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1a1a2e:s=1280x720:d=1",
                "-frames:v",
                "1",
                str(dest),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if not dest.is_file():
            dest.write_bytes(b"")
        return dest

    model = (settings.openai_image_model or "").strip()
    key = settings.openai_api_key.strip()
    if model and key:
        try:
            from openai import OpenAI
            import base64

            client = OpenAI(api_key=key, timeout=45.0)
            size = "1024x1024" if model.startswith("dall-e-2") else "1536x1024"
            resp = client.images.generate(
                model=model,
                prompt=clean_prompt[:3800],
                size=size,
                n=1,
            )
            item = resp.data[0]
            b64 = getattr(item, "b64_json", None)
            if b64:
                dest.write_bytes(base64.b64decode(b64))
                return dest
            url = getattr(item, "url", None)
            if url:
                dest.write_bytes(_download_bytes(url, timeout=45.0))
                return dest
        except Exception as e:
            logger.warning("OpenAI image gen failed (%s), trying Pollinations: %s", model, e)

    try:
        encoded = quote(clean_prompt[:700])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true"
        dest.write_bytes(_download_bytes(url, timeout=40.0))
        if dest.is_file() and dest.stat().st_size > 1000:
            return dest
    except Exception as e:
        logger.warning("Pollinations still failed, using placeholder: %s", e)

    return _placeholder()


def write_srt(beats: list[VisualBeat], path: Path) -> Path:
    def _ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    lines: list[str] = []
    for beat in beats:
        text = (beat.on_screen_text or beat.narration).strip()
        if len(text) > 90:
            text = text[:87] + "…"
        lines.append(str(beat.index))
        lines.append(f"{_ts(beat.start_sec)} --> {_ts(beat.end_sec)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_capcut_guide(beats: list[VisualBeat], path: Path, *, has_audio: bool, has_video: bool) -> Path:
    steps = [
        "# CapCut import (almost zero work)",
        "",
        "This pack is pre-timed so CapCut is optional. Prefer the auto-built MP4 first.",
        "",
        "## Fast path (recommended)",
        "1. Open **rough_cut.mp4** — voice + AI stills + captions already assembled.",
        "2. Optional: drop into CapCut → AutoCut / polish transitions.",
        "",
        "## Manual CapCut path",
        "1. New project → **9:16** for Shorts or **16:9** for long-form.",
        "2. Import **voice.mp3** (or your Speak MP3) onto the main audio track.",
        "3. Import every file in **stills/** in order (`001.jpg`, `002.jpg`, …).",
        "4. Stretch each still to match the times in **timeline.json** (start/end seconds).",
        "5. Import **captions.srt** → CapCut → Text → Auto captions / import SRT.",
        "6. Apply Ken Burns (push-in) on each still — camera_move is already suggested per beat.",
        "7. Export 1080p.",
        "",
        f"- Audio included: {'yes' if has_audio else 'no (estimate timing from script)'}",
        f"- Rough MP4 included: {'yes' if has_video else 'no'}",
        f"- Beats: {len(beats)}",
        "",
        "## Beat cheat sheet",
        "",
    ]
    for b in beats:
        steps.append(
            f"- **{b.index:02d}** `{b.start_sec:.1f}s–{b.end_sec:.1f}s` · {b.visual_type} · "
            f"{b.camera_move} — {b.edit_note}"
        )
    path.write_text("\n".join(steps) + "\n", encoding="utf-8")
    return path


def _make_clip(image: Path, duration: float, out: Path) -> None:
    ffmpeg = ensure_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(image),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p,"
        "zoompan=z='min(zoom+0.0008,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-an",
        str(out),
    ]
    # zoompan with -loop can be finicky; fallback to simple still if it fails
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and out.is_file():
        return
    simple = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(image),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-an",
        str(out),
    ]
    result2 = subprocess.run(simple, capture_output=True, text=True)
    if result2.returncode != 0 or not out.is_file():
        raise VisualEditError(
            f"FFmpeg clip failed: {(result2.stderr or result.stderr or '')[:400]}"
        )


def build_rough_mp4(
    beats: list[VisualBeat],
    stills_dir: Path,
    audio_path: Optional[Path],
    srt_path: Path,
    out_mp4: Path,
) -> Path:
    ensure_media_bins()
    ffmpeg = ensure_ffmpeg()
    work = out_mp4.parent / "_clips"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    for beat in beats:
        img_name = beat.image_filename or f"{beat.index:03d}.jpg"
        img = stills_dir / img_name
        if not img.is_file():
            raise VisualEditError(f"Missing still for beat {beat.index}: {img_name}")
        clip = work / f"clip_{beat.index:03d}.mp4"
        _make_clip(img, max(MIN_BEAT_SEC, beat.duration_sec), clip)
        clip_paths.append(clip)

    list_file = work / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in clip_paths) + "\n",
        encoding="utf-8",
    )
    silent = work / "silent.mp4"
    concat = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(silent),
        ],
        capture_output=True,
        text=True,
    )
    if concat.returncode != 0 or not silent.is_file():
        raise VisualEditError(f"Concat failed: {(concat.stderr or '')[:400]}")

    # Burn soft captions when possible; otherwise mux audio only
    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
    if audio_path and audio_path.is_file():
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(silent),
            "-i",
            str(audio_path),
            "-vf",
            f"subtitles='{srt_escaped}':force_style='FontSize=22,PrimaryColour=&H00FFFFFF&,Outline=2'",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(out_mp4),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out_mp4.is_file():
            # Retry without burned-in subs
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(silent),
                    "-i",
                    str(audio_path),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    str(out_mp4),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not out_mp4.is_file():
                raise VisualEditError(f"Mux audio failed: {(result.stderr or '')[:400]}")
    else:
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(silent),
                "-vf",
                f"subtitles='{srt_escaped}':force_style='FontSize=22,Outline=2'",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(out_mp4),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not out_mp4.is_file():
            shutil.copy2(silent, out_mp4)

    shutil.rmtree(work, ignore_errors=True)
    return out_mp4


def _safe_slug(title: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", (title or "edit").strip(), flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:48]
    return slug or "edit"


def run_auto_edit_pack(
    *,
    script: str,
    title: str = "edit",
    voice_mp3_filename: Optional[str] = None,
    generate_images: bool = True,
    build_video: bool = True,
    on_progress: Optional[ProgressCb] = None,
) -> dict[str, Any]:
    def prog(step: str, p: float) -> None:
        if on_progress:
            on_progress(step, min(0.99, max(0.0, p)))

    text = (script or "").strip()
    if len(text) < 20:
        raise VisualEditError("Paste a longer script (at least a few sentences).")

    ensure_media_bins()
    prog("Timing script into 3–5s beats", 0.05)
    audio = resolve_voice_mp3(voice_mp3_filename)
    audio_dur = _probe_duration(audio) if audio else None
    base = _chunk_into_beats(text, audio_dur)

    prog("Suggesting visuals with AI", 0.15)
    beats = enrich_beats_with_llm(base)

    slug = _safe_slug(title)
    pack_dir = edit_packs_dir() / f"{slug}-{beats[0].start_sec:.0f}s-{len(beats)}b"
    if pack_dir.exists():
        shutil.rmtree(pack_dir, ignore_errors=True)
    stills = pack_dir / "stills"
    stills.mkdir(parents=True, exist_ok=True)

    if audio and audio.is_file():
        shutil.copy2(audio, pack_dir / "voice.mp3")

    if generate_images:
        for i, beat in enumerate(beats):
            prog(f"Generating still {i + 1}/{len(beats)}", 0.2 + 0.55 * (i / max(1, len(beats))))
            name = f"{beat.index:03d}.jpg"
            dest = stills / name
            try:
                generate_still(beat.image_prompt, dest)
                beat.image_filename = name
            except Exception as e:
                logger.warning("Still %s failed: %s", beat.index, e)
                # Tiny placeholder JPEG via ffmpeg color source
                ensure_ffmpeg()
                subprocess.run(
                    [
                        ensure_ffmpeg(),
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=0x1a1a2e:s=1280x720:d=1",
                        "-frames:v",
                        "1",
                        str(dest),
                    ],
                    capture_output=True,
                    text=True,
                )
                beat.image_filename = name if dest.is_file() else None

    prog("Writing captions + CapCut guide", 0.78)
    srt_path = write_srt(beats, pack_dir / "captions.srt")
    timeline = {
        "title": title,
        "beat_seconds_target": TARGET_BEAT_SEC,
        "audio_file": "voice.mp3" if audio else None,
        "beats": [asdict(b) for b in beats],
    }
    (pack_dir / "timeline.json").write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    mp4_name = None
    if build_video and any(b.image_filename for b in beats):
        prog("Building rough MP4", 0.84)
        try:
            out_mp4 = pack_dir / "rough_cut.mp4"
            build_rough_mp4(
                beats,
                stills,
                pack_dir / "voice.mp3" if audio else None,
                srt_path,
                out_mp4,
            )
            if out_mp4.is_file():
                public_mp4 = edit_packs_dir() / f"{pack_dir.name}.mp4"
                shutil.copy2(out_mp4, public_mp4)
                mp4_name = public_mp4.name
        except Exception as e:
            logger.exception("Rough MP4 failed")
            (pack_dir / "video_error.txt").write_text(str(e)[:1000], encoding="utf-8")

    write_capcut_guide(
        beats,
        pack_dir / "CAPCUT_IMPORT.md",
        has_audio=bool(audio),
        has_video=bool(mp4_name),
    )

    prog("Zipping edit pack", 0.94)
    zip_path = edit_packs_dir() / f"{pack_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in pack_dir.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=str(file.relative_to(pack_dir)))

    return {
        "title": title,
        "pack_dir": str(pack_dir),
        "zip_filename": zip_path.name,
        "mp4_filename": mp4_name,
        "beat_count": len(beats),
        "has_audio": bool(audio),
        "beats": [asdict(b) for b in beats],
        "capcut_note": (
            "CapCut has no public auto-import API. Open rough_cut.mp4 or follow CAPCUT_IMPORT.md "
            "— stills, voice, and captions are already timed."
        ),
    }
