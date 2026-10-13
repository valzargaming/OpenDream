using System;
using Lidgren.Network;
using Robust.Shared.Network;
using Robust.Shared.Serialization;

namespace OpenDreamShared.Network.Messages;

public sealed class MsgNativeIdentityChallenge : NetMessage {
    // Admission precedes InGame; entity traffic is not available yet.
    public override MsgGroups MsgGroup => MsgGroups.Core;
    public Guid Epoch;
    public string Nonce = "";
    public override void ReadFromBuffer(NetIncomingMessage buffer, IRobustSerializer serializer) {
        Epoch = new Guid(buffer.ReadBytes(16));
        Nonce = Convert.ToHexString(buffer.ReadBytes(32));
    }
    public override void WriteToBuffer(NetOutgoingMessage buffer, IRobustSerializer serializer) {
        buffer.Write(Epoch.ToByteArray());
        var nonce = Convert.FromHexString(Nonce);
        if (nonce.Length != 32) throw new FormatException("Invalid native identity challenge.");
        buffer.Write(nonce);
    }
}
