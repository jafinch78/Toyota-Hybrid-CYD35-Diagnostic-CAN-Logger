@echo off
setlocal EnableExtensions EnableDelayedExpansion
title ToyotaCAN Win10 1607 Capture Installer and Checklist

rem Toyota CAN Windows 10 1607 capture installer/checker.
rem Place this BAT in the ToyotaCANEvidenceBuilder folder and run it from there.
rem It creates/repairs the local Python virtual environment, installs Python
rem requirements, optionally builds the Win1607 BLE bridge, and prints A-G status.

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VSVC=C:\Program Files (x86)\Microsoft Visual Studio 14.0\VC"
set "MSB=C:\Program Files (x86)\MSBuild\14.0\Bin\MSBuild.exe"
set "V140=C:\Program Files (x86)\MSBuild\Microsoft.Cpp\v4.0\V140"
set "SDK=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.14393.0"
set "BRIDGE=%ROOT%\win1607_ble_bridge\Win1607_BLE_Bridge.exe"
set "PROJ=%ROOT%\win1607_ble_bridge\Win1607_BLE_Bridge.vcxproj"
set "REQ=%ROOT%\requirements-windows.txt"
set "REQVOICE=%ROOT%\requirements-voice-optional.txt"
set "VENV=%ROOT%\.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPIP=%VENV%\Scripts\pip.exe"
set "SETUPLOG=%ROOT%\WIN1607_CAPTURE_INSTALL_LOG.txt"

for %%L in (A B C D E F G) do set "S%%L=MISSING"
set "PYLAUNCH="
set "PYBASE="
set "PYOK=MISSING"
set "PIPOK=MISSING"
set "REQOK=MISSING"
set "FFMPEGOK=MISSING"
set "BRIDGEOK=MISSING"
set "MODULEOK=MISSING"

echo ToyotaCAN Win10 1607 Capture Installer and Checklist > "%SETUPLOG%"
echo Started %DATE% %TIME% >> "%SETUPLOG%"
echo Root: %ROOT% >> "%SETUPLOG%"

echo.
echo ToyotaCAN Windows 10 1607 Capture - setup and prerequisite check
echo ================================================================
echo Project root: %ROOT%
echo Log file: %SETUPLOG%
echo.

rem A - Windows 10 build 14393
for /f "tokens=3" %%V in ('reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CurrentBuildNumber 2^>nul ^| find "CurrentBuildNumber"') do set "BUILD=%%V"
if "%BUILD%"=="14393" set "SA=INSTALLED"

rem B - VS2015 C++ compiler toolchain
if exist "%VSVC%\vcvarsall.bat" if exist "%VSVC%\bin\amd64\cl.exe" if exist "%VSVC%\bin\amd64\link.exe" if exist "%VSVC%\bin\amd64\c1xx.dll" set "SB=INSTALLED"

rem C - VS2015 C++/CX headers + Platform metadata
if exist "%VSVC%\include\collection.h" if exist "%VSVC%\include\vccorlib.h" if exist "%VSVC%\lib\store\references\platform.winmd" set "SC=INSTALLED"

rem D - MSBuild 14 + v140 targets
if exist "%MSB%" if exist "%V140%\Microsoft.Cpp.Default.props" set "SD=INSTALLED"

rem E - Windows SDK 14393 headers + Windows metadata
if exist "%SDK%\Include\%SDKVER%\um" if exist "%SDK%\Include\%SDKVER%\winrt" if exist "%SDK%\UnionMetadata\Windows.winmd" set "SE=INSTALLED"

rem F - Windows SDK 14393 x64 link libraries
if exist "%SDK%\Lib\%SDKVER%\um\x64\WindowsApp.lib" if exist "%SDK%\Lib\%SDKVER%\um\x64\runtimeobject.lib" set "SF=INSTALLED"

echo A-F platform/toolchain check complete.
echo A=%SA% B=%SB% C=%SC% D=%SD% E=%SE% F=%SF% >> "%SETUPLOG%"

rem Locate Python for venv creation.
if exist "%VPY%" (
  set "PYBASE=%VPY%"
) else (
  py -3 --version >nul 2>&1 && set "PYLAUNCH=py -3"
  if not defined PYLAUNCH where python.exe >nul 2>&1 && set "PYLAUNCH=python.exe"
)

if not exist "%VPY%" (
  if defined PYLAUNCH (
    echo.
    choice /C YN /N /M "Local .venv is missing. Create it now? [Y/N] "
    if errorlevel 2 goto :skip_venv_create
    echo Creating .venv... >> "%SETUPLOG%"
    %PYLAUNCH% -m venv "%VENV%" >> "%SETUPLOG%" 2>&1
  ) else (
    echo No suitable Python launcher was found. Install Python 3.10+ or ensure python.exe is on PATH.
    echo No suitable Python launcher found. >> "%SETUPLOG%"
  )
)
:skip_venv_create

if exist "%VPY%" set "PYOK=INSTALLED"
if exist "%VPIP%" set "PIPOK=INSTALLED"

if exist "%VPY%" (
  echo.
  echo Local Python: "%VPY%"
  "%VPY%" --version
  echo Upgrading pip/setuptools/wheel...
  "%VPY%" -m pip install --upgrade pip setuptools wheel >> "%SETUPLOG%" 2>&1
  if exist "%REQ%" (
    echo Installing requirements-windows.txt...
    "%VPY%" -m pip install -r "%REQ%" >> "%SETUPLOG%" 2>&1
    if not errorlevel 1 set "REQOK=INSTALLED"
  ) else (
    echo requirements-windows.txt is missing.
    echo requirements-windows.txt missing. >> "%SETUPLOG%"
  )

  if exist "%REQVOICE%" (
    echo.
    choice /C YN /N /M "Install optional voice transcription requirements? [Y/N] "
    if not errorlevel 2 "%VPY%" -m pip install -r "%REQVOICE%" >> "%SETUPLOG%" 2>&1
  )

  pushd "%ROOT%" >nul
  "%VPY%" -c "import toyota_can_processor; import toyota_can_processor.capture_cli; import toyota_can_processor.ble_transport; import toyota_can_processor.windows_capture" >> "%SETUPLOG%" 2>&1
  if not errorlevel 1 set "MODULEOK=INSTALLED"
  popd >nul
)

where ffmpeg.exe >nul 2>&1 && set "FFMPEGOK=INSTALLED"

if exist "%ROOT%\sdksetup.exe" if not "%SE%"=="INSTALLED" (
  echo.
  choice /C YN /N /M "Windows SDK 14393 appears incomplete. Run bundled sdksetup.exe now? [Y/N] "
  if not errorlevel 2 start /wait "" "%ROOT%\sdksetup.exe"
)

if exist "%BRIDGE%" set "BRIDGEOK=INSTALLED"
if not exist "%BRIDGE%" if exist "%VSVC%\vcvarsall.bat" if exist "%MSB%" if exist "%PROJ%" (
  echo.
  choice /C YN /N /M "Win1607 bridge EXE is missing. Build Release x64 now? [Y/N] "
  if not errorlevel 2 (
    call "%VSVC%\vcvarsall.bat" amd64
    "%MSB%" "%PROJ%" /p:Configuration=Release /p:Platform=x64 /v:minimal >> "%SETUPLOG%" 2>&1
  )
)
if exist "%BRIDGE%" set "BRIDGEOK=INSTALLED"

if "%PYOK%"=="INSTALLED" if "%PIPOK%"=="INSTALLED" if "%REQOK%"=="INSTALLED" if "%FFMPEGOK%"=="INSTALLED" if "%BRIDGEOK%"=="INSTALLED" if "%MODULEOK%"=="INSTALLED" set "SG=INSTALLED"

echo.
echo ================================================================
echo FINAL INSTALLATION REQUIREMENTS CHECKLIST
echo ================================================================
echo A. Windows 10 build 14393 ......................... %SA%
echo B. VS2015 x64 C++ compiler/linker ................. %SB%
echo C. VS2015 C++/CX headers + platform.winmd ......... %SC%
echo D. MSBuild 14 + v140 targets ...................... %SD%
echo E. Windows SDK 10.0.14393 headers/metadata ........ %SE%
echo F. SDK WindowsApp/runtimeobject x64 libs .......... %SF%
echo G. Capture runtime, Python deps, FFmpeg, bridge ... %SG%
echo.
echo    G1. Local .venv Python ......................... %PYOK%
echo    G2. Local .venv pip ............................ %PIPOK%
echo    G3. requirements-windows.txt installed ......... %REQOK%
echo    G4. FFmpeg available on PATH ................... %FFMPEGOK%
echo    G5. Win1607 BLE bridge EXE present ............. %BRIDGEOK%
echo    G6. Toyota capture Python modules import ....... %MODULEOK%
echo ================================================================

set "FAIL=0"
for %%L in (A B C D E F G) do if "!S%%L!"=="MISSING" set "FAIL=1"

if "%FAIL%"=="0" (
  echo RESULT: READY - all A through G requirements are installed.
  echo Next: run RUN_TECHSTREAM_CAPTURE_WIN1607.bat for Windows 10 1607.
) else (
  echo RESULT: NOT READY - one or more requirements are missing.
  echo See %SETUPLOG% for pip/build details.
)

echo.
pause
exit /b %FAIL%
