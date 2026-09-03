@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

if not exist "win1607_ble_bridge\Win1607_BLE_Bridge.exe" (
  echo ERROR: Windows 1607 BLE bridge is not built.
  echo Run win1607_ble_bridge\BUILD_WIN1607_BRIDGE.bat from a Visual Studio 2015 Developer Command Prompt first.
  pause
  exit /b 1
)

set TOYOTA_BLE_BACKEND=win1607
set TOYOTA_WIN1607_BLE_BRIDGE=%CD%\win1607_ble_bridge\Win1607_BLE_Bridge.exe

echo Windows 10 1607 BLE backend selected.
echo The ToyotaCYD logger must already be paired in Windows Settings.
echo Enter the exact FFmpeg microphone name, or leave blank for screen-only capture.
echo To list names, run LIST_AUDIO_DEVICES.bat.
set /p TOYOTA_MIC=Microphone name: 
.venv\Scripts\python.exe -m toyota_can_processor.capture_cli -o "%USERPROFILE%\Documents\ToyotaCANSync" --microphone "%TOYOTA_MIC%"
pause
