# Native-only client identity boundary

The custom client replaces the editable username field with a read-only BYOND
account label. Its Connecting event overwrites CLI/console/config identity using
only the current native observation and throws before ClientConnect when absent.
Each menu attempt starts a new observation; cancellation, replacement, disconnect
and faults clear it. CID is retained as digit text without numeric conversion.

The registered provider is deliberately unavailable. The real native observer,
native helper packaging, channel report transport and server DM client/mob gate
are not installed. This source stage refuses every game connection until those
pieces are implemented. Do not ship it as a playable launcher or treat the injected
observer tests as native acquisition or DreamDaemon CID parity evidence.

Run `tests/native_client_identity/run.py` with a verified Python interpreter and
.NET 10. It links the production coordinator into a standalone injected-observer
probe and verifies 1000 reconnect/account-switch cycles, pending failures,
one-use login, malformed reports, late replacement, guest rejection and disposal.
Four omission controls must compile and fail their designated runtime assertion.
Source checks pin the UI and Connecting event wiring. Full engine CI compilation
checks integration signatures; actual console/autoconnect/native behavior remains
unverified until an exclusive native/client runtime turn is granted.

The native observer must disclose that connecting its local observation world
can disconnect an existing native BYOND world. It must obtain a fresh native key
and CID before Connect, preserve the report for the channel-bound handoff, clean
up owned temporary files/processes, and cancel on timeout/shutdown. The server
must accept the channel-bound report before creating a DM client or mob. No
passwords, Windows/GitHub names, volume serials or user-entered identity qualify.
