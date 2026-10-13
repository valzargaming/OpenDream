using OpenDreamClient.NativeByond;

static class Probe {
    private static int _assertions;
    static void Check(bool condition, string message) {
        _assertions++;
        if (!condition) throw new Exception("IDENTITY ASSERTION: " + message);
    }
    static bool Login(NativeIdentityCoordinator coordinator, out string? sent) {
        string? name = "CLI-Entered-Name";
        sent = null;
        try { coordinator.AuthorizeHandshake(value => name = value); }
        catch (InvalidOperationException) { Check(name == null, "failed handshake clears supplied name"); return false; }
        sent = name;
        return true;
    }
    public static void Main() {
        using (var unavailable = new NativeIdentityCoordinator(new UnavailableNativeIdentityProvider())) {
            unavailable.Begin(); unavailable.Poll();
            Check(!Login(unavailable, out _), "missing provider blocks handshake");
        }
        var provider = new Provider();
        using var coordinator = new NativeIdentityCoordinator(provider);
        Check(!Login(coordinator, out _), "no report blocks handshake");
        for (var index = 0; index < 1000; index++) {
            coordinator.Begin();
            var first = provider.Last;
            Check(!coordinator.Poll() && !Login(coordinator, out _), "pending observation blocks handshake");
            provider.Complete("NativeAccount" + index, "00018446744073709551616000");
            Check(coordinator.Poll(), "completed provider polled");
            Check(coordinator.Identity?.ComputerId == "00018446744073709551616000", "CID remains exact digit text");
            coordinator.ConnectionReset();
            Check(coordinator.Identity.HasValue, "retry reset preserves fresh unused observation");
            Check(Login(coordinator, out var sent) && sent == "NativeAccount" + index, "native name replaces supplied name");
            Check(!Login(coordinator, out _), "one observation cannot authorize another handshake");
            coordinator.Begin();
            Check(coordinator.Identity == null, "account switch clears old report");
            Check(provider.Last.Request != first.Request, "reconnect uses fresh request");
            provider.Complete("OtherAccount", "002");
            coordinator.Poll();
            Check(Login(coordinator, out sent) && sent == "OtherAccount", "reconnect uses fresh account");
            coordinator.ConnectionReset();
            Check(!Login(coordinator, out _), "disconnect clears identity");
        }
        coordinator.Begin();
        var replaced = provider.Last;
        coordinator.Begin();
        Check(replaced.Cancellation.IsCancellationRequested, "replacement cancels provider");
        replaced.Completion.SetResult(new(replaced.Request.Epoch, replaced.Request.Nonce, "StaleAccount", "12"));
        Check(!coordinator.Poll() && coordinator.Identity == null, "late replaced report ignored");
        provider.Complete("FreshAccount", "34"); coordinator.Poll();
        Check(Login(coordinator, out var fresh) && fresh == "FreshAccount", "replacement retains only fresh report");
        foreach (var malformed in new[] { "guest", "nonce", "epoch", "cid", "empty" }) {
            coordinator.Begin();
            var request = provider.Last.Request;
            provider.Last.Completion.SetResult(new(
                malformed == "epoch" ? Guid.NewGuid() : request.Epoch,
                malformed == "nonce" ? "bad" : request.Nonce,
                malformed == "guest" ? "Guest-123" : malformed == "empty" ? "" : "NativeAccount",
                malformed == "cid" ? "12e3" : "001"));
            coordinator.Poll();
            Check(!Login(coordinator, out _), "malformed report blocks handshake");
        }
        coordinator.Begin(); provider.Last.Completion.SetException(new IOException("injected observer error"));
        coordinator.Poll(); Check(!Login(coordinator, out _), "provider fault blocks handshake");
        coordinator.Dispose(); Check(!Login(coordinator, out _), "disposed coordinator blocks handshake");
        Console.WriteLine("NATIVE CLIENT IDENTITY PASS: " + _assertions);
    }
    sealed class Provider : INativeIdentityProvider {
        public Observation Last = default!;
        public Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request, CancellationToken cancellation) {
            Last = new(request, cancellation);
            return Last.Completion.Task;
        }
        public void Complete(string key, string cid) => Last.Completion.SetResult(new(Last.Request.Epoch, Last.Request.Nonce, key, cid));
    }
    sealed record Observation(NativeIdentityRequest Request, CancellationToken Cancellation) {
        public readonly TaskCompletionSource<NativeIdentityReport?> Completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }
}
