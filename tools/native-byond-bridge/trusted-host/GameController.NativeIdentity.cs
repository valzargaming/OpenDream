using System;
using Robust.Client.NativeByond;
using Robust.Shared.Configuration;
using Robust.Shared.IoC;
using Robust.Shared.Timing;

namespace Robust.Client;

// Compiled into the trusted engine, never into a downloadable content assembly.
internal sealed partial class GameController {
    private bool _startupSmoke;

    private void InitializeNativeIdentity() {
        // Snapshot operator configuration before any content code is loaded. Content
        // can request an observation, but cannot choose executables or helper paths.
        var options = new NativeObserverOptions(
            _configurationManager.GetCVar(NativeHostCVars.ByondBin),
            _configurationManager.GetCVar(NativeHostCVars.ObserverDirectory));
        _startupSmoke = _configurationManager.GetCVar(NativeHostCVars.StartupSmoke);
        var address = "";
        if (LaunchState.ConnectEndpoint is { } endpoint) {
            var host = endpoint.Host.Contains(':') ? $"[{endpoint.Host}]" : endpoint.Host;
            address = $"{host}:{endpoint.Port}";
        }
        IoCManager.RegisterInstance<NativeIdentityCoordinator>(new NativeIdentityCoordinator(
            new NativeIdentityObserverProvider(new FileNativeObserverHost(), () => options),
            startupAddress: address));
    }

    private void ConfigureStartupSmokeExit() {
        if (!_startupSmoke) return;
        var loop = _mainLoop ?? throw new InvalidOperationException("Startup smoke requires the client loop.");
        // Registered after the normal Update handler: disconnected menus pause
        // simulation ticks, but still complete real client frame updates.
        void QuitAfterFrame(object? sender, FrameEventArgs frame) {
            loop.Update -= QuitAfterFrame;
            if (!loop.Running) throw new InvalidOperationException("Startup smoke frame did not complete in a running loop.");
            _logger.Info("PASS native identity startup smoke client frame");
            _console.ExecuteCommand("quit");
        }
        loop.Update += QuitAfterFrame;
    }
}

[CVarDefs]
internal abstract class NativeHostCVars {
    public static readonly CVarDef<bool> StartupSmoke =
        CVarDef.Create("opendream.startup_smoke", false, CVar.CLIENTONLY);
    public static readonly CVarDef<string> ByondBin =
        CVarDef.Create("opendream.native_byond_bin", "", CVar.CLIENTONLY);
    public static readonly CVarDef<string> ObserverDirectory =
        CVarDef.Create("opendream.native_observer_directory", "", CVar.CLIENTONLY);
}
