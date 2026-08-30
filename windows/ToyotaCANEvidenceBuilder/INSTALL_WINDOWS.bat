@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install 64-bit Python 3.12 from python.org.
  pause
  exit /b 1
)
where powershell >nul 2>nul
if errorlevel 1 (
  echo Windows PowerShell was not found. It is required for automatic FFmpeg/Tesseract setup.
  pause
  exit /b 1
)
echo Checking and installing FFmpeg, ffprobe, and Tesseract OCR...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_WINDOWS_DEPENDENCIES.ps1"
if errorlevel 1 (
  echo External tool setup failed. No partial Python installation was reported as successful.
  pause
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --disable-pip-version-check --upgrade pip
python -m pip install --disable-pip-version-check -e . -r requirements-windows.txt -r requirements-voice-optional.txt
if errorlevel 1 (
  echo Python dependency installation failed.
  pause
  exit /b 1
)
echo Verifying the active Evidence Builder virtual environment...
.venv\Scripts\python.exe -c "import requests; from faster_whisper import WhisperModel; print('VOICE_IMPORT_OK')"
if errorlevel 1 (
  echo Voice dependency verification failed in .venv.
  pause
  exit /b 1
)
echo.
echo Installation and dependency verification complete.
echo FFmpeg/Tesseract paths were checked and added to the user PATH when needed.
echo.
echo Run RUN_EVIDENCE_BUILDER.bat. The Transcribe option will re-check and repair
echo voice dependencies automatically if a later environment change removes one.
pause
