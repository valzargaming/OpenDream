using System.Text;
using OpenDreamRuntime.NativeByondBridge;
using Binding = OpenDreamRuntime.NativeByondBridge.NativeClientReportLedger.SessionBinding;

var checks = 0;
void Check(bool condition, string name) {
    checks++;
    if (!condition) throw new InvalidOperationException("PROOF ASSERTION: " + name);
}

var current = new HashSet<Binding>();
var time = new ManualTime();
var binding = new Binding(Guid.NewGuid(), 1, Guid.NewGuid());
current.Add(binding);
using var ledger = new NativeClientReportLedger(ProductionCkey.Ckey, current.Contains, time);
byte[] Form(string nonce, Guid? epoch = null, string key = "Proof Admin", string cid = "000184467440737095516160") =>
    Encoding.UTF8.GetBytes("epoch=" + (epoch ?? ledger.Epoch).ToString("D") + "&nonce=" + nonce +
        "&key=" + Uri.EscapeDataString(key) + "&cid=" + Uri.EscapeDataString(cid));
bool Accept(byte[] body, out Guid ticket) => ledger.TryAccept(binding, body, out ticket);
var delivered = 0;
bool Deliver(Binding target, NativeClientReportLedger.Claim claim) {
    if (!current.Contains(target)) return false;
    Check(claim.ComputerId == "000184467440737095516160", "CID text preserved without integer conversion");
    Check(claim.Ckey == "proofadmin" && claim.Key == "Proof Admin", "production Ckey with original key preserved");
    delivered++;
    return true;
}
try {
    Check(ProductionCkey.Ckey("Proof Admin^!@") == "proofadmin@", "actual engine normalization");
    for (var i = 0; i < 1000; i++) {
        Check(ledger.TryBegin(binding, out var nonce), "begin live exact binding");
        Check(!ledger.TryDeliver(Guid.NewGuid(), Deliver), "unverified delivery rejected");
        Check(Accept(Form(nonce), out var ticket), "valid local callback");
        Check(!Accept(Form(nonce), out _), "callback replay rejected");
        Check(ledger.TryDeliver(ticket, Deliver), "verified adapter delivery");
        Check(!ledger.TryDeliver(ticket, Deliver), "delivery replay rejected");
        Check(ledger.PendingCount == 0, "completed claims released");
    }
    Check(delivered == 1000, "one adapter effect per challenge");
    ledger.TryBegin(binding, out var activeNonce);
    Check(!Accept(Form(activeNonce, epoch: Guid.NewGuid()), out _), "wrong bridge epoch rejected");
    Check(!ledger.TryAccept(new Binding(binding.SessionId, 2, Guid.NewGuid()), Form(activeNonce), out _), "different active channel rejected");
    Check(!Accept(Form(activeNonce, key: "Guest-123"), out _), "native guest format rejected");
    Check(!Accept(Form(activeNonce, cid: "1e9"), out _), "non-digit CID rejected");
    Check(!Accept(Form(activeNonce, cid: new string('1', 33)), out _), "oversized CID rejected");
    var valid = Encoding.UTF8.GetString(Form(activeNonce));
    foreach (var malformed in new[] {
        valid + "&key=ProofAdmin", valid + "&%6bey=ProofAdmin", valid + "&unknown=1", valid + "&",
        valid.Replace("key=Proof%20Admin", "key=%FF"), valid.Replace("key=Proof%20Admin", "key=%G0"),
        valid.Replace("key=Proof%20Admin", "key=%"), valid.Replace("key=Proof%20Admin", "key=%00ProofAdmin"),
        valid.Replace("&cid=000184467440737095516160", "")
    }) Check(!Accept(Encoding.UTF8.GetBytes(malformed), out _), "malformed or duplicate form rejected");
    Check(!Accept(new byte[NativeClientReportLedger.MaximumBodyBytes + 1], out _), "body bound enforced");
    Check(Accept(Form(activeNonce), out var acceptedTicket), "rejects do not forge verified ticket");
    current.Remove(binding);
    Check(!ledger.TryDeliver(acceptedTicket, (_, _) => { delivered++; return true; }), "disconnected session delivery rejected");
    Check(delivered == 1000, "no disconnected adapter effect");
    current.Add(binding);
    ledger.TryBegin(binding, out var cancelledNonce);
    Accept(Form(cancelledNonce), out var cancelledTicket);
    ledger.Cancel(binding);
    Check(!ledger.TryDeliver(cancelledTicket, Deliver), "explicit disconnect cancels ticket");
    ledger.TryBegin(binding, out var replacedNonce);
    Accept(Form(replacedNonce), out var replacedTicket);
    ledger.TryBegin(binding, out var replacementNonce);
    Check(!ledger.TryDeliver(replacedTicket, Deliver), "replacement challenge invalidates ticket");
    Check(!Accept(Form(replacedNonce), out _), "replacement challenge invalidates nonce");
    Check(Accept(Form(replacementNonce), out var throwTicket), "prepare throwing adapter ticket");
    try {
        ledger.TryDeliver(throwTicket, (_, _) => throw new InvalidOperationException("injected adapter failure"));
        Check(false, "throwing adapter propagated");
    } catch (InvalidOperationException error) when (error.Message == "injected adapter failure") { }
    Check(!ledger.TryDeliver(throwTicket, Deliver), "throwing adapter consumes ticket");
    ledger.TryBegin(binding, out replacementNonce);
    time.Advance(TimeSpan.FromSeconds(60));
    Check(!Accept(Form(replacementNonce), out _), "callback at total deadline rejected");
    ledger.TryBegin(binding, out var queuedNonce);
    Accept(Form(queuedNonce), out var queuedTicket);
    time.Advance(TimeSpan.FromSeconds(60));
    Check(!ledger.TryDeliver(queuedTicket, Deliver), "queued delivery at total deadline rejected");
    for (var i = 0; i < NativeClientReportLedger.MaximumPending; i++) {
        var candidate = new Binding(Guid.NewGuid(), 1, Guid.NewGuid());
        current.Add(candidate);
        Check(ledger.TryBegin(candidate, out _), "bounded population admission");
    }
    Check(!ledger.TryBegin(binding, out _), "population bound enforced");
    Check(ledger.PendingCount == NativeClientReportLedger.MaximumPending, "bounded retained records");
    time.Advance(TimeSpan.FromSeconds(60));
    ledger.PruneExpired();
    Check(ledger.PendingCount == 0, "expired records released");
    ledger.TryBegin(binding, out var finalNonce);
    Accept(Form(finalNonce), out var finalTicket);
    ledger.Dispose(); ledger.Dispose();
    Check(ledger.PendingCount == 0 && !ledger.TryBegin(binding, out _), "disposed ledger releases records");
    Check(!Accept(Form(finalNonce), out _) && !ledger.TryDeliver(finalTicket, Deliver), "disposed ledger fails closed");
    using var rotated = new NativeClientReportLedger(ProductionCkey.Ckey, current.Contains, time);
    rotated.TryBegin(binding, out var rotatedNonce);
    Check(!rotated.TryAccept(binding, Form(rotatedNonce), out _), "startup epoch rotation rejects old proof");
    Console.WriteLine($"NATIVE REPORT LEDGER PASS: {checks} assertions; 1000 adapter deliveries; no listener/DM client/native bridge launched");
    return 0;
} catch (Exception error) {
    Console.Error.WriteLine(error);
    return 1;
}

sealed class ManualTime : TimeProvider {
    private long _timestamp;
    public override long TimestampFrequency => 1000;
    public override long GetTimestamp() => _timestamp;
    public void Advance(TimeSpan duration) => _timestamp += (long)duration.TotalMilliseconds;
}
