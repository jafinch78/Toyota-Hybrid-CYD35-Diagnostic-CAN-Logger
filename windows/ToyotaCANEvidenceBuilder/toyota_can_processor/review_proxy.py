from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from .dependency_setup import hidden_process_kwargs, resolve_tool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_video(path: Path) -> dict[str, Any]:
    ffprobe = resolve_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe is unavailable; review-proxy validation was skipped")
    result = subprocess.run([
        ffprobe, "-v", "error", "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
        "-of", "json", str(path),
    ], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
       **hidden_process_kwargs())
    data = json.loads(result.stdout)
    video = next((row for row in data.get("streams", []) if row.get("codec_type") == "video"), {})
    audio = next((row for row in data.get("streams", []) if row.get("codec_type") == "audio"), {})
    rate = str(video.get("r_frame_rate", "0/1")).split("/")
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
    return {
        "path": str(path), "sha256": _sha256(path),
        "size_bytes": int(data.get("format", {}).get("size", path.stat().st_size)),
        "duration_seconds": float(data.get("format", {}).get("duration", 0.0)),
        "bit_rate": int(data.get("format", {}).get("bit_rate", 0) or 0),
        "video_codec": video.get("codec_name"), "width": int(video.get("width", 0) or 0),
        "height": int(video.get("height", 0) or 0), "fps": fps,
        "audio_codec": audio.get("codec_name"), "audio_channels": audio.get("channels"),
        "audio_sample_rate": int(audio.get("sample_rate", 0) or 0),
    }


def assess_or_create_review_proxy(video: Path, output_root: Path,
                                  capture_sync: dict[str, Any] | None,
                                  *, enabled: bool = True,
                                  threshold_mb: float = 100.0,
                                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"enabled": enabled, "created": False, "warnings": []}
    try:
        original = inspect_video(video)
    except Exception as error:
        report["error"] = str(error)
        return report
    report["input"] = original
    if capture_sync:
        expected_width = capture_sync.get("video_width")
        expected_height = capture_sync.get("video_height")
        if ((expected_width and int(expected_width) != original["width"])
                or (expected_height and int(expected_height) != original["height"])):
            report["warnings"].append(
                "CAPTURE_SYNC video dimensions describe the original recording, not the supplied derivative")
            report["capture_sync_dimensions"] = {
                "width": expected_width, "height": expected_height,
            }
    already_compact = original["width"] <= 720 and original["fps"] <= 10.5
    if already_compact:
        report["decision"] = "ALREADY_OCR_COMPACT"
    elif not enabled:
        report["decision"] = "DISABLED"
    elif original["size_bytes"] < int(threshold_mb * 1024 * 1024):
        report["decision"] = "BELOW_SIZE_THRESHOLD"
    else:
        ffmpeg = resolve_tool("ffmpeg")
        if not ffmpeg:
            report["error"] = "FFmpeg is unavailable; review proxy was not created"
        else:
            target = output_root / "SCREEN_REVIEW_720W_10FPS.mp4"
            if progress:
                progress("Creating 720-pixel/10-fps OCR review proxy while preserving the original video")
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                "-vf", "scale='min(720,iw)':-2,fps=10", "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", "250k", "-maxrate", "350k", "-bufsize", "500k",
                "-c:a", "aac", "-ac", "1", "-b:a", "64k", "-movflags", "+faststart", str(target),
            ], check=True, **hidden_process_kwargs())
            proxy = inspect_video(target)
            duration_delta = abs(proxy["duration_seconds"] - original["duration_seconds"])
            if duration_delta > 0.25:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"Review proxy duration changed by {duration_delta:.3f} seconds")
            if not proxy.get("audio_codec"):
                target.unlink(missing_ok=True)
                raise RuntimeError("Review proxy lost the narration audio track")
            report.update({
                "created": True, "decision": "CREATED", "output": proxy,
                "duration_delta_seconds": duration_delta,
                "compression_ratio": proxy["size_bytes"] / original["size_bytes"],
            })
    (output_root / "CAPTURE_DERIVATIVE_REPORT.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report
