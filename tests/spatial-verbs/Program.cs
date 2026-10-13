using SourceProbe;
using OpenDreamShared.Dream;

int assertions = 0;
void Check(bool value, string label) {
    assertions++;
    if (!value) throw new Exception(label);
}
var spatial = Enum.GetValues<VerbAccessibility>().Take(8).ToArray();
foreach (var access in spatial) {
    var client = new ClientVerbSystem();
    client._verbs[0] = new(access, 2);
    Check(client.GetExecutableVerbs().Count() == 1, "connected nearby spatial verb must be offered");
    client._playerManager.LocalEntity = null;
    Check(!client.GetExecutableVerbs().Any(), "absent mob must safely deny spatial verbs");
    client._playerManager.LocalEntity = 1;
    client._verbs[0] = new(access, -1);
    Check(!client.GetExecutableVerbs().Any(), "negative radius denies spatial verb");
    client._verbs[0] = new(access, 2);
    client._xformQuery.Values[2].Position = new(3, 0);
    Check(!client.GetExecutableVerbs().Any(), "outside radius denies spatial verb");
    client._xformQuery.Values[2].Position = new(1, 0);
    client._xformQuery.Values[2].GridUid = 200;
    Check(!client.GetExecutableVerbs().Any(), "different grid denies spatial verb");
}
var map = new FakeMap();
for (int x = -3; x <= 3; x++) for (int y = -3; y <= 3; y++) {
    var cell = new Cell();
    cell.Turf.Position = (x, y, 1);
    cell.Turf.Map = map;
    map.Cells[(x, y)] = cell;
}
var mob = new DreamObjectMob { Position = (0, 0, 1), Map = map };
map.Cells[(0, 0)].Movables.Add(mob);
var target = new DreamObjectMovable { Position = (2, 0, 1), Map = map };
map.Cells[(2, 0)].Movables.Add(target);
var carried = new DreamObjectMovable { Map = map };
mob.Contents.AddValue(new(carried));
var connection = new DreamConnection { Mob = mob };
var server = new ServerVerbSystem(map);
foreach (var access in spatial) {
    server._verbs.Clear(); server._verbs.Add(new(access, 3));
    Check(server.TestExecute(connection, target), "unobstructed same-distance spatial verb permits target");
    foreach (var (position, cell) in map.Cells) cell.Turf.Appearance.Opacity = position.Item1 == 1;
    int before = DreamList.Released;
    Check(server.TestExecute(connection, target) == access.IsRange(), "opaque obstruction must deny view while preserving range");
    Check(DreamList.Released == before+1, "authorization releases temporary list");
    foreach (var cell in map.Cells.Values) cell.Turf.Appearance.Opacity = false;
    connection.Mob = null;
    Check(!server.TestExecute(connection, target), "server absent mob denies");
    connection.Mob = mob;
    server._verbs[0] = new(access, 1);
    Check(!server.TestExecute(connection, target), "server outside radius denies");
}
var view = DreamProcNativeHelpers.HandleView(new(), map, mob, new(0), true);
Check(view.ContainsValue(new(mob)), "view zero includes center mob");
Check(view.ContainsValue(new(carried)), "view includes center contents");
view.DecRef();
var oview = DreamProcNativeHelpers.HandleView(new(), map, mob, new(0), false);
Check(!oview.ContainsValue(new(mob)) && !oview.ContainsValue(new(carried)), "oview zero excludes center and contents");
oview.DecRef();
Console.WriteLine($"PASS {assertions} production spatial-verb assertions");
