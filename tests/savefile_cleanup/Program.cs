using System.Runtime.CompilerServices;

internal static class Program {
    private static int _assertions;
    private static void Check(bool value, string message) {
        _assertions++;
        if (!value) throw new Exception("FAIL: " + message);
    }
    private static void Empty(string label) {
        Check(Registry.Instance.Count == 0, label + " retains registered refs");
        Check(DreamObjectSavefile.Savefiles.Count == 0, label + " retains savefile handles");
        Check(DreamObjectSavefile.DirtyCount == 0, label + " retains dirty handles");
        Check(DreamObjectSavefile.DirectoryCount == 0, label + " retains directory cache");
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference NullResource() {
        var file = new DreamObjectSavefile();
        var child = new DreamObject();
        file.AttachVariable(child);
        child.DecRef();
        file.DecRef();
        Check(file.Deleted && child.Deleted, "null-resource deletion releases object variables");
        file.Delete(); // Idempotent deletion must not re-run cleanup.
        return new(file);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference Malformed(string path) {
        var file = new DreamObjectSavefile();
        try {
            file.Initialize(new(path));
            throw new Exception("FAIL: malformed input accepted");
        } catch (InvalidDataException error) {
            Check(error.Message.Contains("Error parsing savefile"), "malformed-input error preserved");
        } finally { file.DecRef(); }
        Check(file.Deleted, "malformed initialization retains registered object");
        return new(file);
    }
    private static DreamObjectSavefile Open(string path) {
        var file = new DreamObjectSavefile();
        file.Initialize(new(path));
        return file;
    }
    private static void InitializationFailures() {
        var failure = new IOException("fixture injected resource load failure");
        var file = new DreamObjectSavefile();
        DreamResourceManager.LoadFailure = failure;
        try { file.Initialize(new("load-failure.json")); throw new Exception("FAIL: load error swallowed"); }
        catch (IOException error) { Check(ReferenceEquals(error, failure), "resource-load exception changed"); }
        finally { DreamResourceManager.LoadFailure = null; file.DecRef(); }
        Check(file.Deleted, "resource load failure retains object"); Empty("resource load failure");

        failure = new IOException("fixture injected first write failure");
        file = new DreamObjectSavefile();
        DreamResourceManager.NextClearFailure = failure;
        try { file.Initialize(new("first-write-failure.json")); throw new Exception("FAIL: first write error swallowed"); }
        catch (IOException error) { Check(ReferenceEquals(error, failure), "first-write exception changed"); }
        file.DecRef(); // File never existed, so Close must not retry the failed write.
        Check(file.Deleted && !File.Exists("first-write-failure.json"), "failed creation retained object or created file");
        Empty("first write failure");
    }
    private static void FlushFailure(bool shared) {
        var path = shared ? "shared-failure.json" : "last-failure.json";
        File.WriteAllText(path, "{}");
        var first = Open(path);
        var second = shared ? Open(path) : null;
        first.MarkDirty();
        var failure = new IOException("fixture injected flush failure");
        first.Resource!.ClearFailure = failure;
        try { first.DecRef(); throw new Exception("FAIL: flush error swallowed"); }
        catch (IOException error) { Check(ReferenceEquals(error, failure), "original flush exception propagates"); }
        Check(first.Deleted, "flush failure retains registered object");
        Check(DreamObjectSavefile.DirtyCount == 0, "flush failure retains dirty handle");
        Check(!DreamObjectSavefile.Savefiles.Contains(first), "flush failure retains open handle");
        var clearCalls = first.Resource.ClearCalls;
        first.Delete();
        Check(first.Resource.ClearCalls == clearCalls, "deleted failed handle flushes twice");
        Check(File.ReadAllText(path) == "{}", "injected pre-write failure changed disk bytes");
        if (second != null) {
            Check(DreamObjectSavefile.DirectoryCount == 1 && Registry.Instance.Count == 1,
                "failed shared close prematurely drops surviving handle/cache");
            second.CurrentDir["continued"] = "yes";
            second.DecRef();
            Check(File.ReadAllText(path).Contains("continued"), "surviving shared handle cannot flush");
        }
        Empty(shared ? "shared flush failure" : "last flush failure");
    }
    private static int Main() {
        try {
            var watched = new List<WeakReference>();
            for (var i = 0; i < 100; i++) { watched.Add(NullResource()); Empty("null-resource batch"); }
            File.WriteAllText("malformed.json", "{ invalid JSON - preserve these bytes");
            for (var i = 0; i < 100; i++) { watched.Add(Malformed("malformed.json")); Empty("malformed batch"); }
            Check(File.ReadAllText("malformed.json") == "{ invalid JSON - preserve these bytes",
                "malformed cleanup overwrites invalid input");
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            Check(watched.All(reference => !reference.IsAlive), "retired savefiles remain CLR rooted");
            InitializationFailures();
            File.WriteAllText("shared.json", "{}");
            var first = Open("shared.json"); var second = Open("shared.json");
            Check(ReferenceEquals(first.CurrentDir, second.CurrentDir), "open handles do not share directory");
            first.CurrentDir["value"] = "shared payload";
            first.DecRef();
            Check(second.CurrentDir.ContainsKey("value") && DreamObjectSavefile.DirectoryCount == 1,
                "closing one handle drops shared contents");
            second.DecRef(); Empty("shared close");
            Check(File.ReadAllText("shared.json").Contains("shared payload"), "normal close fails to flush payload");
            var missing = Open("removed.json"); File.Delete("removed.json"); missing.DecRef();
            Check(!File.Exists("removed.json"), "close recreated removed file"); Empty("removed file");
            FlushFailure(false); FlushFailure(true);
            var temporary = new DreamObjectSavefile(); temporary.Initialize(new(null));
            var temporaryPath = temporary.Resource!.ResourcePath;
            Check(File.Exists(temporaryPath), "temporary initialization did not create file");
            temporary.DecRef(); Check(!File.Exists(temporaryPath), "temporary deletion left disk file"); Empty("temporary close");
            Console.WriteLine($"PASS {_assertions} production savefile cleanup assertions");
            return 0;
        } catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
    }
}
