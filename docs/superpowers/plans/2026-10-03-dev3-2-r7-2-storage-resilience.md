# DEV3.2 / DIAG4 R7.2 Storage-Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build field-testable DEV3.2 and DIAG4 R7.2 firmware that remains a trustworthy RAW+META recorder through the observed Card-B storage-latency tail, using a memory-gated 1536-frame queue target, pressure-aware RAW catch-up, and complete resilience telemetry while preserving the proven 25 MHz / START-PERF2 / external-tester-latch baseline.

**Architecture:** Start only from the exact NORMAL-mode DEV3.1/R7.1 SD25M field packages used for S0214-S0217. Preserve the existing CAN RX task, 128-record RAW write unit, file formats, START-PERF2, draining STOP, and session-latched software TX inhibition; add compile-time queue headroom, hysteretic pressure recovery, pressure-aware routine filesystem service, and bounded telemetry. The forced-LISTEN_ONLY S0218/S0219 edits and the separate 500/250-kbit/s Autel experiment are validation evidence, not production source inputs.

**Tech Stack:** ESP32 Arduino core 3.3.10, C++/Arduino, FreeRTOS queue/TWAI, TFT_eSPI, SD/SPI at 25 MHz, BLE, TVM1 SESSION.META, TCB1 RAW, Python source-contract tests, existing host/stub verification where available.

**Spec:** `docs/superpowers/specs/2026-10-03-dev3-2-r7-2-storage-resilience-design.md`

## Global Constraints

- Authoritative DEV3.1 package SHA-256: `5b1675792c727ae63dc7c19d9400248e6207e1e7039eb34cf93008e46763b5df`.
- Authoritative DIAG4 R7.1 package SHA-256: `e9c62ab6535a4518d5cc4825356a22f06dbd8e90e8bcfca7406fc7b4a8a9f760`.
- Implementation starts from the NORMAL-mode S0214-S0217 baseline, never the S0218/S0219 forced-LISTEN_ONLY experimental edits.
- SD SPI remains exactly 25,000,000 Hz.
- Preferred queue capacity is 1536 for both variants, but release is conditional on the memory gate; there is no silent runtime fallback.
- For a 1536 queue, `PRESSURE_HIGH = 768` and `PRESSURE_LOW = 384`; if the accepted compile-time capacity changes, HIGH remains 50% and LOW remains 25%.
- Post-allocation free internal heap must remain at least 64 KiB and largest free internal block at least 32 KiB on both variants.
- RAW batch remains exactly 128 records.
- TCB1 remains a 24-byte record format and unchanged.
- TVM1 framing, CRC, sequence semantics, historical IDs, and unknown-metric forward skipping remain backward compatible.
- Draining STOP remains authoritative; BLE STOP response remains after finalization.
- `SESSION.OPEN` remains required.
- NVS/high-water session allocation remains unchanged.
- Existing read-only Toyota diagnostic whitelist remains unchanged.
- Wi-Fi remains stopped-state maintenance mode.
- TFT PERF2 dirty rendering remains the baseline.
- External-tester ownership remains session-latched and uses software diagnostic-TX inhibition; ownership does not tear down/restart TWAI.
- `postLatchDiagnosticTxAttempts` and `postLatchDiagnosticTxFrames` must remain zero in field acceptance.
- Production firmware does not automatically switch CAN bitrate or force LISTEN_ONLY in response to Autel bus errors.
- Dedicated SD writer task, SdFat migration, SD clocks above 25 MHz, RAW batch >128, and queues >1536 remain deferred unless this plan fails acceptance.

## File Structure

- Create working tree: `firmware/field/DEV3_2_RAW_META/` — DEV3.2/1536-target production source and package material.
- Create working tree: `firmware/field/DEV_DIAG4_R7_2_RAW_META/` — R7.2/1536-target production source and package material.
- Create: `firmware/tests/test_dev3_2_r7_2_source_contract.py` — source/invariant/registry tests shared by both variants.
- Create: `firmware/tests/test_dev3_2_r7_2_pressure_policy.py` — deterministic policy/model tests for HIGH/LOW hysteresis, service deferral, coalescing, and stall-envelope calculations using the exact production constants.
- Create: `firmware/field/DEV3_2_R7_2_BASELINE_SHA256.txt` — authoritative package and extracted-source provenance.
- Modify in both working trees: `logger_v2_4_3_core.inc` — queue creation, pressure state, RAW catch-up, storage service gating, START/STOP/pressure telemetry, test-only stall injection.
- Modify in both working trees: `TVM1_SessionMeta.h/.cpp`, `TVM1_Meta.h/.cpp` only when required for new metric/event IDs or schema declarations.
- Modify variant `.ino`/build identity files only for DEV3.2/R7.2 and explicit production-vs-stall-test labels.
- Update package `VALIDATION.txt`, `SOURCE_BASELINES.txt`, `SHA256SUMS.txt`, and add `DEV3_2_R7_2_STORAGE_RESILIENCE_TESTING.md`.

## Review Focus

1. **Memory fragmentation / allocation failure:** a nominal 36,864-byte queue payload is not enough proof; tests and telemetry must verify queue allocation, post-allocation free heap, and largest free block on the real boot path without runtime fallback.
2. **Pressure-mode starvation:** repeated RAW catch-up must not starve STOP recognition, required RAW rotation, or the minimum metadata needed to keep files structurally valid; owning task must test those escape paths explicitly.
3. **Durability over-deferral:** periodic flush/checkpoint work may be deferred under pressure, but STOP/rotation durability cannot be skipped and deferred routine work must eventually resume/coalesce after recovery.
4. **Telemetry registry completeness:** every new event/metric ID must have one stable registry/schema meaning; no unmapped `65535`-style event flood is permitted in production or stall-test builds.
5. **Deterministic-stall validity:** the 650 ms test must begin only after steady state with queue depth at or below LOW, keep CAN RX running, inject exactly once, and prove recovery rather than merely proving a large queue exists.

---

### Task 1: Freeze the exact DEV3.1/R7.1 SD25M field baselines and create DEV3.2/R7.2 trees

**Files:**
- Create: `firmware/field/DEV3_2_RAW_META/`
- Create: `firmware/field/DEV_DIAG4_R7_2_RAW_META/`
- Create: `firmware/field/DEV3_2_R7_2_BASELINE_SHA256.txt`
- Create: `firmware/tests/test_dev3_2_r7_2_source_contract.py`

**Interfaces:**
- Consumes: `Toyota_Hybrid_CYD35_HV_Health_DEV3_1_RAW_META_SD25M_TEST.zip` and `Toyota_Hybrid_CYD35_HV_Health_DEV_DIAG4_R7_1_RAW_META_SD25M_TEST.zip` with the exact hashes in Global Constraints.
- Produces: two source trees initially identical to those field packages except version/build identity, plus per-file baseline SHA-256 evidence used by every later task.

- [ ] **Step 1: Write `test_exact_sd25m_baseline_packages_and_invariants` before creating DEV3.2/R7.2 source trees.** Assert the two package hashes, `SD_SPI_FREQUENCY == 25000000`, RAW batch 128, original queue capacities 1024/768, TCB1 24-byte invariant, draining STOP symbols, `SESSION.OPEN`, session-latched external-tester gating, and NORMAL-mode production TWAI configuration.
- [ ] **Step 2: Run:** `py -3 -m unittest firmware.tests.test_dev3_2_r7_2_source_contract -v`. **Expected:** FAIL because DEV3.2/R7.2 trees and provenance file do not yet exist.
- [ ] **Step 3: Verify both archive SHA-256 values, extract exact field source trees, and record SHA-256 for every implementation source in `DEV3_2_R7_2_BASELINE_SHA256.txt`.** Do not source files from the forced-LISTEN_ONLY experiment.
- [ ] **Step 4: Copy extracted sources into the two DEV3.2/R7.2 working trees and change only sketch/build/version identity.** Production identity must remain NORMAL-mode and SD25M.
- [ ] **Step 5: Re-run the focused test command.** **Expected:** PASS for baseline/provenance/invariant tests.
- [ ] **Step 6: Commit:** `chore: freeze DEV3.1 R7.1 25MHz field baselines`.

### Task 2: Add the 1536 queue target, memory gate, and queue-capacity telemetry

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: TVM1 registry/helper files only if new memory/capacity metrics require IDs.
- Modify: `firmware/tests/test_dev3_2_r7_2_source_contract.py`.
- Create/modify: `firmware/tests/test_dev3_2_r7_2_pressure_policy.py`.

**Interfaces:**
- Produces compile-time constants `CAN_CAPTURE_QUEUE_LEN`, `PRESSURE_HIGH`, `PRESSURE_LOW` and persisted boot/session telemetry for queue capacity, allocation result, pre/post free heap, pre/post largest free block, and minimum free heap.
- Later tasks consume the accepted queue constants and pressure thresholds; there is no runtime capacity fallback path.

- [ ] **Step 1: Write failing tests `test_queue_target_and_thresholds` and `test_no_runtime_queue_fallback`.** For the target build assert `CAN_CAPTURE_QUEUE_LEN == 1536`, `PRESSURE_HIGH == CAN_CAPTURE_QUEUE_LEN/2`, `PRESSURE_LOW == CAN_CAPTURE_QUEUE_LEN/4`, and no code path silently retries queue allocation at a smaller capacity.
- [ ] **Step 2: Run the two tests.** **Expected:** FAIL because the untouched baseline remains 1024/768 and has no common pressure constants.
- [ ] **Step 3: Write failing test `test_queue_allocation_memory_telemetry_contract`.** Require measurement names/IDs for free heap and largest free block immediately before and after queue creation, allocation success, configured queue capacity, and minimum free heap after normal initialization.
- [ ] **Step 4: Implement the compile-time 1536 target and memory snapshots around the existing queue-creation point using internal-capability heap APIs already available in the ESP32 stack.** A failed queue allocation remains a visible startup failure; do not auto-downsize.
- [ ] **Step 5: Persist the configured capacity and memory snapshots through existing startup/health META service without filesystem writes from CAN/TWAI callbacks.
**
- [ ] **Step 6: Add validation/reporting text that declares the field memory acceptance gate:** post-allocation free heap >= 64 KiB and largest free block >= 32 KiB on both variants; package remains TEST-only until measured hardware evidence satisfies both.
- [ ] **Step 7: Run the full DEV3.2/R7.2 source-contract suite and pressure-policy tests.** **Expected:** PASS.
- [ ] **Step 8: Commit:** `feat: add 1536 queue target and memory gate telemetry`.

### Task 3: Implement hysteretic capture-pressure mode and RAW catch-up

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: `firmware/tests/test_dev3_2_r7_2_source_contract.py`.
- Modify: `firmware/tests/test_dev3_2_r7_2_pressure_policy.py`.

**Interfaces:**
- Consumes: `CAN_CAPTURE_QUEUE_LEN`, `PRESSURE_HIGH`, `PRESSURE_LOW` from Task 2.
- Produces bounded session state `capturePressureMode`, pressure-enter timestamp/count, pressure maximum depth, RAW-drained count, drop baseline/delta, and pressure-exit duration.
- Exposes one queue-pressure predicate/state used by Task 4 to gate routine filesystem service.

- [ ] **Step 1: Write failing policy tests `test_pressure_enters_at_high_not_below` and `test_pressure_exits_only_at_low_or_below`.** Include the exact 1536/768/384 boundary cases and one non-1536 compile-time example to prove thresholds derive from capacity.
- [ ] **Step 2: Write failing source test `test_pressure_mode_raw_catchup_repeats_existing_128_batch`.** Require repeated existing 128-record RAW service while pressure remains set; forbid changing RAW batch size to solve the problem.
- [ ] **Step 3: Write failing source test `test_pressure_mode_preserves_stop_rotation_and_structural_meta`.** Require pending STOP recognition, required RAW rotation, CAN RX/queueing, and minimum format-critical metadata paths to remain reachable while optional TFT/routine service is suppressed.
- [ ] **Step 4: Implement pressure entry/exit state transitions around actual queue depth.** Entry records one snapshot at `>= HIGH`; exit occurs only at `<= LOW`, recording duration, max depth, drop delta, and RAW records drained.
- [ ] **Step 5: Modify the main acquisition loop so pressure mode repeatedly services the existing 128-record RAW batch until backlog falls to LOW or a required STOP/rotation condition needs handling.** Do not spin indefinitely without checking those required conditions.
- [ ] **Step 6: Gate TFT rendering, optional BLE status work, noncritical Serial/audit formatting, and nonessential deferred START work while pressure mode is active.
**
- [ ] **Step 7: Run policy tests and the complete source-contract suite.** **Expected:** PASS with the preserved RAW-batch/STOP/rotation invariants.
- [ ] **Step 8: Commit:** `perf: add queue pressure RAW catchup mode`.

### Task 4: Make periodic flush/checkpoint service pressure-aware and coalescing

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: TVM1 helper/registry files only for new deferral metrics.
- Modify: both DEV3.2/R7.2 test files.

**Interfaces:**
- Consumes: pressure state/predicate from Task 3.
- Produces `flushDeferredCount`, `flushDeferredMaxUs`, pending routine flush state, checkpoint-deferred/coalesced counters, and one resumed service action after pressure clears.
- STOP finalization and required RAW rotation bypass routine-pressure deferral.

- [ ] **Step 1: Write failing policy tests `test_routine_flush_defers_above_low` and `test_routine_flush_resumes_after_recovery`.** A routine flush request while depth > LOW must become pending; once depth <= LOW and pressure is false, one deferred flush becomes eligible.
- [ ] **Step 2: Write failing policy test `test_checkpoint_intervals_coalesce_under_pressure`.** Multiple missed routine checkpoint intervals during one pressure episode must produce one later checkpoint plus a count of deferred/coalesced intervals, not a burst of stale writes.
- [ ] **Step 3: Write failing source test `test_stop_and_rotation_durability_not_pressure_deferred`.** Explicitly distinguish routine periodic flush from STOP finalization and RAW file rotation.
- [ ] **Step 4: Implement pressure-aware routine `flushLogFiles()` scheduling:** defer if queue depth > LOW or pressure mode is active; record first deferral time/count; execute after recovery; update maximum deferral duration.
- [ ] **Step 5: Implement pressure-aware health/storage checkpoint scheduling with coalescing.** Preserve critical one-shot session/open/close evidence.
- [ ] **Step 6: Ensure recovery ordering is RAW catch-up first, then one due deferred durability/service action, then normal TFT/optional work.** Do not immediately replay every missed periodic action.
- [ ] **Step 7: Run full policy/source suites.** **Expected:** PASS.
- [ ] **Step 8: Commit:** `perf: defer routine storage service under queue pressure`.

### Task 5: Complete START, STOP, pressure, storage, and registry observability

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: `TVM1_SessionMeta.h/.cpp`, `TVM1_Meta.h/.cpp` only as required for stable new IDs/schema declarations.
- Modify: `firmware/tests/test_dev3_2_r7_2_source_contract.py`.

**Interfaces:**
- Consumes: pressure/memory/deferral state from Tasks 2-4.
- Produces durable META fields for four START windows through steady state, STOP request-to-close timing, pressure statistics, memory-gate evidence, and storage deferral metrics.

- [ ] **Step 1: Write failing test `test_start_four_windows_persisted`.** Require durable fields for postamble begin, postamble complete, steady-state timestamp, drops before first RAW, drops during postamble, and startup maximum RAW gap, while preserving existing START metric meanings.
- [ ] **Step 2: Write failing test `test_stop_finalization_metrics_written_before_meta_close`.** Require STOP request timestamp/depth, drained count, last accepted/persisted RAW timestamp, final RAW flush, final META flush, request-to-stream-close, and request-to-session-close to be durably emitted before the metadata stream becomes unavailable.
- [ ] **Step 3: Write failing test `test_pressure_memory_storage_metrics_registered_once`.** Require stable IDs for configured queue capacity, pre/post heap/largest block, pressure enter/exit/count/duration/max depth/RAW drained/drop delta, flush deferrals, and checkpoint deferrals/coalescing; fail on duplicate IDs or unmapped event/metric names.
- [ ] **Step 4: Add explicit regression assertion `test_no_unmapped_event_65535_path`.** New production and stall-test event names must resolve through the event registry and must not deliberately emit the unmapped fallback code used in the experimental LISTEN_ONLY regression.
- [ ] **Step 5: Implement the missing START persistence at the existing state transitions without adding filesystem writes to CAN/TWAI/BLE callbacks.
**
- [ ] **Step 6: Reorder/extend STOP telemetry so finalization durations are captured and persisted before SESSION.META closes; preserve exact STREAM_FILE_CLOSE and SESSION_CLOSE ordering.
**
- [ ] **Step 7: Register/persist pressure, memory, and service-deferral metrics using previously unused IDs or an explicit compatible schema extension; preserve old ID meanings.
**
- [ ] **Step 8: Run the complete source-contract suite and any existing TVM1 parser compatibility tests.** **Expected:** PASS with no duplicate/unmapped IDs and no format change.
- [ ] **Step 9: Commit:** `feat: complete storage resilience runtime telemetry`.

### Task 6: Add the isolated one-shot 650 ms stall-injection validation build

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies behind a compile-time TEST-only flag.
- Modify: variant/build identity files to produce explicit stall-test labels without changing production defaults.
- Modify: both DEV3.2/R7.2 test files.

**Interfaces:**
- Consumes: steady-state and pressure state from Tasks 3-5.
- Produces one test-only injection event pair and one-shot state; production builds compile with injection disabled.

- [ ] **Step 1: Write failing test `test_stall_injection_disabled_in_production`.** Canonical DEV3.2/R7.2 production identities must have the test flag false/undefined and no automatic delay path active.
- [ ] **Step 2: Write failing policy/source test `test_stall_injection_arms_only_steady_and_queue_at_or_below_low`.** The injection may not begin during START/postamble, pressure recovery, or a pre-existing backlog.
- [ ] **Step 3: Write failing test `test_stall_injection_exactly_once_and_rx_not_disabled`.** Require one-shot session state, approximately 650 ms main-loop delay, before/after RAM-safe telemetry, and forbid disabling interrupts, TWAI RX, or the CAN RX task.
- [ ] **Step 4: Implement a clearly isolated compile-time test flag and one-shot stall state.** Use a main-loop blocking delay/timed wait that leaves TWAI RX/task operation intact; do not simulate electrical SD failure.
- [ ] **Step 5: Persist before/after injection evidence after the stall through normal META service, including queue depth/high-water/drop delta and pressure entry/exit evidence.
**
- [ ] **Step 6: Add model acceptance calculation for 1536 at 1,670 frames/s:** 650 ms predicts approximately 1,086 incoming frames, which is below 1536 but above HIGH; the test expects pressure entry, zero drops, and eventual recovery below LOW.
- [ ] **Step 7: Run full production and stall-test source/policy suites.** **Expected:** PASS; production remains injection-free.
- [ ] **Step 8: Commit:** `test: add deterministic 650ms capture stall validation mode`.

### Task 7: Verify, package, and prove provenance for DEV3.2/R7.2 production and stall-test archives

**Files:**
- Update in both package trees: `VALIDATION.txt`, `SOURCE_BASELINES.txt`, `SHA256SUMS.txt`.
- Create: `DEV3_2_R7_2_STORAGE_RESILIENCE_TESTING.md`.
- Produce four clearly distinct archives: DEV3.2 production TEST, R7.2 production TEST, DEV3.2 STALL650 TEST, R7.2 STALL650 TEST.

**Interfaces:**
- Consumes: final verified source trees from Tasks 1-6.
- Produces: reopen-verified archives and a field-validation checklist; production and artificial-stall builds cannot be confused by filename, build identity, or manifest.

- [ ] **Step 1: Run the complete Python test suite for `firmware/tests/test_dev3_2_r7_2_*.py`.** **Expected:** zero failures.
- [ ] **Step 2: Run structural/static checks on both source trees.** Require SD=25 MHz, RAW batch=128, target queue/threshold constants, NORMAL production TWAI mode, external-tester software latch, zero intentional production stall flag, no forced-LISTEN_ONLY experimental edits, and no unmapped metric/event IDs.
- [ ] **Step 3: Run the existing host C++/stub compile used by the prior DEV3.x/R7.x package workflow.** **Expected:** exit 0. If the environment lacks Arduino core/TFT_eSPI, record Arduino IDE Verify as an explicit user-side gate instead of claiming compilation.
- [ ] **Step 4: Build the two production TEST archives and two STALL650 TEST archives with deterministic folder/sketch naming and explicit build identities.
**
- [ ] **Step 5: Calculate SHA-256 for every archive and every internal file manifest, reopen each ZIP into a clean directory, and verify internal hashes/names against the final source trees.
**
- [ ] **Step 6: Verify production-vs-STALL650 source diffs are limited to the explicit test flag/build identity and code guarded by that flag; no unrelated behavior difference is allowed.
**
- [ ] **Step 7: Write the field checklist:** first boot memory-gate capture; cold/warm START; deterministic 650 ms injection on both physical CYDs; Card A control; Card B stress; external Autel ownership-latch check; clean Android STOP; exact CLOCK_SYNC/FILE_CLOSE/SESSION_CLOSE validation.
- [ ] **Step 8: State release gate explicitly:** if either real board reports post-allocation free heap <64 KiB or largest block <32 KiB, do not field-test 1536 as production; revise the common compile-time queue target and rerun Tasks 2-7.
- [ ] **Step 9: Commit:** `build: package DEV3.2 R7.2 storage resilience test firmware`.

## Physical Validation Sequence

1. **Memory gate first:** boot each production build on its intended physical CYD, do not begin a long field drive until queue-allocation telemetry proves the accepted capacity and the 64 KiB / 32 KiB gates.
2. **Deterministic resilience second:** flash the matching STALL650 TEST build, begin logging only with the queue initially <= LOW, allow steady state, trigger/allow the one-shot 650 ms stall, then verify zero queue drops, pressure enter/exit, high-water < capacity, and exact clean STOP.
3. **Card A control:** run normal production firmware long enough to cross repeated flush/checkpoint intervals and verify no regression.
4. **Card B stress:** run the same production build on Card B and specifically compare any natural raw-write/flush tail against queue high-water, pressure duration, deferral counters, and loss.
5. **External tester:** repeat one Autel connection to confirm the ownership latch remains TX-silent; do not treat the expected externally observed TWAI storm as a storage-resilience failure unless RAW/META integrity is affected.
6. **Independent Autel track:** queue the 500-kbit/s + 250-kbit/s dual-LISTEN_ONLY observation, then scope CANH/CANL if alternate-rate coherent traffic is not decoded. This track does not block DEV3.2/R7.2 acceptance.

## Self-Review Result

- **Spec coverage:** queue/memory gate = Task 2; hysteretic pressure recovery = Task 3; pressure-aware flush/checkpoint = Task 4; START/STOP/pressure/memory telemetry = Task 5; 650 ms deterministic proof = Task 6; package/provenance/field matrix = Task 7; external-tester/TWAI production invariants are pinned in Tasks 1, 5, and 7.
- **Shared-interface consistency:** Task 2 produces queue/threshold constants consumed by Tasks 3-6; Task 3 produces pressure state consumed by Task 4 and Task 6; Tasks 2-4 produce telemetry consumed by Task 5; Task 7 consumes only verified final source/build identities.
- **Review Focus coverage:** memory fragmentation is Task 2; pressure starvation is Task 3; durability over-deferral is Task 4; registry completeness is Task 5; deterministic-stall validity is Task 6.
- **Scope control:** no dedicated writer task, SdFat migration, >25 MHz SD, RAW batch increase, auto bitrate switching, forced production LISTEN_ONLY, or unrelated TFT feature work appears in implementation tasks.
- **Proportion:** the plan fixes interfaces, exact constants, tests, and verification gates without prescribing full function bodies; implementation choices within those contracts remain with the executor.
