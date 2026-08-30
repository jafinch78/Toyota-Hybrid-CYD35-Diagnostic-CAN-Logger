# Evidence Builder 1.0.2 validation

## Automated tests

- 18 unit/integration tests pass; Python `compileall` is clean.
- Coverage includes TCB1 and version compatibility, BLE alignment, `21CE`
  reassembly, graph geometry/orientation, Dr. Prius reconstruction and pack
  gating, diagnostic grouping, dependency repair, and processor behavior.

## S0012 2007 Camry Hybrid capture

- CYD v2.4.2, format 1.4, TWAI listen-only, GPIO25 TX/GPIO32 RX.
- 737,093 raw records; zero logger CAN transmissions and zero SD log drops;
  1,466 CAN queue drops are retained in the summary.
- 2,943 external diagnostic transactions (2,541 OK, 382 no response, 17
  incomplete, 3 unmatched) and 351 complete `7E2 / 21CE` battery samples.
- BLE fit used 127/135 samples, -11.728 ppm drift, 6.561 ms RMS residual,
  20.975 ms maximum residual; the warning is retained.
- 273 video frames at a two-second interval: 70 Hybrid Assistant and 18 Dr.
  Prius Battery Monitor graph rows; all 88 matched an aligned CAN sample.
- Dr. Prius rows retain 17 block values, printed pack voltage, SOC, current,
  direction, three temperatures, reconstruction metadata, CAN RMSE, and source
  frame. The 330 s row reconstructed two labels and matched the displayed
  277.43 V pack within rounded values.
- Four grouped diagnostic actions were aligned: two read-code operations
  returned `53 00` (`NO_DTC_PRESENT`) and two clear operations returned `44`
  (`ACKNOWLEDGED`). These are passive observations; clear-code definitions are
  `CONTROL_WRITE_QUARANTINED` and never enabled for automatic transmit.

All AHV40 decoder and Dr. Prius graph evidence remains `PROBABLE` until an
independent repeated capture or AP200/Techstream corroboration is available.
