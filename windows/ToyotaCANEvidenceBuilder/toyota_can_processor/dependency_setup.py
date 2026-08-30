"""Windows dependency checks and on-demand repair for Evidence Builder.

The installer and the GUI must use the same virtual-environment interpreter.
This module deliberately invokes ``sys.executable -m pip`` instead of a
machine-wide ``pip`` command, so a package cannot be installed successfully
into one Python while the application runs from another.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


Progress = Callable[[str], None]


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    installed_version: str | None
    import_ok: bool
    error: str | None = None


def app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def hidden_process_kwargs() -> dict[str, object]:
    """Return subprocess flags that suppress child console windows on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": startupinfo, "creationflags": subprocess.CREATE_NO_WINDOW}


def _status(distribution: str, module: str) -> DependencyStatus:
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = None
    try:
        importlib.import_module(module)
    except Exception as error:  # imports can fail when a transitive dependency is absent
        return DependencyStatus(distribution, version, False, f"{type(error).__name__}: {error}")
    return DependencyStatus(distribution, version, True)


def voice_dependency_status() -> list[DependencyStatus]:
    return [_status("faster-whisper", "faster_whisper"), _status("requests", "requests")]


def format_voice_status(statuses: list[DependencyStatus]) -> str:
    parts = []
    for status in statuses:
        version = status.installed_version or "not installed"
        state = "OK" if status.import_ok else "BROKEN"
        detail = f" ({status.error})" if status.error else ""
        parts.append(f"{status.name} {version}: {state}{detail}")
    return "; ".join(parts)


def ensure_voice_dependencies(progress: Progress | None = None) -> list[DependencyStatus]:
    """Check voice packages and repair them in this app's venv when needed."""
    progress = progress or (lambda message: None)
    statuses = voice_dependency_status()
    if all(status.import_ok for status in statuses):
        progress("Voice dependencies verified in the active Evidence Builder environment")
        return statuses

    requirements = app_root() / "requirements-voice-optional.txt"
    progress(f"Voice dependencies need repair; installing with {sys.executable}")
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "-r", str(requirements)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            check=False, **hidden_process_kwargs())
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for line in lines[-20:]:
        progress("pip: " + line)
    if result.returncode != 0:
        raise RuntimeError("Automatic voice dependency installation failed (exit "
                           f"{result.returncode}). Last output: {' | '.join(lines[-5:])}")

    statuses = voice_dependency_status()
    if not all(status.import_ok for status in statuses):
        raise RuntimeError("Voice dependency installation completed but imports remain broken: "
                           + format_voice_status(statuses))
    progress("Voice dependencies installed and verified in the active Evidence Builder environment")
    return statuses


def _candidate_tool_paths() -> dict[str, list[Path]]:
    if os.name != "nt":
        return {}
    local_app_data = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
    return {
        "ffmpeg": [Path(r"C:\Tools\ffmpeg\bin\ffmpeg.exe"),
                   local_app_data / "ToyotaCAN" / "ffmpeg" / "bin" / "ffmpeg.exe"],
        "ffprobe": [Path(r"C:\Tools\ffmpeg\bin\ffprobe.exe"),
                    local_app_data / "ToyotaCAN" / "ffmpeg" / "bin" / "ffprobe.exe"],
        "tesseract": [Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                      Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")],
    }


def resolve_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in _candidate_tool_paths().get(name, []):
        if candidate.is_file():
            return str(candidate)
    return None


def verify_external_tools() -> dict[str, str]:
    """Return resolved FFmpeg/Tesseract executables or raise a clear error."""
    required = {name: resolve_tool(name) for name in ("ffmpeg", "ffprobe", "tesseract")}
    missing = [name for name, path in required.items() if path is None]
    if missing:
        raise RuntimeError("Missing OCR tools: " + ", ".join(missing)
                           + ". Run INSTALL_WINDOWS.bat to install or repair them.")
    return {name: path for name, path in required.items() if path}


def installation_check() -> dict[str, object]:
    """Return a machine-readable installation check used by the installer/tests."""
    venv_python = app_root() / ".venv" / "Scripts" / "python.exe"
    return {
        "app_root": str(app_root()),
        "python": sys.executable,
        "expected_venv_python": str(venv_python),
        "python_matches_venv": Path(sys.executable).resolve() == venv_python.resolve()
        if venv_python.exists() else False,
        "voice": [status.__dict__ for status in voice_dependency_status()],
        "tools": {name: resolve_tool(name) for name in ("ffmpeg", "ffprobe", "tesseract")},
    }
