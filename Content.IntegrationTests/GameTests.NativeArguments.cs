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
        Assert.That(tree.TryGetGlobalProc("arglist_failure_owner_probe", out var failureProc), Is.True);
        Assert.That(tree.TryGetGlobalProc("arglist_overwrite_owner_probe", out var overwriteProc), Is.True);
        var arglistOriginal = tree.CreateObject(tree.Datum);
        var arglistReplacement = tree.CreateObject(tree.Datum);
        var arglistOriginalId = arglistOriginal.RefId;
        var arglistReplacementId = arglistReplacement.RefId;
        try {
            for (var iteration = 0; iteration < 1000; iteration++) {
                foreach (var namedFirst in new[] { 0, 1 }) {
                    using (var result = DreamThread.Run(failureProc!, manager.WorldInstance, null,
                               new DreamValue(arglistOriginal), new DreamValue(namedFirst))) {
                        Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1), "Actual arglist conversion rejects its invalid key");
                    }
                    Assert.That(arglistOriginal.RefCount, Is.EqualTo(1), "Failed arglist conversion releases temporary owners");
                    using (var result = DreamThread.Run(overwriteProc!, manager.WorldInstance, null,
                               new DreamValue(arglistOriginal), new DreamValue(arglistReplacement), new DreamValue(namedFirst))) {
                        Assert.That(result.MustGetValueAsDreamObject(), Is.SameAs(arglistReplacement), "Arglist keeps existing last assignment semantics");
                    }
                    Assert.That(arglistOriginal.RefCount, Is.EqualTo(1), "Arglist overwritten slot releases previous owner");
                    Assert.That(arglistReplacement.RefCount, Is.EqualTo(1), "Arglist replacement releases after caller disposal");
                    using (var result = DreamThread.Run(overwriteProc!, manager.WorldInstance, null,
                               new DreamValue(arglistOriginal), new DreamValue(arglistOriginal), new DreamValue(namedFirst))) {
                        Assert.That(result.MustGetValueAsDreamObject(), Is.SameAs(arglistOriginal), "Arglist same-value replacement remains alive");
                    }
                    Assert.That(arglistOriginal.RefCount, Is.EqualTo(1), "Arglist same-value replacement balances owners");
                    Assert.That(arglistOriginal.Deleted || arglistReplacement.Deleted, Is.False);
                }
            }
        } finally {
            arglistOriginal.DecRef();
            arglistReplacement.DecRef();
        }
        Assert.That(arglistOriginal.Deleted && arglistReplacement.Deleted, Is.True);
        using (var located = refs.LocateRef(arglistOriginalId))
            Assert.That(located.IsNull, Is.True, "Arglist original leaves actual reference bucket");
        using (var located = refs.LocateRef(arglistReplacementId))
            Assert.That(located.IsNull, Is.True, "Arglist replacement leaves actual reference bucket");
        Assert.That(manager.LastDMException, Is.Null);
        TestContext.Progress.WriteLine("Arglist ownership: 2000 caught conversion failures, 2000 overwritten slots and 2000 same-value assignments released owners");

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
