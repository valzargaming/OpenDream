#nullable enable
#if SAVECOST_PROFILE
using System;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Procs;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Resources;
using OpenDreamShared;
using Robust.Shared.Log;
using Serilog.Events;

namespace Content.IntegrationTests;

// Host-only candidate. Compile and native controls are required before acceptance.
[TestFixture, NonParallelizable]
[Explicit("One fresh guarded process; root-owned isolated full Gaia input plan required")]
public sealed class GaiaSaveCostHostTests : ContentIntegrationTest {
    private sealed record Plan(string JsonPath, string JsonSha256, string SaveEntryPoint,
        string OwnedRoot, string OwnershipId, int MaximumTicks, int MaximumFlushes, string WorldParamsPath, string ReadinessGlobal);
    private sealed class StrictLogs : ILogHandler {
        public void Log(string sawmillName, LogEvent message) {
            TestContext.Out.WriteLine($"GAIA_SAVE_ACTUAL_LOG [{message.Level}] {sawmillName}: {message.RenderMessage()}");
            if (message.Level >= LogEventLevel.Error)
                Assert.Fail("Unexpected actual host error: " + message.RenderMessage());
        }
    }
    private static string Full(string path) => Path.GetFullPath(path);
    private static string? DiskSha(string path) {
        if (!File.Exists(path)) return null;
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    [Test]
    public async Task FullGaiaSaveWindow() {
        var planPath = Environment.GetEnvironmentVariable("OD_GAIA_SAVE_HOST_PLAN")
            ?? throw new InvalidOperationException("Explicit root-reviewed safe host plan required");
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath))!;
        Assert.That(plan.MaximumTicks, Is.InRange(1, 600));
        Assert.That(plan.MaximumFlushes, Is.InRange(2, 4096));
        Assert.That(Guid.TryParseExact(plan.OwnershipId, "N", out _), Is.True);
        Assert.That(Path.IsPathFullyQualified(plan.OwnedRoot), Is.True);
        Assert.That(Path.IsPathFullyQualified(plan.JsonPath), Is.True);
        var owned = Full(plan.OwnedRoot);
        var json = Full(plan.JsonPath);
        Assert.That(Path.GetDirectoryName(json), Is.EqualTo(owned), "resource root must be the task-owned tree");
        Assert.That(File.ReadAllText(Path.Combine(owned, ".gaia-save-host-owner")).Trim(), Is.EqualTo(plan.OwnershipId));
        Assert.That(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(json))).ToLowerInvariant(), Is.EqualTo(plan.JsonSha256));
        // Restrict invocation to an explicitly reviewed diagnostic global wrapper.
        Assert.That(plan.SaveEntryPoint, Is.EqualTo("gaia_host_run_save_probe"));
        var shardPaths = new[] { Full(Path.Combine(owned, "map_saves", "1.sav")), Full(Path.Combine(owned, "map_saves", "2.sav")) };
        Assert.That(plan.ReadinessGlobal, Is.EqualTo("new_process_dispatch_init_complete"));
        var priorDirectory = Directory.GetCurrentDirectory();
        var options = new ServerContentIntegrationOption { OverrideLogHandler = () => new StrictLogs() };
        options.CVarOverrides[OpenDreamCVars.TopicPort.Name] = (ushort)0;
        options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = json;
        options.CVarOverrides[OpenDreamCVars.WorldParams.Name] = File.ReadAllText(plan.WorldParamsPath); // never log private parameters
        bool finished = false;
        Exception? completionFailure = null;
        string?[] beforeSha = shardPaths.Select(DiskSha).ToArray();
        bool captureStarted = false, sealedCapture = false, successfulHost = false;
        Func<Task>? preservePartial = null;
        DreamRefManager? scalarRefs = null;
        DreamObjectTree? scalarTree = null;
        (int Open, int Dirty) Observe(string label, bool sample = true) {
            bool Owned(DreamObjectSavefile file) => file.Resource?.ResourcePath is string path && shardPaths.Contains(Full(path));
            var dirty = (HashSet<DreamObjectSavefile>)typeof(DreamObjectSavefile)
                .GetField("SavefilesToFlush", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
            // Enumeration borrows handles only in this synchronous callback; no IncRef/cache.
            int openCount = DreamObjectSavefile.Savefiles.Count(Owned), dirtyCount = dirty.Count(Owned);
            if (sample) {
            // Count only: do not enumerate directory values or acquire DreamObject refs.
            var directoryCount = ((System.Collections.IDictionary)typeof(DreamObjectSavefile)
                .GetField("SavefileDirectories", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!).Count;
            using var process = Process.GetCurrentProcess();
            var gc = GC.GetGCMemoryInfo();
            TestContext.Out.WriteLine("GAIA_SAVE_SCALARS " + JsonSerializer.Serialize(new {
                label, engineThread = Environment.CurrentManagedThreadId, openOwnedShards = openCount, dirtyOwnedShards = dirtyCount,
                totalOpenSavefiles = DreamObjectSavefile.Savefiles.Count, totalDirtySavefiles = dirty.Count,
                totalSavefileDirectories = directoryCount,
                aliveDatums = scalarRefs!.GetCountOf(RefType.DreamObjectDatum),
                aliveLists = scalarRefs.GetCountOf(RefType.DreamObjectList),
                aliveAssocLists = scalarRefs.GetCountOf(RefType.DreamObjectAssocList),
                aliveSpecialLists = scalarRefs.GetCountOf(RefType.DreamObjectSpecialList),
                aliveArgsLists = scalarRefs.GetCountOf(RefType.DreamObjectListArgs),
                aliveSavefiles = scalarRefs.GetCountOf(RefType.DreamObjectSavefile),
                aliveMovables = scalarRefs.GetCountOf(RefType.DreamObjectMovable),
                aliveMobs = scalarRefs.GetCountOf(RefType.DreamObjectMob),
                aliveTurfs = scalarRefs.GetCountOf(RefType.DreamObjectTurf),
                aliveAreas = scalarRefs.GetCountOf(RefType.DreamObjectArea),
                pooledDmProcStates = DMProcState.Pool.Count,
                pooledNullProcStates = NullProcState.Pool.Count,
                pooledAsyncProcStates = AsyncNativeProc.AsyncNativeProcState.Pool.Count,
                internedStrings = scalarTree!.Strings.Count,
                process.PrivateMemorySize64, process.WorkingSet64, managedBytes = GC.GetTotalMemory(false),
                lastGcHeapBytes = gc.HeapSizeBytes, lastGcFragmentedBytes = gc.FragmentedBytes,
                engineAllocatedBytes = GC.GetAllocatedBytesForCurrentThread(), processAllocatedBytes = GC.GetTotalAllocatedBytes(false),
                gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2)
            }));
            }
            return (openCount, dirtyCount);
        }
        string WrapperState(DreamManager manager) {
            int index = manager.GlobalNames.IndexOf("gaia_host_save_state");
            Assert.That(index, Is.GreaterThanOrEqualTo(0));
            return manager.Globals[index].MustGetValueAsString(); // borrowed global, no owner acquired
        }
        try {
            var server = StartServer(options);
            preservePartial = async () => {
                if (!captureStarted || successfulHost || !server.IsAlive) return;
                try { await server.WaitAssertion(() => {
                    Observe("partial-failure");
                    TestContext.Out.WriteLine("GAIA_SAVE_PARTIAL " + JsonSerializer.Serialize(SaveCostProfile.Snapshot()));
                }); } catch (Exception error) { TestContext.Out.WriteLine("GAIA_SAVE_PARTIAL_UNAVAILABLE " + error.GetType().Name); }
            };
            await server.WaitIdleAsync();
            bool ready = false;
            for (int tick = 0; tick < plan.MaximumTicks && !ready; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    var manager = server.ResolveDependency<DreamManager>();
                    Assert.That(manager.LastDMException, Is.Null);
                    int index = manager.GlobalNames.IndexOf(plan.ReadinessGlobal);
                    Assert.That(index, Is.GreaterThanOrEqualTo(0), "reviewed actual final setup marker must exist in compiled input");
                    ready = manager.Globals[index].MustGetValueAsFloat() == 1;
                });
            }
            Assert.That(ready, Is.True, "actual final setup completion within bounded natural ticks");
            await server.WaitRunTicks(1);
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                Assert.That(manager.Initialized && !manager.IsShutDown && !manager.WorldInstance.Deleted, Is.True);
                Assert.That(manager.LastDMException, Is.Null);
                Assert.That(manager.TryGetGlobalProc(plan.SaveEntryPoint, out var proc), Is.True);
                // Resolve the same server IoC services on the engine thread once.
                // DreamManager exposes no public RefManager/ObjectTree properties.
                scalarRefs = server.ResolveDependency<DreamRefManager>();
                scalarTree = server.ResolveDependency<DreamObjectTree>();
                Assert.That(WrapperState(manager), Is.EqualTo("idle"));
                Observe("before");
                SaveCostProfile.Enable(plan.MaximumFlushes);
                SaveCostProfile.BeginCapture("full-gaia-save", exactResourcePath: null);
                captureStarted = true;
                using var result = DreamThread.Run("Gaia SAVE host window", async state => {
                    try {
                        using var saved = await state.Call(proc!, manager.WorldInstance, null);
                        Assert.That(saved.MustGetValueAsFloat(), Is.EqualTo(1), "reviewed wrapper must await SAVE and return completion 1");
                        Assert.That(manager.LastDMException, Is.Null);
                        Assert.That(WrapperState(manager), Is.EqualTo("returned"));
                        Observe("logical-completion");
                        Assert.That(!manager.IsShutDown && !manager.WorldInstance.Deleted, Is.True);

                    } catch (Exception error) { completionFailure = error; }
                    finally { finished = true; }
                    return DreamValue.Null;
                });
            });
            for (var tick = 0; tick < plan.MaximumTicks && !finished; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    Assert.That(server.ResolveDependency<DreamManager>().LastDMException, Is.Null);
                    if (tick % 32 == 0) {
                        Observe("progress-" + tick);
                        TestContext.Out.WriteLine("GAIA_SAVE_PARTIAL " + JsonSerializer.Serialize(SaveCostProfile.Snapshot()));
                    }
                });
            }
            // Require two naturally separated owned-handle quiescent observations.
            int stable = 0;
            for (int tick = 0; tick < plan.MaximumTicks && stable < 2; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    var observed = Observe("drain-" + tick, sample: tick % 32 == 0);
                    stable = observed.Open == 0 && observed.Dirty == 0 ? stable + 1 : 0;
                });
            }
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                Assert.That(finished, Is.True, "SAVE must finish within bounded engine ticks");
                if (completionFailure != null) ExceptionDispatchInfo.Capture(completionFailure).Throw();
                Assert.That(manager.LastDMException, Is.Null);
                Assert.That(!manager.IsShutDown && !manager.WorldInstance.Deleted, Is.True);
                Assert.That(stable, Is.EqualTo(2), "owned shard handles must naturally close and stop dirtying before seal");
                Assert.That(WrapperState(manager), Is.EqualTo("returned"));
                Observe("after-before-seal");
                SaveCostProfile.EndCapture();
                sealedCapture = true;
                using var coverage = JsonDocument.Parse(JsonSerializer.Serialize(SaveCostProfile.Snapshot()));
                var snapshot = coverage.RootElement;
                Assert.That(snapshot.GetProperty("capExcluded").GetInt64(), Is.Zero);
                Assert.That(snapshot.GetProperty("samplingCompleteForSelectedCalls").GetBoolean(), Is.True);
                // Aggregated lifecycle coverage cannot independently identify shard paths.
                var lifecycleCompleted = snapshot.GetProperty("origins").EnumerateArray()
                    .Where(row => row.GetProperty("name").GetString() is "DirtyTick" or "Close")
                    .Sum(row => row.GetProperty("completed").GetInt64());
                Assert.That(lifecycleCompleted, Is.GreaterThanOrEqualTo(2));
                Assert.That(snapshot.GetProperty("origins").EnumerateArray().All(row => row.GetProperty("failed").GetInt64() == 0), Is.True);
                // Observe disk only AFTER sealing. Stream SHA rather than building a
                // full-game serializer/root/string copy inside the measured window.
                for (int i = 0; i < shardPaths.Length; i++) {
                    Assert.That(File.Exists(shardPaths[i]), Is.True);
                    var length = new FileInfo(shardPaths[i]).Length;
                    Assert.That(length, Is.GreaterThan(0));
                    var hash = DiskSha(shardPaths[i]);
                    TestContext.Out.WriteLine("GAIA_SAVE_SHARD " + JsonSerializer.Serialize(new {
                        shard = Path.GetFileName(shardPaths[i]), bytes = length, sha256 = hash,
                        beforeSha256 = beforeSha[i], changed = beforeSha[i] != hash,
                        generationAndFormatChecked = false, freshRecoveryRequired = true
                    }));
                }
                SaveCostProfile.ExportOnce(Path.Combine(owned, "gaia-save-profile.json"));
                TestContext.Out.WriteLine("GAIA_SAVE_PROFILE " + JsonSerializer.Serialize(SaveCostProfile.Snapshot()));
            });
            var sealedHashes = shardPaths.Select(DiskSha).ToArray();
            await server.WaitRunTicks(2);
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                Assert.That(manager.LastDMException, Is.Null);
                Assert.That(WrapperState(manager), Is.EqualTo("returned"));
                var observed = Observe("stopped-audit");
                Assert.That(observed.Open == 0 && observed.Dirty == 0, Is.True);
                Assert.That(shardPaths.Select(DiskSha).ToArray(), Is.EqualTo(sealedHashes), "late owned shard writes invalidate capture");
                TestContext.Out.WriteLine("GAIA_SAVE_STOPPED_AUDIT " + JsonSerializer.Serialize(new {
                    postSealNaturalTicks = 2, openOwned = observed.Open, dirtyOwned = observed.Dirty,
                    hashesStable = true, frameworkTeardownExcluded = true, finalProcessStoppedAuditRequired = true
                }));
            });
            successfulHost = true;
        } finally {
            if (preservePartial != null) await preservePartial();
            // Test framework owns server teardown. Root guard owns process kill and
            // retained task tree cleanup AFTER all owned process exits. No del(world).
            Directory.SetCurrentDirectory(priorDirectory);
            TestContext.Out.WriteLine($"GAIA_SAVE_HOST_END captureStarted={captureStarted} sealed={sealedCapture}");
        }
    }
}
#endif
