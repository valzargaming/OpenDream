using OpenDreamClient.Audio;
using OpenDreamClient.Interface;
using OpenDreamClient.Rendering.Particles;
using OpenDreamClient.Resources;
using OpenDreamClient.States;
using OpenDreamClient.NativeByond;
using OpenDreamShared;
using Robust.Shared.Configuration;

namespace OpenDreamClient;

public static class ClientContentIoC {
    public static void Register() {
        IoCManager.RegisterInstance<NativeIdentityCoordinator>(new NativeIdentityCoordinator(
            new NativeIdentityObserverProvider(new FileNativeObserverHost(), () => {
                var config = IoCManager.Resolve<IConfigurationManager>();
                return new NativeObserverOptions(config.GetCVar(OpenDreamCVars.NativeByondBin),
                    config.GetCVar(OpenDreamCVars.NativeObserverDirectory));
            })));
        IoCManager.Register<IDreamInterfaceManager, DreamInterfaceManager>();
        IoCManager.Register<IDreamResourceManager, DreamResourceManager>();
        IoCManager.Register<DreamUserInterfaceStateManager>();
        IoCManager.Register<IDreamSoundEngine, DreamSoundEngine>();
        IoCManager.Register<ParticlesManager>(); //TODO remove when particles RT PR is merged
    }
}
