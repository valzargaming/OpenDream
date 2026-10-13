using System;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace OpenDreamClient.NativeByond;

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
public sealed class NativeIdentityCoordinator(INativeIdentityProvider provider) : IDisposable {
    private CancellationTokenSource? _cancellation;
    private Task<NativeIdentityReport?>? _pending;
    private NativeIdentityRequest _request;
    private NativeIdentityReport? _identity;
    private bool _handshakeUsed;
    private bool _disposed;
    public NativeIdentityReport? Identity => _identity;
    public bool Pending => _pending != null;

    public void Begin() {
        ObjectDisposedException.ThrowIf(_disposed, this);
        Clear();
        _request = new NativeIdentityRequest(Guid.NewGuid(), Convert.ToHexString(RandomNumberGenerator.GetBytes(32)));
        _cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        try {
            _pending = provider.ObserveAsync(_request, _cancellation.Token);
        } catch {
            Clear();
        }
    }

    // Poll from the client frame, keeping UI and connection effects on its own thread.
    public bool Poll() {
        if (_pending == null) return true;
        if (_cancellation!.IsCancellationRequested) {
            Clear();
            return true;
        }
        if (!_pending.IsCompleted) return false;
        var pending = _pending;
        _pending = null;
        if (pending.Status == TaskStatus.RanToCompletion && pending.Result is { } report &&
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

    public void Clear() {
        _identity = null;
        _handshakeUsed = false;
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
