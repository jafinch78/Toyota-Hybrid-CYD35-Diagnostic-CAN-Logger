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
from .graph_ocr import (correlate_with_can, detect_app_layout, extract_battery_graph, load_can_battery,
                        ordered_text, parse_dr_prius_block_tsv, parse_tsv,
                        prepare_dr_prius_block_strip, prepare_ocr_image, write_graph_csv)


def run_ocr(video: Path, output_csv: Path, interval_seconds: float = 2.0,
            profile: str = "AUTO", progress: Callable[[str], None] | None = None,
            graph_output_csv: Path | None = None, can_battery_csv: Path | None = None,
            vehicle_profile: str = "UNKNOWN", expected_blocks: int | None = None,
            keyframe_dir: Path | None = None) -> dict:
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
        keyframe_rows = []
        frame_detections: list[tuple[float, str, str, str]] = []
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
                psm = "6" if frame_mode in {"LANDSCAPE_BAND", "YELLOW_GUIDE_CROP"} else "11"
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
                lowered = text.lower()
                detected_app, detected_layout = detect_app_layout(text, "AUTO")
                frame_detections.append((index * interval_seconds, detected_app,
                                         detected_layout, frame_mode))
                keyframe_terms = ("battery block vol", "internal resistance", "temp of batt",
                                  "state of charge", "model code", "inverter coolant")
                if keyframe_dir is not None and any(term in lowered for term in keyframe_terms):
                    if not keyframe_rows or index * interval_seconds - keyframe_rows[-1][0] >= 4.0:
                        keyframe_dir.mkdir(parents=True, exist_ok=True)
                        time_token = f"{index * interval_seconds:08.3f}".replace(".", "_")
                        keyframe_name = f"ocr_{time_token}s.jpg"
                        detail_image.save(keyframe_dir / keyframe_name, "JPEG", quality=78, optimize=True)
                        keyframe_rows.append((index * interval_seconds, keyframe_name,
                                              " ".join(text.split())[:500]))
                direct_block_values = None
                dr_graph_bounds = None
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
                        ocr_image, words, index * interval_seconds,
                        detected_app if detected_app != "UNKNOWN" else profile, vehicle_profile,
                        expected_blocks, frame.name, crop_dir, detail_image, detail_words,
                        direct_block_values, dr_graph_bounds)
                except Exception:
                    graph = None
                if graph:
                    correlate_with_can(graph, can_rows)
                    graph_rows.append(graph)
                writer.writerow([f"{index * interval_seconds:.3f}", profile, frame_mode,
                                 graph.get("App", detected_app) if graph else detected_app,
                                 graph.get("Layout", detected_layout) if graph else detected_layout,
                                 text, tokens, frame.name])
                if progress and index and index % 25 == 0:
                    progress(f"OCR processed {index}/{len(frames)} frames; battery graphs={len(graph_rows)}")
        if graph_output_csv is not None:
            write_graph_csv(graph_output_csv, graph_rows)
        if keyframe_dir is not None:
            with (output_csv.parent / "OCR_KEYFRAMES.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Video_s", "File", "TextExcerpt"])
                writer.writerows(keyframe_rows)
        segment_rows = []
        for time_s, app, layout, frame_mode in frame_detections:
            if (segment_rows and segment_rows[-1]["App"] == app
                    and segment_rows[-1]["Layout"] == layout
                    and segment_rows[-1]["FrameMode"] == frame_mode):
                segment_rows[-1]["End_s"] = f"{time_s:.3f}"
                segment_rows[-1]["FrameCount"] += 1
            else:
                segment_rows.append({
                    "Segment": len(segment_rows) + 1, "Start_s": f"{time_s:.3f}",
                    "End_s": f"{time_s:.3f}", "App": app, "Layout": layout,
                    "FrameMode": frame_mode, "FrameCount": 1,
                })
        segment_path = output_csv.parent / "OCR_APP_LAYOUT_SEGMENTS.csv"
        with segment_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "Segment", "Start_s", "End_s", "App", "Layout", "FrameMode", "FrameCount"])
            writer.writeheader()
            writer.writerows(segment_rows)
        matched = sum(1 for row in graph_rows if row.get("CANMatch") == "MATCHED")
        review_power = sum(1 for row in graph_rows if row.get("PowerPlausibility") == "REVIEW_OCR")
        requested_app = ("DR_PRIUS" if profile.startswith("DR_PRIUS") else
                         "HYBRID_ASSISTANT" if profile.startswith("HYBRID_ASSISTANT") else
                         "AUTEL_MAXIAP200" if profile.startswith("AUTEL") else None)
        routing_mismatches = sum(
            app not in {"UNKNOWN", requested_app} for _, app, _, _ in frame_detections
        ) if requested_app else 0
        return {"frames": len(frames), "interval_seconds": interval_seconds,
                "profile": profile, "output": str(output_csv),
                "battery_graph_rows": len(graph_rows), "can_matched_graph_rows": matched,
                "power_ocr_review_rows": review_power,
                "graph_output": str(graph_output_csv) if graph_output_csv else None,
                "graph_keyframes": str(crop_dir) if graph_rows else None,
                "ocr_keyframes": len(keyframe_rows), "app_layout_segments": len(segment_rows),
                "segment_output": str(segment_path),
                "routing_policy": "DETECTED_SEGMENT_FIRST_REQUESTED_PROFILE_FALLBACK",
                "requested_profile_mismatch_frames": routing_mismatches}


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
