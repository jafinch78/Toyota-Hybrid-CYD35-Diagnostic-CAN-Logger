from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


def _require(command: str) -> str:
    path = shutil.which(command)
    if not path:
        raise RuntimeError(f"{command} was not found on PATH")
    return path


def run_ocr(video: Path, output_csv: Path, interval_seconds: float = 2.0,
            profile: str = "AUTO", progress: Callable[[str], None] | None = None) -> dict:
    ffmpeg = _require("ffmpeg")
    tesseract = _require("tesseract")
    profile = profile.upper().replace(" ", "_")
    if progress:
        progress(f"Extracting OCR frames from {video.name}")
    with tempfile.TemporaryDirectory(prefix="toyota_ocr_") as temporary:
        pattern = str(Path(temporary) / "frame_%07d.png")
        vf = f"fps=1/{interval_seconds},scale=iw*1.5:ih*1.5:flags=lanczos"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                   "-vf", vf, pattern]
        subprocess.run(command, check=True)
        frames = sorted(Path(temporary).glob("frame_*.png"))
        with output_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Video_s", "Profile", "Text", "NumericTokens", "Frame"])
            for index, frame in enumerate(frames):
                result = subprocess.run([tesseract, str(frame), "stdout", "--psm", "11"],
                                        check=False, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace")
                text = " ".join(result.stdout.split())
                tokens = ";".join(re.findall(r"[-+]?\d+(?:\.\d+)?(?:\s*[°%A-Za-z/]+)?", text))
                writer.writerow([f"{index * interval_seconds:.3f}", profile, text, tokens, frame.name])
        return {"frames": len(frames), "interval_seconds": interval_seconds,
                "profile": profile, "output": str(output_csv)}


def run_transcription(video: Path, output_csv: Path, model_name: str = "small.en",
                      progress: Callable[[str], None] | None = None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("Voice transcription requires: pip install faster-whisper") from error
    if progress:
        progress(f"Transcribing narration with {model_name}; first use may download the model")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(video), vad_filter=True)
    count = 0
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Start_s", "End_s", "Language", "Probability", "Text"])
        for segment in segments:
            count += 1
            writer.writerow([f"{segment.start:.3f}", f"{segment.end:.3f}", info.language,
                             f"{info.language_probability:.4f}", segment.text.strip()])
    return {"segments": count, "language": info.language,
            "language_probability": info.language_probability, "output": str(output_csv)}
