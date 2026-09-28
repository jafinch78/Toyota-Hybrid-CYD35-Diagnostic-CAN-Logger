# Task 9 Gate Amendment — Builder-Only Compatibility Boundary

Date: 2026-09-28

This amendment supersedes the Analyzer-smoke requirement in Task 9 of `2026-09-27-native-session-offline-expander.md`.

## Rationale

Evidence Builder compatibility is the firmware/offline-preprocessor boundary being validated. Analyzer already consumes the Builder-integrated processing path, so repeating an Analyzer smoke is not an independent requirement for authorizing firmware SD-product removal.

The latest pertinent standalone Builder lineage for this gate is Evidence Builder 1.0.4 with `EvidenceBuilder_v1.0.4_RC7_CanonicalDB_Patch_v1.0.1`. Later Matcher-only patches do not change this processing boundary and are not additional Task 9 gate requirements.

## Superseding Task 9 authorization rule

Firmware SD-product removal is authorized only when all four conditions are true:

1. S0141 RAW identity gate = PASS and Builder 1.0.4 compatibility gate = PASS.
2. S0149 RAW identity gate = PASS and Builder 1.0.4 compatibility gate = PASS.
3. S0128 RAW identity gate = PASS and Builder 1.0.4 compatibility gate = PASS.
4. Windows 10 1607 preprocessor/launcher validation = PASS.

No Analyzer RC7/RC8 smoke report is an input to the authorization function.

The executable validator must therefore reject missing, duplicate, substituted, or failing required Builder sessions and must fail closed when Windows 10 1607 evidence is absent or not PASS.

## Required final statement

Only after all four conditions pass may validation state:

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```

Otherwise it must state:

```text
TVM1 OFFLINE EXPANDER GATE: FAIL — do not remove legacy firmware SD products.
```

This amendment does not remove Analyzer from the overall project workflow; it removes Analyzer only as a redundant prerequisite for this specific firmware compatibility gate.
