# Native argument ownership

The existing connected NoRuntimesTest executes real DM bytecode calling the actual
clamp native handler. Its datatype failure is caught/rethrown without runtime-log
suppression. RefCount must return to the caller's single owner after each of 2000
failed native calls and 1000 successful isnull calls. Payload retirement must leave
the actual DreamRefManager bucket. A separate production AsyncNativeProc frame
checks 1000 replacements, self-assignment, rejected indexes and disposal with real
datum owners. It does not run an asynchronous gameplay action or live game.

Remote omission CI builds the actual engine and runs this connected test against an
immutable df99 baseline, a removed synchronous finally, and removed async slot
ownership. Compilation failure, unrelated failure or missing named ownership
assertion is rejected. No local helper/compiler/server was executed in the reserved
production investigation window. These counts prove ownership contracts, not
production memory attribution, full-map latency or long-term memory stability.
