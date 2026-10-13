# Async return ownership

The connected engine test executes real DM returns through 1000 Call and 1000
CallNoWait continuations, each requesting another real DM call while retaining
the first awaited owner. It checks exact reference counts, liveness and final
DreamRefManager retirement. No assertion is thrown inside an engine continuation.
Another 1000 production frames acquire real DM return values, replace the pending
value, then cancel/pop before delivery. This is a controlled frame boundary test,
not a live gameplay cancellation scenario.

Another 1000 connected CallNoWait tasks cancel their actual live TCS before a
real DM return, hold the async frame open through refused delivery and then drain
through connected game ticks. Refused delivery releases its owned value and
repeated cancellation is idempotent.

Six remote controls restore the immutable pre-fix AsyncNativeProc or omit
acquisition, pending replacement release, disposal release, reentry scheduling
or refused-delivery release.
The shared strict verifier requires exactly one intended NUnit assertion with
its complete expression, delta and actual fixture stack. Existing native-argument
verifier defaults and unrelated-error guards remain unchanged.

Production callers that ignore Stat/verb/Move results dispose their awaited
owners. Topic transfers separate owners to the scheduler and reply consumer.
These callers receive source review; no actual player/network fixture or live
Gaia attribution is claimed. No local helper/compiler/server was run.
