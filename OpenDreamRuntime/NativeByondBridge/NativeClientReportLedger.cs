using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace OpenDreamRuntime.NativeByondBridge;

/// <summary>
/// Dormant client-reported native identity handoff. No listener, connection hooks or DM clients.
/// Native CID and key are client reports, not authentication or server-attested identity.
/// </summary>
public sealed class NativeClientReportLedger : IDisposable {
    public readonly record struct SessionBinding(Guid SessionId, long Generation, Guid ChannelId);
    public readonly record struct Claim(string Key, string Ckey, string ComputerId);
    private sealed class Pending(SessionBinding binding, long started) {
        public readonly SessionBinding Binding = binding;
        public readonly long Started = started;
        public Guid Ticket;
        public Claim? VerifiedClaim;
    }

    public const int MaximumBodyBytes = 8192;
    public const int MaximumPending = 128;
    public static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(60);
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private readonly object _lock = new();
    private readonly Dictionary<string, Pending> _pending = new(StringComparer.Ordinal);
    private Func<string, string>? _ckey;
    private Func<SessionBinding, bool>? _isCurrent;
    private readonly TimeProvider _time;
    private bool _disposed;
    public Guid Epoch { get; } = Guid.NewGuid();

    /// <param name="ckey">Must be the engine's DreamProcNativeHelpers.Ckey.</param>
    /// <param name="isCurrent">Checks the exact active channel and session generation.</param>
    public NativeClientReportLedger(Func<string, string> ckey,
        Func<SessionBinding, bool> isCurrent, TimeProvider? time = null) {
        ArgumentNullException.ThrowIfNull(ckey);
        ArgumentNullException.ThrowIfNull(isCurrent);
        _ckey = ckey;
        _isCurrent = isCurrent;
        _time = time ?? TimeProvider.System;
    }

    public int PendingCount { get { lock (_lock) { Prune(); return _pending.Count; } } }
    // Future owner must call from its periodic update even when no reports arrive.
    public void PruneExpired() { lock (_lock) { Prune(); } }

    public bool TryBegin(SessionBinding binding, out string nonce) {
        nonce = "";
        lock (_lock) {
            Prune();
            if (_disposed || binding.SessionId == Guid.Empty || binding.ChannelId == Guid.Empty ||
                binding.Generation <= 0 || !_isCurrent!(binding)) return false;
            // A replaced challenge cannot retain an old completion ticket for the same channel.
            CancelCore(binding);
            if (_pending.Count >= MaximumPending) return false;
            nonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
            _pending.Add(nonce, new Pending(binding, _time.GetTimestamp()));
            return true;
        }
    }

    /// <summary>
    /// Accepts a bounded report on its actual authenticated connection. The future transport must
    /// enforce body-read deadlines and derive binding from that connection, never payload fields.
    /// The launcher formats the client-local native report as a form body on this channel.
    /// </summary>
    public bool TryAccept(SessionBinding binding, ReadOnlySpan<byte> body, out Guid ticket) {
        ticket = Guid.Empty;
        if (!TryParse(body, out var fields)) return false;
        lock (_lock) {
            Prune();
            if (_disposed ||
                !Guid.TryParseExact(fields["epoch"], "D", out var epoch) || epoch != Epoch ||
                !_pending.TryGetValue(fields["nonce"], out var pending) ||
                pending.Binding != binding || pending.VerifiedClaim.HasValue || !_isCurrent!(pending.Binding)) return false;
            var key = fields["key"];
            var canonical = _ckey!(key);
            // Identity comes only from the native report; never a launcher username field.
            if (canonical.Length == 0 || IsGuest(key)) return false;
            pending.VerifiedClaim = new Claim(key, canonical, fields["cid"]);
            pending.Ticket = Guid.NewGuid();
            ticket = pending.Ticket;
            return true;
        }
    }

    /// <summary>
    /// Must execute on the owning game thread. The adapter must atomically recheck its exact
    /// active binding before any effects. This prototype never creates a DM client or mob.
    /// A failed or throwing adapter consumes the ticket; it cannot be replayed.
    /// </summary>
    public bool TryDeliver(Guid ticket, Func<SessionBinding, Claim, bool> deliverIfCurrent) {
        ArgumentNullException.ThrowIfNull(deliverIfCurrent);
        lock (_lock) {
            Prune();
            if (_disposed || ticket == Guid.Empty) return false;
            string? nonce = null;
            Pending? selected = null;
            foreach (var pair in _pending) {
                if (pair.Value.Ticket != ticket) continue;
                nonce = pair.Key;
                selected = pair.Value;
                break;
            }
            if (nonce == null || selected == null || !selected.VerifiedClaim.HasValue) return false;
            _pending.Remove(nonce);
            return _isCurrent!(selected.Binding) && deliverIfCurrent(selected.Binding, selected.VerifiedClaim.Value);
        }
    }

    public void Cancel(SessionBinding binding) { lock (_lock) { CancelCore(binding); } }

    private void CancelCore(SessionBinding binding) {
        List<string>? remove = null;
        foreach (var pair in _pending) {
            if (pair.Value.Binding != binding) continue;
            (remove ??= new()).Add(pair.Key);
        }
        if (remove != null) foreach (var nonce in remove) _pending.Remove(nonce);
    }

    private void Prune() {
        List<string>? remove = null;
        foreach (var pair in _pending) {
            if (_time.GetElapsedTime(pair.Value.Started) < Lifetime) continue;
            (remove ??= new()).Add(pair.Key);
        }
        if (remove != null) foreach (var nonce in remove) _pending.Remove(nonce);
    }

    public void Dispose() {
        lock (_lock) {
            if (_disposed) return;
            _disposed = true;
            _pending.Clear();
            _ckey = null;
            _isCurrent = null;
        }
    }

    private static bool TryParse(ReadOnlySpan<byte> body, out Dictionary<string, string> fields) {
        fields = new(StringComparer.Ordinal);
        if (body.Length == 0 || body.Length > MaximumBodyBytes) return false;
        try {
            while (body.Length > 0) {
                var separator = body.IndexOf((byte)'&');
                var part = separator < 0 ? body : body[..separator];
                var equals = part.IndexOf((byte)'=');
                if (equals <= 0 || !Decode(part[..equals], out var name) ||
                    !Decode(part[(equals + 1)..], out var value) ||
                    !fields.TryAdd(name, value) || fields.Count > 4) return false;
                if (separator < 0) break;
                body = body[(separator + 1)..];
                if (body.Length == 0) return false;
            }
        } catch (DecoderFallbackException) { return false; }
        if (fields.Count != 4 || !fields.ContainsKey("epoch") || !fields.ContainsKey("nonce") ||
            !fields.ContainsKey("key") || !fields.ContainsKey("cid")) return false;
        if (!Hex(fields["nonce"]) || fields["epoch"].Length != 36 ||
            fields["key"].Length == 0 || fields["key"].Length > 128 ||
            fields["cid"].Length == 0 || fields["cid"].Length > 32) return false;
        foreach (var digit in fields["cid"]) if (digit < '0' || digit > '9') return false;
        foreach (var character in fields["key"]) if (char.IsControl(character)) return false;
        return true;
    }

    private static bool Hex(string text) {
        if (text.Length != 64) return false;
        foreach (var character in text) if (Unhex((byte)character) < 0 || character > 127) return false;
        return true;
    }

    private static bool IsGuest(string key) {
        if (!key.StartsWith("Guest-", StringComparison.Ordinal) || key.Length == 6) return false;
        foreach (var digit in key.AsSpan(6)) if (digit < '0' || digit > '9') return false;
        return true;
    }

    private static bool Decode(ReadOnlySpan<byte> encoded, out string value) {
        var bytes = new byte[encoded.Length];
        var count = 0;
        for (var i = 0; i < encoded.Length; i++) {
            var next = encoded[i];
            if (next == '%') {
                if (i + 2 >= encoded.Length) { value = ""; return false; }
                var high = Unhex(encoded[++i]);
                var low = Unhex(encoded[++i]);
                if (high < 0 || low < 0) { value = ""; return false; }
                next = (byte)((high << 4) | low);
            } else if (next == '+') next = (byte)' ';
            bytes[count++] = next;
        }
        value = StrictUtf8.GetString(bytes, 0, count);
        return true;
    }

    private static int Unhex(byte value) => value switch {
        >= (byte)'0' and <= (byte)'9' => value - '0',
        >= (byte)'a' and <= (byte)'f' => value - 'a' + 10,
        >= (byte)'A' and <= (byte)'F' => value - 'A' + 10,
        _ => -1
    };
}
