#nullable enable
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamShared;
using Robust.Shared.Log;
using Serilog.Events;

namespace Content.IntegrationTests;

[TestFixture, NonParallelizable]
[Explicit("Fresh controlled process reading retained small fixture outputs; no full Gaia acceptance")]
public sealed class GaiaSaveCostReaderControlTests : ContentIntegrationTest {
    private sealed record ReaderPlan(string JsonPath, string JsonSha256, string OwnedRoot, string OwnershipId);
    private sealed class NoErrors : ILogHandler {
        public void Log(string sawmillName, LogEvent message) {
            TestContext.Out.WriteLine($"GAIA_READER_ACTUAL_LOG [{message.Level}] {sawmillName}: {message.RenderMessage()}");
            if (message.Level >= LogEventLevel.Error) Assert.Fail("Unexpected reader host error: " + message.RenderMessage());
        }
    }
    [Test]
    public async Task RejectWrongShardPayload() {
        var planPath = Environment.GetEnvironmentVariable("OD_GAIA_READER_CONTROL_PLAN")
            ?? throw new InvalidOperationException("Explicit retained small-fixture reader plan required");
        var plan = JsonSerializer.Deserialize<ReaderPlan>(File.ReadAllText(planPath))!;
        Assert.That(Guid.TryParseExact(plan.OwnershipId, "N", out _), Is.True);
        Assert.That(Path.IsPathFullyQualified(plan.JsonPath), Is.True);
        Assert.That(Path.IsPathFullyQualified(plan.OwnedRoot), Is.True);
        Assert.That(Path.GetDirectoryName(Path.GetFullPath(plan.JsonPath)), Is.EqualTo(Path.GetFullPath(plan.OwnedRoot)));
        Assert.That(File.ReadAllText(Path.Combine(plan.OwnedRoot, ".gaia-save-host-owner")).Trim(), Is.EqualTo(plan.OwnershipId));
        Assert.That(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(plan.JsonPath))).ToLowerInvariant(), Is.EqualTo(plan.JsonSha256));
        var prior = Directory.GetCurrentDirectory();
        try {
            var options = new ServerContentIntegrationOption { OverrideLogHandler = () => new NoErrors() };
            options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = plan.JsonPath;
            var server = StartServer(options);
            await server.WaitIdleAsync();
            await server.WaitRunTicks(1);
            await server.WaitAssertion(() => {
                var manager = server.ResolveDependency<DreamManager>();
                Assert.That(manager.LastDMException, Is.Null);
                Assert.That(manager.TryGetGlobalProc("gaia_host_recovery_control", out var proc), Is.True);
                using var result = DreamThread.Run(proc!, manager.WorldInstance, null);
                Assert.That(result.MustGetValueAsFloat(), Is.Zero, "actual fresh savefile reader must reject wrong shard payload");
                Assert.That(manager.LastDMException, Is.Null);
                TestContext.Out.WriteLine("GAIA_READER_REJECTION_COMPLETE");
            });
        } finally { Directory.SetCurrentDirectory(prior); }
    }
}
