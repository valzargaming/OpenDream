# Decoder allocation regression

Production changes only StringFormatDecoder. Unformatted input returns directly;
formatted input uses a local builder. The same U+FF00-U+FFFF code units are
removed. Savefile serialization, append, Clear, dirty scheduling and Close remain
unchanged. Formatting still allocates O(input length) temporary storage.

The separate explicit StringFormatDecoderTests class exercises all UTF-16 code
units, seeded random and large mixed strings, concurrent calls, warmed
unformatted allocations and post-GC capacity retention. The retention fixture
uses a non-inlined helper so the large input leaves scope, verifies its weak
reference is dead and verifies a deliberately live sentinel remains alive.
It asserts retained growth below a generous 4 MiB ceiling after processing an
8 MiB mostly formatted input. This is observed managed retention, not a hard
memory ceiling or a full-world/OOM diagnosis.

Actual SfDreamDir/SfDreamPrimitive/SfDreamListValue polymorphic trees use real
DreamValue strings/numbers and its real converter on the integration server's
IoC thread. Byte oracles cover default escaping, all formatting characters,
Unicode, unmatched surrogates, CRLF and no BOM. Actual DreamResource checks
private clear/public append path separation, aliases, cache timing, append
failure and converter failure after Clear. These are resource/tree integration
checks. Actual handle/last-Close/failed-initialization ownership comes from the
unchanged GameTests.NoRuntimesTest savefile hook, run in a separate testhost.

The GitHub workflow builds the actual solution with SDK 10.0.401, matching other
ownership workflows. Both matrix modes require the existing NoRuntimesTest to
pass and its 200-disposal/shared-file completion marker to be present. Positive
runs all seven decoder tests. Immutable baseline runs six, excluding concurrency
because the old shared builder has a nondeterministic race. Baseline must pass
all content/resource tests and fail exactly the allocation and retained-capacity
markers. Compilation errors, missing/extra/skipped results, wrong test identity,
unexpected stacks, arbitrary failures and runner/runtime errors are rejected.
The verifier's direct NUnit-failure formatting is source-prepared; the first
real run must validate it against original TRX rather than weakening acceptance.

Source controls bind the reviewed files to the exact PR head and the original
decoder to immutable fork master 53554597f7b594ea8a75570240d69d7d3003d56f.
The baseline decoder is byte-identical after the stated LF transform; only the
read-only GameTests pin advanced to include merged range PR 31.
CRLF to LF is the only permitted transformation; whitespace, BOM and lone CR
are preserved. Receipts retain raw/canonical SHA-256 and Git blob identity, plus
original and prepared source files. Artifacts preserve full build/test/runtime
logs, original TRX, SDK information, source receipts and tested DLL/PDBs.
No existing GameTests/DM project/source pin is changed. The explicit fixture is
selected by the focused workflow with NUnit.ExplicitMode=Relaxed. This keeps its
engine server in a separate test host from the ordinary GameTests run because
BYOND API native-library initialization is process-global. The strict verifier
requires all seven positive tests or all six baseline tests, so a skipped fixture
cannot pass as regression evidence.

## Optional standalone seam benchmark

`Benchmark.csproj` links the actual selected production resource/decoder sources
with minimal string-only DreamValue bindings. It is intentionally separate from
the actual-converter NUnit integration above. Run each 1/16/64 MiB payload in a
fresh process; three total flushes yield one cold and two warm rows. Deterministic
trees use unique string members. Rows retain encoded bytes/SHA-256, member and
flush counts, total allocations/GC counts, managed retained heap, elapsed flush
time and OS process metrics. Hashing is streaming and outside flush timing.
Payload sizes exclude JSON punctuation; use measured output bytes for comparison.

Under the root's exclusive native queue, build identical benchmark sources
once with reviewed candidate and once with the immutable baseline, placing the
built DLLs under BuildRoot/decoder/Benchmark.dll and BuildRoot/baseline/Benchmark.dll.
Record exact
source/build/runtime receipts and run separately. Check every hash, byte count,
member count and flush count before comparing metrics. RunBenchmark.ps1 launches
these already-built DLLs separately and verifies cross-variant output receipts:
at most 2 GiB sampled process memory, 90 seconds per process
and 300 seconds total; a killed/missing/error run is rejected. Sampling cannot
enforce an OS hard memory ceiling. This workflow does not auto-run benchmarks.

```powershell
# Future template only, with a trusted absolute SDK path and exclusive queue.
& $trustedDotnet run --project tests/string_format_decoder/Benchmark.csproj -c Release -- 16 3
# Preferred bounded comparison after both exact-source builds:
& ./tests/string_format_decoder/RunBenchmark.ps1 -DotnetPath $trustedDotnet -BuildRoot $buildRoot -OutputDirectory $resultRoot
```

Root's prior source-seam comparison found lower 64 MiB allocations and retained
heap for this candidate, but the 1 MiB case was slower. Those earlier receipts
are external evidence, not a result produced by these versioned integration
tests. Do not claim uniform speedup, completed Gaia saves or live-server OOM,
latency, recovery or durability acceptance. CI and actual integration are pending.
