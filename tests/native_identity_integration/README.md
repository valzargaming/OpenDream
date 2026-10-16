# Native identity integration

`python tests/native_identity_integration/run.py` compiles the actual observation provider,
file/process adapter, client handoff, report ledger and admission gate. All external
effects use an injected host. It checks 1,000 admission cycles and 1,000 observation
cycles, unchanged native key/CID text, canceled/failed observation disposal, serialized
world ownership, stale epochs/channels, report/admission replay and idle expiry/caps.
Six omitted-guard controls must fail exactly their named assertion; a compilation
failure or additional exception cannot count as a successful control.

The existing connected `GameTests.NoRuntimesTest` enables the real required admission
adapter and uses an injected native observation. The actual messages create a real
DM client whose `key`, `ckey` and `computer_id` are checked, including a CID with leading
zeros and more digits than a 64-bit integer. Its test network connects directly and
explicitly consumes the fixture handshake; the global Connecting gate remains covered
by `tests/native_client_identity`.

These tests do not launch native DreamDaemon, the BYOND URI handler or a logged-in
native client. Remote native compilation produces a separately bound helper artifact.
Actual native account/CID parity, native client lifecycle, graphical join, R_SERVER
authorization and a successful current-world save remain separate acceptance gates.
