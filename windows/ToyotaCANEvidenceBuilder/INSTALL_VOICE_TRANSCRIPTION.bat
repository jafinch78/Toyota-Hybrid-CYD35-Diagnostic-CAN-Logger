@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pip install -r requirements-voice-optional.txt
pause
