# Resource output allocation

`DreamResource.Output` still removes DM formatting and appends literal CRLF with
strict UTF8 without BOM. Text up to 4096 characters retains AppendAllText and its
bounded temporary copy. Above that boundary a locally disposed StreamWriter writes
text and CRLF separately, avoiding the full-size temporary string. Cache invalidation
and successful profiling occur after writer disposal. Flush cadence, JSON schema,
virtual Output dispatch and complete-tree serialization remain unchanged.

The external workflow tests the candidate on Linux and Windows, and three negative
controls on Linux. It builds the real integration assembly with pinned .NET SDK
10.0.401 and the committed RobustToolbox submodule. It runs three explicit NUnit
tests with the actual resource, profiler, compiler and isolated runtime:

* Byte/error/cache/handle-disposal contracts, Unicode and formatting, null/invalid
  values, strict encoding errors, failed disk writes and enabled profiling.
* Native interpreted DM savefile writes, explicit Flush, shared handles, deletion,
  reopened values, nested associative lists, escaped formatting and CRLF/no-BOM.
* Identical output workloads: 16/1024/4096/4097/1048576/8388608 characters, three warmups and
  eight measured calls each. Inputs and Clear are outside measurement. Records
  thread allocated bytes, elapsed seconds, all GC collection counts, runtime and
  OS; no forced collection. The largest workload must allocate less than one byte
  per input character per call, exposing the original two-byte-per-character copy.
  Small-text allocations must stay below twice the input length plus 1024 bytes
  per call, preserving baseline costs including the 4096 boundary. Elapsed time is reported,
  not used as a noisy correctness gate.

The baseline replaces only DreamResource.cs with the authenticated immutable
Git blob from 31b11b063e4b10be15472de8a566d9a466781e4c. It must pass byte and
round-trip tests and fail only OUTPUT_ALLOCATION_SCALING after emitting all four
workloads. The unsafe platform-newline control replaces only the literal CRLF
write with WriteLine; on Linux it must fail both named CRLF contracts while the
allocation workload passes. Sources are authenticated before and after build.
The no-small-path control disables only the 4096 guard and must fail only the
small-allocation bound after emitting all six workloads. Malformed UTF8, failed
appends, cache and enabled-profile success/failure cover both paths. The native
savefile text is larger than the threshold so its CRLF check exercises streaming.
Original logs, TRX, prepared sources and DLL/PDB binaries are retained with hashes.

The existing immutable save-profile package explicitly composes the two changed
append calls and exact helper into its candidate and all prior negative controls.
Its historical sources, frozen manifest and original variants remain unchanged;
any unrelated resource edit, cache change or platform terminator is rejected.

Pure checks (use a verified full interpreter path on Windows):

```
python3 -m unittest discover -s tests/resource_output_allocation -v
```

No test accesses production storage, saves or a running server. External integration
evidence is not full Gaia performance, whole-server RSS or OOM acceptance. Partial
file bytes after an exceptional append are not a promised atomic-write contract;
exception type, disposal and cache behavior are checked. No JSON streaming or
dirty-flush deferral is introduced.
