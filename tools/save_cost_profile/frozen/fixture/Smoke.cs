using System;
using System.Linq;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Resources;

namespace SaveCostDetachedSmoke;

// Host supplies an initialized isolated savefile at NEW task-directory/success.json.
// Compile into the root-owned runtime harness, not as a game source change.
public static class Smoke {
    public static void Run(DreamObjectSavefile savefile, string emptyUniqueDirectory) {
        if (!Path.IsPathFullyQualified(emptyUniqueDirectory) || !Directory.Exists(emptyUniqueDirectory) ||
            Directory.EnumerateFileSystemEntries(emptyUniqueDirectory).Any(path => Path.GetFileName(path) != "success.json"))
            throw new InvalidOperationException("Require a fresh empty absolute task directory");
        savefile.CurrentPath = "/";
        var root = savefile.CurrentDir;
        root.Clear();
        root["unicode"] = new DreamObjectSavefile.SfDreamPrimitive { Value = new OpenDreamRuntime.DreamValue("plain é 😀") };
        var json = JsonSerializer.Serialize(root);
        var output = Path.Combine(emptyUniqueDirectory, "success.json");
        Require(savefile.Resource?.ResourcePath == output, "host initializes savefile at task success.json before enabling");
        var originalResource = savefile.Resource;
        try {
        savefile.Resource = new DreamResource(0, output, output);
        SaveCostProfile.Enable(4);
        SaveCostProfile.BeginCapture("actual-flush-negative-controls");
        var outerWall = Stopwatch.GetTimestamp();
        savefile.Flush(); // real Clear/Serialize/RemoveFormatting/AppendAllText path
        Require(File.ReadAllText(output) == json + "\r\n", "output parity");
        var expectedBytes = Encoding.UTF8.GetByteCount(json + "\r\n");
        Require(new FileInfo(output).Length == expectedBytes, "UTF8 byte count/BOM parity");

        var directoryTarget = Path.Combine(emptyUniqueDirectory, "directory-target");
        Directory.CreateDirectory(directoryTarget);
        savefile.Resource = new DreamResource(1, directoryTarget, output);
        ExpectFailure(() => savefile.Flush()); // Clear fails before serializer/formatter/append.

        savefile.Resource = new DreamResource(2, output, output);
        root["cycle"] = root;
        try {
            ExpectFailure(() => savefile.Flush()); // real serializer depth/cycle failure AFTER Clear.
            Require(new FileInfo(output).Length == 0, "original Clear-before-Serialize behavior");
        } finally { root.Remove("cycle"); }

        savefile.Resource = new DreamResource(3, output, directoryTarget);
        ExpectFailure(() => savefile.Flush()); // Clear and JSON succeed; actual append to directory fails.
        var elapsed = (Stopwatch.GetTimestamp() - outerWall) / (double)Stopwatch.Frequency;
        SaveCostProfile.EndCapture();
        using var snapshot = JsonDocument.Parse(JsonSerializer.Serialize(SaveCostProfile.Snapshot()));
        var record = snapshot.RootElement;
        var phases = record.GetProperty("phases");
        Check(phases[0], 4, 1, 3);
        Check(phases[1], 4, 3, 1);
        Check(phases[2], 3, 2, 1);
        Check(phases[3], 2, 2, 0);
        Check(phases[4], 2, 1, 1);
        Check(phases[5], 2, 2, 0);
        Require(record.GetProperty("completedAppendUtf8Bytes").GetInt64() == expectedBytes, "successful appended bytes");
        Require(record.GetProperty("plannedUtf8Bytes").GetInt64() == 2L * expectedBytes, "planned bytes include failed append");
        var totalWall = phases[0].GetProperty("wallSeconds").GetDouble();
        Require(totalWall > 0 && totalWall <= elapsed, "actual monotonic clock wall bound");
        foreach (var phase in phases.EnumerateArray()) {
            Require(phase.GetProperty("wallSeconds").GetDouble() >= 0, "wall nonnegative");
            Require(phase.GetProperty("processCpuSeconds").GetDouble() >= 0, "CPU nonnegative");
            Require(phase.GetProperty("cpuUnavailable").GetInt64() == 0, "require actual CPU clock in smoke");
        }
        // Leave a successful usable resource; Close remains outside the capped profile.
        savefile.Resource = new DreamResource(4, output, output);
        SaveCostProfile.ExportOnce(Path.Combine(emptyUniqueDirectory, "profile-final.json"));
        ExpectFailure(() => SaveCostProfile.ExportOnce(Path.Combine(emptyUniqueDirectory, "profile-final.json")));
        } finally {
            root.Remove("cycle");
            savefile.Resource = originalResource;
        }
    }
    private static void Check(JsonElement phase, long attempts, long completed, long failed) {
        Require(phase.GetProperty("attempted").GetInt64() == attempts, "attempt count " + phase.GetProperty("name"));
        Require(phase.GetProperty("completed").GetInt64() == completed, "completion count");
        Require(phase.GetProperty("failed").GetInt64() == failed, "failure count");
    }
    private static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void ExpectFailure(Action action) {
        bool failed = false;
        try { action(); } catch { failed = true; }
        Require(failed, "negative control must fail");
    }
}
