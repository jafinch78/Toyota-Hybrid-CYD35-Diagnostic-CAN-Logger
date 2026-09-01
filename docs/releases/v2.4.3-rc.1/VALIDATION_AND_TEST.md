# Validation and test matrix — v2.4.3-rc.1

Do not label v2.4.3 stable until both source builds compile and the applicable physical tests pass.

## Completed source checks

- Static logger preflight: PASS for both board sources.
- Board build isolation: PASS; N35T has profile macro 0, Dorhea has profile macro 1.
- No `MONOTONIC_V1`, `NEXT_SESSION`, or allocator Preferences key remains: PASS.
- Safety review: TWAI startup is listen-only; existing diagnostic transmission remains explicit/profile-gated/read-only.
- Arduino compile and hardware tests: NOT RUN in the source-preparation environment.

The static checker warns whenever it sees `twai_transmit`, `TWAI_MODE_NORMAL`, or actuator-related terminology. Those expected warnings require the manual safety review above; they are not compile failures.

## Compile gate — both builds

- [ ] Compile with the same ESP32 Arduino core and TFT_eSPI version used for v2.4.2.
- [ ] Record board target, core version, TFT_eSPI version, flash size, RAM use, and warnings.
- [ ] Confirm `.ino` name matches its folder.
- [ ] Confirm firmware reports `v2.4.3-rc.1` and the correct board profile.

## N35T bench gate

- [ ] Boot with the established GPIO25 TX / GPIO32 RX VP230 wiring.
- [ ] Verify all four touch corners and every bottom-row button.
- [ ] Start and cleanly stop ten empty bench sessions; no white screen, reset, or zero-byte partial session.
- [ ] Verify each session is unique and the next absent `S####` is selected after reboot.
- [ ] Verify BLE sync plus Android start/stop creates a closed session.
- [ ] Verify Wi-Fi list/download/ZIP, then exit/restart logger.

## Dorhea bench and vehicle gate

- [ ] Confirm touch calibration flag 3 and all bottom-row buttons.
- [ ] Confirm the GPIO4 red LED turns off at boot.
- [ ] Start and cleanly stop ten empty bench sessions; no white screen or reset.
- [ ] With VP230 TXD on GPIO22 and RXD on GPIO35, confirm real vehicle RX traffic and nonzero raw records.
- [ ] Confirm the serial `TWAI_READY` event reports GPIO22 TX / GPIO35 RX and candidate status.
- [ ] Confirm Wi-Fi and BLE operations as in the N35T gate.

## Retained-directory clear gate

Use a disposable closed test session.

- [ ] Wi-Fi refuses an incorrect confirmation and refuses any session with `SESSION.OPEN`.
- [ ] Type `CLEAR-S####`; verify original files are removed.
- [ ] Verify `/CANLOG/S####/SESSION_TOMBSTONE.JSON` exists and parses as JSON.
- [ ] Reboot; verify the cleared `S####` is not reused.
- [ ] Clear the already-cleared session again; verify one valid tombstone remains.
- [ ] Verify an interrupted/failed clear retains the session directory and does not affect another session.

## Vehicle safety gate

- [ ] With diagnostics disabled, confirm zero TX records and `LISTEN_ONLY` operation.
- [ ] Confirm Camry/unknown profiles cannot enable diagnostic requests.
- [ ] On a strongly identified Gen 2 Prius only, confirm explicit diagnostic enable uses the existing read-only whitelist.
- [ ] Confirm an external tester causes the existing diagnostic conflict/rejection behavior.

## Rollback

If any start/stop reset, white screen, zero-byte session, BLE-control regression, or CAN-RX failure occurs, reinstall the exact v2.4.2 source from commit `05de4a24506e925547487da1eba2fbc9abd605ac`. Preserve the failing `S####` folder and serial log for comparison.
