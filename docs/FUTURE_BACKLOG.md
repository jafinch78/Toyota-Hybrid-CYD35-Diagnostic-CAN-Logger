# Future firmware backlog

## Deletion-safe session folder numbering

The CYD logger should allocate `/CANLOG/S####` identifiers monotonically even
when older session folders are deleted to reclaim microSD space. A future
firmware revision should:

- inspect existing `S####` directories at startup and never choose a number
  lower than the highest valid directory already present;
- persist a recoverable next-session counter (or equivalent high-water mark)
  using an atomic temporary-file/rename update;
- ignore malformed folder names without reusing their apparent numbers;
- reserve the identifier before opening session files and recover safely after a
  power loss; and
- record the allocator policy and selected identifier in `MANIFEST.JSON` and
  the startup event stream.

This is queued for a later CYD logger release. Capture package 1.4 and existing
session folders remain unchanged until the allocator is implemented and tested
on the actual microSD/SPIFFS partition layout.
