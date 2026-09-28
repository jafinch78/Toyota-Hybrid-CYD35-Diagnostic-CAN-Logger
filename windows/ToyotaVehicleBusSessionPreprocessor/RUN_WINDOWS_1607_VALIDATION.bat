@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "FINAL_RC=1"
set "OUT_DIR=%~dp0validation\win1607_runtime"
set "LOG_FILE=%OUT_DIR%\WINDOWS_1607_VALIDATION.log"
set "REPORT_FILE=%OUT_DIR%\WINDOWS_1607_VALIDATION.json"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%" >nul 2>&1
>"%LOG_FILE%" echo ============================================================
>>"%LOG_FILE%" echo Toyota Vehicle Bus Session Preprocessor - Windows 10 1607 Validation
>>"%LOG_FILE%" echo ============================================================
>>"%LOG_FILE%" echo Working directory: %CD%
>>"%LOG_FILE%" echo Started: %DATE% %TIME%
>>"%LOG_FILE%" ver

echo ============================================================
echo Toyota Vehicle Bus Session Preprocessor - Windows 10 1607 Validation
echo ============================================================
echo [STAGE 1] Working directory: %CD%
echo [STAGE 1] Log: %LOG_FILE%

if "%~1"=="" goto :usage
set "SOURCE=%~f1"
if not exist "%SOURCE%" goto :missing_source

echo [STAGE 2] Source CANLOG: %SOURCE%
>>"%LOG_FILE%" echo Source CANLOG: %SOURCE%

if exist "%PYTHON%" goto :python_ready

echo [STAGE 3] Local .venv not found. Creating an offline local environment...
>>"%LOG_FILE%" echo Local .venv not found; attempting creation with Python launcher.
where py >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto :missing_python

py -3.10 -m venv "%~dp0.venv" >>"%LOG_FILE%" 2>&1
if not errorlevel 1 goto :python_ready
py -3 -m venv "%~dp0.venv" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto :venv_fail

:python_ready
if not exist "%PYTHON%" goto :venv_fail
echo [STAGE 3] Python: %PYTHON%
"%PYTHON%" --version >>"%LOG_FILE%" 2>&1
set "STAGE_RC=%ERRORLEVEL%"
if not "%STAGE_RC%"=="0" goto :python_fail
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 3)" >>"%LOG_FILE%" 2>&1
set "STAGE_RC=%ERRORLEVEL%"
if not "%STAGE_RC%"=="0" goto :python_version_fail

echo [PASS] Python environment is available.

set "WHEEL="
for %%F in ("%~dp0dist\toyota_vehicle_bus_session_preprocessor-*.whl") do if exist "%%~fF" set "WHEEL=%%~fF"
if not defined WHEEL goto :missing_wheel

echo [STAGE 4] Installing tested local wheel with no network access...
echo [STAGE 4] Wheel: %WHEEL%
>>"%LOG_FILE%" echo Wheel: %WHEEL%
"%PYTHON%" -m pip install --no-index --no-deps --force-reinstall "%WHEEL%" >>"%LOG_FILE%" 2>&1
set "STAGE_RC=%ERRORLEVEL%"
if not "%STAGE_RC%"=="0" goto :install_fail

echo [PASS] Local wheel installed.

echo [STAGE 5] Running one-session Windows 10 1607 RAW identity validation...
if exist "%REPORT_FILE%" del /q "%REPORT_FILE%" >nul 2>&1
"%PYTHON%" "%~dp0scripts\validate_windows_1607.py" "%SOURCE%" -o "%OUT_DIR%" >>"%LOG_FILE%" 2>&1
set "FINAL_RC=%ERRORLEVEL%"

echo ------------------------------------------------------------
type "%LOG_FILE%"
echo ------------------------------------------------------------

if not "%FINAL_RC%"=="0" goto :validation_fail
if not exist "%REPORT_FILE%" goto :missing_report

echo [PASS] Windows 10 1607 runtime and RAW identity validation passed.
echo [PASS] Report: %REPORT_FILE%
goto :finish

:usage
echo [FAIL] No CANLOG ZIP was supplied.
echo Usage: %~nx0 "C:\path\to\CANLOG_xxxxxx.zip"
>>"%LOG_FILE%" echo FAIL: no CANLOG ZIP supplied.
set "FINAL_RC=2"
goto :finish

:missing_source
echo [FAIL] CANLOG not found: %SOURCE%
>>"%LOG_FILE%" echo FAIL: CANLOG not found: %SOURCE%
set "FINAL_RC=2"
goto :finish

:missing_python
echo [FAIL] Python launcher not found and local .venv does not exist.
>>"%LOG_FILE%" echo FAIL: Python launcher not found.
set "FINAL_RC=2"
goto :finish

:venv_fail
echo [FAIL] Could not create or locate .venv\Scripts\python.exe.
>>"%LOG_FILE%" echo FAIL: local venv creation failed.
set "FINAL_RC=2"
goto :finish

:python_fail
echo [FAIL] Python executable failed. ERRORLEVEL=%STAGE_RC%
>>"%LOG_FILE%" echo FAIL: Python executable failed. ERRORLEVEL=%STAGE_RC%
set "FINAL_RC=%STAGE_RC%"
goto :finish

:python_version_fail
echo [FAIL] Python 3.10 or newer is required. ERRORLEVEL=%STAGE_RC%
>>"%LOG_FILE%" echo FAIL: Python version is below 3.10. ERRORLEVEL=%STAGE_RC%
set "FINAL_RC=%STAGE_RC%"
goto :finish

:missing_wheel
echo [FAIL] Tested wheel not found under dist\.
>>"%LOG_FILE%" echo FAIL: tested wheel not found under dist\.
set "FINAL_RC=2"
goto :finish

:install_fail
echo [FAIL] Local wheel install failed. ERRORLEVEL=%STAGE_RC%
>>"%LOG_FILE%" echo FAIL: wheel install failed. ERRORLEVEL=%STAGE_RC%
set "FINAL_RC=%STAGE_RC%"
goto :finish

:validation_fail
echo [FAIL] Windows validation failed. ERRORLEVEL=%FINAL_RC%
echo [FAIL] Review: %REPORT_FILE%
goto :finish

:missing_report
echo [FAIL] Validation returned success but the expected report is missing.
>>"%LOG_FILE%" echo FAIL: expected report missing after success return.
set "FINAL_RC=1"
goto :finish

:finish
echo ------------------------------------------------------------
echo Final ERRORLEVEL = %FINAL_RC%
echo ------------------------------------------------------------
>>"%LOG_FILE%" echo Final ERRORLEVEL = %FINAL_RC%
pause
exit /b %FINAL_RC%
