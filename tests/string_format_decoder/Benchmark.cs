using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using OpenDreamRuntime;
using OpenDreamRuntime.Resources;

// Resource seam benchmark. Identical deterministic DTOs, not SfDreamJsonValue.
// Run one variant/size per fresh process. The external runner enforces caps.
const string variant = "decoder-resource-seam";
if (args.Length != 2 || !int.TryParse(args[0], out var mib) ||
    !new[] { 1, 16, 64 }.Contains(mib) || !int.TryParse(args[1], out var repeats) ||
    repeats < 2 || repeats > 4)
    throw new ArgumentException("Expected 1|16|64 MiB and 2..4 total flushes");

var folder = Path.Combine(Path.GetTempPath(), "save-allocation-" + Guid.NewGuid());
Directory.CreateDirectory(folder);
try {
    const int chunkBytes = 4096;
    var targetBytes = checked(mib * 1024 * 1024);
    // Unique strings avoid representing a large tree with one shared payload.
    var tree = new SortedDictionary<string, string>(StringComparer.Ordinal);
    for (var i = 0; i < targetBytes / chunkBytes; i++) {
        var prefix = i.ToString("X8");
        tree.Add(prefix, prefix + new string((char)('a' + i % 26), chunkBytes - prefix.Length));
    }
    var file = Path.Combine(folder, "output.sav");
    var resource = new DreamResource(1, file, file);
    string? expectedHash = null;
    long expectedBytes = 0;
    // Deliberate GC outside measured region: comparable start, retained static
    // decoder remains observable. No forced collections during a flush.
    for (var iteration = 0; iteration < repeats; iteration++) {
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        var retainedBefore = GC.GetTotalMemory(false);
        var allocatedBefore = GC.GetTotalAllocatedBytes(true);
        var collectionsBefore = new[] { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) };
        var timer = Stopwatch.StartNew();
        resource.Clear();
        resource.Output(new DreamValue(JsonSerializer.Serialize(tree)));
        timer.Stop();
        var allocatedBytes = GC.GetTotalAllocatedBytes(true) - allocatedBefore;
        var collections = Enumerable.Range(0, 3).Select(i => GC.CollectionCount(i) - collectionsBefore[i]).ToArray();
        var heapAfterFlush = GC.GetTotalMemory(false);
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        var retainedAfter = GC.GetTotalMemory(false);
        // Streaming hash outside measurements; avoid ReadAllBytes(size) copies.
        using var read = File.OpenRead(file);
        var outputBytes = read.Length;
        var hash = Convert.ToHexString(SHA256.HashData(read)).ToLowerInvariant();
        if (iteration == 0) { expectedHash = hash; expectedBytes = outputBytes; }
        else if (hash != expectedHash || outputBytes != expectedBytes)
            throw new Exception("Warm output hash/byte mismatch");
        read.Seek(-2, SeekOrigin.End);
        if (read.ReadByte() != 13 || read.ReadByte() != 10) throw new Exception("Missing CRLF");
        using var process = Process.GetCurrentProcess();
        Console.WriteLine(JsonSerializer.Serialize(new {
            variant, requestedPayloadMiB = mib, members = tree.Count, iteration,
            phase = iteration == 0 ? "cold" : "warm", flushCount = 1,
            elapsedMilliseconds = timer.Elapsed.TotalMilliseconds, allocatedBytes,
            collections, retainedBefore, heapAfterFlush, retainedAfter,
            outputBytes, sha256 = hash, processPeakWorkingSetBytes = process.PeakWorkingSet64,
            processPrivateBytes = process.PrivateMemorySize64,
            runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            pid = Environment.ProcessId
        }));
    }
    GC.KeepAlive(tree);
} finally {
    Directory.Delete(folder, true);
}
