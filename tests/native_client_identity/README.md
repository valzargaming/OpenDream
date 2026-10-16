# Native-only client identity boundary

The custom client replaces the editable username field with a read-only BYOND
account label. Its Connecting event overwrites CLI/console/config identity using
only the current native observation and throws before ClientConnect when absent.
Each menu attempt starts a new observation; cancellation, replacement, disconnect
and faults clear it. CID is retained as digit text without numeric conversion.

The production provider now lives in the trusted Robust.Client engine, with
internal file/process capabilities and operator paths captured before content
loads. The native helper, channel transport and server admission gate are present
in source. Genuine native account/CID, rendering, admin admission and save
acceptance remain unproved; the path is not activated on Gaia. Do not treat these
injected observer tests as native acquisition or DreamDaemon CID parity evidence.

Run `tests/native_client_identity/run.py` with a verified Python interpreter and
.NET 10. It links the production coordinator into a standalone injected-observer
probe and verifies 1000 reconnect/account-switch cycles, pending failures,
one-use login, malformed reports, late replacement, guest rejection and disposal.
Five omission controls must compile and fail their designated runtime assertion.
Monotonic expiry checks cover completion and handshake at the exact deadline,
independent of cancellation timer scheduling.
Source checks pin the UI and Connecting event wiring. Full engine CI compilation
checks integration signatures; actual console/autoconnect/native behavior remains
unverified until an exclusive native/client runtime turn is granted.

The native observer must disclose that connecting its local observation world
can disconnect an existing native BYOND world. It must obtain a fresh native key
and CID before Connect, preserve the report for the channel-bound handoff, clean
up owned temporary files/processes, and cancel on timeout/shutdown. The server
must accept the channel-bound report before creating a DM client or mob. No
passwords, Windows/GitHub names, volume serials or user-entered identity qualify.
