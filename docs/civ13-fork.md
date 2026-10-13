# Civ13 maintained OpenDream fork

Integration repository: https://github.com/valzargaming/OpenDream

`master` is the tested fork integration branch. Keep upstream fixes on separate
branches so their upstream PRs do not acquire fork configuration changes.
The memory ownership fixes are proposed upstream in OpenDreamProject/OpenDream#2728.

For each integration PR, require successful exact-head build/tests on Windows and
Linux, ownership regressions and the applicable inherited workflows. Local checks
are supplementary evidence. Do not merge through failing checks.

Before bringing in upstream changes, fetch OpenDreamProject/OpenDream and inspect
the commit range and RobustToolbox submodule revision. Use a review branch and PR
instead of replacing fork master. Retain local fixes until their upstream
equivalents have been reviewed and regression-tested.

Fork master builds retain artifacts, but automatic upstream-style release
publication is disabled for this repository. CI and a merge do not deploy a
server. Installations must record the engine SHA, runtime hashes, game SHA,
preserved sprite/movement changes, backup and matched benchmark conditions.

Keep Actions' repository default token permissions read-only. The label job has
explicit write permissions for labels; game builds do not need that grant.

## Upstream correctness integration

The `upstream-runtime-correctness` integration selects OpenDream PRs #2708
(special-list Find), #2719 (filter variables and attachment ownership), #2723
(caught runtime exception datums) and #2720 (stale test output cleanup).
Their original commits retain cherry-pick attribution. Filter and Find fixtures
use separate tiles because both originally assumed exclusive contents at (2,2,1).

The narrow eye ownership correction from #2477 removes the second reference
transition in `DreamObjectClient`: `DreamConnection.Eye` already performs it.
The existing real-server integration test checks 200 eye assignment/self-assignment
and reset cycles, and 200 filter wrapper creation/deletion cycles. It reuses the
existing server because BYOND API initialization is process-global.

Defer the remainder of #2477's client/PVS rewrite and #2478's scheduling rewrite.
The latter would remove the fault/cancellation cleanup already fixed here.
Compiler optimizations #2717 and #2718 both assign opcode 0x9D and require a
separate reconciled compiler/runtime integration and recompiled game bytecode.
