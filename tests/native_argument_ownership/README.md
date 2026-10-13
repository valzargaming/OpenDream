# Native argument ownership

The existing connected NoRuntimesTest executes real DM bytecode calling the actual
clamp native handler. Its datatype failure is caught/rethrown without runtime-log
suppression. RefCount must return to the caller's single owner after each of 2000
failed native calls and 1000 successful isnull calls. Payload retirement must leave
the actual DreamRefManager bucket. A separate production AsyncNativeProc frame
checks 1000 replacements, self-assignment, rejected indexes and disposal with real
datum owners. It does not run an asynchronous gameplay action or live game.

Remote omission CI builds the actual engine and runs this connected test against an
immutable df99 NativeProc/SetArgument baseline, a removed synchronous finally, and removed async slot
ownership. Compilation failure, unrelated failure or missing named ownership
assertion is rejected. Structured TRX must contain exactly one failing NoRuntimesTest
with the complete intended assertion/refcount delta and actual fixture stack. Mixed
engine errors, runner errors and additional test/assertion failures are rejected;
the verifier has explicit intended-plus-unrelated-failure negative examples.
Only the historical SetArgument method is restored from AsyncNativeProc, so
independent newer async return/scheduling fixes remain present in this control.
No local helper/compiler/server was executed in the reserved
production investigation window. These counts prove ownership contracts, not
production memory attribution, full-map latency or long-term memory stability.
