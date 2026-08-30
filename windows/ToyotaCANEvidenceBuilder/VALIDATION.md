# Evidence Builder 1.0.1 validation

## Automated tests

- 11 unit/integration tests pass under Python 3.12-compatible code.
- Tests cover TCB1 parsing/truncated tails, manifest version compatibility,
  BLE alignment, S0010 `21CE` ISO-TP reconstruction, the exact 17-block test
  vector, graph geometry, and existing v1.0 processor behavior.

## Supplied S0010 2007 Camry Hybrid capture

- Logger: CYD v2.4.2, capture format 1.4, TWAI listen-only, GPIO25 TX/GPIO32 RX.
- 364,076 raw records processed; zero session CAN transmissions and zero logged drops.
- 1,679 external diagnostic transaction records reconstructed.
- 133 complete `7E2 / 21CE` 17-block samples decoded; incomplete samples remain classified and are never guessed.
- BLE alignment: 85 samples used, -9.471 ppm drift, 6.831 ms RMS residual.
- 32 Hybrid Assistant Battery Check graph frames extracted at a 2-second interval.
- 32/32 graph frames matched an aligned CAN sample.
- Mean absolute signed graph/CAN pack-average difference: approximately 2.2 mV.
- Mean graph/CAN block RMSE: approximately 24.4 mV; part of this includes screen-update versus request timing and rounded OCR axis labels.
- All 32 displayed power readings were consistent with graph pack sum × displayed current.

## Evidence grade

The AHV40 `21CE` block-voltage definition is `PROBABLE`, not `CONFIRMED`.
Promotion requires an independent repeated capture or AP200/Techstream
corroboration on the same vehicle profile. Dr. Prius graph extraction remains
unvalidated until a representative capture is supplied.
