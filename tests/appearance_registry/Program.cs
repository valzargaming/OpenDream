using System.Runtime.CompilerServices;

try {
var registry = new ProductionRegistry();
for (var iteration = 0; iteration < 100; iteration++) {
    Collect();
    registry.Drain();
    ReplaceCollectedAppearance(registry, iteration);
}
Collect();
registry.Drain();
if (registry.LookupCount != 0 || registry.IdCount != 0)
    throw new Exception($"Final registry retained metadata: lookup={registry.LookupCount}, IDs={registry.IdCount}");
Console.WriteLine("PASS 100 collected appearances replaced with equal live appearances: retired IDs removed, live replacements preserved, final registry empty.");
Console.WriteLine("Source-extracted production registration, removal and ProxyWeakRef; stand-in appearance payload. No live engine or heap attribution.");
return 0;
} catch (Exception exception) {
    Console.Error.WriteLine($"FAIL {exception.Message}");
    return 1;
}

[MethodImpl(MethodImplOptions.NoInlining)]
static void ReplaceCollectedAppearance(ProductionRegistry registry, int iteration) {
    var retired = RegisterRetired(registry, iteration);
    Collect();
    if (retired.Weak.TryGetTarget(out _)) throw new Exception("Retired appearance remained strongly rooted");
    var replacement = new ImmutableAppearance(iteration, registry);
    registry.AddAppearance(replacement);
    registry.ClearSendQueue();
    if (registry.LookupCount != 2 || registry.IdCount != 2) throw new Exception("Expected dead and replacement appearance proxies");
    registry.Drain();
    if (registry.HasId(retired.Id) || registry.LookupCount != 1 || registry.IdCount != 1)
        throw new Exception($"Retired metadata retained after replacement: lookup={registry.LookupCount}, IDs={registry.IdCount}");
    GC.KeepAlive(replacement);
}

[MethodImpl(MethodImplOptions.NoInlining)]
static (uint Id, WeakReference<ImmutableAppearance> Weak) RegisterRetired(ProductionRegistry registry, int value) {
    var appearance = new ImmutableAppearance(value, registry);
    registry.AddAppearance(appearance);
    registry.ClearSendQueue();
    return (appearance.MustGetId(), new WeakReference<ImmutableAppearance>(appearance));
}

static void Collect() {
    GC.Collect();
    GC.WaitForPendingFinalizers();
    GC.Collect();
}

public sealed class ImmutableAppearance(int value, ProductionRegistry registry) : IEquatable<ImmutableAppearance> {
    private uint? _id;
    public void MarkRegistered(uint id) => _id = id;
    public bool TryGetId(out uint? id) { id = _id; return id.HasValue; }
    public uint MustGetId() => _id!.Value;
    public override int GetHashCode() => value;
    public bool Equals(ImmutableAppearance? other) => other is not null && other.GetHashCode() == value;
    ~ImmutableAppearance() { if (_id is { } id) registry.Retire(id); }
}
