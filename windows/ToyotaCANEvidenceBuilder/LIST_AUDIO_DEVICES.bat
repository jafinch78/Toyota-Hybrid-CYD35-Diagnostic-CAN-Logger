@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m toyota_can_processor.capture_cli --list-audio-devices
pause
