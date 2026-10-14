using System.Text.Json;
using OpenDreamRuntime.Resources;

// External effects use only the runner's unique temporary working directory.
// The generated source supplies production object teardown and savefile bodies.
public partial class DreamObject {
    public int RefCount = 1;
    public bool Deleted, Deleting;
    public bool ShouldGarbageCollect => true;
    public uint RefId;
    public string? Tag;
    public object ObjectDefinition = new();
    protected Dictionary<string, DreamValue>? Variables;
    protected DreamObject? _varsList;
    protected Registry DreamRefManager => Registry.Instance;
    public DreamObject() { RefId = Registry.Instance.Add(this); }
    public virtual void Initialize(DreamProcArguments args) { }
    public bool TryGetProc(string name, out object proc) { proc = null!; return false; }
    public void AttachVariable(DreamObject value) {
        value.IncRef();
        Variables = new() { ["fixture"] = new DreamValue(value) };
    }
}
public sealed class DMProc { public byte[] Bytecode = []; }
public static class DreamThread {
    public static IDisposable Run(object proc, DreamObject src, object? usr) =>
        throw new InvalidOperationException("Fixture must never execute DM procs");
}
public readonly struct DreamValue(object? value) {
    public void DecRef() { if (value is DreamObject obj) obj.DecRef(); }
    public bool TryGetValueAsString(out string? result) { result = value as string; return result != null; }
}
public readonly struct DreamProcArguments(string? path) {
    public DreamValue GetArgument(int index) => new(index == 0 ? path : null);
}
public sealed class SfDreamJsonValue : Dictionary<string, object?> { }
public static class DreamResourceManager {
    public static Exception? LoadFailure, NextClearFailure;
    public static DreamResource LoadResource(string path) {
        if (LoadFailure != null) throw LoadFailure;
        var resource = new DreamResource(path) { ClearFailure = NextClearFailure };
        NextClearFailure = null;
        return resource;
    }
}
namespace OpenDreamRuntime.Resources {
public sealed class DreamResource(string path) {
    public string ResourcePath { get; } = path;
    public Exception? ClearFailure;
    public int ClearCalls;
    public string? ReadAsString() => File.Exists(ResourcePath) ? File.ReadAllText(ResourcePath) : null;
    public void Clear() {
        ClearCalls++;
        if (ClearFailure != null) throw ClearFailure;
        File.WriteAllText(ResourcePath, "");
    }
    public void Output(DreamValue value) {
        value.TryGetValueAsString(out var text);
        File.WriteAllText(ResourcePath, text);
    }
}
}
public sealed partial class DreamObjectSavefile : DreamObject {
    public static readonly List<DreamObjectSavefile> Savefiles = new();
    private static readonly HashSet<DreamObjectSavefile> SavefilesToFlush = new();
    private static readonly Dictionary<string, SfDreamJsonValue> SavefileDirectories = new();
    private bool _isTemporary;
    private SfDreamJsonValue _rootNode = new();
    public SfDreamJsonValue CurrentDir;
    public DreamResource? Resource;
    public DreamObjectSavefile() { CurrentDir = _rootNode; }
    public void MarkDirty() => SavefilesToFlush.Add(this);
    public static int DirectoryCount => SavefileDirectories.Count;
    public static int DirtyCount => SavefilesToFlush.Count;
}
