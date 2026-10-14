# Native typesof creator ownership

This explicit integration test compiles an isolated DM fixture, uses the established host, and performs 18 rejection cases x 1000 calls. It checks both local catch and outer catch after callee unwind; no global uncaught error is accepted. The same caller datum/list aliases are repeated, with one child owned solely by the caller list. Every result is disposed. Success return/drop and empty controls verify exact type sequence, creator transfer, bucket identities and final deletion/locate.

Positive requires one executed/pass test and exit 0, one success row, eighteen exact ownership/list rows, one completion marker and no error. Baseline requires one executed/fail test and exit 1, exactly eighteen ordered UNRETURNED_LISTS_1000 failures, each actual 1000 expected 0, and no completion marker. For every baseline case all 1000 new list identities must have RefCount 1 and the precise type-only partial contents; held owners and other buckets remain unchanged. Per-case cleanup deletes only new identities after observing them so leaks cannot contaminate later cases. Unexpected outcomes, ownership, contents, identities or cleanup failures invalidate evidence.

control.py requires exact committed source hashes, raw historical Git blob bytes and a matching HEAD. Baseline restores only the frozen NativeProc_typesof method. The composed baseline retains matrix cleanup and matches composed-baseline-native-root.txt; the bounded restored typesof method matches base644. The authenticated full historical raw source remains a separate immutable input, not the composed baseline output. Each mode retains preparation receipt, three prepared source files/hashes, SDK, full build log/exit, DLL/PDB/hashes, original test log/TRX/exit and separate unchanged NoRuntimes log/TRX/exit. NoRuntimes is a fresh process, using the existing strict runtime verifier.

Parser/provenance tests are synthetic Python checks, not native evidence. This detached candidate is not compiled or executed. Root independently confirmed the raw base644 NativeRoot Git blob and supplied its original bytes; the worker verified byte equality with the frozen baseline. Other dependency pins reflect the established current constructor host and must be reviewed when integrating into another head. Source-only expected outcomes are fail-closed: an actual NUnit spelling, source frame, contents order or count differing from these oracles must be investigated from originals, never relaxed merely to pass.

No cycle, full-world gameplay, OS memory reduction, live-server attribution or 12.5 GB explanation is claimed.

Raw-log retention: after the separate runtime host, CI archives exactly `sdk-info.log`, `build.log`, `typesof.log`, `runtime.log` as `original-runner-logs.zip` and writes `original-runner-logs.json` with each original byte count/SHA256 and ZIP SHA256. The archive is retention evidence, not test acceptance. Archive failure fails the job. The step runs after a successful build even if dedicated or runtime classification failed, provided the job was not cancelled; absent logs remain a failure and are not synthesized.

Replay from downloaded original artifacts in a fresh directory:

```text
python tests/typesof_ownership/extract_logs.py --archive RESULTS/original-runner-logs.zip --receipt RESULTS/original-runner-logs.json --destination FRESH_ORIGINAL_LOGS
python tests/typesof_ownership/verify.py RESULTS/typesof.trx MODE ACTUAL_TEST_EXIT --log FRESH_ORIGINAL_LOGS/typesof.log
python tests/string_format_decoder/verify.py RESULTS/runtime.trx positive ACTUAL_RUNTIME_EXIT --log FRESH_ORIGINAL_LOGS/runtime.log --runtime
```

Use actual numeric exits from retained `test-exit-code.txt` / `runtime-exit-code.txt` and the recorded positive/baseline mode. Require the exact-head source receipt, prepared sources, binaries and exit/build evidence in addition to parser results. Extraction validates ZIP checksum, exact member order/names, no duplicates/traversal/symlinks/encryption, bounded ordinary compression, per-member size/checksum, strict receipt schema and a fresh destination. Each file is limited to 8 MiB, total original logs to 32 MiB, archive to 32 MiB plus 64 KiB. Preserve downloaded originals and receipts; never substitute an Actions web rendering for archived logs. If interrupted before archive creation or any required record is missing, that mode is incomplete.
