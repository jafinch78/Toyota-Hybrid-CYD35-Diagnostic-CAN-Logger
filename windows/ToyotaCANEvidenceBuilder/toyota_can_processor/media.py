from __future__ import annotations

import csv
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from PIL import Image

from .dependency_setup import (ensure_voice_dependencies, hidden_process_kwargs,
                               verify_external_tools)
from .graph_ocr import (correlate_with_can, extract_battery_graph, load_can_battery,
                        ordered_text, parse_dr_prius_block_tsv, parse_tsv,
                        prepare_dr_prius_block_strip, prepare_ocr_image, write_graph_csv)


def run_ocr(video: Path, output_csv: Path, interval_seconds: float = 2.0,
            profile: str = "AUTO", progress: Callable[[str], None] | None = None,
            graph_output_csv: Path | None = None, can_battery_csv: Path | None = None,
            vehicle_profile: str = "UNKNOWN", expected_blocks: int | None = None) -> dict:
    tools = verify_external_tools()
    ffmpeg = tools["ffmpeg"]
    tesseract = tools["tesseract"]
    profile = profile.upper().replace(" ", "_")
    if progress:
        progress(f"Extracting OCR frames from {video.name}")
    with tempfile.TemporaryDirectory(prefix="toyota_ocr_") as temporary:
        pattern = str(Path(temporary) / "frame_%07d.png")
        vf = f"fps=1/{interval_seconds}"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                   "-vf", vf, pattern]
        subprocess.run(command, check=True, **hidden_process_kwargs())
        frames = sorted(Path(temporary).glob("frame_*.png"))
        can_rows = load_can_battery(can_battery_csv)
        graph_rows = []
        crop_dir = output_csv.parent / "GRAPH_KEYFRAMES"
        with output_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Video_s", "RequestedProfile", "FrameMode", "DetectedApp", "DetectedLayout",
                             "Text", "NumericTokens", "Frame"])
            for index, frame in enumerate(frames):
                with Image.open(frame) as source_image:
                    detail_image = source_image.convert("RGB")
                    ocr_image, frame_mode = prepare_ocr_image(source_image)
                ocr_path = frame
                if frame_mode != "FULL_FRAME":
                    ocr_path = Path(temporary) / f"prepared_{index:07d}.png"
                    ocr_image.save(ocr_path, "PNG", optimize=True)
                psm = "6" if frame_mode == "LANDSCAPE_BAND" else "11"
                result = subprocess.run([tesseract, str(ocr_path), "stdout", "--psm", psm, "tsv"],
                                        check=False, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace",
                                        **hidden_process_kwargs())
                words = parse_tsv(result.stdout)
                detail_words = words
                if frame_mode == "LANDSCAPE_BAND":
                    detail_image = ocr_image
                    detail_result = subprocess.run(
                        [tesseract, str(ocr_path), "stdout", "--psm", "11", "tsv"],
                        check=False, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", **hidden_process_kwargs())
                    detail_words = parse_tsv(detail_result.stdout)
                text = ordered_text(words)
                direct_block_values = None
                dr_graph_bounds = None
                lowered = text.lower()
                if (frame_mode == "LANDSCAPE_BAND" and "battery monitor" in lowered
                        and "special features" not in lowered):
                    block_count = expected_blocks if expected_blocks and 8 <= expected_blocks <= 40 else 17
                    prepared_strip = prepare_dr_prius_block_strip(ocr_image, block_count)
                    if prepared_strip is not None:
                        block_strip, strip_meta = prepared_strip
                        strip_path = Path(temporary) / f"blocks_{index:07d}.png"
                        block_strip.save(strip_path, "PNG", optimize=True)
                        block_result = subprocess.run(
                            [tesseract, str(strip_path), "stdout", "--psm", "6", "tsv",
                             "-c", "tessedit_char_whitelist=0123456789."],
                            check=False, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", **hidden_process_kwargs())
                        direct_block_values = parse_dr_prius_block_tsv(
                            block_result.stdout, block_count, strip_meta["slot_height"])
                        dr_graph_bounds = (strip_meta["chart_left"], strip_meta["graph_top"],
                                           strip_meta["chart_right"], strip_meta["graph_bottom"])
                tokens = ";".join(re.findall(r"[-+]?\d+(?:\.\d+)?(?:\s*[°%A-Za-z/]+)?", text))
                graph = None
                try:
                    graph = extract_battery_graph(
                        ocr_image, words, index * interval_seconds, profile, vehicle_profile,
                        expected_blocks, frame.name, crop_dir, detail_image, detail_words,
                        direct_block_values, dr_graph_bounds)
                except Exception:
                    graph = None
                if graph:
                    correlate_with_can(graph, can_rows)
                    graph_rows.append(graph)
                writer.writerow([f"{index * interval_seconds:.3f}", profile, frame_mode,
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
    ensure_voice_dependencies(progress)
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
