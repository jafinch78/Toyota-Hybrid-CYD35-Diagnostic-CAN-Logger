call "C:\Program Files (x86)\Microsoft Visual Studio 14.0\VC\vcvarsall.bat" amd64

cd /d "C:\Users\USB3.0\Documents\Arduino\Toyota_Hybrid_CAN_Sync_Toolkit_v1.0\windows\ToyotaCANEvidenceBuilder\win1607_ble_bridge"

"C:\Program Files (x86)\MSBuild\14.0\Bin\MSBuild.exe" Win1607_BLE_Bridge.vcxproj /p:Configuration=Release /p:Platform=x64 /v:minimal