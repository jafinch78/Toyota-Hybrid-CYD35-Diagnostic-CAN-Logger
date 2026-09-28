# Toyota Vehicle Bus Session Preprocessor

Standalone offline preprocessor for the native Toyota vehicle-bus capture contract. The core package uses only the Python standard library and is designed to expand immutable `RAW stream(s) + SESSION.META` input into a legacy Evidence Builder-compatible CANLOG package.

The native evidence is never modified. TCB1 remains authoritative for CAN traffic, while TVM1 carries bus-neutral session and stream metadata.

## Firmware authorization boundary

The compatibility gate is deliberately limited to the boundaries that can invalidate the simplified logger contract: authoritative RAW identity/integrity, three-session Evidence Builder 1.0.4 oracle equivalence, and a Windows 10 1607 preprocessor/launcher validation run. Analyzer RC7/RC8 processing is downstream of the Builder-compatible package and is not a firmware-authorization requirement.

The three-session Builder campaign (S0141, S0149, S0128) is already frozen in `VALIDATION.md` and `validation/BUILDER_CAMPAIGN_20260928.json`. It must not be rerun merely to complete the Windows platform gate.

## Windows 10 1607 final runtime check

Use the tested CI artifact so the folder contains the tested wheel under `dist/`, `scripts/validate_windows_1607.py`, and `RUN_WINDOWS_1607_VALIDATION.bat`. Copy any one real historical CANLOG ZIP to the Windows 10 1607 machine and run:

```bat
RUN_WINDOWS_1607_VALIDATION.bat "C:\path\to\CANLOG_xxxxxx.zip"
```

The launcher is offline-only. It uses or creates the local `.venv`, installs the bundled wheel with `--no-index --no-deps`, verifies Windows build 14393, then performs only the native-session synthesis/expansion and authoritative RAW identity checks. It does not run downstream evidence processing.

Expected output files are written under `validation\win1607_runtime\`:

- `WINDOWS_1607_VALIDATION.log`
- `WINDOWS_1607_VALIDATION.json`

A valid final report must contain `"status": "PASS"`, `"windows_build": 14393`, `"final_errorlevel": 0`, and identical source/native/expanded RAW record counts, RX/TX counts, logical hashes, physical chunk hashes, and truncation state.
