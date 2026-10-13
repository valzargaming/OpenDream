# Native exception ownership regression

The existing connected `GameTests.NoRuntimesTest` calls production bytecode,
thread dispatch, object fields, reference counting and `DreamRefManager.LocateRef`.
It checks 1,000 bound catches, 1,000 discarded catches, 1,000 nested rethrows,
100 uncaught object throws, and exception field replacement/repeated deletion.
Uncaught throws intentionally set `LastDMException`; its previous diagnostic
state is restored afterward. No CLR collection is forced and no live game is used.

Normal Windows/Linux engine CI supplies the positive native test. The separate
exception workflow tests the immutable pre-fix production baseline and three
independent omissions against the same connected assertions. Compilation failures
do not count as a rejected control. Control scripts mutate only disposable CI
checkouts and retain source hashes, exact head, logs and the expected assertion.

This proves reference ownership for these error paths. It does not attribute
Gaia's memory use to them, measure multiplayer latency, or prove long-term stability.
