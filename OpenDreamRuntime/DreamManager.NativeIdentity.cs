using System.Linq;
using OpenDreamRuntime.NativeByondBridge;
using OpenDreamRuntime.Procs.Native;
using OpenDreamShared;
using OpenDreamShared.Network.Messages;
using Robust.Shared.Enums;
using Robust.Shared.Network;
using Robust.Shared.Player;

namespace OpenDreamRuntime;

public sealed partial class DreamManager {
    private sealed record NativeChannel(ICommonSession Session, NativeClientReportLedger.SessionBinding Binding);
    private readonly Dictionary<INetChannel, NativeChannel> _nativeChannels = new(ReferenceEqualityComparer.Instance);
    private NativeIdentityAdmissionGate? _nativeAdmission;
    private long _nativeGeneration;

    private bool CurrentNativeBinding(NativeClientReportLedger.SessionBinding binding) =>
        _nativeChannels.Values.Any(active => active.Binding == binding &&
            active.Session.Status == SessionStatus.Connected && active.Session.Channel.IsConnected &&
            _playerManager.TryGetSessionByChannel(active.Session.Channel, out var session) &&
            ReferenceEquals(session, active.Session));

    private bool BeginNativeAdmission(ICommonSession session) {
        var channel = session.Channel;
        if (_nativeChannels.Remove(channel, out var previous)) _nativeAdmission!.Disconnect(previous.Binding);
        var binding = new NativeClientReportLedger.SessionBinding(session.UserId.UserId, ++_nativeGeneration, Guid.NewGuid());
        _nativeChannels[channel] = new NativeChannel(session, binding);
        if (!_nativeAdmission!.TryBegin(binding, out var nonce)) {
            _nativeChannels.Remove(channel);
            channel.Disconnect("Native BYOND identity observation is unavailable.");
            return false;
        }
        channel.SendMessage(new MsgNativeIdentityChallenge { Epoch = _nativeAdmission.Epoch, Nonce = nonce });
        return true;
    }

    private void RxNativeIdentityReport(MsgNativeIdentityReport message) {
        if (_nativeAdmission == null || !_nativeChannels.TryGetValue(message.MsgChannel, out var active) ||
            !_nativeAdmission.TryAccept(active.Binding, message.Body)) {
            message.MsgChannel.Disconnect("Native BYOND identity report was rejected.");
            return;
        }
        // No DM client/mob is constructed until the interface ack consumes this admission.
        SendInitialInterface(active.Session);
    }

    private void UpdateNativeAdmission() {
        _nativeAdmission?.PruneExpired(binding => {
            var pair = _nativeChannels.FirstOrDefault(pair => pair.Value.Binding == binding);
            if (pair.Key == null) return;
            _nativeChannels.Remove(pair.Key);
            pair.Key.Disconnect("Native BYOND identity observation expired.");
        });
    }

    private void SendInitialInterface(ICommonSession session) => session.Channel.SendMessage(new MsgLoadInterface {
        InterfaceText = _dreamResourceManager.InterfaceFile?.ReadAsString()
    });

    private bool AdmitNativeClient(ICommonSession session) {
        if (_nativeAdmission == null) return true;
        if (!_nativeChannels.TryGetValue(session.Channel, out var active) ||
            !ReferenceEquals(active.Session, session) || !_nativeAdmission.TryConsume(active.Binding, out var claim)) {
            session.Channel.Disconnect("A fresh native BYOND identity is required.");
            return false;
        }
        _nativeChannels.Remove(session.Channel);
        // Network-session names can be rewritten by Robust; only the observed native key is authoritative here.
        if (_connections.Remove(session.UserId, out var old)) old.HandleDisconnection();
        var connection = new DreamConnection(claim.Key, claim.ComputerId);
        _connections.Add(session.UserId, connection);
        connection.HandleConnection(session);
        return true;
    }
}
