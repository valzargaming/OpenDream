#nullable enable
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

[TestFixture, NonParallelizable]
[Explicit("Separate fresh guarded full Gaia recovery process; root-owned VERIFY plan required")]
public sealed class GaiaSaveRecoveryHostTests : ContentIntegrationTest {
    private sealed record Plan(string JsonPath, string JsonSha256, string OwnedRoot, string OwnershipId,
        string WorldParamsPath, int MaximumTicks, string ReceiptSha256, string[] ShardSha256, long[] ShardBytes);
    private sealed class StrictLogs : ILogHandler {
        public void Log(string sawmillName, LogEvent message) {
            TestContext.Out.WriteLine($"GAIA_RECOVERY_ACTUAL_LOG [{message.Level}] {sawmillName}: {message.RenderMessage()}");
            if (message.Level >= LogEventLevel.Error) Assert.Fail("Unexpected actual recovery error: " + message.RenderMessage());
        }
    }
    private static string Full(string path) => Path.GetFullPath(path);
    private static string DiskSha(string path) {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
    [Test]
    public async Task FullGaiaFreshRecovery() {
        var planPath = Environment.GetEnvironmentVariable("OD_GAIA_RECOVERY_HOST_PLAN")
            ?? throw new InvalidOperationException("Explicit fresh recovery input plan required");
        var plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath))!;
        Assert.That(Guid.TryParseExact(plan.OwnershipId, "N", out _), Is.True);
        Assert.That(plan.MaximumTicks, Is.InRange(1, 12000));
        Assert.That(Path.IsPathFullyQualified(plan.OwnedRoot) && Path.IsPathFullyQualified(plan.JsonPath), Is.True);
        var owned = Full(plan.OwnedRoot);
        Assert.That(Path.GetDirectoryName(Full(plan.JsonPath)), Is.EqualTo(owned));
        Assert.That(File.ReadAllText(Path.Combine(owned, ".gaia-save-host-owner")).Trim(), Is.EqualTo(plan.OwnershipId));
        Assert.That(DiskSha(plan.JsonPath), Is.EqualTo(plan.JsonSha256));
        Assert.That(plan.ShardSha256.Length, Is.EqualTo(2));
        Assert.That(plan.ShardBytes.Length, Is.EqualTo(2));
        var shardPaths = new[] { Full(Path.Combine(owned, "map_saves", "1.sav")), Full(Path.Combine(owned, "map_saves", "2.sav")) };
        var receiptPath = Path.Combine(owned, "new_process_save_receipt.json");
        var resultPath = Path.Combine(owned, "new_process_VERIFY_result.txt");
        var failurePath = Path.Combine(owned, "new_process_probe_failure.txt");
        void AssertStoppedInputs() {
            Assert.That(DiskSha(receiptPath), Is.EqualTo(plan.ReceiptSha256));
            for (int i=0; i<2; i++) {
                Assert.That(new FileInfo(shardPaths[i]).Length, Is.EqualTo(plan.ShardBytes[i]));
                Assert.That(DiskSha(shardPaths[i]), Is.EqualTo(plan.ShardSha256[i]));
            }
        }
        Assert.That(File.Exists(resultPath) || File.Exists(failurePath), Is.False, "fresh VERIFY must not inherit result files");
        AssertStoppedInputs();
        var prior = Directory.GetCurrentDirectory();
        bool finished = false;
        Exception? completionFailure = null;
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
            TestContext.Out.WriteLine("GAIA_RECOVERY_SCALARS " + JsonSerializer.Serialize(new {
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
        try {
            var options = new ServerContentIntegrationOption { OverrideLogHandler = () => new StrictLogs() };
            options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = plan.JsonPath;
            options.CVarOverrides[OpenDreamCVars.WorldParams.Name] = File.ReadAllText(plan.WorldParamsPath); // private VERIFY bindings never logged
            options.CVarOverrides[OpenDreamCVars.TopicPort.Name] = "0"; // actual runtime binds loopback ephemeral port
            var server = StartServer(options);
            await server.WaitIdleAsync();
            bool ready = false;
            for (int tick=0; tick<plan.MaximumTicks && !ready; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    var manager = server.ResolveDependency<DreamManager>();
                    Assert.That(manager.LastDMException, Is.Null);
                    int index = manager.GlobalNames.IndexOf("new_process_dispatch_init_complete");
                    Assert.That(index, Is.GreaterThanOrEqualTo(0));
                    ready = manager.Globals[index].MustGetValueAsFloat() == 1;
                });
            }
            Assert.That(ready, Is.True, "actual numeric setup marker must complete naturally");
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                scalarRefs = server.ResolveDependency<DreamRefManager>();
                scalarTree = server.ResolveDependency<DreamObjectTree>();
                AssertStoppedInputs();
                Assert.That(manager.LastDMException, Is.Null);
                Observe("before");
                int index = manager.GlobalNames.IndexOf("new_process_save_probe");
                Assert.That(index, Is.GreaterThanOrEqualTo(0));
                // MustGetValueAsDreamObject borrows the existing global object; no Dispose/IncRef.
                var probe = manager.Globals[index].MustGetValueAsDreamObject();
                Assert.That(probe, Is.Not.Null);
                Assert.That(probe!.TryGetProc("run_probe", out var proc), Is.True);
                using var scheduled = DreamThread.Run("Full Gaia fresh VERIFY", async state => {
                    try {
                        using var completed = await state.Call(proc!, probe, null);
                        Assert.That(completed.IsNull, Is.True, "actual run_probe has no explicit return value");
                        Assert.That(manager.LastDMException, Is.Null);
                        Assert.That(File.Exists(failurePath), Is.False);
                        Assert.That(File.ReadAllText(resultPath), Is.EqualTo("PASS: VERIFY explicit production persistence probe"));
                        Assert.That(!manager.IsShutDown && !manager.WorldInstance.Deleted, Is.True);
                        Observe("logical-completion");
                    } catch (Exception error) { completionFailure = error; }
                    finally { finished = true; }
                    return DreamValue.Null;
                });
            });
            for (int tick=0; tick<plan.MaximumTicks && !finished; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    Assert.That(server.ResolveDependency<DreamManager>().LastDMException, Is.Null);
                    if (tick % 32 == 0) Observe("progress-"+tick);
                });
            }
            Assert.That(finished, Is.True, "actual awaited VERIFY must finish within bounded ticks");
            if (completionFailure != null) ExceptionDispatchInfo.Capture(completionFailure).Throw();
            int stable=0;
            for (int tick=0; tick<plan.MaximumTicks && stable<2; tick++) {
                await server.WaitRunTicks(1);
                await server.WaitAssertion(() => {
                    Assert.That(server.ResolveDependency<DreamManager>().LastDMException, Is.Null);
                    var observed=Observe("drain-"+tick, sample: tick%32==0);
                    stable=observed.Open==0 && observed.Dirty==0 ? stable+1 : 0;
                });
            }
            Assert.That(stable, Is.EqualTo(2));
            await server.WaitRunTicks(2);
            await server.WaitAssertion(() => {
                var manager=server.ResolveDependency<DreamManager>();
                Assert.That(manager.LastDMException, Is.Null);
                Assert.That(!manager.IsShutDown && !manager.WorldInstance.Deleted, Is.True);
                var observed=Observe("after");
                Assert.That(observed.Open==0 && observed.Dirty==0, Is.True);
                Assert.That(File.Exists(failurePath), Is.False);
                Assert.That(File.ReadAllText(resultPath), Is.EqualTo("PASS: VERIFY explicit production persistence probe"));
                AssertStoppedInputs();
                for (int i=0; i<2; i++) TestContext.Out.WriteLine("GAIA_RECOVERY_SHARD " + JsonSerializer.Serialize(new {
                    shard=Path.GetFileName(shardPaths[i]), bytes=new FileInfo(shardPaths[i]).Length, sha256=DiskSha(shardPaths[i])
                }));
                TestContext.Out.WriteLine("GAIA_RECOVERY_COMPLETE " + JsonSerializer.Serialize(new {
                    receiptSha256=DiskSha(receiptPath), ownedOpen=observed.Open, ownedDirty=observed.Dirty,
                    actualAwaitedProbe=true, originalVerifyResult=true, freshProcessGuardRequired=true, stoppedAuditRequired=true
                }));
            });
        } finally { Directory.SetCurrentDirectory(prior); } // framework teardown; root owns process/tree cleanup
    }
}
