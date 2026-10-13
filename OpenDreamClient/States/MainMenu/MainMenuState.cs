using System.Text.RegularExpressions;
using OpenDreamClient.NativeByond;
using Robust.Shared.Timing;
using Robust.Client;
using Robust.Client.ResourceManagement;
using Robust.Client.State;
using Robust.Client.UserInterface;
using Robust.Client.UserInterface.Controls;
using Robust.Shared;
using Robust.Shared.AuthLib;
using Robust.Shared.Configuration;
using Robust.Shared.Network;
using Robust.Shared.Utility;

namespace OpenDreamClient.States.MainMenu;

public sealed partial class MainMenuState : State {
    [Dependency] private IUserInterfaceManager _userInterfaceManager = default!;
    [Dependency] private IBaseClient _client = default!;
    [Dependency] private IClientNetManager _netManager = default!;
    [Dependency] private IResourceCache _resourceCache = default!;
    [Dependency] private IConfigurationManager _configurationManager = default!;
    [Dependency] private IGameController _controllerProxy = default!;
    [Dependency] private NativeIdentityCoordinator _nativeIdentity = default!;

    private MainMenuControl _mainMenuControl = default!;
    private bool _isConnecting;
    private string? _pendingAddress;
    private bool _handingOff;

    // ReSharper disable once InconsistentNaming
    private static readonly Regex IPv6Regex = new(@"\[(.*:.*:.*)](?::(\d+))?");

    protected override void Startup() {
        _mainMenuControl = new MainMenuControl(_resourceCache, _configurationManager);
        _userInterfaceManager.StateRoot.AddChild(_mainMenuControl);

        _mainMenuControl.QuitButton.OnPressed += QuitButtonPressed;
        _mainMenuControl.ConnectButton.OnPressed += ConnectButtonPressed;
        _mainMenuControl.AddressBox.OnTextEntered += AddressBoxEntered;

        _client.RunLevelChanged += RunLevelChanged;
    }

    protected override void Shutdown() {
        _client.RunLevelChanged -= RunLevelChanged;
        _netManager.ConnectFailed -= _onConnectFailed;

        _mainMenuControl.Dispose();
        if (!_handingOff) _nativeIdentity.Clear();
    }

    private void RunLevelChanged(object? obj, RunLevelChangedEventArgs args) {
        if (args.NewLevel == ClientRunLevel.Initialize) {
            _setConnectingState(false);
            _netManager.ConnectFailed -= _onConnectFailed;
        }
    }

    private void QuitButtonPressed(BaseButton.ButtonEventArgs args) {
        _controllerProxy.Shutdown();
    }

    private void ConnectButtonPressed(BaseButton.ButtonEventArgs args) {
        var input = _mainMenuControl.AddressBox;
        TryConnect(input.Text);
    }

    private void AddressBoxEntered(LineEdit.LineEditEventArgs args) {
        if (_isConnecting) {
            return;
        }

        TryConnect(args.Text);
    }

    private void TryConnect(string address) {
        if (_isConnecting) return;
        _setConnectingState(true);
        _pendingAddress = address;
        _mainMenuControl.NativeAccount.Text = "Reading logged-in BYOND account...";
        _nativeIdentity.Begin();
    }

    public override void FrameUpdate(FrameEventArgs e) {
        base.FrameUpdate(e);
        if (_pendingAddress == null || !_nativeIdentity.Poll()) return;
        var address = _pendingAddress;
        _pendingAddress = null;
        if (_nativeIdentity.Identity is not { } report) {
            _mainMenuControl.NativeAccount.Text = "BYOND identity unavailable";
            _userInterfaceManager.Popup("Log into BYOND. The native identity bridge must be installed before connecting.", "BYOND account required");
            _setConnectingState(false);
            return;
        }
        _mainMenuControl.NativeAccount.Text = report.Key;
        _netManager.ConnectFailed += _onConnectFailed;
        try {
            ParseAddress(address, out var ip, out var port);
            _handingOff = true;
            _client.ConnectToServer(ip, port);
        } catch (Exception error) when (error is ArgumentException or InvalidOperationException) {
            _handingOff = false;
            _nativeIdentity.Clear();
            _userInterfaceManager.Popup($"Unable to connect: {error.Message}", "Connection error.");
            Logger.GetSawmill("opendream").Warning(error.ToString());
            _netManager.ConnectFailed -= _onConnectFailed;
            _setConnectingState(false);
        }
    }

    private void ParseAddress(string address, out string ip, out ushort port) {
        var match6 = IPv6Regex.Match(address);
        if (match6 != Match.Empty) {
            ip = match6.Groups[1].Value;
            if (!match6.Groups[2].Success) {
                port = _client.DefaultPort;
            } else if (!ushort.TryParse(match6.Groups[2].Value, out port)) {
                throw new ArgumentException("Not a valid port.");
            }

            return;
        }

        // See if the IP includes a port.
        var split = address.Split(':');
        ip = address;
        port = _client.DefaultPort;
        if (split.Length > 2) {
            throw new ArgumentException("Not a valid Address.");
        }

        // IP:port format.
        if (split.Length == 2) {
            ip = split[0];
            if (!ushort.TryParse(split[1], out port)) {
                throw new ArgumentException("Not a valid port.");
            }
        }
    }


    private void _onConnectFailed(object? _, NetConnectFailArgs args) {
        _userInterfaceManager.Popup($"Failed to connect: {args.Reason}");
        _netManager.ConnectFailed -= _onConnectFailed;
        _setConnectingState(false);
    }

    private void _setConnectingState(bool state) {
        _isConnecting = state;
        _mainMenuControl.ConnectButton.Disabled = state;
    }
}
