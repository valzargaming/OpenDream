#nullable enable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using NUnit.Framework;
using Robust.Shared.Log;
using Serilog.Events;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Procs;
using OpenDreamShared;
#if SAVECOST_PROFILE
using OpenDreamRuntime.Resources;
using SaveCostDetachedSmoke;
#endif

namespace Content.IntegrationTests;

[TestFixture]
[NonParallelizable]
[Explicit("Select one named method in a fresh process: BYOND initialization and profiling are process-global")]
public sealed class SaveCostProfileHostTests : ContentIntegrationTest {
    private readonly FactualLogClassifier _logs = new();
#if SAVECOST_PROFILE
    [Test]
    public Task ActualFlushCountsBytesAndClocks() => WithHost((tree, directory) => {
        var file = InitializeFile(tree, Path.Combine(directory, "success.json"));
        try {
            Smoke.Run(file, directory);
            TestContext.Out.WriteLine("SAVE_COST_SMOKE " + File.ReadAllText(Path.Combine(directory, "profile-final.json")));
        } finally { file.CurrentDir.Remove("cycle"); file.DecRef(); }
    });

    [Test]
    public Task CappedFlushStopsCounters() => WithHost((tree, directory) => {
        var file = InitializeFile(tree, Path.Combine(directory, "cap.json"));
        try {
            file.SetSavefileValue("payload", new DreamValue("cap"));
            SaveCostProfile.Enable(1);
            SaveCostProfile.BeginCapture("cap", file.Resource!.ResourcePath);
            file.Flush();
            var first = SnapshotText();
            file.Flush();
            file.Close();
            SaveCostProfile.EndCapture(SaveCostProfile.CaptureEnd.Shutdown);
            using var before = JsonDocument.Parse(first);
            using var after = JsonDocument.Parse(SnapshotText());
            Assert.That(after.RootElement.GetProperty("phases").GetRawText(), Is.EqualTo(before.RootElement.GetProperty("phases").GetRawText()));
            Assert.That(after.RootElement.GetProperty("capExcluded").GetInt64(), Is.EqualTo(2));
            Assert.That(after.RootElement.GetProperty("captureEnd").GetString(), Is.EqualTo("Shutdown"));
            Assert.That(File.ReadAllText(file.Resource!.ResourcePath!), Does.Contain("cap"));
            Assert.That(DreamObjectSavefile.Savefiles.Contains(file), Is.False);
            Assert.That(Dirty().Contains(file), Is.False);
        } finally { file.DecRef(); }
    });

    [Test]
    public Task EnabledCloseAndDirtyFailure() => WithHost((tree, directory) => {
        SaveCostProfile.Enable(64);
        SaveCostProfile.BeginCapture("lifecycle");
        LifecycleFailures(tree, directory);
        SaveCostProfile.EndCapture();
        using var snapshot = JsonDocument.Parse(SnapshotText());
        var total = snapshot.RootElement.GetProperty("phases")[0];
        Assert.That(total.GetProperty("attempted").GetInt64(), Is.EqualTo(5));
        Assert.That(total.GetProperty("completed").GetInt64(), Is.EqualTo(3));
        Assert.That(total.GetProperty("failed").GetInt64(), Is.EqualTo(2));
        AssertOrigin(snapshot.RootElement, "Initialize", 1, 1, 0);
        AssertOrigin(snapshot.RootElement, "DirtyTick", 1, 0, 1);
        AssertOrigin(snapshot.RootElement, "Direct", 1, 1, 0);
        AssertOrigin(snapshot.RootElement, "Close", 2, 1, 1);
        TestContext.Out.WriteLine("SAVE_COST_LIFECYCLE " + SnapshotText());
    });

    private static string SnapshotText() => JsonSerializer.Serialize(SaveCostProfile.Snapshot());
    private static void AssertOrigin(JsonElement snapshot, string name, long sampled, long completed, long failed) {
        var origin = snapshot.GetProperty("origins").EnumerateArray().Single(row => row.GetProperty("name").GetString() == name);
        Assert.That(origin.GetProperty("sampled").GetInt64(), Is.EqualTo(sampled));
        Assert.That(origin.GetProperty("completed").GetInt64(), Is.EqualTo(completed));
        Assert.That(origin.GetProperty("failed").GetInt64(), Is.EqualTo(failed));
    }

    [Test]
    public Task ScopeAndResourceFilterCoverage() => WithHost((tree, directory) => {
        var selected = InitializeFile(tree, Path.Combine(directory, "selected.json"));
        var other = InitializeFile(tree, Path.Combine(directory, "other.json"));
        try {
            SaveCostProfile.Enable(1);
            selected.Flush(); // outside capture, still actual functional save
            SaveCostProfile.BeginCapture("resource-filter", selected.Resource!.ResourcePath);
            other.Flush(); // filtered resource
            selected.Flush();
            selected.Flush(); // cap excluded
            SaveCostProfile.EndCapture();
            selected.Flush(); // after closure
            using var snapshot = JsonDocument.Parse(SnapshotText());
            var root = snapshot.RootElement;
            Assert.That(root.GetProperty("outsideCapture").GetInt64(), Is.EqualTo(2));
            Assert.That(root.GetProperty("resourceExcluded").GetInt64(), Is.EqualTo(1));
            Assert.That(root.GetProperty("capExcluded").GetInt64(), Is.EqualTo(1));
            Assert.That(root.GetProperty("captureActive").GetBoolean(), Is.False);
            AssertOrigin(root, "Direct", 1, 1, 0);
            var direct = root.GetProperty("origins")[1];
            Assert.That(direct.GetProperty("seen").GetInt64(), Is.EqualTo(5));
            Assert.That(direct.GetProperty("selected").GetInt64(), Is.EqualTo(2));
            Assert.That(File.ReadAllText(other.Resource!.ResourcePath!), Is.Not.Empty);
            TestContext.Out.WriteLine("SAVE_COST_COVERAGE " + SnapshotText());
        } finally { selected.DecRef(); other.DecRef(); }
    });
#endif

    [Test]
    public Task DisabledFlushAndLifecycle() => WithHost((tree, directory) => {
#if SAVECOST_PROFILE
        Assert.That(SaveCostProfile.Enabled, Is.False);
#endif
        LifecycleFailures(tree, directory);
#if SAVECOST_PROFILE
        var attempts = (long[])typeof(SaveCostProfile).GetField("Attempts", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
        Assert.That(attempts.All(value => value == 0), Is.True, "disabled paths record no phases");
        Assert.That(SaveCostProfile.Enabled, Is.False);
#endif
        TestContext.Out.WriteLine("SAVE_COST_DISABLED_LIFECYCLE_COMPLETE");
    });

    [Test]
    public Task ModerateFlushWorkload() => WithHost((tree, directory) => {
        const int entries = 1024, warmup = 4, repetitions = 16;
        var mode = Environment.GetEnvironmentVariable("OD_SAVE_COST_MODE") ?? "disabled";
#if SAVECOST_PROFILE
        Assert.That(mode, Is.EqualTo("disabled").Or.EqualTo("enabled"));
#else
        Assert.That(mode, Is.EqualTo("original"), "original build selects original mode explicitly");
#endif
        var file = InitializeFile(tree, Path.Combine(directory, "workload.json"));
        try {
            for (int i = 0; i < entries; i++)
                file.SetSavefileValue("entry" + i.ToString("D4"), new DreamValue(new string('x', 128) + "é😀"));
            string expected = JsonSerializer.Serialize(file.CurrentDir) + "\r\n";
            for (int i = 0; i < warmup; i++) file.Flush();
#if SAVECOST_PROFILE
            if (mode == "enabled") {
                SaveCostProfile.Enable(repetitions);
                SaveCostProfile.BeginCapture("moderate-real-flush", file.Resource!.ResourcePath);
            }
#endif
            using var process = Process.GetCurrentProcess();
            var allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
            var allAllocatedBefore = GC.GetTotalAllocatedBytes(precise: true);
            var cpuBefore = process.TotalProcessorTime;
            var begin = Stopwatch.GetTimestamp();
            var durations = new double[repetitions];
            for (int i = 0; i < repetitions; i++) {
                var slice = Stopwatch.GetTimestamp();
                file.Flush();
                durations[i] = (Stopwatch.GetTimestamp() - slice) / (double)Stopwatch.Frequency;
            }
            var elapsed = (Stopwatch.GetTimestamp() - begin) / (double)Stopwatch.Frequency;
            var cpu = (process.TotalProcessorTime - cpuBefore).TotalSeconds;
            var allocated = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
            var allAllocated = GC.GetTotalAllocatedBytes(precise: true) - allAllocatedBefore;
#if SAVECOST_PROFILE
            if (mode == "enabled") SaveCostProfile.EndCapture();
#endif
            Assert.That(File.ReadAllText(file.Resource!.ResourcePath!), Is.EqualTo(expected));
            var bytes = new FileInfo(file.Resource.ResourcePath!).Length;
            Assert.That(bytes, Is.EqualTo(Encoding.UTF8.GetByteCount(expected)));
            Array.Sort(durations);
            TestContext.Out.WriteLine("SAVE_COST_WORKLOAD " + JsonSerializer.Serialize(new {
                mode, entries, warmup, repetitions, bytes, wallSeconds = elapsed, processCpuSeconds = cpu,
                engineThreadAllocatedBytes = allocated, processAllocatedBytes = allAllocated,
                medianFlushSeconds = durations[repetitions / 2], maximumFlushSeconds = durations[^1],
                cpuIncludesBackgroundWork = true, allocationIncludesObserver = true
            }));
#if SAVECOST_PROFILE
            if (mode == "enabled") TestContext.Out.WriteLine("SAVE_COST_PHASES " + SnapshotText());
#endif
        } finally { file.DecRef(); }
    });

#if SAVECOST_PROFILE
    [Test]
    public Task EmptyClockCalibration() => WithHost((_, _) => {
        TestContext.Out.WriteLine("SAVE_COST_CLOCK_CALIBRATION " + JsonSerializer.Serialize(SaveCostProfile.Calibrate(1000)));
    });
#endif

    private static DreamObjectSavefile InitializeFile(DreamObjectTree tree, string path) {
        var file = new DreamObjectSavefile(tree.Savefile.ObjectDefinition);
        try {
            using var args = new DreamProcArguments(new DreamValue(path));
            file.Initialize(args);
            return file;
        } catch { file.DecRef(); throw; }
    }
    private static HashSet<DreamObjectSavefile> Dirty() =>
        (HashSet<DreamObjectSavefile>)typeof(DreamObjectSavefile).GetField("SavefilesToFlush", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
    private static Dictionary<string, DreamObjectSavefile.SfDreamJsonValue> Directories() =>
        (Dictionary<string, DreamObjectSavefile.SfDreamJsonValue>)typeof(DreamObjectSavefile).GetField("SavefileDirectories", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;

    private void LifecycleFailures(DreamObjectTree tree, string directory) {
        var openBefore = DreamObjectSavefile.Savefiles.Count;
        var dirtyBefore = Dirty().Count;
        Assert.That(dirtyBefore, Is.Zero, "isolated host starts with no foreign dirty savefiles");
        var path = Path.Combine(directory, "dirty.json");
        var file = InitializeFile(tree, path);
        try {
            file.SetSavefileValue("payload", new DreamValue("dirty"));
            Assert.That(Dirty().Contains(file), Is.True);
            file.CurrentDir["cycle"] = file.CurrentDir;
            _logs.ExpectDirtyJsonFailure(path);
            try { Assert.DoesNotThrow(() => DreamObjectSavefile.FlushAllUpdates()); }
            finally { _logs.FinishExpectedDirtyFailure(); }
            Assert.That(Dirty().Contains(file), Is.False);
            Assert.That(new FileInfo(path).Length, Is.Zero, "original Clear-before-Serialize failure");
            file.CurrentDir.Remove("cycle");
            file.Flush();
            Assert.That(File.ReadAllText(path), Does.Contain("dirty"));
            file.SetSavefileValue("close", new DreamValue("pending"));
            file.CurrentDir["cycle"] = file.CurrentDir;
            Assert.Throws<JsonException>(() => file.Close());
            Assert.That(DreamObjectSavefile.Savefiles.Contains(file), Is.False, "failed Close detaches open registry");
            Assert.That(Dirty().Contains(file), Is.False, "failed Close detaches dirty registry");
            Assert.That(Directories().ContainsKey(path), Is.False, "failed Close detaches last shared directory owner");
        } finally { file.CurrentDir.Remove("cycle"); file.DecRef(); }
        Assert.That(DreamObjectSavefile.Savefiles.Count, Is.EqualTo(openBefore));
        Assert.That(Dirty().Count, Is.EqualTo(dirtyBefore));
    }

    private async Task WithHost(Action<DreamObjectTree, string> body) {
        var originalDirectory = Directory.GetCurrentDirectory();
        var temporary = Path.Combine(Path.GetTempPath(), "opendream-save-cost-host-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try {
            var fixture = Path.Combine(temporary, "fixture.dm");
            File.WriteAllText(fixture, "/proc/save_cost_host_probe()\n    return 1\n");
            var compiler = new DMCompiler.DMCompiler();
            var compiled = compiler.Compile(new() { Files = [fixture], StoreMessages = true });
            var json = Path.ChangeExtension(fixture, "json");
            Assert.That(compiled && File.Exists(json), Is.True,
                "Isolated host compilation failed: " + string.Join("\n", compiler.CompilerMessages));
            var options = new ServerContentIntegrationOption();
            options.OverrideLogHandler = () => _logs;
            options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = json;
            var server = StartServer(options);
            // Existing inherited RobustIntegrationTest teardown owns server disposal.
            await server.WaitIdleAsync();
            await server.WaitRunTicks(1);
            Assert.That(server.IsAlive, Is.True);
            var data = Path.Combine(temporary, "data");
            Directory.CreateDirectory(data);
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                var tree = server.ResolveDependency<DreamObjectTree>();
                Assert.That(manager.LastDMException, Is.Null, "isolated host boot");
                body(tree, data);
                Assert.That(manager.LastDMException, Is.Null, "direct host probes create no DM runtimes");
            });
        } finally {
            Directory.SetCurrentDirectory(originalDirectory);
            // Only this literal GUID task-owned absolute directory is removed.
            Directory.Delete(temporary, recursive: true);
        }
    }

    // Explicit source-factual classifier, not blanket ERROR suppression. Emits the
    // original complete log and rejects every unexpected error, including duplicates.
    // API pointers verified in local Robust reference; root must confirm pinned signatures.
    private sealed class FactualLogClassifier : ILogHandler {
        private string? _expectedPath;
        private int _expectedCount;
        public void ExpectDirtyJsonFailure(string path) {
            Assert.That(_expectedPath, Is.Null);
            _expectedPath = path;
            _expectedCount = 0;
        }
        public void FinishExpectedDirtyFailure() {
            _expectedPath = null;
            Assert.That(_expectedCount, Is.EqualTo(1), "exactly one actual dirty JsonException ERROR must remain visible");
        }
        public void Log(string sawmillName, LogEvent message) {
            string rendered = message.RenderMessage();
            TestContext.Out.WriteLine($"SAVE_COST_ACTUAL_LOG [{message.Level}] {sawmillName}: {rendered}");
            if (message.Level < LogEventLevel.Error) return;
            bool expected = message.Level == LogEventLevel.Error && sawmillName == "opendream.res" &&
                _expectedPath != null && _expectedCount == 0 &&
                rendered.StartsWith("Error flushing savefile " + _expectedPath + ": System.Text.Json.JsonException:", StringComparison.Ordinal) &&
                rendered.Contains("System.Text.Json", StringComparison.Ordinal) &&
                rendered.Contains("DreamObjectSavefile.Flush", StringComparison.Ordinal);
            if (!expected) Assert.Fail("Unexpected actual runtime error: " + rendered);
            _expectedCount++;
            TestContext.Out.WriteLine("SAVE_COST_EXPECTED_DIRTY_JSON_ERROR_CLASSIFIED " + _expectedPath);
        }
    }
}
