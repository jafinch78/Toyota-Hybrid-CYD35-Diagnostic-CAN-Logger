# Toyota CAN Evidence Analyzer v0.2.0-rc1 PRE-ALPHA

Status: **PRE-ALPHA / research-only deployment**

This branch publishes the verified Analyzer v0.2.0-rc1 release candidate for pre-alpha testing. It is intentionally isolated from `main` and does not represent a production release.

## Verified scope

- 38/38 automated tests pass with ResourceWarnings promoted to errors.
- Canonical v0.9.12 and proposed v0.9.13/v0.9.14 databases import without branch confusion.
- Master Session Index, Successful Decode Method Registry, and Method Exhaustion Matrix import as first-class inputs.
- 12 executable decoding methods are registered.
- Exhaustion fingerprints skip identical exhausted reruns.
- Deterministic text/CSV/JSON/HTML outputs match across repeated real-reference runs.
- S0093 Builder broadcast-routing limitation is treated as a Builder defect, not negative evidence against confirmed broadcast definitions.
- S0094 incomplete-finalization provenance is retained conservatively without fabricating decoded evidence.

## Outstanding certification gate

A native Windows PyInstaller EXE has not yet been built/launched on the supported Windows target. Python source/wheel validation is complete; Windows-native executable certification remains required before alpha/production promotion.

## Release-candidate bundle

Google Drive folder:
https://drive.google.com/drive/folders/1baKzY0ZoSW3BNOsiPNPpuhB5Gf8OqIe0

Release candidate:
https://drive.google.com/file/d/11lgI93Fo-nvMLdEIEjlUfnK-fJbuUGZW/view?usp=drivesdk

Release-candidate SHA-256:
`e1f9925ffc12fef3a7ce81ec33cbbd90b343b61e52f890bcf3af690fa53e8725`

Verified source commit from the isolated implementation workspace:
`50facb6d31926dff5a56df5f2b26ac31799e8b0c`
