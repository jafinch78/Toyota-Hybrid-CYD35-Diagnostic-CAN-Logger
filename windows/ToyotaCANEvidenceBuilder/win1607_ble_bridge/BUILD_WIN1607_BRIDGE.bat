@echo off
setlocal
cd /d "%~dp0"

where msbuild.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: msbuild.exe was not found on PATH.
  echo Use a Visual Studio 2015 Developer Command Prompt with the Windows 10 SDK 10.0.14393.0 installed.
  exit /b 1
)

msbuild Win1607_BLE_Bridge.vcxproj /m /p:Configuration=Release /p:Platform=x64
if errorlevel 1 exit /b 1

if not exist "x64\Release\Win1607_BLE_Bridge.exe" (
  echo ERROR: build reported success but the expected EXE was not found.
  exit /b 1
)

copy /y "x64\Release\Win1607_BLE_Bridge.exe" "Win1607_BLE_Bridge.exe" >nul
if errorlevel 1 exit /b 1

echo Built: %CD%\Win1607_BLE_Bridge.exe
exit /b 0
