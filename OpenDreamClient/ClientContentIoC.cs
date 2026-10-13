using OpenDreamClient.Audio;
using OpenDreamClient.Interface;
using OpenDreamClient.Rendering.Particles;
using OpenDreamClient.Resources;
using OpenDreamClient.States;

namespace OpenDreamClient;

public static class ClientContentIoC {
    public static void Register() {
        // Native observation is registered by the trusted engine before content loads.
        IoCManager.Register<IDreamInterfaceManager, DreamInterfaceManager>();
        IoCManager.Register<IDreamResourceManager, DreamResourceManager>();
        IoCManager.Register<DreamUserInterfaceStateManager>();
        IoCManager.Register<IDreamSoundEngine, DreamSoundEngine>();
        IoCManager.Register<ParticlesManager>(); //TODO remove when particles RT PR is merged
    }
}
