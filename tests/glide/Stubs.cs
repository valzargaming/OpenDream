global using System.Numerics;
global using Robust.Shared.GameObjects;
global using Robust.Shared.IoC;
global using Robust.Shared.Maths;
namespace Robust.Shared.IoC { public class DependencyAttribute : Attribute {} }
namespace Robust.Shared.Maths {
    public static class MathHelper { public static bool CloseTo(float a, float b) => Math.Abs(a-b) < 0.00001f; }
    public static class VectorExtensions { public static bool EqualsApprox(this Vector2 a, Vector2 b) => Vector2.Distance(a,b) < 0.00001f; }
}
namespace Robust.Shared.Utility {
    public static class ListExtensions { public static void RemoveSwap<T>(this List<T> list, int i) { list[i]=list[^1]; list.RemoveAt(list.Count-1); } }
}
namespace Robust.Shared.Timing { public interface IGameTiming { ushort TickRate {get;} } }
namespace Robust.Shared.GameObjects {
    public record struct EntityUid(int Value);
    public class TransformComponent { public Vector2 LocalPosition; }
    public record struct Coordinates(Vector2 PositionValue) { public Vector2 Position => PositionValue; }
    public struct MoveEvent { public bool ParentChanged; public EntityUid Sender; public TransformComponent Component; public Coordinates OldPosition; public Coordinates NewPosition; }
    public delegate void MoveHandler(ref MoveEvent e);
    public class SharedTransformSystem {}
    public interface IEntityManager { bool Deleted(EntityUid uid); EntityQuery<T> GetEntityQuery<T>() => new() {Value=(T)EntitySystem.QueryValue}; }
    public struct EntityQuery<T> { public T Value; public bool TryGetComponent(EntityUid uid, out T value) {value=Value; return true;} }
    public class EntitySystem {
        public List<Type> UpdatesBefore = new();
        public static object QueryValue = null!;
        protected EntityQuery<T> GetEntityQuery<T>() => new() { Value=(T)QueryValue };
        public virtual void Initialize() {} public virtual void Shutdown() {} public virtual void FrameUpdate(float dt) {}
    }
}
namespace Robust.Client.Graphics {
    public class Appearance { public float GlideSize; }
    public class Icon { public Appearance? Appearance = new(); }
    public class DMISpriteComponent { public Icon Icon = new(); }
}
namespace OpenDreamClient.Interface { public interface IDreamInterfaceManager { int IconSize {get;} } }
namespace Robust.Client.GameObjects {
    public class TransformSystem {
        public event MoveHandler? OnGlobalMoveEvent;
        public void Reset() {}
        public void SetLocalPositionNoLerp(EntityUid uid, Vector2 pos, TransformComponent transform) {transform.LocalPosition=pos;}
        public void Receive(TransformComponent transform, Vector2 target) {
            var e=new MoveEvent { Sender=new(1), Component=transform, OldPosition=new(transform.LocalPosition), NewPosition=new(target) };
            transform.LocalPosition=target; OnGlobalMoveEvent?.Invoke(ref e);
        }
    }
}
