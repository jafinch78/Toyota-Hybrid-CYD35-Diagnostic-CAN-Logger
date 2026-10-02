# Windows 10 1607 executable release gate

Target: Windows 10 version 1607, build 14393, x64.

1. Run `INSTALL_WINDOWS.bat` and confirm the package-local `.venv` is used.
2. Run `RUN_EVIDENCE_BUILDER.bat`, open the GUI, and confirm version 1.0.4 and
   the bundled database v0.5.9 are displayed.
3. Run `.venv\Scripts\python -m toyota_can_processor --check-install` and retain
   the JSON result.
4. Run `BUILD_WINDOWS_EXE.bat` and retain the PyInstaller console log.
5. Launch `dist\ToyotaCANEvidenceBuilder_v1.0.4.exe` without network access.
6. Process the minimal regression fixture and one known CANLOG/CAPTURE pair.
7. Confirm source hashes are unchanged, database immutability is `true`, the
   report opens offline, and the evidence capsule passes ZIP testing.
8. Confirm the established Windows 1607 BLE bridge remains the capture path;
   Builder must not introduce a new BLE stack requirement.

Until all steps pass, distribute the source ZIP as validated and label the EXE
build as pending rather than validated.
