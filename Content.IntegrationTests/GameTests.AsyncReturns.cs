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
    private static async Task AsyncReturnsOwnValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs,
        Func<Action, Task> onServer, Func<int, Task> advanceTicks) {
        DreamProc? proc = null;
        DreamObject payload = null!;
        await onServer(() => {
            Assert.That(tree.TryGetGlobalProc("async_return_ownership_probe", out proc), Is.True);
            payload = tree.CreateObject(tree.Datum);
        });
        var id = payload.RefId;
        try {
            foreach (var noWait in new[] { false, true }) {
                for (var iteration = 0; iteration < 1000; iteration++) {
                    var observed = 0;
                    var reentrant = 0;
                    var delivered = false;
                    var finished = false;
                    await onServer(() => {
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
                        finished = true;
                        return DreamValue.Null;
                    })) {
                        Assert.That(completed.IsNull, Is.True);
                    }
                    });
                    // CallNoWait intentionally schedules its continuation later.
                    // Pump the real connected game ticks, without blocking its thread.
                    var done = false;
                    for (var tick = 0; tick < 100 && !done; tick++) {
                        await advanceTicks(1);
                        await onServer(() => done = finished);
                    }
                    await onServer(() => {
                    Assert.That(observed, Is.EqualTo(2), "Async returned value acquires an awaited owner");
                    Assert.That(delivered, Is.True);
                    Assert.That(reentrant, Is.EqualTo(3), "Reentrant async call preserves the earlier awaited owner");
                    Assert.That(payload.RefCount, Is.EqualTo(1), "Completed async calls release awaited owners");
                    Assert.That(payload.Deleted, Is.False);
                    Assert.That(finished, Is.True, "Async continuation completes within bounded game ticks");
                    });
                }
            }

            // Actual DM returns a temporary owner. ReturnedInto borrows it; the
            // production frame must acquire before that temporary is released.
            // Exercise cancellation/disposal before delivery, including replacement.
            await onServer(() => {
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
            });

            // Real CallNoWait creates a live TCS. Cancel before the real DM
            // callee returns, holding the async task open through refused delivery.
            for (var iteration = 0; iteration < 1000; iteration++) {
                var cleanup = new TaskCompletionSource<bool>();
                var canceled = false;
                var finished = false;
                await onServer(() => {
                    using var initial = DreamThread.Run("canceled live async delivery", async state => {
                        var pending = state.CallNoWait(proc!, manager.WorldInstance, null, new DreamValue(payload));
                        state.Thread.CancelAll();
                        state.Thread.CancelAll(); // Cancellation is idempotent.
                        try {
                            using var unexpected = await pending;
                        } catch (OperationCanceledException) {
                            canceled = true;
                        }
                        await cleanup.Task;
                        finished = true;
                        return DreamValue.Null;
                    });
                    Assert.That(canceled, Is.True, "Actual awaited CallNoWait TCS was canceled");
                    Assert.That(payload.RefCount, Is.EqualTo(1), "Canceled live async delivery releases refused owner");
                    cleanup.SetResult(true);
                });
                var done = false;
                for (var tick = 0; tick < 100 && !done; tick++) {
                    await advanceTicks(1);
                    await onServer(() => done = finished);
                }
                await onServer(() => {
                    Assert.That(finished, Is.True, "Canceled live async continuation drains");
                    Assert.That(payload.RefCount, Is.EqualTo(1));
                    Assert.That(payload.Deleted, Is.False);
                });
            }
        } finally {
            await onServer(() => payload.DecRef());
        }
        await onServer(() => {
        Assert.That(payload.Deleted, Is.True);
        using var located = refs.LocateRef(id);
        Assert.That(located.IsNull, Is.True);
        Assert.That(manager.LastDMException, Is.Null, "Async return fixture produces no engine runtime errors");
        TestContext.Progress.WriteLine("Async return ownership: 2000 connected Call/CallNoWait deliveries, 2000 reentrant calls, 1000 pending-return replacements/cancellations and 1000 live canceled-TCS refused deliveries passed");
        });
    }
}
