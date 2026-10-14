# World clock regression

`world.realtime` is UTC deciseconds since 2000-01-01. The previous getter used
the `TimeSpan.Milliseconds` component, returning a repeating integer from 0 to 9.
The fix uses `TotalMilliseconds` and a UTC epoch. DreamValue still stores a
float, so current epoch values have coarse precision; use `world.timeofday`
with midnight wrap handling for short elapsed-time diagnostics.

The dedicated workflow builds the real solution at the exact PR head with
SDK 10.0.401 and runs the public getter and compiled DM getter in one isolated
engine fixture. Its Explicit attribute keeps native-library initialization in
a separate test host from the ordinary integration suite. Positive evidence
requires one executed passing test. An immutable source control must fail
exactly four realtime epoch/bracket assertions, with no unrelated failures.

Both modes must first pass an actual timeofday advancement smoke: public and
compiled values are bracketed by UTC day samples before and after a measured
1.2-second delay. Modulo-864000 advancement must match broad Stopwatch/UTC
bounds. The strict verifier rejects missing/skipped tests, frozen or repeating
component clocks, invalid host timing, wrong test identities and unrelated
errors. This bounded smoke does not establish general clock monotonicity.

The workflow retains original build/test logs, actual exit codes, source
receipts and TRX results. Pure controls can be run without launching an engine:

```text
<verified-python> -m unittest discover -s tests/world_realtime_clock -p test_*.py -v
```

This clock repair does not identify a live memory leak, make native save
serialization resumable, or establish completed Gaia saves and recovery.
