using System;
using Lidgren.Network;
using Robust.Shared.Network;
using Robust.Shared.Serialization;

namespace OpenDreamShared.Network.Messages;

public sealed class MsgNativeIdentityReport : NetMessage {
    public const int MaximumBodyBytes = 8192;
    public override MsgGroups MsgGroup => MsgGroups.Core;
    public byte[] Body = Array.Empty<byte>();
    public override void ReadFromBuffer(NetIncomingMessage buffer, IRobustSerializer serializer) {
        var count = buffer.ReadVariableInt32();
        if (count <= 0 || count > MaximumBodyBytes) throw new ArgumentException("Invalid native report size.");
        Body = buffer.ReadBytes(count);
    }
    public override void WriteToBuffer(NetOutgoingMessage buffer, IRobustSerializer serializer) {
        if (Body.Length <= 0 || Body.Length > MaximumBodyBytes) throw new ArgumentException("Invalid native report size.");
        buffer.WriteVariableInt32(Body.Length);
        buffer.Write(Body);
    }
}
