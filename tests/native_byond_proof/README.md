# Client-reported native identity handoff prototype

This draft is dormant. It adds no listener, launcher UI, connection registration,
DM client gating or game startup changes. CID is a client report, not authentication.
Ordinary players may run the native helper locally; there is no shared server secret.

The linked-source .NET probe tests the production report ledger and extracts the
actual production Ckey body/regex rather than reimplementing normalization. It
checks 1000 one-use deliveries, exact channel/generation binding, replay, disposal,
replacement, disconnect, total 60-second expiry including queued delivery, strict
UTF-8/form parsing and the 128-record bound. CID remains exact digit text, including
leading zeroes and values exceeding machine integers. Four independent omissions
must fail their named assertion after compilation succeeds.

Run `python tests/native_byond_proof/run.py` using a verified interpreter and SDK10.
The registered GitHub workflow runs positive and omission probes. These are adapter
tests, not actual native client presence, DM client gating or multiplayer acceptance.
No local probes were run during the reserved production investigation window.

`tools/native-byond-bridge/bridge.dm` is a standalone native observation world. In a
launcher-owned temporary directory, `bridge-request.json` supplies the server epoch,
nonce, with no user-entered name. The launcher must explicitly disclose that
connecting the native client disconnects its current world, then open a loopback
`byond://` connection with the nonce as its only topic parameter. The native world
rejects remote peers and observes native `client.key`, `client.ckey` and
`client.computer_id` directly. It writes one bounded `native-report.json`, disconnects
the native observer, and stops after 60 seconds. The future launcher validates that
bounded file, forwards its four fields on the actual authenticated OpenDream channel,
then deletes its owned temporary outputs/process. No credentials are read or stored.

Remaining acceptance: compile with native BYOND516.1681; observe logged-in and guest
connections; compare exact report CID/key with native DreamDaemon values; prove
actual native disconnect/report completion; implement/review temporary-directory
ownership, fixed loopback port, file-read deadline and process cancellation; prove
zero actual OpenDream DM client/mob creation before required-mode acceptance and no
creation after disconnect; prove required-mode username UI/arguments cannot override
the native-reported name and reconnect/account-switch clears the old key/CID.
Shared connection/client hooks remain withheld. Same-PC
native presence is not hub authentication and cannot establish server-attested login.
The game-thread adapter must atomically recheck its binding before effects; the
ledger alone cannot make an arbitrary external adapter atomic.

Official references: [BYOND DM reference](https://www.byond.com/docs/ref/),
[BYOND author's guest format explanation](https://www.byond.com/forum/post/272477).
The latter documents older native releases; it does not replace pinned-version proof.
