using System;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace Robust.Client.NativeByond;

public readonly record struct NativeIdentityRequest(Guid Epoch, string Nonce);
public readonly record struct NativeIdentityReport(Guid Epoch, string Nonce, string Key, string ComputerId);

/// <summary>The provider must observe a fresh logged-in native client for each request.</summary>
public interface INativeIdentityProvider {
    Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request, CancellationToken cancellation);
}

/// <summary>Fails closed until the real native observer and channel handoff are installed.</summary>
public sealed class UnavailableNativeIdentityProvider : INativeIdentityProvider {
    public Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request, CancellationToken cancellation) =>
        Task.FromResult<NativeIdentityReport?>(null);
}

/// <summary>
/// Client-thread coordinator. No username/config/CLI input is an identity source.
/// The native report remains client-reported, without spoof-resistance claims.
/// </summary>
public sealed class NativeIdentityCoordinator(INativeIdentityProvider provider, TimeProvider? time = null, string startupAddress = "") : IDisposable {
    public static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(60);
    private readonly TimeProvider _time = time ?? TimeProvider.System;
    private long _started;
    private bool Expired => _time.GetElapsedTime(_started) >= Lifetime;
    private CancellationTokenSource? _cancellation;
    private Task<NativeIdentityReport?>? _pending;
    private NativeIdentityRequest _request;
    private NativeIdentityReport? _identity;
    private bool _handshakeUsed;
    private bool _channelUsed;
    private bool _disposed;
    public NativeIdentityReport? Identity => _identity;
    public string StartupAddress { get; } = startupAddress;
    public bool Pending => _pending != null;

    public void Begin() {
        ObjectDisposedException.ThrowIf(_disposed, this);
        Clear();
        _request = new NativeIdentityRequest(Guid.NewGuid(), Convert.ToHexString(RandomNumberGenerator.GetBytes(32)));
        _started = _time.GetTimestamp();
        _cancellation = new CancellationTokenSource(Lifetime);
        try {
            _pending = provider.ObserveAsync(_request, _cancellation.Token);
        } catch {
            Clear();
        }
    }

    // Poll from the client frame, keeping UI and connection effects on its own thread.
    public bool Poll() {
        if (_pending == null) return true;
        if (Expired || _cancellation!.IsCancellationRequested) {
            Clear();
            return true;
        }
        if (!_pending.IsCompleted) return false;
        var pending = _pending;
        _pending = null;
        // Never wait on the frame thread: read only an already completed successful task.
        if (pending.IsCompletedSuccessfully && pending.GetAwaiter().GetResult() is { } report &&
            report.Epoch == _request.Epoch && report.Nonce == _request.Nonce && Valid(report))
            _identity = report;
        else if (pending.IsFaulted)
            _ = pending.Exception;
        _cancellation.Dispose();
        _cancellation = null;
        return true;
    }

    public bool TryAuthorizeHandshake(out NativeIdentityReport identity) {
        identity = default;
        if (Expired) Clear();
        if (_disposed || _handshakeUsed || _identity is not { } observed) return false;
        _handshakeUsed = true;
        identity = observed;
        return true;
    }

    public void AuthorizeHandshake(Action<string?> applyOverride) {
        // Clear any CLI/console name even when native acquisition failed.
        applyOverride(null);
        if (!TryAuthorizeHandshake(out var observed))
            throw new InvalidOperationException("Log into BYOND and use the native identity connection flow.");
        applyOverride(observed.Key);
    }

    public void ConnectionReset() {
        // BaseClient resets its previously rejected Connecting state before retry.
        // Preserve only the new, unused observation acquired for that retry.
        if (_identity.HasValue && !_handshakeUsed) return;
        Clear();
    }

    public bool TryTakeChannelReport(Guid epoch, string nonce, out byte[] body) {
        body = Array.Empty<byte>();
        if (Expired) Clear();
        if (_disposed || !_handshakeUsed || _channelUsed || _identity is not { } report || epoch == Guid.Empty || nonce.Length != 64)
            return false;
        foreach (var character in nonce)
            if (!(character is >= '0' and <= '9' or >= 'A' and <= 'F')) return false;
        _channelUsed = true;
        body = System.Text.Encoding.UTF8.GetBytes($"epoch={epoch:D}&nonce={nonce}&key={Uri.EscapeDataString(report.Key)}&cid={report.ComputerId}");
        _identity = null;
        return true;
    }

    public void Clear() {
        _identity = null;
        _handshakeUsed = false;
        _channelUsed = false;
        _request = default;
        _cancellation?.Cancel();
        _cancellation?.Dispose();
        _cancellation = null;
        if (_pending != null) {
            // Observe late faults but never install a canceled/replaced report.
            _ = _pending.ContinueWith(task => { _ = task.Exception; },
                CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
                TaskScheduler.Default);
            _pending = null;
        }
    }

    private static bool Valid(NativeIdentityReport report) {
        if (string.IsNullOrWhiteSpace(report.Key) || report.Key.Length > 128 ||
            report.Key.StartsWith("Guest-", StringComparison.OrdinalIgnoreCase) ||
            string.IsNullOrEmpty(report.ComputerId) || report.ComputerId.Length > 32) return false;
        foreach (var character in report.Key)
            if (char.IsControl(character)) return false;
        foreach (var character in report.ComputerId)
            if (character < '0' || character > '9') return false;
        return true;
    }

    public void Dispose() {
        if (_disposed) return;
        Clear();
        _disposed = true;
    }
}
