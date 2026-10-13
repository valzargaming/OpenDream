#nullable enable
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Procs;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void NativeArgumentsReleaseOwnedValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs) {
        foreach (var name in new[] { "native_argument_failure_probe", "native_argument_rethrow_probe", "native_argument_success_probe" }) {
            Assert.That(tree.TryGetGlobalProc(name, out var proc), Is.True);
            var payload = tree.CreateObject(tree.Datum);
            var id = payload.RefId;
            for (var iteration = 0; iteration < 1000; iteration++) {
                using (var result = DreamThread.Run(proc!, manager.WorldInstance, null, new DreamValue(payload))) {
                    Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1), "Real native handler must execute its expected branch");
                }
                Assert.That(payload.RefCount, Is.EqualTo(1), $"Native call argument ownership balanced: {name}");
                Assert.That(payload.Deleted, Is.False, "Native failure must not prematurely delete caller payload");
            }
            payload.DecRef();
            Assert.That(payload.Deleted, Is.True);
            using var located = refs.LocateRef(id);
            Assert.That(located.IsNull, Is.True, "Native call payload leaves actual reference bucket");
        }

        var original = tree.CreateObject(tree.Datum);
        var replacement = tree.CreateObject(tree.Datum);
        var originalId = original.RefId;
        var replacementId = replacement.RefId;
        var procStateFactory = new AsyncNativeProc(-1, tree.Root, "native_slot_ownership_probe",
            new List<string> { "payload" }, new Dictionary<string, DreamValue>(),
            _ => Task.FromResult(DreamValue.Null));
        for (var iteration = 0; iteration < 1000; iteration++) {
            var state = procStateFactory.CreateState(new DreamThread("native slot ownership"), null, null,
                new DreamProcArguments(new DreamValue(original)));
            try {
                Assert.That(original.RefCount, Is.EqualTo(2), "Async frame initially owns its argument");
                state.SetArgument(0, new DreamValue(replacement));
                Assert.That(original.RefCount, Is.EqualTo(1), "Async slot replacement releases original owner");
                Assert.That(replacement.RefCount, Is.EqualTo(2), "Async slot replacement owns new value");
                state.SetArgument(0, new DreamValue(replacement));
                Assert.That(replacement.RefCount, Is.EqualTo(2), "Async slot self-assignment balances ownership");
                Assert.Throws<IndexOutOfRangeException>(() => state.SetArgument(1, new DreamValue(original)));
                Assert.That(original.RefCount, Is.EqualTo(1), "Rejected async slot must not change ownership");
                Assert.That(state.GetArguments()[0].MustGetValueAsDreamObject(), Is.SameAs(replacement));
            } finally {
                state.Dispose();
            }
            Assert.That(original.RefCount, Is.EqualTo(1));
            Assert.That(replacement.RefCount, Is.EqualTo(1), "Async frame disposal releases replacement owner");
            Assert.That(original.Deleted || replacement.Deleted, Is.False);
        }
        original.DecRef(); replacement.DecRef();
        Assert.That(original.Deleted && replacement.Deleted, Is.True);
        using var originalLocated = refs.LocateRef(originalId);
        using var replacementLocated = refs.LocateRef(replacementId);
        Assert.That(originalLocated.IsNull && replacementLocated.IsNull, Is.True);
        TestContext.Progress.WriteLine("Native argument ownership: 2000 caught/rethrown native failures, 1000 successful calls and 1000 async slot replacements/self-assignments passed");
    }
}
