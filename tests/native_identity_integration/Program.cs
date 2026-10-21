using System.Text;
using Robust.Client.NativeByond;
using OpenDreamRuntime.NativeByondBridge;
using Binding = OpenDreamRuntime.NativeByondBridge.NativeClientReportLedger.SessionBinding;

var checks = 0;
void Check(bool value, string message) {
    checks++;
    if (!value) throw new InvalidOperationException("INTEGRATION ASSERTION: " + message);
}
var current = new HashSet<Binding>();
var time = new ManualTime();
using var gate = new NativeIdentityAdmissionGate(current.Contains, time);
byte[] Form(string nonce, Guid? epoch = null) => Encoding.UTF8.GetBytes(
    $"epoch={epoch ?? gate.Epoch:D}&nonce={nonce}&key=Native%20Fixture%20Account&cid=000184467440737095516160");
for (var i = 0; i < 1000; i++) {
    var binding = new Binding(Guid.NewGuid(), i + 1, Guid.NewGuid());
    current.Add(binding);
    Check(gate.TryBegin(binding, out var nonce), "begin fresh channel");
    Check(!gate.TryAccept(binding, Form(nonce, Guid.NewGuid())), "wrong server epoch rejected");
    Check(gate.TryAccept(binding, Form(nonce)), "accept observed channel report");
    Check(!gate.TryAccept(binding, Form(nonce)), "report replay rejected");
    Check(gate.TryConsume(binding, out var claim), "consume admission before DM effects");
    Check(claim.Key == "Native Fixture Account" && claim.Ckey == "nativefixtureaccount" &&
        claim.ComputerId == "000184467440737095516160", "original key and exact native CID preserved");
    Check(!gate.TryConsume(binding, out _), "admission replay rejected");
    Check(gate.Count == 0, "consumed admission released");
    current.Remove(binding);
}
var stale = new Binding(Guid.NewGuid(), 1001, Guid.NewGuid());
current.Add(stale);
gate.TryBegin(stale, out var staleNonce);
gate.TryAccept(stale, Form(staleNonce));
current.Remove(stale);
Check(!gate.TryConsume(stale, out _), "disconnected channel cannot create DM client");
current.Add(stale);
gate.TryBegin(stale, out staleNonce);
gate.TryAccept(stale, Form(staleNonce));
time.Advance(TimeSpan.FromSeconds(60));
Check(!gate.TryConsume(stale, out _), "expired completed report cannot create DM client");
gate.TryBegin(stale, out staleNonce);
time.Advance(TimeSpan.FromSeconds(60));
var expired = 0;
gate.PruneExpired(_ => expired++);
Check(expired == 1 && gate.Count == 0, "idle pending channel expires and releases ownership");
gate.TryBegin(stale, out staleNonce);
Check(!gate.TryConsume(stale, out _), "unverified channel cannot create DM client");
for (var i = 0; i < NativeClientReportLedger.MaximumPending; i++) {
    var binding = new Binding(Guid.NewGuid(), i + 2000, Guid.NewGuid());
    current.Add(binding);
    Check(gate.TryBegin(binding, out _), "pending cap admits bounded attempts");
}
Check(!gate.TryBegin(stale, out _), "pending cap rejects overflow");
time.Advance(TimeSpan.FromSeconds(60));
gate.PruneExpired(_ => { });
Check(gate.Count == 0, "all idle attempts released");

var host = new FakeHost();
var provider = new NativeIdentityObserverProvider(host, () => new NativeObserverOptions("injected", "injected"));
var request = new NativeIdentityRequest(Guid.NewGuid(), new string('A', 64));
for (var i = 0; i < 1000; i++) {
    var report = await provider.ObserveAsync(request, CancellationToken.None);
    Check(report?.ComputerId == "000184467440737095516160", "provider returns native observation unchanged");
    Check(host.Active == 0 && host.Disposed == i + 1, "successful observation disposes owned world");
}
host.WrongBinding = true;
Check(await provider.ObserveAsync(request, CancellationToken.None) == null, "provider rejects stale local observation");
host.WrongBinding = false;
host.Fail = true;
try { await provider.ObserveAsync(request, CancellationToken.None); Check(false, "observer failure propagated"); }
catch (InvalidDataException) { Check(host.Active == 0, "failed observation disposes owned world"); }
host.Fail = false;
host.Wait = true;
using (var cancellation = new CancellationTokenSource()) {
    var pending = provider.ObserveAsync(request, cancellation.Token);
    var queued = provider.ObserveAsync(request, cancellation.Token);
    Check(host.Active == 1, "replaced observation never starts concurrent worlds");
    cancellation.Cancel();
    foreach (var task in new[] { pending, queued }) {
        try { await task; Check(false, "cancellation propagated"); }
        catch (OperationCanceledException) { }
    }
    Check(host.Active == 0, "canceled observation disposes owned world");
}
using var coordinator = new NativeIdentityCoordinator(new ImmediateProvider(), time);
coordinator.Begin(); coordinator.Poll(); coordinator.AuthorizeHandshake(_ => { });
Check(coordinator.TryTakeChannelReport(gate.Epoch, new string('B', 64), out var body), "native report handed to server challenge once");
Check(Encoding.UTF8.GetString(body).Contains("cid=000184467440737095516160"), "channel handoff preserves CID text");
Check(!coordinator.TryTakeChannelReport(gate.Epoch, new string('C', 64), out _), "local native report cannot cross two channels");
Check(coordinator.Identity == null, "channel handoff releases native observation");
Console.WriteLine($"NATIVE INTEGRATION PASS: {checks} assertions; injected external effects only");

sealed class ManualTime : TimeProvider {
    private long _ticks;
    public override long TimestampFrequency => TimeSpan.TicksPerSecond;
    public override long GetTimestamp() => _ticks;
    public void Advance(TimeSpan value) => _ticks += value.Ticks;
}
sealed class ImmediateProvider : INativeIdentityProvider {
    public Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request, CancellationToken cancellation) =>
        Task.FromResult<NativeIdentityReport?>(new(request.Epoch, request.Nonce, "Native Fixture Account", "000184467440737095516160"));
}
sealed class FakeHost : INativeObserverHost {
    public int Active, Disposed;
    public bool WrongBinding, Fail, Wait;
    public Task<INativeObservation> StartAsync(NativeObserverOptions options, NativeIdentityRequest request, CancellationToken cancellation) {
        cancellation.ThrowIfCancellationRequested();
        Active++;
        return Task.FromResult<INativeObservation>(new Observation(this));
    }
    private sealed class Observation(FakeHost host) : INativeObservation {
        public async Task<NativeIdentityReport?> ReadAsync(NativeIdentityRequest request, CancellationToken cancellation) {
            if (host.Wait) await Task.Delay(Timeout.Infinite, cancellation);
            if (host.Fail) throw new InvalidDataException("Injected observer failure");
            return new NativeIdentityReport(host.WrongBinding ? Guid.NewGuid() : request.Epoch, request.Nonce,
                "Native Fixture Account", "000184467440737095516160");
        }
        public ValueTask DisposeAsync() { host.Active--; host.Disposed++; return ValueTask.CompletedTask; }
    }
}
