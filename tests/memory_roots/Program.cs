using System.Reflection;
using System.Text.Json;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Procs;
using OpenDreamRuntime.Procs.Native;

static void Equal(int expected, int actual, string message) {
    if (expected != actual) throw new Exception($"{message}: expected {expected}, got {actual}");
}
var rows = new List<object>();
foreach (var mode in new[] { "unfiltered-break", "filtered-break", "filtered-exception", "filtered-complete", "range", "orange", "area-range", "async-pool" }) {
    var area = new DreamObjectArea();
    var turf = new DreamObjectTurf { Cell = new() { Area = area }, Contents = new(16) };
    area.Turfs.Add(turf);
    var first = new DreamObjectAtom(); var second = new DreamObjectAtom();
    var holder = new DreamObjectAtom { Contents = new(16), Loc = turf };
    holder.Contents.AddValue(new(first)); holder.Contents.AddValue(new(second));
    turf.Contents.AddValue(new(holder));
    DreamProcNativeHelpers.Surrounding = [turf];
    var watched = new DreamObject[] { first, second, holder, holder.Contents, turf, turf.Contents, area };
    var starting = watched.Select(o => o.RefCount).ToArray();
    var poolStart = AsyncNativeProc.AsyncNativeProcState.Pool.Count;
    var scheduler = new ProcScheduler();
    for (var batch = 0; batch < 10; batch++) {
        for (var i = 0; i < 1000; i++) {
            if (mode == "async-pool") {
                AsyncNativeProc.AsyncNativeProcState state = AsyncNativeProc.AsyncNativeProcState.Pool.TryPop(out var popped) ? popped : new();
                state.ProcScheduler = scheduler;
                state.Initialize(null, _ => Task.FromResult(DreamValue.Null), new(), null, null,
                    new DreamProcArguments([new(first), new(second)]));
                state.Dispose();
                var slots = (DreamValue[])typeof(AsyncNativeProc.AsyncNativeProcState).GetField("_arguments", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(state)!;
                if (slots.Any(value => !value.IsNull)) throw new Exception("pooled arguments retain managed objects");
                if (AsyncNativeProc.AsyncNativeProcState.Pool.Count > poolStart + 1) throw new Exception("async pool must remain bounded");
            } else if (mode.Contains("range") || mode == "orange") {
                var center = mode == "area-range" ? (DreamObjectAtom)area : holder;
                var list = DreamProcNativeHelpers.HandleRange(center, new(3,3), mode != "orange");
                if (list.Count == 0) throw new Exception("range workload unexpectedly empty");
                list.DecRef();
            } else {
                using var state = new DMProcState { ThrowAssignment = mode == "filtered-exception" };
                using var enumerator = ProductionContents.Create(new(), new(holder), mode == "unfiltered-break" ? null : new());
                try {
                    if (mode == "filtered-complete") while (enumerator.Enumerate(state, DreamReference.Value, DreamReference.NoRef)) {}
                    else enumerator.Enumerate(state, DreamReference.Value, DreamReference.NoRef);
                } catch (InvalidOperationException) when (mode == "filtered-exception") {}
            }
            for (var n = 0; n < watched.Length; n++) Equal(starting[n], watched[n].RefCount, $"{mode} owned reference {n}");
            Equal(0, DreamList.PooledValues, "pooled list storage retains values");
        }
        var refs = watched.Select(o => o.RefCount).ToArray();
        rows.Add(new { mode, batch, operations = 1000, references = refs, async_pool = AsyncNativeProc.AsyncNativeProcState.Pool.Count });
    }
    holder.Contents.DecRef(); turf.Contents.DecRef();
    first.DecRef(); second.DecRef(); holder.DecRef(); turf.DecRef(); area.DecRef();
}
Console.WriteLine("PASS 80000 repeated production-body ownership operations");
Console.WriteLine(JsonSerializer.Serialize(rows));
