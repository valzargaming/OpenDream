using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;

namespace Content.IntegrationTests;
[TestFixture]
public sealed class GameTests : ContentIntegrationTest {

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
        if(manager.LastDMException is not null) {
            Assert.Fail($"Runtime occurred on server boot: {manager.LastDMException}");
        }
        // Reuse the existing server: BYOND API initialization is process-global.
        await server.WaitAssertion(() => {
            var tree = server.ResolveDependency<DreamObjectTree>();
            FilterWrappersReleaseOnAtomDeletion(tree);
            EyeAssignmentOwnsExactlyOneReference(tree);
        });
    }
}
