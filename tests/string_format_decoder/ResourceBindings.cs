// Pure bindings ONLY for the resource string-output seam, not DM/runtime tests.
namespace OpenDreamRuntime {
    public sealed class DMException(string message) : Exception(message);
    public readonly struct DreamValue(string? text) {
        public bool IsNull => text == null;
        public bool TryGetValueAsString([System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out string? value) {
            value = text;
            return text != null;
        }
    }
}

[AttributeUsage(AttributeTargets.Class)]
internal sealed class VirtualAttribute : Attribute;
