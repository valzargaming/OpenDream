using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;

namespace OpenDreamRuntime.Resources;

// Detached opt-in measurement candidate. No DM-facing API or automatic export.
public static class SaveCostProfile {
    public enum Phase { TotalFlush, ClearDisk, SerializeTree, RemoveFormatting, AppendDisk, ProfilerByteCount }
    public enum Origin { Initialize, Direct, DirtyTick, Close, EmbeddedSavefile }
    public enum CaptureEnd { Completed, Aborted, Shutdown }
    private const int OriginCount = 5;
    private static readonly long[] OriginSeen = new long[OriginCount];
    private static readonly long[] OriginSelected = new long[OriginCount];
    private static readonly long[] OriginSampled = new long[OriginCount];
    private static readonly long[] OriginCompleted = new long[OriginCount];
    private static readonly long[] OriginFailed = new long[OriginCount];
    private static bool _captureStarted, _captureActive;
    private static string? _captureName, _exactResourcePath;
    private static CaptureEnd? _captureEnd;
    private static long _captureBegin, _captureStop, _outsideCapture, _resourceExcluded, _capExcluded;
    private static long _firstCapExcludedAt;
    private const int PhaseCount = 6;
    private static readonly long[] Attempts = new long[PhaseCount];
    private static readonly long[] Completed = new long[PhaseCount];
    private static readonly long[] Failed = new long[PhaseCount];
    private static readonly long[] WallTicks = new long[PhaseCount];
    private static readonly long[] CpuTicks = new long[PhaseCount];
    private static readonly long[] CpuUnavailable = new long[PhaseCount];
    private static readonly long[] MaxWallTicks = new long[PhaseCount];
    private static int _ownerThread;
    private static int _remaining, _configuredMax;
    private static long _serializedChars, _appendChars, _plannedUtf8Bytes, _emittedUtf8Bytes;
    private static Process? _process;
    [ThreadStatic] private static Context? _active;
    public static bool Enabled { get; private set; }

    // Host/test explicitly calls once on the engine thread. Default is disabled.
    public static void Enable(int maxFlushes = 4096) {
        if (Enabled || _active != null || Attempts[(int)Phase.TotalFlush] != 0)
            throw new InvalidOperationException("Use a fresh process for another profile run");
        if (maxFlushes < 1 || maxFlushes > 4096) throw new ArgumentOutOfRangeException(nameof(maxFlushes));
        _ownerThread = Environment.CurrentManagedThreadId;
        _remaining = _configuredMax = maxFlushes;
        Enabled = true;
    }

    // One explicit window, possibly spanning ticks, with one bounded optional path.
    public static void BeginCapture(string name, string? exactResourcePath = null) {
        RequireOwner();
        if (_captureStarted || _active != null) throw new InvalidOperationException("One capture per fresh process");
        if (string.IsNullOrWhiteSpace(name) || name.Length > 64) throw new ArgumentException("Capture name length 1..64");
        if (exactResourcePath != null && (exactResourcePath.Length > 4096 || !Path.IsPathFullyQualified(exactResourcePath)))
            throw new ArgumentException("Exact resource filter must be absolute and at most 4096 chars");
        _captureStarted = _captureActive = true;
        _captureName = name;
        _exactResourcePath = exactResourcePath;
        _captureBegin = Stopwatch.GetTimestamp();
    }
    public static void EndCapture(CaptureEnd reason = CaptureEnd.Completed) {
        RequireOwner();
        if (!_captureActive || _active != null) throw new InvalidOperationException("Seal between flushes in active capture");
        _captureStop = Stopwatch.GetTimestamp();
        _captureEnd = reason;
        _captureActive = false;
    }
    private static void RequireOwner() {
        if (!Enabled || Environment.CurrentManagedThreadId != _ownerThread)
            throw new InvalidOperationException("Profile owner engine thread required");
    }

    public sealed class Context {
        internal readonly Origin Origin;
        internal readonly DreamResource? Resource;
        internal readonly Context? Previous;
        internal readonly Sample Total;
        internal long PendingBytes;
        internal bool PendingBytesValid;
        internal bool Ended;
        internal Context(DreamResource? resource, Context? previous, Origin origin) {
            Origin = origin;
            Resource = resource;
            Previous = previous;
            Total = Start(Phase.TotalFlush);
        }
    }

    public readonly record struct Sample(Phase Phase, long Wall, long Cpu);
    private static long ReadCpu() {
        try {
            _process ??= Process.GetCurrentProcess();
            return _process.TotalProcessorTime.Ticks;
        } catch { return -1; } // CPU availability must never change save errors/results.
    }
    public static Context? Begin(DreamResource? resource, Origin origin) {
        if (!Enabled || Environment.CurrentManagedThreadId != _ownerThread) return null;
        int index = (int)origin;
        OriginSeen[index]++;
        if (!_captureActive) { _outsideCapture++; return null; }
        if (_exactResourcePath != null && !string.Equals(resource?.ResourcePath, _exactResourcePath, StringComparison.Ordinal)) {
            _resourceExcluded++; return null;
        }
        OriginSelected[index]++;
        if (_remaining == 0) {
            if (_capExcluded == 0) _firstCapExcludedAt = Stopwatch.GetTimestamp();
            _capExcluded++;
            return null;
        }
        --_remaining;
        OriginSampled[index]++;
        var context = new Context(resource, _active, origin);
        _active = context;
        return context;
    }
    public static Context? SuspendObservation() { var previous = _active; _active = null; return previous; }
    public static void RestoreObservation(Context? previous) { _active = previous; }
    public static Context? For(DreamResource resource) =>
        _active != null && ReferenceEquals(_active.Resource, resource) ? _active : null;
    public static Sample Start(Phase phase) {
        Attempts[(int)phase]++;
        // CPU read overhead is partly outside wall bracket; this is deliberate and calibrated.
        var cpu = ReadCpu();
        return new Sample(phase, Stopwatch.GetTimestamp(), cpu);
    }
    public static void End(Sample sample, bool successful) {
        var wall = Stopwatch.GetTimestamp() - sample.Wall;
        var cpu = ReadCpu();
        int index = (int)sample.Phase;
        WallTicks[index] += wall;
        MaxWallTicks[index] = Math.Max(MaxWallTicks[index], wall);
        if (sample.Cpu < 0 || cpu < sample.Cpu) CpuUnavailable[index]++;
        else CpuTicks[index] += cpu - sample.Cpu;
        if (successful) Completed[index]++; else Failed[index]++;
    }
    public static void Finish(Context context, bool successful) {
        if (context.Ended) return;
        context.Ended = true;
        End(context.Total, successful);
        if (successful) OriginCompleted[(int)context.Origin]++; else OriginFailed[(int)context.Origin]++;
        _active = context.Previous;
        // No snapshots retain Context, resource, tree, text or path references.
    }
    public static void Serialized(string json) => _serializedChars += json.Length;
    public static void PlannedAppend(Context context, string text) {
        // Extra UTF8 scan is profiler work, outside formatter and disk phase timers.
        var sample = Start(Phase.ProfilerByteCount);
        bool successful = false;
        try {
            context.PendingBytes = (long)Encoding.UTF8.GetByteCount(text) + 2; // literal CRLF
            context.PendingBytesValid = true;
            _plannedUtf8Bytes += context.PendingBytes;
            _appendChars += (long)text.Length + 2; // UTF16 code units, including CRLF
            successful = true;
        } catch { context.PendingBytesValid = false; } // Measurement failure cannot block original append.
        finally { End(sample, successful); }
    }
    public static void Appended(Context context) {
        if (context.PendingBytesValid) _emittedUtf8Bytes += context.PendingBytes;
    }

    public static object Snapshot() {
        if (Environment.CurrentManagedThreadId != _ownerThread || _active != null)
            throw new InvalidOperationException("Snapshot only between flushes on profile owner thread");
        var phases = new object[PhaseCount];
        for (int i = 0; i < PhaseCount; i++) phases[i] = new {
            name = ((Phase)i).ToString(), attempted = Attempts[i], completed = Completed[i], failed = Failed[i],
            wallSeconds = WallTicks[i] / (double)Stopwatch.Frequency,
            processCpuSeconds = CpuTicks[i] / (double)TimeSpan.TicksPerSecond,
            cpuUnavailable = CpuUnavailable[i], maxWallSeconds = MaxWallTicks[i] / (double)Stopwatch.Frequency
        };
        var origins = new object[OriginCount];
        for (int i = 0; i < OriginCount; i++) origins[i] = new {
            name = ((Origin)i).ToString(), seen = OriginSeen[i], selected = OriginSelected[i],
            sampled = OriginSampled[i], completed = OriginCompleted[i], failed = OriginFailed[i]
        };
        var snapshotAt = Stopwatch.GetTimestamp();
        return new { schema = 2, captureName = _captureName, exactResourcePath = _exactResourcePath,
            captureStarted = _captureStarted, captureActive = _captureActive, captureEnd = _captureEnd?.ToString(),
            captureWallSeconds = !_captureStarted ? 0 : ((_captureActive ? snapshotAt : _captureStop) - _captureBegin) / (double)Stopwatch.Frequency,
            outsideCapture = _outsideCapture, resourceExcluded = _resourceExcluded, capExcluded = _capExcluded,
            firstCapExcludedSecondsFromCapture = _capExcluded == 0 ? (double?)null : (_firstCapExcludedAt - _captureBegin) / (double)Stopwatch.Frequency,
            samplingCompleteForSelectedCalls = _captureEnd == CaptureEnd.Completed && _capExcluded == 0,
            coverageObservedThroughSnapshot = true, ownerThreadOnly = true, offOwnerCallsUncounted = true,
            originPhasesAggregated = true, origins,
            maxFlushes = _configuredMax, remaining = _remaining, sampleLimitReached = _remaining == 0, stopwatchFrequency = Stopwatch.Frequency,
            processCpuIncludesBackgroundWork = true, totalOverlapsPhases = true,
            serializedUtf16Chars = _serializedChars, appendedUtf16Chars = _appendChars,
            plannedUtf8Bytes = _plannedUtf8Bytes, completedAppendUtf8Bytes = _emittedUtf8Bytes, phases };
    }

    // One explicit end-of-run export; caller supplies a fresh unique absolute task path.
    // Export failure belongs to the measurement caller, never Flush/Close/dirty processing.
    public static void ExportOnce(string uniqueAbsolutePath) {
        if (!Path.IsPathFullyQualified(uniqueAbsolutePath)) throw new ArgumentException("Absolute profile target required");
        var snapshot = Snapshot();
        using var stream = new FileStream(uniqueAbsolutePath, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        JsonSerializer.Serialize(stream, snapshot);
    }

    // Run in separate empty calibration process, after warming Process/Stopwatch.
    // Does not modify measured phase counters or save state.
    public static object Calibrate(int samples = 1000) {
        if (samples < 1 || samples > 10000) throw new ArgumentOutOfRangeException(nameof(samples));
        ReadCpu(); Stopwatch.GetTimestamp();
        var beginWall = Stopwatch.GetTimestamp(); var beginCpu = ReadCpu();
        long pairWall = 0;
        for (int i = 0; i < samples; i++) {
            ReadCpu(); var start = Stopwatch.GetTimestamp();
            pairWall += Stopwatch.GetTimestamp() - start; ReadCpu();
        }
        var endCpu = ReadCpu(); var endWall = Stopwatch.GetTimestamp();
        return new { samples, wallSeconds = (endWall - beginWall) / (double)Stopwatch.Frequency,
            cpuSeconds = beginCpu < 0 || endCpu < beginCpu ? (double?)null : (endCpu - beginCpu) / (double)TimeSpan.TicksPerSecond,
            emptyBracketWallSeconds = pairWall / (double)Stopwatch.Frequency };
    }
}
