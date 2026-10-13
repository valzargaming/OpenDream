using System;
using System.IO;
using NUnit.Framework;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Procs;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void SavefileFailuresReleaseRegisteredObjects(DreamObjectTree tree, DreamRefManager refs) {
        var initialOpenCount = DreamObjectSavefile.Savefiles.Count;
        for (var i = 0; i < 100; i++) {
            var file = new DreamObjectSavefile(tree.Savefile.ObjectDefinition);
            var id = file.RefId;
            file.DecRef();
            Assert.That(file.Deleted, Is.True, "Uninitialized savefile must run base deletion");
            using var located = refs.LocateRef(id);
            Assert.That(located.IsNull, Is.True, "Uninitialized savefile must release its real reference bucket slot");
            file.Delete();
        }

        var path = Path.Combine(Path.GetTempPath(), "opendream-savefile-cleanup-" + Guid.NewGuid() + ".json");
        const string malformed = "{ invalid JSON - preserve these bytes";
        try {
            File.WriteAllText(path, malformed);
            for (var i = 0; i < 100; i++) {
                var file = new DreamObjectSavefile(tree.Savefile.ObjectDefinition);
                var id = file.RefId;
                using var args = new DreamProcArguments(new DreamValue(path));
                // A ref struct cannot be captured by Assert.Throws' delegate.
                var rejected = false;
                try { file.Initialize(args); }
                catch (InvalidDataException error) {
                    rejected = true;
                    Assert.That(error.Message, Does.Contain("Error parsing savefile"));
                } finally { file.DecRef(); }
                Assert.That(rejected, Is.True);
                Assert.That(file.Deleted, Is.True);
                using var located = refs.LocateRef(id);
                Assert.That(located.IsNull, Is.True, "Failed native initialization must release its reference slot");
                Assert.That(DreamObjectSavefile.Savefiles.Count, Is.EqualTo(initialOpenCount));
            }
            Assert.That(File.ReadAllText(path), Is.EqualTo(malformed));
        } finally { File.Delete(path); }

        path = Path.Combine(Path.GetTempPath(), "opendream-savefile-shared-" + Guid.NewGuid() + ".json");
        DreamObjectSavefile? first = null, second = null;
        try {
            first = new DreamObjectSavefile(tree.Savefile.ObjectDefinition);
            second = new DreamObjectSavefile(tree.Savefile.ObjectDefinition);
            using var args = new DreamProcArguments(new DreamValue(path));
            first.Initialize(args);
            second.Initialize(args);
            Assert.That(second.CurrentDir, Is.SameAs(first.CurrentDir));
            first.CurrentDir["payload"] = new DreamObjectSavefile.SfDreamPrimitive { Value = new DreamValue("persisted") };
            var firstId = first.RefId;
            first.DecRef();
            using var located = refs.LocateRef(firstId);
            Assert.That(located.IsNull, Is.True);
            Assert.That(second.CurrentDir.ContainsKey("payload"), Is.True);
            Assert.That(second.Deleted, Is.False);
            second.DecRef();
            Assert.That(File.ReadAllText(path), Does.Contain("persisted"));
            Assert.That(DreamObjectSavefile.Savefiles.Count, Is.EqualTo(initialOpenCount));
        } finally {
            first?.Delete();
            second?.Delete();
            File.Delete(path);
        }
        TestContext.Progress.WriteLine("Savefile cleanup: 200 native failed/uninitialized disposals and shared-file preservation passed");
    }
}
