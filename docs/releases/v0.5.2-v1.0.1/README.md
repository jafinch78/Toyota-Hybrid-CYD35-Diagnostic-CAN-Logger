# Toyota Hybrid CAN Database v0.5.2 + Evidence Builder v1.0.1

This release updates analysis/database components only. It does not replace the
tested CYD logger v2.4.2 firmware or the currently installed Android sync
recorder.

## Files

- `Toyota_Hybrid_CAN_Database_v0.5.2.xlsx` — auditable workbook with S0010
  diagnostic inventory, all complete 21CE battery samples, graph correlation,
  and decoder export.
- `toyota_hybrid_can_db_v0.5.2.json` — machine-readable, version-checked decoder
  database used by Evidence Builder.
- `ToyotaCANEvidenceBuilder_v1.0.1` — Windows 10/11 source/install folder.

Run `INSTALL_WINDOWS.bat` once in the Evidence Builder folder, then run
`RUN_EVIDENCE_BUILDER.bat`. Existing v1.0 users should rerun the installer so
Pillow and the updated package are installed in the local virtual environment.

Safety: the application decodes passively observed traffic. It does not send
CAN requests or control/write commands.
