# Gaia save capture

These explicit integration tests observe the actual diagnostic SAVE wrapper in
a fresh task-owned resource directory. They require a Release build with
`SaveCostHostProfile=true` and a reviewed `OD_GAIA_SAVE_HOST_PLAN` JSON file.
The plan contains `JsonPath`, `JsonSha256`, `SaveEntryPoint`, `OwnedRoot`,
`OwnershipId`, `MaximumTicks`, `MaximumFlushes`, `WorldParamsPath` and
`ReadinessGlobal`. Private world parameters are read from the owned file and
must not be logged. Registry metadata binds the accepted full-game input.
Natural tick limits must be chosen before launch, between 1 and 12000; the
exclusive caller must also impose finite wall-time and memory limits.

The host samples scalar memory, live-reference and pool counts without forcing
collection, copying trees or changing flush timing. It awaits the real SAVE
wrapper, observes natural handle closure, seals the profiler and checks two
further natural ticks. Its null resource filter aggregates all savefiles in the
window. Counts and aggregate completed flushes do not prove per-shard success.
Small scalar/profile rows are also appended to `gaia-host-journal.jsonl` in the
owned directory as they happen, preserving partial leads if the guard stops a
process. This journal does not establish completion. Failure cleanup first
drains the integration host's idle acknowledgement before inspecting its state.

Compile `fixtures/seam.dme` with the selected engine compiler first. In separate
fresh processes, `fixture_case` selects close and yield positives, return-failure,
missing-shard, late-write and cap controls. The cap case requires
`MaximumFlushes=2`. A reader-rejection SAVE followed by the separate explicit
reader test verifies rejection of wrong but valid shard data. `verify_control.py`
classifies the exact TRX assertion and rejects unrelated failures.
The TRX result must link to one matching test definition by ID; its class and
method identify the selected test independently of the short display name.

After every owned process exits, run `verify.py` with retained original log,
TRX, guard and pre-launch binary/source pins. It verifies stopped shard hashes;
the independent core generation/format check and a separate fresh full-game
recovery remain mandatory. Neither parser tests nor this host alone establish
gameplay, persistent memory growth or an OOM fix.

`GaiaSaveRecoveryHostTests.FullGaiaFreshRecovery` runs in a separate fresh
process using `OD_GAIA_RECOVERY_HOST_PLAN`. The plan pins the compiled game,
owned directory, private VERIFY parameters, stopped receipt and both shard
hashes and lengths. It awaits the real core `run_probe`, which validates the
generation before restoring it, and requires the original VERIFY oracle.
The root caller must hash the inputs again after every process has exited.

Run parser regressions with a verified Python interpreter:
`python.exe -m unittest discover -s tools/gaia_save_cost/tests -p "test_*.py"`.
The regression tests do not compile or execute the game. Native launches must
use the existing exclusive root guard, retained process exits and bounded
memory/time policy. Automatic CI registration is disabled.
