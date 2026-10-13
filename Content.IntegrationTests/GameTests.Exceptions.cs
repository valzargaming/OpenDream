#nullable enable
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void ExceptionsReleaseOwnedValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs) {
        foreach (var name in new[] { "exception_bound_probe", "exception_discard_probe", "exception_nested_probe" }) {
            Assert.That(tree.TryGetGlobalProc(name, out var proc), Is.True);
            var payload = tree.CreateObject(tree.Datum);
            var id = payload.RefId;
            for (var i = 0; i < 1000; i++) {
                using (var result = DreamThread.Run(proc!, manager.WorldInstance, null, new DreamValue(payload))) {
                    if (name == "exception_discard_probe")
                        Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1));
                    else
                        Assert.That(result.MustGetValueAsDreamObject(), Is.SameAs(payload), "Catch/rethrow preserves object identity");
                }
                Assert.That(payload.RefCount, Is.EqualTo(1), $"Exception ownership balanced: {name}");
                Assert.That(payload.Deleted, Is.False, "Caught payload must remain alive for its caller");
            }
            payload.DecRef();
            Assert.That(payload.Deleted, Is.True);
            using var located = refs.LocateRef(id);
            Assert.That(located.IsNull, Is.True, "Caught exception payload leaves the actual reference bucket");
        }

        // SetVar owns each native field, including arbitrary object-valued fields.
        var original = tree.CreateObject(tree.Datum);
        var replacement = tree.CreateObject(tree.Datum);
        var originalId = original.RefId;
        var replacementId = replacement.RefId;
        var error = tree.CreateObject<DreamObjectException>(tree.Exception);
        foreach (var field in new[] { "name", "desc", "file", "line" })
            error.SetVariable(field, new DreamValue(original));
        Assert.That(original.RefCount, Is.EqualTo(5));
        error.SetVariable("name", new DreamValue(replacement));
        error.SetVariable("desc", new DreamValue(replacement));
        Assert.That(original.RefCount, Is.EqualTo(3));
        Assert.That(replacement.RefCount, Is.EqualTo(3));
        error.DecRef();
        error.Delete(); // Repeated retirement must not release fields twice.
        Assert.That(original.RefCount, Is.EqualTo(1), "Exception native fields release original owner");
        Assert.That(replacement.RefCount, Is.EqualTo(1), "Exception native fields release replacement owner");
        Assert.That(error.Name.IsNull && error.Desc.IsNull && error.File.IsNull && error.Line.IsNull, Is.True);
        original.DecRef();
        replacement.DecRef();
        using var oldLocated = refs.LocateRef(originalId);
        using var newLocated = refs.LocateRef(replacementId);
        Assert.That(oldLocated.IsNull && newLocated.IsNull, Is.True);

        Assert.That(tree.TryGetGlobalProc("exception_uncaught_probe", out var uncaught), Is.True);
        var previousError = manager.LastDMException;
        try {
            for (var i = 0; i < 100; i++) {
                var payload = tree.CreateObject(tree.Datum);
                var id = payload.RefId;
                using (var result = DreamThread.Run(uncaught!, manager.WorldInstance, null, new DreamValue(payload))) {
                    Assert.That(result.IsNull, Is.True);
                }
                Assert.That(manager.LastDMException?.GetType().Name, Is.EqualTo("DMThrowException"));
                Assert.That(payload.RefCount, Is.EqualTo(1), "Uncaught exception releases transferred name owner");
                payload.DecRef();
                using var located = refs.LocateRef(id);
                Assert.That(located.IsNull, Is.True, "Uncaught payload retires despite LastDMException retaining its wrapper");
            }
        } finally {
            // These deliberate runtimes do not replace unrelated diagnostic state.
            manager.LastDMException = previousError;
        }
        TestContext.Progress.WriteLine("Exception ownership: 3000 caught/rethrown and 100 uncaught native throws plus field replacement/deletion passed");
    }
}
