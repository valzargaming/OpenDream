# Disk-backed savefile read cache

The production change releases only the cached byte array of a disk-backed resource after virtual ReadAsString materializes its text, before JSON parsing. The existing ResourceData setter balances TOOLS accounting. Resource identity/ID, parsed roots, embedded resources, close/flush/error handling and failed-file contents remain unchanged.

The explicit real-host test compiles the bounded DM fixture into unique temporary storage and runs actual savefile creation/read/deletion and file/file2text procs. It checks live and last-close paths, usable remaining shared owners, valid round trips, 16 distinct 65536-byte malformed inputs and 16 repeated reads of one path, deletion before close, actual cyclic serialization rejection, direct append rejection with a held FileShare.None file, and a shared preloaded disk resource followed by external rewrite and fresh file2text. The cyclic serialization and append cases retain the existing truncation/error behavior. Append is a direct production Output failure, not a simulated whole Close failure. Reflection observes backing arrays without invoking ResourceData and verifies open/directory/dirty and datum/list/savefile buckets. It never forces GC.

Four committed-source modes run in separate processes:

- positive: release disk bytes and preserve in-memory resource bytes.
- baseline: restore the historical ReadAsString statement at the one read site, retaining every other current fix.
- omit-release: retain the try/finally and omit its release call; observe the same retained raw-byte counts.
- drop-inmemory: remove only the disk-backed guard. Require the sole intended RAW_CACHE_EMBEDDED_UNCHANGED assertion failure, rather than accepting arbitrary failures.

Baseline and omitted release are passing observation controls: unique malformed paths retain 1048576 bytes, repeated one-path reads retain 65536 bytes, while successful final close still clears ordinary read bytes. They do not claim every successful close leaks. Positive requires zero backing read bytes at each measured point. Shared wrappers/IDs and preheld byte arrays remain valid. The embedded byte-array and console checks prohibit clearing data that cannot be reloaded from disk.

The dedicated workflow pins SDK 10.0.401, records exact prepared source and binary hashes, original SDK/build/native/ordinary logs, exit codes and TRX, and runs unchanged GameTests.NoRuntimesTest in another fresh process for every mode. Bounded original-log ZIPs retain loose log bytes with SHA receipts. Native classification requires exactly the registered test, all seven rows, expected counts/outcomes and no runtime errors. An unrun source fixture is not runtime evidence; synthetic parser/mutation tests establish only those validators.

Pure checks: `python -m unittest discover -s tests/savefile_raw_cache -p 'test_*.py' -v`. CI invokes control.py against the exact committed head, captures prepared bytes, builds, then reauthenticates the prepared source before classifying originals. No live game, large-save latency, RSS reduction, cache-wrapper cardinality bound or OOM claim follows from this suite. CI must establish compiler/runtime behavior, including Unix file sharing and genuine serialization rejection.

Inherited control composition is explicit. Frozen 644 source files remain byte-identical in the profiler package; the separately prepared historical serialization variant adds only the exact disk-cache helper/read-finally spans. Its receipt records that distinction. The decoded-resource baseline retains the finally while restoring its authenticated old decode call. The historical append variant restores the authenticated old Output implementation and retains only the disk-cache helper. Their prior assertions, workload, profiler counters and raw original identities are preserved.
