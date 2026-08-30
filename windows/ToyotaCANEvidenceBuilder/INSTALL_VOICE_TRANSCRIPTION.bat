@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run INSTALL_WINDOWS.bat first so the correct .venv is created.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-voice-optional.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -c "import requests; from faster_whisper import WhisperModel; print('VOICE_IMPORT_OK')"
if errorlevel 1 (
  echo faster-whisper or requests could not be imported from .venv.
  pause
  exit /b 1
)
echo Voice transcription dependencies are installed in this Evidence Builder .venv.
pause
