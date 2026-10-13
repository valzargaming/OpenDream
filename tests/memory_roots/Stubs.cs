using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
namespace JetBrains.Annotations { [AttributeUsage(AttributeTargets.All)] public sealed class HandlesResourceDisposalAttribute: Attribute {} }
namespace DMCompiler.DM { public enum ProcAttributes { None } }
namespace Robust.Shared.IoC { [AttributeUsage(AttributeTargets.All)] public sealed class DependencyAttribute: Attribute {} }
namespace OpenDreamRuntime.Resources { public sealed class DreamResourceManager {} }
namespace OpenDreamRuntime.Objects {
    public sealed class TreeEntry {}
    public class DreamObject {
        public int RefCount = 1;
        public bool Deleted, Matches = true;
        public DreamList? Contents;
        public DreamObject? Loc;
        public Definition ObjectDefinition = new();
        public void IncRef() { if (!Deleted) RefCount++; }
        public void DecRef() { if (Deleted) return; if (--RefCount == 0) { HandleDeletion(); Deleted = true; } else if (RefCount < 0) throw new Exception("double ownership release"); }
        protected virtual void HandleDeletion() {}
        public bool IsSubtypeOf(TreeEntry _) => !Deleted && Matches;
        public DreamValue GetVariable(string name) { var value = new DreamValue(name == "contents" ? Contents : Loc); value.IncRef(); return value; }
        public bool TryGetVariable(string name, out DreamValue value) { value = GetVariable(name); return !value.IsNull; }
    }
    public sealed class Definition { public DreamObjectTree ObjectTree = new(); public OpenDreamRuntime.AtomManager AtomManager = new(); }
    public sealed class DreamObjectTree { public DreamList CreateList(int size = 0) => new(size); }
}
namespace OpenDreamRuntime.Objects.Types {
    public interface IDreamList { bool IsAssociative { get; } DreamValue[] CopyToArray(); Dictionary<DreamValue,DreamValue> CopyAssocValues(); }
    public class DreamObjectAtom: DreamObject { public Appearance Appearance = new(); }
    public sealed class Appearance { public int Invisibility; }
    public sealed class DreamObjectArea: DreamObjectAtom { public List<DreamObjectTurf> Turfs = []; }
    public sealed class Cell { public DreamObjectArea Area = null!; }
    public sealed class DreamObjectTurf: DreamObjectAtom { public Cell Cell = new(); }
    public sealed class DreamObjectWorld: DreamObject {}
    public class WorldContentsList: DreamList {}
    public partial class DreamList: DreamObject, IDreamList {
        private static readonly Stack<List<DreamValue>> ListPool = new();
        private readonly List<DreamValue> _values;
        private Dictionary<DreamValue,DreamValue>? _associativeValues;
        public bool IsAssociative => _associativeValues is { Count: > 0 };
        public DreamList(int size = 0) { _values = new(size); }
        public IEnumerable<DreamValue> EnumerateValues() => _values;
        public DreamValue[] CopyToArray() => _values.ToArray();
        public int Count => _values.Count;
        public static int PooledValues => ListPool.Sum(list => list.Count);
        public void UpdateTracyContentsMemory() {}
    }
}
namespace OpenDreamRuntime {
    public sealed class DreamManager { public const int ListPoolThreshold = 4, ListPoolSize = 64; }
    public sealed class AtomManager {
        public IEnumerable<DreamObjectAtom> EnumerateAtoms(TreeEntry? _) => [];
        public Appearance MustGetAppearance(DreamObjectAtom atom) => atom.Appearance;
    }
    public readonly record struct DreamValue(DreamObject? Object): IDisposable {
        public static DreamValue Null => default;
        public bool IsNull => Object == null;
        public DreamValue(float _): this((DreamObject?)null) {}
        public void IncRef() => Object?.IncRef();
        public void DecRef() => Object?.DecRef();
        public void Dispose() => DecRef();
        public bool TryGetValueAsDreamObject(out DreamObject? value) { value = Object; return value != null && !value.Deleted; }
        public bool TryGetValueAsDreamObject<T>(out T value) where T: DreamObject { value = (Object as T)!; return value != null && !value.Deleted; }
        public bool TryGetValueAsDreamList(out DreamList value) { value = (Object as DreamList)!; return value != null; }
        public DreamList MustGetValueAsDreamList() => Object as DreamList ?? throw new InvalidOperationException("expected list");
        public bool TryGetValueAsIDreamList(out IDreamList value) { value = (Object as IDreamList)!; return value != null; }
    }
    public sealed class DreamThread {
        public Func<DreamValue>? OnResume;
        public DreamValue Resume() => OnResume?.Invoke() ?? default;
        public Procs.ProcStatus HandleDefer() => Procs.ProcStatus.Deferred;
        public void PushProcState(Procs.ProcState _) {}
    }
}
namespace OpenDreamRuntime.Procs {
    public enum DreamReference { NoRef, Value, Association }
    public enum ProcStatus { Returned, Called, Deferred }
    public sealed class DMProcState: IDisposable {
        public bool ThrowAssignment;
        private DreamValue _value, _association;
        public void AssignReference(DreamReference reference, DreamValue value) {
            if (ThrowAssignment) throw new InvalidOperationException("assignment control");
            if (reference == DreamReference.NoRef) return;
            value.IncRef();
            if (reference == DreamReference.Value) { _value.Dispose(); _value = value; } else { _association.Dispose(); _association = value; }
        }
        public void Dispose() { _value.Dispose(); _association.Dispose(); _value = _association = default; }
    }
    public static class IoCManager { public static void InjectDependencies(object _) {} }
    public abstract class DreamProc {
        public DreamProc(params object?[] _) {}
        public virtual ProcState CreateState(DreamThread thread, DreamObject? src, DreamObject? usr, DreamProcArguments arguments) => throw new NotImplementedException();
    }
    public abstract class ProcState: IDisposable {
        private static int _idCounter;
        public int Id = -1, ArgumentCount;
        public DreamThread Thread = null!;
        public DreamValue Result;
        public DreamObject? Instance, Usr;
        public bool WaitFor;
        public abstract DreamProc? Proc { get; }
        protected void Initialize(DreamThread thread, bool waitFor) { Thread = thread; WaitFor = waitFor; Id = _idCounter++; }
        public virtual void Dispose() { Result.Dispose(); Result = default; Thread = null!; Id = -1; }
        public abstract ProcStatus Resume();
        public virtual void ReturnedInto(DreamValue value) {}
        public virtual void Cancel() {}
        public abstract void AppendStackFrame(System.Text.StringBuilder builder);
        public abstract ReadOnlySpan<DreamValue> GetArguments();
        public abstract void SetArgument(int id, DreamValue value);
    }
    public readonly struct DreamProcArguments: IDisposable {
        public readonly DreamValue[] Values;
        public int Count => Values?.Length ?? 0;
        public DreamProcArguments() { Values = []; }
        public DreamProcArguments(DreamValue[] values) { Values = values; foreach (var value in values) value.IncRef(); }
        public void Dispose() { foreach (var value in Values) value.Dispose(); }
    }
    public sealed partial class ProcScheduler { private readonly Queue<TaskCompletionSource> _deferredTasks = new(); private void UpdateDelays() {} }
}
namespace OpenDreamRuntime.Procs.Native {
    public readonly record struct ViewRange(int Width, int Height);
    public static partial class DreamProcNativeHelpers {
        public static List<DreamObjectTurf> Surrounding = [];
        public static IEnumerable<DreamObjectTurf> MakeViewSpiral(DreamObjectAtom _, ViewRange __) => Surrounding;
    }
}
