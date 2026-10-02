# Toyota CAN Evidence Builder 1.0.4

Version 1.0.4 implements the corrective and preventive actions for ambiguous
zero-pair reporting while retaining passive, offline, read-only processing and
Toyota Hybrid CAN Database v0.5.9/schema 1.2.0.

Key changes are per-field fixed-lag one-to-one CAN/OCR matching; unique-frame
and effective-sample accounting; stronger time/range/error confirmation gates;
explicit zero-pair cause codes; per-frame app/layout detection; the S0060
Hybrid Assistant routing correction; yellow-guide camera crops; hash
deduplication; blocking duplicate-session ambiguity; scoped counter
reconciliation; new outlier/rejection/decision panels; and matched-frame OCR
approval before using a generated 720-pixel/10-fps proxy.

Audit-environment verification:

- 37 automated tests passed and Python bytecode compilation passed.
- The full unchanged S0069 run produced 5,491 decoded rows, 284 OCR rows,
  817 one-to-one correlation rows from 209 unique OCR frames, 717 agreements,
  100 outliers, and 11 rejected semantic observations.
- Parsed raw records reconciled exactly with logger-processed frames:
  729,252 / 729,252, with no queue or SD loss indicators.
- Source CANLOG and CAPTURE SHA-256 values remained unchanged.
- The evidence capsule passed ZIP CRC validation and includes the new decision,
  counter, outlier, rejection, and app/layout segment outputs.

Platform boundary: this source release is validated, but its PyInstaller
executable has not been built or smoke-tested in this Linux audit environment.
Complete that final gate on Windows 10 version 1607 (build 14393) before calling
the executable validated.
