# ToyotaCAN Session Matcher v1.3 — Windows 10 1607

This release publishes the tested x64 Windows GUI executable as `ToyotaCAN_Session_Matcher_v1.3_Win10_1607_EXE.zip`.

Full package (EXE + PDB + source + tests + validation documentation) is retained in the project Google Drive under `CANbus/ToyotaCAN_Session_Matcher/v1.3_Win10_1607`.

Release hashes:
- EXE SHA-256: `6e048ad95855fa0005746328cae9ef2266ccced947e35f6a03dc01b08dd2829f`
- PDB SHA-256: `7627c64ddc475b4ac2926b4c45dad50f6b3a471a620c2ece59a8f7c19b3e9436`
- Full package ZIP SHA-256: `54687f6587a02644b50a64bb372684356d894ebe4bddce73a7513cbd75d69f91`
- GitHub EXE-only ZIP SHA-256: `68067df74f6d9927bc456de461933b1055b8887ac0ec0ae248a0350c01217a6e`

Compatibility profile:
- PE32+ x86-64 Windows GUI
- linker header 14.0
- Windows subsystem 6.02
- Windows 10 1607 x64 target

v1.3 adds direct `S####` ↔ CAPTURE `cyd_session` identity matching, conflict detection, content-based candidate discovery, and an auditable evidence inventory.
