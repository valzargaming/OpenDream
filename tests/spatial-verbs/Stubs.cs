using System.Numerics;
using OpenDreamShared.Dream;

namespace Robust.Shared.Maths {
    public readonly record struct Vector2i(int X, int Y) {
        public static implicit operator Vector2i((int X, int Y) value) => new(value.X, value.Y);
    }
}
namespace SourceProbe {
    public enum VerbAccessibility { View, InView, OView, InOView, Range, InRange, ORange, InORange, InWorld, Usr, InUsr, UsrLoc, UsrGroup }
    public static class AccessExtensions {
        public static bool IsO(this VerbAccessibility a) => a is VerbAccessibility.OView or VerbAccessibility.InOView or VerbAccessibility.ORange or VerbAccessibility.InORange;
        public static bool IsRange(this VerbAccessibility a) => a is VerbAccessibility.Range or VerbAccessibility.InRange or VerbAccessibility.ORange or VerbAccessibility.InORange;
        public static bool IsView(this VerbAccessibility a) => !a.IsRange();
    }
    public record VerbInfo(VerbAccessibility Accessibility, int Range) {
        public bool IsHidden(bool ignore, sbyte see) => false;
    }
    public record ClientObjectReference(int Entity) { public static ClientObjectReference Client = new(-1); }
    public class Query<T> where T : class {
        public Dictionary<int, T> Values = new();
        public bool TryGetComponent(int? uid, out T value) {
            value = default!;
            return uid.HasValue && Values.TryGetValue(uid.Value, out value!);
        }
    }
    public class Sight { public sbyte SeeInvisibility; }
    public class Transform { public int GridUid = 100; public int ParentUid = 100; public Vector2 Position; }
    public class Appearance { public List<int> Verbs = [0]; public bool Opacity; }
    public class Icon { public Appearance? Appearance = new(); }
    public class Sprite { public Icon Icon = new(); }
    public class Player { public int? LocalEntity = 1; }
    public class DreamViewOverlay { public HashSet<int> EntitiesInView = [2]; }
    public class Overlays { public DreamViewOverlay View = new(); public T GetOverlay<T>() => (T)(object)View; }
    public class Transforms(Query<Transform> query) {
        public int? GetParentUid(int uid) => query.Values[uid].ParentUid;
        public Vector2 GetWorldPosition(Transform transform) => transform.Position;
    }
    public class Entities { public int GetNetEntity(int uid) => uid; }
    public partial class ClientVerbSystem {
        public Player _playerManager = new();
        public Query<Sight> _sightQuery = new();
        public Query<Sprite> _spriteQuery = new();
        public Query<Transform> _xformQuery = new();
        public Overlays _overlayManager = new();
        public Dictionary<int, VerbInfo> _verbs = new();
        public List<int>? _clientVerbs;
        public Transforms _transformSystem;
        public Entities _entityManager = new();
        public ClientVerbSystem() {
            _transformSystem = new(_xformQuery);
            _sightQuery.Values[1] = new();
            _spriteQuery.Values[2] = new();
            _xformQuery.Values[1] = new();
            _xformQuery.Values[2] = new() { Position = new(1, 0) };
        }
    }
    public class DreamObject { }
    public class DreamObjectClient : DreamObject { public VerbList ClientVerbs = new(); }
    public class VerbList { public HashSet<DreamProc> Verbs = new(); }
    public class DreamObjectAtom : DreamObject {
        public ObjectDefinition ObjectDefinition = new();
        public Appearance Appearance = new();
        public DreamList Contents = new();
        public (int X, int Y, int Z) Position;
        public FakeMap Map = null!;
        public bool TryGetVariable(string name, out DreamValue value) { value = new(Contents); return true; }
    }
    public class DreamObjectMovable : DreamObjectAtom { public DreamObject? Loc; }
    public class DreamObjectTurf : DreamObjectAtom { }
    public class DreamObjectMob : DreamObjectMovable { }
    public class DreamProc { public int? VerbId = 0; }
    public class DreamConnection { public DreamObjectMob? Mob; }
    public class ObjectDefinition { public ObjectTree ObjectTree = new(); }
    public class ObjectTree { public DreamList CreateList() => new(); }
    public readonly record struct DreamValue(object Value) : IDisposable {
        public bool TryGetValueAsDreamList(out DreamList list) { list = Value as DreamList ?? null!; return list != null; }
        public void Dispose() { }
    }
    public class DreamList {
        public static int Released;
        public List<DreamValue> Values = new();
        public void AddValue(DreamValue value) => Values.Add(value);
        public bool ContainsValue(DreamValue value) => Values.Contains(value);
        public IEnumerable<DreamValue> EnumerateValues() => Values;
        public void DecRef() => Released++;
    }
    public class AtomManager {
        public Appearance MustGetAppearance(DreamObjectAtom atom) => atom.Appearance;
        public (int X, int Y, int Z) GetAtomPosition(DreamObjectAtom atom) => atom.Position;
    }
    public class Cell { public DreamObjectTurf Turf = new(); public List<DreamObjectMovable> Movables = new(); }
    public interface IDreamMapManager { bool TryGetCellAt((int X, int Y) position, int z, out Cell cell); }
    public class FakeMap : IDreamMapManager {
        public Dictionary<(int, int), Cell> Cells = new();
        public bool TryGetCellAt((int X, int Y) position, int z, out Cell cell) {
            cell = null!;
            return z == 1 && Cells.TryGetValue(position, out cell!);
        }
    }
    public partial class ServerVerbSystem {
        public AtomManager _atomManager = new();
        public IDreamMapManager _mapManager;
        public List<VerbInfo> _verbs = new();
        public ServerVerbSystem(IDreamMapManager map) { _mapManager = map; }
        public bool TestExecute(DreamConnection connection, DreamObject src) => CanExecute(connection, src, new());
    }
    public static partial class DreamProcNativeHelpers {
        // Inert distance-only adapter: the regression checks production routing to view vs range.
        public static DreamList HandleRange(DreamObjectAtom center, ViewRange range, bool includeCenter) {
            var list = new DreamList();
            foreach (var (position, cell) in center.Map.Cells) {
                if (Math.Abs(position.Item1-center.Position.X) > range.Width/2 || Math.Abs(position.Item2-center.Position.Y) > range.Height/2)
                    continue;
                if (!includeCenter && position == (center.Position.X, center.Position.Y))
                    continue;
                list.AddValue(new(cell.Turf));
                foreach (var atom in cell.Movables) list.AddValue(new(atom));
            }
            return list;
        }
    }
}
