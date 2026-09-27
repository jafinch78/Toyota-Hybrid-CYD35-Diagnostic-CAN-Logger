@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Toyota Vehicle Bus Session Preprocessor
echo ============================================================
echo [STAGE 1] Working directory: %CD%

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [FAIL] Expected Python was not found:
  echo        %PYTHON%
  echo Create the local .venv before running this launcher.
  set "FINAL_RC=2"
  goto :finish
)

echo [STAGE 2] Python: %PYTHON%
"%PYTHON%" --version
set "STAGE_RC=%ERRORLEVEL%"
if not "%STAGE_RC%"=="0" (
  echo [FAIL] Python version check failed. ERRORLEVEL=%STAGE_RC%
  set "FINAL_RC=%STAGE_RC%"
  goto :finish
)

echo [PASS] Python environment is available.

if "%~1"=="" (
  echo [STAGE 3] Launching GUI...
  "%PYTHON%" -m toyota_vehicle_bus_session.gui
  set "FINAL_RC=%ERRORLEVEL%"
) else (
  echo [STAGE 3] Running CLI...
  "%PYTHON%" -m toyota_vehicle_bus_session.cli %*
  set "FINAL_RC=%ERRORLEVEL%"
)

if "%FINAL_RC%"=="0" (
  echo [PASS] Session preprocessor completed successfully.
) else (
  echo [FAIL] Session preprocessor returned ERRORLEVEL=%FINAL_RC%
)

:finish
if not defined FINAL_RC set "FINAL_RC=1"
echo ------------------------------------------------------------
echo Final ERRORLEVEL = %FINAL_RC%
echo ------------------------------------------------------------
pause
exit /b %FINAL_RC%
