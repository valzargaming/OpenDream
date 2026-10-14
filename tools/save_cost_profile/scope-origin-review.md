# Frozen scope/origin refinement

Source-only packet for root integration at supplied fork 644a0eca75c7a5a5d74b16de04ec589cf0ac1faa. All four original SHA-256s match the clean root-owned opendream-save-cost-profile checkout. No Git, compiler, runtime, network, shared-source edit, B79 access or permission change was performed. Main runtime candidate and host sources are frozen in their hash manifests. Current generated controls are `smoke/generated-controls-v3`; earlier control directories are preserved superseded packets.

## Actual entry paths

| Origin | Source-bound meaning |
|---|---|
| Initialize | Initialize creates a new backing file/directory tree and calls Flush. Opening an existing file does not necessarily flush. |
| Direct | Public Flush, including the native savefile Flush proc and C# host calls. It cannot distinguish their callers. |
| DirtyTick | FlushAllUpdates iterates dirty files that still exist. DreamManager.Update calls it between ticks; the host lifecycle probe invokes the same method directly. The label identifies this dispatcher, not proof of elapsed ticks. |
| Close | Close flushes when the backing resource still exists. DecRef/Delete cleanup can call Close again; a closed handle still retains Resource in current source. Count actual calls, not unique handles. |
| EmbeddedSavefile | SerializeDreamValue first flushes an embedded savefile before reading its backing data. This is distinct from JsonSerializer.Serialize(_rootNode): nested value conversion can happen before the later outer Flush. |

The only Savefile changes outside instrumented Flush are these four internal origin arguments. Public Flush retains its signature and delegates to a private origin overload. Pure source normalization verifies every other byte-normalized Savefile body is unchanged, including catch/log/dirty clear and Close finally detachment. Clear still precedes Serialize, which precedes Output. Output encoding and resource cache behavior are unchanged.

## Explicit host capture

On the engine thread, call `Enable(cap)` once, then `BeginCapture("Gaia-SAVE", exactBackingResourcePath)` immediately before the actual authorized SAVE phase. Use the actual `Resource.ResourcePath` value, not a guessed canonical spelling. The optional filter compares ordinal exact strings and does not normalize paths, traverse directories or collect a path list. The name is capped at 64 UTF16 chars and the optional absolute path at 4096. One capture per fresh process.

Keep the window open across ticks until the actual SAVE operation completes and its intended dirty flushes have occurred, then call `EndCapture(Completed)` between Flush calls and explicitly export once to a fresh task-owned target. If SAVE fails, seal Aborted. Before orderly host shutdown, seal an active window Shutdown and export if authorized. There is no automatic shutdown hook or automatic export. An abrupt exit can lose the observation; an active snapshot reports incomplete coverage. The host must use its existing SAVE completion fence; this packet does not invent a Gaia completion callback or add a production DM API.

Initialization belongs to the measurement only if it occurs inside that window. Close belongs only if it happens before the window closes. An exact path filter excludes other resource paths, including temporary or unrelated saves. Unrelated operations using the same backing path during the window remain included. Call origins explain dispatch paths, not semantic SAVE ownership. Host scope and filter are the attribution boundary; if same-path concurrency cannot be excluded, do not label the metrics exclusive Gaia SAVE costs.

Six fixed phase arrays and five fixed origin rows remain bounded. Each origin reports seen, selected, sampled, completed and failed Flush calls; phases aggregate admitted samples across origins. Outside-capture, other-resource and post-cap calls remain functional and increment separate scalar coverage counters on the owner thread. Selected = sampled + capExcluded when summed across origin rows. Seen = outsideCapture + resourceExcluded + selected. Sampled = completed + failed after the last Flush finishes. Off-owner calls are functional but deliberately uncounted, and the snapshot says so; no unsynchronized cross-thread aggregation is claimed.

Snapshots identify capture active/closed/end reason, elapsed capture wall, max/remaining cap, first cap-excluded call time relative to capture start, and excluded counts through snapshot. `samplingCompleteForSelectedCalls` is true only for a completed capture with zero cap-excluded calls. Reaching the cap exactly is not evidence that additional calls were lost; `capExcluded` supplies that evidence. There are no retained trees, node/path collections or per-node instrumentation. Counts include failed attempts; failed partial disk bytes remain unknown. Process CPU and nested/total wall overlap caveats remain unchanged.

## Intentional dirty ERROR

Concrete host bug: the ordinary Robust test log handler can throw Assert.Fail on Error, interrupting the original FlushAllUpdates catch before its dirty-set Clear. The fixture now uses an explicit factual classifier, not a lowered error threshold. It prints the entire original message. During the synchronous expected probe only, it accepts exactly one Error from opendream.res whose text starts with the exact task-owned dirty path and System.Text.Json.JsonException and includes the real Flush stack. It rejects duplicates, Fatal, any other sawmill/path/type, and every unexpected Error. It then asserts exactly one matching log occurred. A change to source/error formatting fails visibly rather than suppressing evidence.

No pinned-compatible expected-error API was established. The classifier's ILogHandler.Log(string, Serilog.Events.LogEvent), RenderMessage and ServerIntegrationOptions.OverrideLogHandler are verified API pointers from the populated read-only Robust reference at different HEAD b1a45. Root must verify these signatures against pinned af2 before building. This is explicit pending compatibility, not a claim that the differing reference is the pinned runtime. Inherited fixture teardown remains the established disposal owner; the host restores cwd and deletes only its unique GUID temporary directory.

## Added meaningful checks

ScopeAndResourceFilterCoverage uses two legitimate initialized files and tests before-window, filtered-resource, one sampled, one post-cap and after-window calls. CappedFlushStopsCounters now compares phase counters while asserting coverage increments and Shutdown sealing, since whole snapshots correctly change after cap. EnabledCloseAndDirtyFailure asserts exact origin totals as well as total phases. Smoke and ModerateFlushWorkload explicitly start/end captures. Moderate mode uses its actual resource path filter.

Nine v3 generated controls cover clocks, availability, failures, completed bytes, CRLF, original Clear ordering, resource filter bypass, missing cap coverage and wrong dirty origin. The last three are discriminated by ScopeAndResourceFilterCoverage, CappedFlushStopsCounters and EnabledCloseAndDirtyFailure respectively. Source generation and hash/preservation checks passed; no C# compile or control/runtime/benchmark pass is claimed. Benchmark limits and same-workload original/disabled/enabled plans remain in smoke/INTEGRATION.md. Root owns all integration, native queue, exact-head CI and runtime acceptance.
