#nullable enable
using System.Collections.Generic;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Procs;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void AsyncReturnsOwnValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs) {
        Assert.That(tree.TryGetGlobalProc("async_return_ownership_probe", out var proc), Is.True);
        var payload = tree.CreateObject(tree.Datum);
        var id = payload.RefId;
        try {
            foreach (var noWait in new[] { false, true }) {
                for (var iteration = 0; iteration < 1000; iteration++) {
                    var observed = 0;
                    var reentrant = 0;
                    var delivered = false;
                    using (var completed = DreamThread.Run("async return ownership", async state => {
                        var value = noWait
                            ? await state.CallNoWait(proc!, manager.WorldInstance, null, new DreamValue(payload))
                            : await state.Call(proc!, manager.WorldInstance, null, new DreamValue(payload));
                        observed = payload.RefCount;
                        delivered = value.MustGetValueAsDreamObject() == payload && !payload.Deleted;
                        // Keep a failing baseline observational: do not dispose its
                        // borrowed value and corrupt the caller's sole owner.
                        if (observed == 2) {
                            using (value) {
                                using var nested = await state.Call(proc!, manager.WorldInstance, null, new DreamValue(payload));
                                reentrant = payload.RefCount;
                            }
                        }
                        return DreamValue.Null;
                    })) {
                        Assert.That(completed.IsNull, Is.True);
                    }
                    Assert.That(observed, Is.EqualTo(2), "Async returned value acquires an awaited owner");
                    Assert.That(delivered, Is.True);
                    Assert.That(reentrant, Is.EqualTo(3), "Reentrant async call preserves the earlier awaited owner");
                    Assert.That(payload.RefCount, Is.EqualTo(1), "Completed async calls release awaited owners");
                    Assert.That(payload.Deleted, Is.False);
                }
            }

            // Actual DM returns a temporary owner. ReturnedInto borrows it; the
            // production frame must acquire before that temporary is released.
            // Exercise cancellation/disposal before delivery, including replacement.
            var factory = new AsyncNativeProc(-1, tree.Root, "async pending return ownership",
                new List<string>(), new Dictionary<string, DreamValue>(), _ => Task.FromResult(DreamValue.Null));
            for (var iteration = 0; iteration < 1000; iteration++) {
                var thread = new DreamThread("pending async cancellation");
                var frame = factory.CreateState(thread, null, null, new DreamProcArguments());
                thread.PushProcState(frame);
                using (var returned = DreamThread.Run(proc!, manager.WorldInstance, null, new DreamValue(payload)))
                    frame.ReturnedInto(returned);
                Assert.That(payload.RefCount, Is.EqualTo(2), "Pending async return owns the borrowed value");
                using (var replacement = DreamThread.Run(proc!, manager.WorldInstance, null, new DreamValue(payload)))
                    frame.ReturnedInto(replacement);
                Assert.That(payload.RefCount, Is.EqualTo(2), "Replacing pending return releases its prior owner");
                thread.CancelAll();
                thread.PopProcState();
                Assert.That(payload.RefCount, Is.EqualTo(1), "Canceled pending async return releases its owner");
            }
        } finally {
            payload.DecRef();
        }
        Assert.That(payload.Deleted, Is.True);
        using var located = refs.LocateRef(id);
        Assert.That(located.IsNull, Is.True);
        TestContext.Progress.WriteLine("Async return ownership: 2000 connected Call/CallNoWait deliveries, 2000 reentrant calls and 1000 pending-return replacements/cancellations passed");
    }
}
