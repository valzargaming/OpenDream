using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Procs;
using OpenDreamRuntime.Resources;

namespace Content.Tests;

// Exercise the production native handlers without an integration server, IoC,
// sockets or a process-wide working-directory change. All disk effects are temporary.
[TestFixture]
public sealed class Text2FileTests {
    private string _temporary = default!;
    private DreamResourceManager _resources = default!;

    [SetUp]
    public void SetUp() {
        _temporary = Path.Combine(Path.GetTempPath(), "opendream-text2file-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_temporary);
        _resources = new DreamResourceManager();
    }

    [TearDown]
    public void TearDown() => Directory.Delete(_temporary, recursive: true);

    private DreamValue Call(string name, params DreamValue[] values) {
        // The containing type is internal; keep production visibility unchanged.
        var type = typeof(NativeProc).Assembly.GetType("OpenDreamRuntime.Procs.Native.DreamProcNativeRoot", throwOnError: true)!;
        var handler = type.GetMethod("NativeProc_" + name, BindingFlags.Public | BindingFlags.Static)!
            .CreateDelegate<NativeProc.HandlerFn>();
        var (procName, defaults, arguments) = NativeProc.GetNativeInfo(handler);
        // These three handlers only use ResourceManager and their arguments.
        var proc = new NativeProc(0, null!, procName, arguments, defaults ?? new Dictionary<string, DreamValue>(),
            handler, null!, null!, null!, null!, _resources, null!, null!);
        return proc.Call(new DreamThread("text2file test"), null, null, new DreamProcArguments(values));
    }

    private void Write(DreamValue text, string path) {
        using var result = Call("text2file", text, new DreamValue(path));
        Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1));
    }

    private void Read(string path, string expected) {
        using var result = Call("file2text", new DreamValue(path));
        Assert.That(result.MustGetValueAsString(), Is.EqualTo(expected));
    }

    [TestCase("", "\n")]
    [TestCase("first", "first\n")]
    [TestCase("already\n", "already\n\n")]
    [TestCase("already\r\n", "already\r\n\n")]
    [TestCase("é😀漢字", "é😀漢字\n")]
    public void CreatesUtf8WithoutBomAndAddsLiteralLf(string text, string expected) {
        var path = Path.Combine(_temporary, "nested", "new.txt");
        Write(new DreamValue(text), path);
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(new UTF8Encoding(false, true).GetBytes(expected)));
        using var exclusive = File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
    }

    [Test]
    public void SuccessiveWritesAppendAndRefreshCachedReadbackAndCopy() {
        var path = Path.Combine(_temporary, "journal.txt");
        var missing = _resources.LoadResource(path);
        Assert.That(missing.ResourceData, Is.Null);
        Write(new DreamValue("intent"), path);
        Read(path, "intent\n"); // Prime the resource byte cache before appending again.
        var oldBytes = missing.ResourceData;
        Write(new DreamValue("commit"), path);
        const string expected = "intent\ncommit\n";
        Read(path, expected);
        Assert.That(_resources.LoadResource(path), Is.SameAs(missing));
        Assert.That(missing.ResourceData, Is.Not.SameAs(oldBytes));
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(Encoding.UTF8.GetBytes(expected)));

        var copy = Path.Combine(_temporary, "copy", "journal.txt");
        using var result = Call("fcopy", new DreamValue(path), new DreamValue(copy));
        Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1));
        Assert.That(File.ReadAllBytes(copy), Is.EqualTo(File.ReadAllBytes(path)));
        Read(copy, expected);
    }

    [TestCase("prefix", "prefixnext\n")]
    [TestCase("prefix\n", "prefix\nnext\n")]
    public void PreservesExistingBytes(string existing, string expected) {
        var path = Path.Combine(_temporary, "existing.txt");
        File.WriteAllText(path, existing, new UTF8Encoding(false));
        Read(path, existing);
        Write(new DreamValue("next"), path);
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(Encoding.UTF8.GetBytes(expected)));
        Read(path, expected);
    }

    [Test]
    public void NonTextRetainsEmptyLineBehavior() {
        var path = Path.Combine(_temporary, "empty.txt");
        Write(DreamValue.Null, path);
        Write(new DreamValue(42), path);
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(new byte[] { 10, 10 }));
    }

    [Test]
    public void InvalidDestinationReturnsZero() {
        foreach (var destination in new[] { DreamValue.Null, new DreamValue(42), new DreamValue(""), new DreamValue("bad\0path") }) {
            using var result = Call("text2file", new DreamValue("payload"), destination);
            Assert.That(result.MustGetValueAsFloat(), Is.Zero);
        }
        Assert.That(Directory.GetFileSystemEntries(_temporary), Is.Empty);
    }

    [Test]
    public void FailedWritesPreserveBytesAndCache() {
        var path = Path.Combine(_temporary, "locked.txt");
        Write(new DreamValue("original"), path);
        var cached = _resources.LoadResource(path).ResourceData;
        using (File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) {
            using var result = Call("text2file", new DreamValue("rejected"), new DreamValue(path));
            Assert.That(result.MustGetValueAsFloat(), Is.Zero);
            Assert.That(_resources.LoadResource(path).ResourceData, Is.SameAs(cached));
        }
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(cached));
        Read(path, "original\n");

        using var directoryResult = Call("text2file", new DreamValue("rejected"), new DreamValue(_temporary));
        Assert.That(directoryResult.MustGetValueAsFloat(), Is.Zero);
        var child = Path.Combine(path, "child.txt"); // A regular file cannot be a parent directory.
        using var parentResult = Call("text2file", new DreamValue("rejected"), new DreamValue(child));
        Assert.That(parentResult.MustGetValueAsFloat(), Is.Zero);
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(cached));
    }

    [Test]
    public void CopyRefreshesReusableJournalDestinations() {
        foreach (var name in new[] { "slot0", "slot1", "pending" }) {
            var destination = Path.Combine(_temporary, name + ".json");
            Write(new DreamValue("old"), destination);
            Read(destination, "old\n");
            for (var revision = 1; revision <= 3; revision++) {
                var temporary = Path.Combine(_temporary, name + revision + ".tmp");
                var payload = "{\"revision\":" + revision + "}";
                Write(new DreamValue(payload), temporary);
                Read(temporary, payload + "\n");
                using var copy = Call("fcopy", new DreamValue(temporary), new DreamValue(destination));
                Assert.That(copy.MustGetValueAsFloat(), Is.EqualTo(1));
                Read(destination, payload + "\n");
                Assert.That(File.ReadAllBytes(destination), Is.EqualTo(Encoding.UTF8.GetBytes(payload + "\n")));
            }
        }
    }

    [TestCase(false)]
    [TestCase(true)]
    public void WritesInvalidateAllCachedPathAliases(bool copy) {
        var path = Path.Combine(_temporary, "aliased.txt");
        Directory.CreateDirectory(Path.Combine(_temporary, "sub"));
        var aliases = new List<string> { path, Path.Combine(_temporary, ".", "aliased.txt"),
            Path.Combine(_temporary, "sub", "..", "aliased.txt"), Path.GetRelativePath(Directory.GetCurrentDirectory(), path) };
        if (OperatingSystem.IsWindows()) {
            aliases.Add(path.ToUpperInvariant());
            aliases.Add(path.Replace('\\', '/'));
        }
        Write(new DreamValue("old"), path);
        var handles = new List<DreamResource>();
        foreach (var alias in aliases) {
            Read(alias, "old\n");
            handles.Add(_resources.LoadResource(alias));
        }
        if (copy) {
            var source = Path.Combine(_temporary, "source.txt");
            Write(new DreamValue("new"), source);
            using var result = Call("fcopy", new DreamValue(source), new DreamValue(aliases[2]));
            Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1));
        } else {
            Write(new DreamValue("new"), aliases[2]);
        }
        var expected = copy ? "new\n" : "old\nnew\n";
        Assert.That(File.ReadAllBytes(path), Is.EqualTo(Encoding.UTF8.GetBytes(expected)));
        for (var i = 0; i < aliases.Count; i++) {
            Read(aliases[i], expected);
            Assert.That(_resources.LoadResource(aliases[i]), Is.SameAs(handles[i]), "keep raw-path resource identity");
            using var result = Call("file2text", new DreamValue(handles[i]));
            Assert.That(result.MustGetValueAsString(), Is.EqualTo(expected));
        }
    }

    [Test]
    public void FailedCopyPreservesDestinationBytesAndCache() {
        var source = Path.Combine(_temporary, "source.txt");
        var destination = Path.Combine(_temporary, "destination.txt");
        Write(new DreamValue("new"), source);
        Write(new DreamValue("old"), destination);
        Read(destination, "old\n");
        var cached = _resources.LoadResource(destination).ResourceData;
        using (File.Open(destination, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) {
            using var result = Call("fcopy", new DreamValue(source), new DreamValue(destination));
            Assert.That(result.MustGetValueAsFloat(), Is.Zero);
            Assert.That(_resources.LoadResource(destination).ResourceData, Is.SameAs(cached));
        }
        Assert.That(File.ReadAllBytes(destination), Is.EqualTo(cached));
        Read(destination, "old\n");
    }
}
