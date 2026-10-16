using System;
using System.Threading;
using System.Threading.Tasks;

namespace Robust.Client.NativeByond;

internal readonly record struct NativeObserverOptions(string ByondBin, string ObserverDirectory);

/// <summary>Owns only the temporary observation world it created, never a game or existing client.</summary>
internal interface INativeObservation : IAsyncDisposable {
    Task<NativeIdentityReport?> ReadAsync(NativeIdentityRequest request, CancellationToken cancellation);
}

internal interface INativeObserverHost {
    Task<INativeObservation> StartAsync(NativeObserverOptions options, NativeIdentityRequest request,
        CancellationToken cancellation);
}

/// <summary>External effects are injected. Each completed, failed or canceled attempt releases its world.</summary>
internal sealed class NativeIdentityObserverProvider(INativeObserverHost host,
    Func<NativeObserverOptions> options) : INativeIdentityProvider {
    private readonly SemaphoreSlim _serial = new(1, 1);

    public async Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request,
        CancellationToken cancellation) {
        // Configuration access belongs to the calling client thread.
        var selected = options();
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(NativeIdentityCoordinator.Lifetime);
        cancellation = deadline.Token;
        await _serial.WaitAsync(cancellation).ConfigureAwait(false);
        try {
            await using var observation = await host.StartAsync(selected, request, cancellation).ConfigureAwait(false);
            var report = await observation.ReadAsync(request, cancellation).ConfigureAwait(false);
            cancellation.ThrowIfCancellationRequested();
            if (report is not { } observed || observed.Epoch != request.Epoch || observed.Nonce != request.Nonce)
                return null;
            return observed;
        } finally {
            _serial.Release();
        }
    }
}
