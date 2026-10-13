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
