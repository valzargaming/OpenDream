using System;
using System.Collections.Generic;
using OpenDreamRuntime.Procs.Native;

namespace OpenDreamRuntime.NativeByondBridge;

/// <summary>Game-thread owner between channel observation and DM client construction.</summary>
public sealed class NativeIdentityAdmissionGate : IDisposable {
    private sealed class Attempt(long started) {
        public readonly long Started = started;
        public NativeClientReportLedger.Claim? Claim;
    }
    private readonly Dictionary<NativeClientReportLedger.SessionBinding, Attempt> _attempts = new();
    private readonly NativeClientReportLedger _reports;
    private readonly Func<NativeClientReportLedger.SessionBinding, bool> _current;
    private readonly TimeProvider _time;
    public Guid Epoch => _reports.Epoch;
    public int Count => _attempts.Count;

    public NativeIdentityAdmissionGate(Func<NativeClientReportLedger.SessionBinding, bool> current,
        TimeProvider? time = null) {
        _current = current;
        _time = time ?? TimeProvider.System;
        _reports = new NativeClientReportLedger(DreamProcNativeHelpers.Ckey, current, _time);
    }

    public bool TryBegin(NativeClientReportLedger.SessionBinding binding, out string nonce) {
        nonce = "";
        if (_attempts.Count >= NativeClientReportLedger.MaximumPending || !_reports.TryBegin(binding, out nonce))
            return false;
        _attempts[binding] = new Attempt(_time.GetTimestamp());
        return true;
    }

    public bool TryAccept(NativeClientReportLedger.SessionBinding binding, ReadOnlySpan<byte> body) {
        if (!_attempts.TryGetValue(binding, out var attempt) || attempt.Claim.HasValue || Expired(attempt) ||
            !_reports.TryAccept(binding, body, out var ticket)) return false;
        return _reports.TryDeliver(ticket, (active, claim) => {
            if (active != binding || !_current(active) || Expired(attempt)) return false;
            attempt.Claim = claim;
            return true;
        });
    }

    // Called immediately before client/mob effects, on the same engine thread.
    public bool TryConsume(NativeClientReportLedger.SessionBinding binding, out NativeClientReportLedger.Claim claim) {
        claim = default;
        if (!_attempts.Remove(binding, out var attempt)) return false;
        _reports.Cancel(binding);
        if (Expired(attempt) || !_current(binding) || attempt.Claim is not { } observed) return false;
        claim = observed;
        return true;
    }

    public void Disconnect(NativeClientReportLedger.SessionBinding binding) {
        _attempts.Remove(binding);
        _reports.Cancel(binding);
    }

    public void PruneExpired(Action<NativeClientReportLedger.SessionBinding> expired) {
        _reports.PruneExpired();
        List<NativeClientReportLedger.SessionBinding>? remove = null;
        foreach (var pair in _attempts) {
            if (Expired(pair.Value) || !_current(pair.Key)) (remove ??= new()).Add(pair.Key);
        }
        if (remove == null) return;
        foreach (var binding in remove) {
            Disconnect(binding);
            expired(binding);
        }
    }

    private bool Expired(Attempt attempt) => _time.GetElapsedTime(attempt.Started) >= NativeClientReportLedger.Lifetime;
    public void Dispose() { _attempts.Clear(); _reports.Dispose(); }
}
