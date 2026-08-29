@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install 64-bit Python 3.12 from python.org.
  pause
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e . -r requirements-windows.txt
if errorlevel 1 exit /b 1
echo.
echo Installation complete. Run RUN_EVIDENCE_BUILDER.bat.
pause
