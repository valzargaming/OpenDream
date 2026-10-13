using System.Reflection;
using OpenDreamClient.Rendering;
using OpenDreamClient.Interface;
using Robust.Client.Graphics;
using Robust.Client.GameObjects;
using Robust.Shared.Timing;

var checks = 0;
void Check(bool result, string label) { if (!result) throw new Exception(label); checks++; }
(AtomGlideSystem System, TransformSystem Transport, TransformComponent Transform, DMISpriteComponent Sprite) Setup(ushort rate=20) {
    var system=new AtomGlideSystem(); var transport=new TransformSystem(); var transform=new TransformComponent(); var sprite=new DMISpriteComponent();
    foreach (var (name,value) in new (string,object)[] {("_transformSystem",transport),("_entityManager",new Manager()),("_interfaceManager",new Interface()),("_gameTiming",new Timing(rate))})
        typeof(AtomGlideSystem).GetField(name,BindingFlags.Instance|BindingFlags.NonPublic)?.SetValue(system,value);
    EntitySystem.QueryValue=sprite; system.Initialize(); return (system,transport,transform,sprite);
}
foreach (ushort rate in new ushort[] {10,20,30,60}) {
    var p=Setup(rate); p.Transport.Receive(p.Transform,new(1,0));
    for (int step=2;step<=50;step++) {
        for (int f=0;f<6;f++) p.System.FrameUpdate(1f/60);
        var before=p.Transform.LocalPosition;
        p.Transport.Receive(p.Transform,new(step,0));
        Check(Vector2.Distance(before,p.Transform.LocalPosition)<0.00001f,"consecutive update must never snap");
    }
    for (int f=0;f<12;f++) p.System.FrameUpdate(1f/60);
    Check(Vector2.Distance(p.Transform.LocalPosition,new(50,0))<0.0001f,"automatic speed catches up to held-key cadence");
    p.Transport.Receive(p.Transform,new(70,0)); Check(p.Transform.LocalPosition.X==70,"teleports remain immediate");
    p.System.FrameUpdate(1f/60); Check(p.Transform.LocalPosition.X==70,"teleport cancels glide");
}
var explicitGlide=Setup(30); explicitGlide.Sprite.Icon.Appearance!.GlideSize=8;
explicitGlide.Transport.Receive(explicitGlide.Transform,new(1,0)); explicitGlide.System.FrameUpdate(0.05f);
Check(Math.Abs(explicitGlide.Transform.LocalPosition.X-0.375f)<0.00001f,"explicit glide uses actual tick rate");
var turn=Setup();turn.Transport.Receive(turn.Transform,new(1,0));turn.System.FrameUpdate(0.1f);
var pos=turn.Transform.LocalPosition;turn.Transport.Receive(turn.Transform,new(1,1));Check(pos==turn.Transform.LocalPosition,"turn continues rendered position");
for(int i=0;i<12;i++)turn.System.FrameUpdate(1f/60);
Check(Vector2.Distance(turn.Transform.LocalPosition,new(1,1))<0.0001f,"turn completes without overshoot");
Console.WriteLine($"PASS {checks} production glide assertions");
class Manager:IEntityManager {public bool Deleted(EntityUid uid)=>false;}
class Interface:IDreamInterfaceManager {public int IconSize=>32;}
class Timing(ushort rate):IGameTiming {public ushort TickRate=>rate;}
