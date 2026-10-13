using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Procs;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void ProcInitializationReleasesOwnedValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs) {
        Assert.That(tree.TryGetGlobalProc("proc_initialization_boundary_probe", out var boundary), Is.True);
        Assert.That(tree.TryGetGlobalProc("proc_initialization_locals_probe", out var locals), Is.True);
        Assert.That(tree.TryGetGlobalProc("proc_initialization_arglist_probe", out var arglist), Is.True);
        Assert.That(tree.TryGetGlobalProc("proc_initialization_null_probe", out var nullProc), Is.True);
        var dm = (DMProc)boundary!;
        var dmLocals = (DMProc)locals!;
        Assert.That(dm.IsNullProc, Is.False);
        Assert.That(dm.LocalCount, Is.Zero);
        Assert.That(dmLocals.LocalCount, Is.GreaterThan(0));
        Assert.That(((DMProc)nullProc!).IsNullProc, Is.True);
        var payload = tree.CreateObject(tree.Datum);
        var instance = tree.CreateObject(tree.Datum);
        var usr = tree.CreateObject(tree.Datum);
        var ids = new[] { payload.RefId, instance.RefId, usr.RefId };
        var asyncProc = new AsyncNativeProc(-1, tree.Root, "initialization_async_probe",
            new List<string>(), new Dictionary<string, DreamValue>(), _ => Task.FromResult(DreamValue.Null));
        static DreamValue[] Arguments(int count, DreamObject owner) {
            var values = new DreamValue[count];
            Array.Fill(values, DreamValue.Null);
            values[0] = new DreamValue(owner);
            return values;
        }
        try {
            for (var iteration = 0; iteration < 1000; iteration++) {
                var padded = dm.CreateState(new DreamThread("missing declared argument"), instance, usr, new DreamProcArguments());
                Assert.That(padded.GetArguments().Length, Is.EqualTo(1));
                Assert.That(padded.GetArguments()[0].IsNull, Is.True);
                padded.Dispose();
                var empty = nullProc!.CreateState(new DreamThread("null procedure"), instance, usr,
                    new DreamProcArguments(Arguments(257, payload)));
                empty.Dispose();
                Assert.That(payload.RefCount, Is.EqualTo(1), "Null procedures retain their existing oversized input disposal");
                var accepted = asyncProc.CreateState(new DreamThread("accepted async initialization"), null, null,
                    new DreamProcArguments(Arguments(128, payload)));
                Assert.That(accepted.GetArguments().Length, Is.EqualTo(128));
                Assert.That(payload.RefCount, Is.EqualTo(2));
                accepted.Dispose();
                var asyncPool = AsyncNativeProc.AsyncNativeProcState.Pool.Count;
                var asyncError = Assert.Throws<ArgumentException>(() => asyncProc.CreateState(
                    new DreamThread("rejected async initialization"), null, null,
                    new DreamProcArguments(Arguments(129, payload))));
                Assert.That(asyncError!.ParamName, Is.EqualTo("destination"));
                Assert.That(payload.RefCount, Is.EqualTo(1), "Rejected async initialization releases input owner");
                Assert.That(AsyncNativeProc.AsyncNativeProcState.Pool.Count, Is.EqualTo(asyncPool));

                foreach (var proc in new[] { dm, dmLocals }) {
                    var capacity = 256 - proc.LocalCount;
                    using (var result = DreamThread.Run(proc, instance, usr, Arguments(capacity, payload))) {
                        Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(capacity), "Supported argument/local boundary executes real DM");
                    }
                    Assert.That(payload.RefCount, Is.EqualTo(1));
                    Assert.That(instance.RefCount, Is.EqualTo(1));
                    Assert.That(usr.RefCount, Is.EqualTo(1));
                    var dmPool = DMProcState.Pool.Count;
                    Assert.Throws<IndexOutOfRangeException>(() => proc.CreateState(
                        new DreamThread("rejected DM initialization"), instance, usr,
                        new DreamProcArguments(Arguments(capacity + 1, payload))));
                    Assert.That(payload.RefCount, Is.EqualTo(1), "Rejected DM initialization releases input and partial owners");
                    Assert.That(instance.RefCount, Is.EqualTo(1), "Rejected DM initialization acquires no instance owner");
                    Assert.That(usr.RefCount, Is.EqualTo(1), "Rejected DM initialization acquires no usr owner");
                    Assert.That(DMProcState.Pool.Count, Is.EqualTo(dmPool));
                }

                foreach (var native in new[] { 0, 1 }) {
                    using var result = DreamThread.Run(arglist!, manager.WorldInstance, null,
                        new DreamValue(payload), new DreamValue(native));
                    Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1), "Real DM arglist reaches and catches frame capacity rejection");
                    Assert.That(payload.RefCount, Is.EqualTo(1), "Rejected arglist frame releases caller input owner");
                }
                Assert.That(payload.Deleted, Is.False);
            }
            TestContext.Progress.WriteLine("Proc initialization: 1000 async128/129, DM256/257 and local-budget boundaries plus actual DM arglist rejections; balanced owners");
        } finally {
            payload.DecRef();
            instance.DecRef();
            usr.DecRef();
        }
        foreach (var id in ids) {
            using var located = refs.LocateRef(id);
            Assert.That(located.IsNull, Is.True, "Initialization payload leaves the actual reference manager bucket");
        }
    }
}
