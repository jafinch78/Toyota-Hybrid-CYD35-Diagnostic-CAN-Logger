from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image

from .graph_ocr import (correlate_with_can, extract_battery_graph, load_can_battery,
                        ordered_text, parse_tsv, write_graph_csv)


def _require(command: str) -> str:
    path = shutil.which(command)
    if not path:
        raise RuntimeError(f"{command} was not found on PATH")
    return path


def run_ocr(video: Path, output_csv: Path, interval_seconds: float = 2.0,
            profile: str = "AUTO", progress: Callable[[str], None] | None = None,
            graph_output_csv: Path | None = None, can_battery_csv: Path | None = None,
            vehicle_profile: str = "UNKNOWN", expected_blocks: int | None = None) -> dict:
    ffmpeg = _require("ffmpeg")
    tesseract = _require("tesseract")
    profile = profile.upper().replace(" ", "_")
    if progress:
        progress(f"Extracting OCR frames from {video.name}")
    with tempfile.TemporaryDirectory(prefix="toyota_ocr_") as temporary:
        pattern = str(Path(temporary) / "frame_%07d.png")
        vf = f"fps=1/{interval_seconds}"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                   "-vf", vf, pattern]
        subprocess.run(command, check=True)
        frames = sorted(Path(temporary).glob("frame_*.png"))
        can_rows = load_can_battery(can_battery_csv)
        graph_rows = []
        crop_dir = output_csv.parent / "GRAPH_KEYFRAMES"
        with output_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Video_s", "RequestedProfile", "DetectedApp", "DetectedLayout",
                             "Text", "NumericTokens", "Frame"])
            for index, frame in enumerate(frames):
                result = subprocess.run([tesseract, str(frame), "stdout", "--psm", "11", "tsv"],
                                        check=False, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace")
                words = parse_tsv(result.stdout)
                text = ordered_text(words)
                tokens = ";".join(re.findall(r"[-+]?\d+(?:\.\d+)?(?:\s*[°%A-Za-z/]+)?", text))
                graph = None
                try:
                    with Image.open(frame) as image:
                        graph = extract_battery_graph(
                            image, words, index * interval_seconds, profile, vehicle_profile,
                            expected_blocks, frame.name, crop_dir)
                except Exception:
                    graph = None
                if graph:
                    correlate_with_can(graph, can_rows)
                    graph_rows.append(graph)
                writer.writerow([f"{index * interval_seconds:.3f}", profile,
                                 graph.get("App", "") if graph else "",
                                 graph.get("Layout", "") if graph else "",
                                 text, tokens, frame.name])
                if progress and index and index % 25 == 0:
                    progress(f"OCR processed {index}/{len(frames)} frames; battery graphs={len(graph_rows)}")
        if graph_output_csv is not None:
            write_graph_csv(graph_output_csv, graph_rows)
        matched = sum(1 for row in graph_rows if row.get("CANMatch") == "MATCHED")
        review_power = sum(1 for row in graph_rows if row.get("PowerPlausibility") == "REVIEW_OCR")
        return {"frames": len(frames), "interval_seconds": interval_seconds,
                "profile": profile, "output": str(output_csv),
                "battery_graph_rows": len(graph_rows), "can_matched_graph_rows": matched,
                "power_ocr_review_rows": review_power,
                "graph_output": str(graph_output_csv) if graph_output_csv else None,
                "graph_keyframes": str(crop_dir) if graph_rows else None}


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
