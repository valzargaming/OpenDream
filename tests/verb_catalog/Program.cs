using System;
using System.Collections.Generic;

// The runner inserts production handlers, event definitions and Shutdown below.
// UI refresh is inert; no networking, window or entity manager is started.
public sealed class ClientVerbSystem {
    private readonly Dictionary<int, VerbInfo> _verbs = new();
    private List<int>? _clientVerbs;
    private readonly InterfaceManager _interfaceManager = new();
    public struct VerbInfo { public string Name; }
    EVENTS
    METHODS

    private static int _checks;
    private static void Check(bool condition, string message) {
        _checks++;
        if (!condition) throw new InvalidOperationException(message);
    }

    private static List<VerbInfo> Catalog(int count) {
        var result = new List<VerbInfo>();
        for (int id = 0; id < count; id++) result.Add(new VerbInfo { Name = $"verb-{id}" });
        return result;
    }

    public static int Main() {
        try {
            var system = new ClientVerbSystem();
            var catalog = Catalog(11);
            system.OnRegisterVerbEvent(new RegisterVerbEvent(10, catalog[10]));
            system.OnAllVerbsEvent(new AllVerbsEvent(catalog));
            Check(system._verbs.Count == 11 && system._verbs[10].Name == "verb-10",
                "incremental registration before catalog must merge overlapping IDs");
            Check(system._interfaceManager.DefaultInfo!.RefreshCount == 1, "catalog refreshes UI once");

            system.OnRegisterVerbEvent(new RegisterVerbEvent(10, new VerbInfo { Name = "updated" }));
            Check(system._verbs.Count == 11 && system._verbs[10].Name == "updated",
                "registration after catalog must update an existing ID");
            system.OnAllVerbsEvent(new AllVerbsEvent(catalog));
            system.OnAllVerbsEvent(new AllVerbsEvent(catalog));
            Check(system._verbs.Count == 11 && system._verbs[10].Name == "verb-10",
                "repeated catalog is authoritative for included IDs and idempotent");

            system.OnRegisterVerbEvent(new RegisterVerbEvent(20, new VerbInfo { Name = "newer" }));
            system.OnAllVerbsEvent(new AllVerbsEvent(catalog));
            Check(system._verbs.Count == 12 && system._verbs[20].Name == "newer",
                "older catalog preserves newer incremental IDs");
            system.OnAllVerbsEvent(new AllVerbsEvent(new List<VerbInfo>()));
            Check(system._verbs.Count == 12, "empty snapshot cannot erase newer registrations");

            system.OnUpdateClientVerbsEvent(new UpdateClientVerbsEvent(new List<int> { 0, 10, 20 }));
            system.OnUpdateClientVerbsEvent(new UpdateClientVerbsEvent(new List<int> { 20 }));
            Check(system._clientVerbs!.Count == 1 && system._clientVerbs[0] == 20,
                "client verb removal replaces the active ID list");
            Check(system._verbs.Count == 12, "client removal does not erase global catalog entries");

            system.Shutdown();
            Check(system._verbs.Count == 0, "shutdown must release previous-session catalog");
            Check(system._clientVerbs == null, "shutdown must release previous-session active IDs");
            system.OnAllVerbsEvent(new AllVerbsEvent(Catalog(1)));
            Check(system._verbs.Count == 1 && !system._verbs.ContainsKey(20),
                "reconnect cannot retain previous-session IDs");
            system.OnRegisterVerbEvent(new RegisterVerbEvent(0, new VerbInfo { Name = "reused" }));
            Check(system._verbs[0].Name == "reused", "new session can reuse catalog IDs");
            system._interfaceManager.DefaultInfo = null;
            system.OnAllVerbsEvent(new AllVerbsEvent(Catalog(1)));
            system.OnUpdateClientVerbsEvent(new UpdateClientVerbsEvent(new List<int>()));
            Check(system._clientVerbs!.Count == 0, "handlers tolerate missing info UI");
            Console.WriteLine($"PASS {_checks} production verb catalog assertions");
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine($"REGRESSION: {error}");
            return 1;
        }
    }
}

public sealed class InterfaceManager { public Info? DefaultInfo = new(); }
public sealed class Info {
    public int RefreshCount;
    public void RefreshVerbs(ClientVerbSystem system) => RefreshCount++;
}
