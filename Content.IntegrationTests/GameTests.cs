using System.Linq;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
using OpenDreamRuntime.Procs;

namespace Content.IntegrationTests;
[TestFixture]
public sealed partial class GameTests : ContentIntegrationTest {

    private static void CompletedSpawnsReuseStates(DreamManager manager, DreamObjectTree tree) {
        Assert.That(tree.TryGetGlobalProc("spawn_pool_reuse_probe", out var proc), Is.True);
        var payload = tree.CreateObject(tree.Datum);
        var originalReferences = payload.RefCount;
        var initialPoolCount = DMProcState.Pool.Count;
        try {
            for (var batch = 0; batch < 10; batch++) {
                using var result = DreamThread.Run(proc!, manager.WorldInstance, payload,
                    new DreamValue(1000), new DreamValue(payload));
                Assert.That(result.MustGetValueAsFloat(), Is.EqualTo(1000));
                Assert.That(payload.RefCount, Is.EqualTo(originalReferences),
                    "Completed spawn copies must release arguments, locals and return values");
                Assert.That(DMProcState.Pool.Count, Is.LessThanOrEqualTo(initialPoolCount + 2),
                    $"Completed spawn batch {batch} must reuse states instead of permanently growing the pool");
            }
            foreach (var state in DMProcState.Pool) {
                Assert.That(state.Thread, Is.Null);
                Assert.That(state.Instance, Is.Null);
                Assert.That(state.Usr, Is.Null);
                Assert.That(state.Proc, Is.Null);
                Assert.That(state.ArgumentCount, Is.Zero);
                Assert.That(state.ProgramCounter, Is.Zero);
                Assert.That(state.Result, Is.EqualTo(DreamValue.Null));
                Assert.That(state.WaitFor, Is.True);
                Assert.That(state.Enumerators, Is.All.Null);
            }
            TestContext.Progress.WriteLine($"Spawn pool: {initialPoolCount} initial, {DMProcState.Pool.Count} after 10000 completed spawns");
        } finally {
            payload.DecRef();
        }
    }

    private static void EyeAssignmentOwnsExactlyOneReference(DreamObjectTree tree) {
        var connection = new DreamConnection("ownership-test");
        var client = new DreamObjectClient(tree.Client.ObjectDefinition, connection, null, null);
        var eye = tree.CreateObject<DreamObjectMovable>(tree.Obj);
        var originalReferences = eye.RefCount;
        try {
            for (var i = 0; i < 200; i++) {
                client.SetVariable("eye", new DreamValue(eye));
                Assert.That(eye.RefCount, Is.EqualTo(originalReferences + 1));
                client.SetVariable("eye", new DreamValue(eye));
                Assert.That(eye.RefCount, Is.EqualTo(originalReferences + 1));
                client.SetVariable("eye", DreamValue.Null);
                Assert.That(eye.RefCount, Is.EqualTo(originalReferences));
                Assert.That(eye.Deleted, Is.False);
            }
        } finally {
            client.SetVariable("eye", DreamValue.Null);
            client.Delete();
            eye.DecRef();
        }
    }

    private static void FilterWrappersReleaseOnAtomDeletion(DreamObjectTree tree) {
        for (var i = 0; i < 200; i++) {
            var atom = tree.CreateObject<DreamObjectAtom>(tree.Obj);
            var standalone = tree.CreateObject<DreamObjectFilter>(tree.Filter);
            standalone.Filter = new OpenDreamShared.Dream.DreamFilterBlur();
            DreamObjectFilter wrapper;
            using (var filtersValue = atom.GetVariable("filters")) {
                var filters = (DreamFilterList)filtersValue.MustGetValueAsDreamList();
                filters.AddValue(new DreamValue(standalone));
                using (var first = filters.GetValue(new DreamValue(1))) {
                    wrapper = (DreamObjectFilter)first.MustGetValueAsDreamObject()!;
                    using var second = filters.GetValue(new DreamValue(1));
                    Assert.That(second.MustGetValueAsDreamObject(), Is.SameAs(wrapper));
                    Assert.That(wrapper.Deleted, Is.False);
                }
                Assert.That(wrapper.Deleted, Is.False);
            }
            atom.Delete();
            Assert.That(wrapper.Deleted, Is.True);
            standalone.DecRef();
        }
    }

    /// <summary>
    /// Tests to make sure the IntegrationTest project does not runtime.
    /// </summary>
    [Test]
    public async Task NoRuntimesTest() {
        var (client, server) = await StartConnectedServerClientPair();
        await RunTicksSync(client, server, 1000);
        Assert.That(server.IsAlive);
        var manager = server.ResolveDependency<DreamManager>();
        // Wait for actual client creation, beyond the asynchronous transport handshake.
        var admissionWait = System.Diagnostics.Stopwatch.StartNew();
        var joined = false;
        while (!joined && admissionWait.Elapsed < System.TimeSpan.FromSeconds(15)) {
            await RunTicksSync(client, server, 1);
            await server.WaitAssertion(() => joined = manager.Connections.Any(connection => connection.Session != null));
            await Task.Delay(1);
        }
        Assert.That(joined, Is.True, "Actual DM client admission completes before ownership fixtures");
        if(manager.LastDMException is not null) {
            Assert.Fail($"Runtime occurred on server boot: {manager.LastDMException}");
        }
        await AsyncReturnsOwnValues(manager, server.ResolveDependency<DreamObjectTree>(),
            server.ResolveDependency<DreamRefManager>(), action => server.WaitAssertion(action),
            ticks => RunTicksSync(client, server, ticks));
        // Reuse the existing server: BYOND API initialization is process-global.
        await server.WaitAssertion(() => {
            var tree = server.ResolveDependency<DreamObjectTree>();
            NativeArgumentsReleaseOwnedValues(manager, tree, server.ResolveDependency<DreamRefManager>());
            NumericListAssignmentsReleaseOwners(manager, tree, server.ResolveDependency<DreamRefManager>());
            ExternalCallRejectionsReleaseArguments(manager, tree, server.ResolveDependency<DreamRefManager>());
            SupportedOperatorFallbacksReleaseOwners(manager, tree, server.ResolveDependency<DreamRefManager>());
            MissingOperatorArgumentsReleaseOwners(manager, tree, server.ResolveDependency<DreamRefManager>());
            ObjectInitializationReleasesOwnedValues(manager, tree, server.ResolveDependency<DreamRefManager>());
            ProcInitializationReleasesOwnedValues(manager, tree, server.ResolveDependency<DreamRefManager>());
            ExceptionsReleaseOwnedValues(manager, tree, server.ResolveDependency<DreamRefManager>());
            SavefileFailuresReleaseRegisteredObjects(tree, server.ResolveDependency<DreamRefManager>());
            FilterWrappersReleaseOnAtomDeletion(tree);
            EyeAssignmentOwnsExactlyOneReference(tree);
            CompletedSpawnsReuseStates(manager, tree);
            CancelledThreadsReleaseOwnedFrames(manager, tree);
            ClientPromptsReleaseOwnedValues(manager, tree, server.ResolveDependency<DreamRefManager>());
        });
    }
}
