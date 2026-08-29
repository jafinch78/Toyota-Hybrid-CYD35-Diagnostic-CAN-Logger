@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
echo Enter the exact FFmpeg microphone name, or leave blank for screen-only capture.
echo To list names, run LIST_AUDIO_DEVICES.bat.
set /p TOYOTA_MIC=Microphone name: 
.venv\Scripts\python.exe -m toyota_can_processor.capture_cli -o "%USERPROFILE%\Documents\ToyotaCANSync" --microphone "%TOYOTA_MIC%"
pause
