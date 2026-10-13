using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamClient.NativeByond;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects.Types;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private const string ObservedNativeKey = "Native Fixture Account";
    private const string ObservedNativeCid = "000184467440737095516160";

    private sealed class InjectedNativeObserver : INativeIdentityProvider {
        public Task<NativeIdentityReport?> ObserveAsync(NativeIdentityRequest request, CancellationToken cancellation) =>
            Task.FromResult<NativeIdentityReport?>(new NativeIdentityReport(request.Epoch, request.Nonce,
                ObservedNativeKey, ObservedNativeCid));
    }

    private static void NativeIdentityCreatesObservedClient(DreamManager manager) {
        var connection = manager.Connections.Single(connection => connection.Session != null);
        Assert.That(connection.Key, Is.EqualTo(ObservedNativeKey), "DM client uses observed native key");
        Assert.That(connection.NativeComputerId, Is.EqualTo(ObservedNativeCid), "DM connection preserves native CID text");
        Assert.That(connection.Client, Is.TypeOf<DreamObjectClient>());
        using var key = connection.Client!.GetVariable("key");
        using var ckey = connection.Client.GetVariable("ckey");
        using var cid = connection.Client.GetVariable("computer_id");
        Assert.That(key.MustGetValueAsString(), Is.EqualTo(ObservedNativeKey));
        Assert.That(ckey.MustGetValueAsString(), Is.EqualTo("nativefixtureaccount"));
        Assert.That(cid.MustGetValueAsString(), Is.EqualTo(ObservedNativeCid), "Native CID is never account-hashed or numerically truncated");
        TestContext.Progress.WriteLine("Native identity channel: required admission created actual DM client with observed key and exact CID text");
    }
}
