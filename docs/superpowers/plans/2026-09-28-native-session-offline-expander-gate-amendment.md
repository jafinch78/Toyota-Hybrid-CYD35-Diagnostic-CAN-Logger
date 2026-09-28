# Native Session Offline Expander Gate Amendment

Date: 2026-09-28

This amendment supersedes the Analyzer RC8 smoke requirement in `2026-09-27-native-session-offline-expander.md`.

## Rationale

Evidence Builder 1.0.4 compatibility is the actual downstream package boundary that the native-session preprocessor must preserve. Once the regenerated CANLOG package is accepted and processed equivalently by the current patched Builder, an additional Analyzer RC7/RC8 processing run does not test a distinct compatibility boundary and is disproportionately expensive for real multi-million-frame sessions.

## Revised Task 9 gate

Firmware SD-product removal is authorized only when all of the following pass:

1. **Authoritative RAW identity/integrity** for the real validation sessions: physical TCB SHA-256 values, complete record counts, logical CAN SHA-256, RX/TX counts, chunk order/rotation continuity, and truncated-tail status all reconcile through historical → synthetic native → expanded legacy conversion.
2. **Evidence Builder 1.0.4 oracle equivalence** for S0141, S0149, and S0128 using the same patched Builder lineage, same selected database, same CAPTURE input/options where applicable, and no material evidence regression.
3. **Windows 10 1607 preprocessor/launcher validation** using a real session, with observable Python path/version, input/output hashes, PASS/FAIL stages, and final ERRORLEVEL.

Analyzer RC7 and RC8 processing are downstream consumers and are **not** required to authorize the simplified firmware. They may be exercised later as part of Analyzer-specific validation, but their runtime cost must not block this logger/preprocessor boundary.

## Revised authorization statement

Task 9 still ends with exactly one of:

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```

or

```text
TVM1 OFFLINE EXPANDER GATE: FAIL — do not remove legacy firmware SD products.
```

The validation script and unit tests must enforce the revised gate directly; they must not retain an Analyzer-smoke CLI argument or Analyzer-smoke PASS dependency.
