@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-data toyota_can_processor --name ToyotaCANEvidenceBuilder run_gui.py
echo Output: dist\ToyotaCANEvidenceBuilder.exe
pause
