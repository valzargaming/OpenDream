#nullable enable
using System;
using System.Linq;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamShared.Dream;
using OpenDreamRuntime;
using OpenDreamRuntime.Resources;
using static OpenDreamRuntime.Objects.Types.DreamObjectSavefile;

namespace Content.IntegrationTests;

[TestFixture, NonParallelizable]
[Explicit("Requires a separate test host because BYOND API initialization is process-global")]
public sealed class StringFormatDecoderTests : ContentIntegrationTest {
    private static string Oracle(string input) => new(input.Where(c => c < '\uFF00').ToArray());

    [Test, Order(1)]
    public void AllUtf16CodeUnitsPreserveContent() {
        var input = new string(Enumerable.Range(0, 65536).Select(i => (char)i).ToArray());
        Assert.That(StringFormatDecoder.RemoveFormatting(input), Is.EqualTo(Oracle(input)));
        foreach (var text in new[] { "", "\ud800\udfff\r\n\0\uFEFF", "\uFF00before\uFFFFafter", "literal \\uFF00" })
            Assert.That(StringFormatDecoder.RemoveFormatting(text), Is.EqualTo(Oracle(text)));
    }

    [Test, Order(2)]
    public void SeededRandomContentMatchesOracle() {
        var rng = new Random(4714);
        for (var test = 0; test < 1000; test++) {
            var chars = new char[rng.Next(4096)];
            for (var i = 0; i < chars.Length; i++) chars[i] = (char)rng.Next(65536);
            var input = new string(chars);
            Assert.That(StringFormatDecoder.RemoveFormatting(input), Is.EqualTo(Oracle(input)));
        }
        var large = new string('x', 512 * 1024) + '\uFF00' + new string('y', 512 * 1024);
        Assert.That(StringFormatDecoder.RemoveFormatting(large), Is.EqualTo(Oracle(large)));
    }

    [Test, Order(3)]
    public void NoFormattingAvoidsCopy() {
        var input = new string('x', 1024 * 1024);
        Assert.That(StringFormatDecoder.RemoveFormatting(input), Is.EqualTo(input)); // warm JIT/capacity
        var before = GC.GetAllocatedBytesForCurrentThread();
        for (var i = 0; i < 4; i++) {
            var result = StringFormatDecoder.RemoveFormatting(input);
            GC.KeepAlive(result);
        }
        var allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        GC.KeepAlive(input);
        if (allocated > 4096) Assert.Fail($"DECODER_FASTPATH_ALLOCATION: expected <=4096 bytes; observed {allocated}");
    }

    private static void Collect() { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference DecodeLargeFormattedInput() {
        var input = new string('\uFF42', 8 * 1024 * 1024) + "x";
        var result = StringFormatDecoder.RemoveFormatting(input);
        Assert.That(result, Is.EqualTo("x"));
        return new WeakReference(input);
    }

    [Test, Order(4)]
    public void LargeFormattedInputIsNotRetained() {
        // A live sentinel and a dead input distinguish decoder capacity retention
        // from accidentally measuring a live test input or ineffective collection.
        var sentinel = new string('z', 1024 * 1024);
        var live = new WeakReference(sentinel);
        Collect();
        var before = GC.GetTotalMemory(false);
        var releasedInput = DecodeLargeFormattedInput();
        Collect();
        var retainedGrowth = GC.GetTotalMemory(false) - before;
        Assert.That(releasedInput.IsAlive, Is.False, "large input must be collectible");
        Assert.That(live.IsAlive, Is.True, "sentinel must remain live");
        GC.KeepAlive(sentinel);
        if (retainedGrowth > 4 * 1024 * 1024)
            Assert.Fail($"DECODER_RETAINED_CAPACITY: expected <=4194304 bytes; observed {retainedGrowth}");
    }

    [Test, Order(5)]
    public void ConcurrentCallsPreserveContent() {
        Parallel.For(0, 128, worker => {
            var content = worker + new string((char)('a' + worker % 26), 32768);
            var input = "\uFF00" + content + "\uFFFF";
            Assert.That(StringFormatDecoder.RemoveFormatting(input), Is.EqualTo(content));
        });
    }

    [Test, Order(6)]
    public async Task RealSavefileTreeOutputMatchesByteOracle() {
        var server = StartServer();
        await server.WaitIdleAsync();
        await server.WaitAssertion(CheckRealSavefileTreeOutput);
    }

    private static void CheckRealSavefileTreeOutput() {
        var folder = Path.Combine(Path.GetTempPath(), "decoder-sf-parity-" + Guid.NewGuid());
        Directory.CreateDirectory(folder);
        try {
            foreach (var text in new[] { "", "quote\" slash\\ CR\r LF\n nul\0", "caf\u00e9 \u4e2d\u6587 \ud83d\ude80 <>&+'", "\ud800 lone \udfff", new string(Enumerable.Range(0xFF00, 256).Select(i => (char)i).ToArray()) }) {
                SfDreamJsonValue tree = new SfDreamDir {
                    ["/relative/../payload"] = new SfDreamPrimitive { Value = new DreamValue(text) },
                    ["nested"] = new SfDreamDir {
                        ["number"] = new SfDreamPrimitive { Value = new DreamValue(42.5f) },
                        ["list"] = new SfDreamListValue {
                            AssocKeys = new() { new SfDreamPrimitive { Value = new DreamValue("key") }, new SfDreamPrimitive { Value = new DreamValue(3f) } },
                            AssocData = new() { new SfDreamPrimitive { Value = new DreamValue(text) }, null }
                        }
                    }
                };
                var json = JsonSerializer.Serialize(tree);
                var expected = Encoding.UTF8.GetBytes(Oracle(json) + "\r\n");
                var path = Path.Combine(folder, "tree.sav");
                var resource = new DreamResource(1, path, path);
                resource.Clear();
                resource.Output(new DreamValue(json));
                var actual = File.ReadAllBytes(path);
                Assert.That(actual, Is.EqualTo(expected));
                Assert.That(actual[^2..], Is.EqualTo(new byte[] { 13, 10 }));
                Assert.That(actual.Take(3), Is.Not.EqualTo(new byte[] { 239, 187, 191 }));
                var reconstructed = JsonSerializer.Deserialize<SfDreamJsonValue>(File.ReadAllText(path));
                Assert.That(reconstructed, Is.TypeOf<SfDreamDir>());
            }
            var failedPath = Path.Combine(folder, "serialize-failure.sav");
            File.WriteAllText(failedPath, "cached-before");
            var failing = new DreamResource(4, failedPath, failedPath);
            var oldCache = failing.ResourceData;
            SfDreamJsonValue invalid = new SfDreamDir {
                ["valid-first"] = new SfDreamPrimitive { Value = new DreamValue("prefix") },
                ["invalid-number"] = new SfDreamPrimitive { Value = new DreamValue(float.NaN) }
            };
            failing.Clear();
            Assert.Throws<ArgumentException>(() => failing.Output(new DreamValue(JsonSerializer.Serialize(invalid))));
            Assert.That(File.ReadAllBytes(failedPath), Is.Empty);
            Assert.That(failing.ResourceData, Is.SameAs(oldCache));
        } finally { Directory.Delete(folder, true); }
    }

    [Test, Order(7)]
    public void RealResourcePreservesPathsCacheAndAppendFailure() {
        var folder = Path.Combine(Path.GetTempPath(), "decoder-resource-" + Guid.NewGuid());
        Directory.CreateDirectory(folder);
        try {
            var clearPath = Path.Combine(folder, "clear.sav");
            var appendPath = Path.Combine(folder, "append.sav");
            File.WriteAllText(clearPath, "cached-before");
            File.WriteAllText(appendPath, "prefix");
            var resource = new DreamResource(2, clearPath, appendPath);
            var alias = resource;
            var cache = resource.ResourceData;
            resource.Clear();
            Assert.That(resource.ResourceData, Is.SameAs(cache));
            alias.Output(new DreamValue("a\uFF00b"));
            Assert.That(File.ReadAllText(clearPath), Is.Empty);
            Assert.That(File.ReadAllText(appendPath), Is.EqualTo("prefixab\r\n"));
            Assert.That(resource.ResourceData, Is.Not.SameAs(cache));

            File.WriteAllText(clearPath, "cache-for-failure");
            var failing = new DreamResource(3, clearPath, folder); // append target is a directory
            var oldCache = failing.ResourceData;
            failing.Clear();
            Exception? error = null;
            try { failing.Output(new DreamValue("payload")); }
            catch (Exception caught) when (caught is IOException or UnauthorizedAccessException) { error = caught; }
            Assert.That(error, Is.Not.Null, "append to a directory must fail");
            Assert.That(failing.ResourceData, Is.SameAs(oldCache));
            Assert.That(File.ReadAllBytes(clearPath), Is.Empty);
        } finally { Directory.Delete(folder, true); }
    }
}
