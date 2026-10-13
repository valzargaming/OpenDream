using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenDreamRuntime;
using OpenDreamRuntime.Objects;
using OpenDreamRuntime.Objects.Types;
using OpenDreamShared.Dream;
using OpenDreamShared.Network.Messages;

namespace Content.IntegrationTests;

public sealed partial class GameTests {
    private static void ClientPromptsReleaseOwnedValues(DreamManager manager, DreamObjectTree tree, DreamRefManager refs) {
        var connection = manager.Connections.Single(connection => connection.Session != null);
        var payload = tree.CreateObject(tree.Datum);
        var eye = tree.CreateObject<DreamObjectMovable>(tree.Obj);
        var list = tree.CreateList();
        list.AddValue(new DreamValue(payload));
        var payloadRef = refs.GetRef(payload);
        var eyeReferences = eye.RefCount;
        var nextId = typeof(DreamConnection).GetField("_nextPromptEvent", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var promptEvents = typeof(DreamConnection).GetField("_promptEvents", BindingFlags.Instance | BindingFlags.NonPublic)!;
        try {
            var emptyList = tree.CreateList();
            try {
                using var emptyResult = connection.PromptList(DreamValueType.Null, emptyList, "", "", DreamValue.Null).GetAwaiter().GetResult();
                Assert.That(emptyResult.IsNull, Is.True);
            } finally {
                emptyList.DecRef();
            }
            for (var iteration = 0; iteration < 1000; iteration++) {
                using var empty = connection.PromptList(DreamValueType.Obj, list, "", "", DreamValue.Null).GetAwaiter().GetResult();
                Assert.That(empty.IsNull, Is.True);
                Assert.That(payload.RefCount, Is.EqualTo(2), "Filtered empty prompt releases snapshot owners");
                foreach (var response in new object[] { null, -1f, 99f, 0f }) {
                    var id = (int)nextId.GetValue(connection)!;
                    var task = connection.PromptList(DreamValueType.Null, list, "", "", DreamValue.Null);
                    Assert.That(payload.RefCount, Is.EqualTo(3), "Pending prompt holds one snapshot owner");
                    connection.HandleMsgPromptResponse(new MsgPromptResponse {
                        PromptId = id, Type = response == null ? DreamValueType.Null : DreamValueType.Num, Value = response
                    });
                    var failures = task.IsFaulted ? 1 : 0;
                    Assert.That(failures, Is.EqualTo(0), "Negative prompt index is handled without an exception");
                    Assert.That(task.IsCompleted, Is.True);
                    using var result = task.GetAwaiter().GetResult();
                    if (response is float index && index == 0) {
                        Assert.That(result.MustGetValueAsDreamObject(), Is.SameAs(payload));
                        Assert.That(payload.RefCount, Is.EqualTo(3), "Selected result has its own owner");
                    } else {
                        Assert.That(result.IsNull, Is.True);
                        Assert.That(payload.RefCount, Is.EqualTo(2), "Cancelled prompt releases snapshot owners");
                    }
                }
                Assert.That(payload.RefCount, Is.EqualTo(2));
                // A non-cancellable invalid response returns an owned first item.
                var fallbackId = (int)nextId.GetValue(connection)!;
                var fallbackTask = connection.PromptList(DreamValueType.Anything, list, "", "", DreamValue.Null);
                connection.HandleMsgPromptResponse(new MsgPromptResponse { PromptId = fallbackId, Type = DreamValueType.Num, Value = -1f });
                using (var fallback = fallbackTask.GetAwaiter().GetResult()) {
                    Assert.That(fallback.MustGetValueAsDreamObject(), Is.SameAs(payload));
                    Assert.That(payload.RefCount, Is.EqualTo(3));
                }
                Assert.That(payload.RefCount, Is.EqualTo(2));
                connection.Client!.SetVariable("statobj", new DreamValue(payload));
                connection.Client.SetVariable("statobj", new DreamValue(payload));
                Assert.That(payload.RefCount, Is.EqualTo(3), "StatObj self assignment owns one reference");
                connection.StatObj = DreamValue.Null;
                Assert.That(payload.RefCount, Is.EqualTo(2), "StatObj replacement releases previous owner");
            }
            var mixed = tree.CreateList();
            try {
                mixed.AddValue(new DreamValue(payload));
                mixed.AddValue(new DreamValue(eye));
                var id = (int)nextId.GetValue(connection)!;
                var filteredTask = connection.PromptList(DreamValueType.Obj, mixed, "", "", DreamValue.Null);
                connection.HandleMsgPromptResponse(new MsgPromptResponse { PromptId = id, Type = DreamValueType.Num, Value = 0f });
                using var filtered = filteredTask.GetAwaiter().GetResult();
                var wrongSelection = ReferenceEquals(filtered.MustGetValueAsDreamObject(), eye) ? 0 : 1;
                Assert.That(wrongSelection, Is.EqualTo(0), "Filtered prompt index selects the displayed item");
            } finally {
                mixed.DecRef();
            }
            // SetClientMob must release an explicitly assigned statobj too.
            connection.Eye = null;
            var originalMob = connection.Mob;
            originalMob?.IncRef();
            var newMob = tree.CreateObject<DreamObjectMob>(tree.Mob);
            var mobReferences = newMob.RefCount;
            try {
                connection.StatObj = new DreamValue(payload);
                connection.Mob = newMob;
                Assert.That(payload.RefCount, Is.EqualTo(2), "Mob change releases previous StatObj owner");
                // The real /mob/Login() places the mob on a turf, which owns another reference.
                Assert.That(newMob.Loc, Is.Not.Null, "Production Login places the mob in the world");
                Assert.That(newMob.RefCount, Is.EqualTo(mobReferences + 3), "Mob, StatObj and world location have separate owners");
                connection.Mob = originalMob;
                Assert.That(newMob.RefCount, Is.EqualTo(mobReferences + 1), "Mob change preserves only the world location owner");
                newMob.SetLoc(null);
                Assert.That(newMob.RefCount, Is.EqualTo(mobReferences));
            } finally {
                newMob.DecRef();
                originalMob?.DecRef();
            }
            connection.Eye = eye;
            connection.StatObj = new DreamValue(payload);
            var pending = connection.PromptList(DreamValueType.Null, list, "", "", DreamValue.Null);
            var nonCancellablePending = connection.PromptList(DreamValueType.Anything, list, "", "", DreamValue.Null);
            var plainPending = connection.Prompt(DreamValueType.Text, "", "", "");
            connection.HandleDisconnection();
            var unfinished = pending.IsCompleted && plainPending.IsCompleted && nonCancellablePending.IsCompleted ? 0 : 1;
            Assert.That(unfinished, Is.EqualTo(0), "Disconnect completes pending prompts");
            using var disconnected = pending.GetAwaiter().GetResult();
            using var plainDisconnected = plainPending.GetAwaiter().GetResult();
            using var nonCancellableDisconnected = nonCancellablePending.GetAwaiter().GetResult();
            Assert.That(disconnected.IsNull, Is.True);
            Assert.That(plainDisconnected.IsNull, Is.True);
            Assert.That(nonCancellableDisconnected.IsNull, Is.True);
            Assert.That(payload.RefCount, Is.EqualTo(2), "Disconnect releases StatObj and prompt snapshot owners");
            var retainedEye = eye.RefCount - eyeReferences;
            Assert.That(retainedEye, Is.EqualTo(0), "Disconnect releases custom Eye owner");
            var callbacks = (System.Collections.IDictionary)promptEvents.GetValue(connection)!;
            Assert.That(callbacks.Count, Is.Zero);
            connection.HandleDisconnection();
            Assert.That(payload.RefCount, Is.EqualTo(2), "Repeated disconnect does not release twice");
            using var afterDisconnect = connection.Prompt(DreamValueType.Text, "", "", "").GetAwaiter().GetResult();
            Assert.That(afterDisconnect.IsNull, Is.True);
            using var afterDisconnectList = connection.PromptList(DreamValueType.Anything, list, "", "", DreamValue.Null).GetAwaiter().GetResult();
            Assert.That(afterDisconnectList.IsNull, Is.True);
            Assert.That(callbacks.Count, Is.Zero);
        } finally {
            connection.HandleDisconnection();
            list.DecRef();
            payload.DecRef();
            eye.DecRef();
        }
        Assert.That(payload.Deleted, Is.True);
        using var located = refs.LocateRef(payloadRef);
        Assert.That(located.IsNull, Is.True, "Released prompt payload leaves reference bucket");
        TestContext.Progress.WriteLine("Client prompt ownership: 1000 filtered-empty, cancelled, negative, invalid, selected and fallback cases; stat replacement, mob transition and disconnect released owners");
    }
}
