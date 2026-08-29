@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
start "Toyota CAN Evidence Builder" .venv\Scripts\pythonw.exe -m toyota_can_processor
