using Robust.Client.NativeByond;
using Robust.Shared.Configuration;
using Robust.Shared.IoC;

namespace Robust.Client;

// Compiled into the trusted engine, never into a downloadable content assembly.
internal sealed partial class GameController {
    private void InitializeNativeIdentity() {
        // Snapshot operator configuration before any content code is loaded. Content
        // can request an observation, but cannot choose executables or helper paths.
        var options = new NativeObserverOptions(
            _configurationManager.GetCVar(NativeHostCVars.ByondBin),
            _configurationManager.GetCVar(NativeHostCVars.ObserverDirectory));
        var address = "";
        if (LaunchState.ConnectEndpoint is { } endpoint) {
            var host = endpoint.Host.Contains(':') ? $"[{endpoint.Host}]" : endpoint.Host;
            address = $"{host}:{endpoint.Port}";
        }
        IoCManager.RegisterInstance<NativeIdentityCoordinator>(new NativeIdentityCoordinator(
            new NativeIdentityObserverProvider(new FileNativeObserverHost(), () => options),
            startupAddress: address));
    }
}

[CVarDefs]
internal abstract class NativeHostCVars {
    public static readonly CVarDef<string> ByondBin =
        CVarDef.Create("opendream.native_byond_bin", "", CVar.CLIENTONLY);
    public static readonly CVarDef<string> ObserverDirectory =
        CVarDef.Create("opendream.native_observer_directory", "", CVar.CLIENTONLY);
}
