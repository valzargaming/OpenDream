"""Linked production coordinator with injected observer; never launches a native/game client."""
import argparse
import pathlib
import subprocess
import tempfile
from xml.sax.saxutils import escape

root = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--control', choices=['name', 'reuse', 'reconnect', 'binding', 'deadline'])
args = parser.parse_args()
source = root / 'OpenDreamClient/NativeByond/NativeIdentityCoordinator.cs'
controls = {
    'name': ('applyOverride(observed.Key);', '// omitted native name override', 'native name replaces supplied name'),
    'reuse': ('_disposed || _handshakeUsed ||', '_disposed ||', 'one observation cannot authorize another handshake'),
    'reconnect': ('_identity = null;', '// omitted identity release', 'account switch clears old report'),
    'binding': ('report.Epoch == _request.Epoch && report.Nonce == _request.Nonce && Valid(report)', 'Valid(report)', 'malformed report blocks handshake'),
    'deadline': ('private bool Expired => _time.GetElapsedTime(_started) >= Lifetime;', 'private bool Expired => false;', 'expired observation cannot authorize handshake'),
}
menu = (root / 'OpenDreamClient/States/MainMenu/MainMenuState.cs').read_text()
xaml = (root / 'OpenDreamClient/States/MainMenu/MainMenuControl.xaml').read_text()
entry = (root / 'OpenDreamClient/EntryPoint.cs').read_text()
assert 'UserNameBox' not in menu and 'CVars.PlayerName' not in menu
assert 'UsernameBox' not in xaml and 'NativeAccountProtected' in xaml
assert 'autoConnect: false' in (root / 'Resources/manifest.yml').read_text()
assert '_nativeIdentity.AuthorizeHandshake(name => _baseClient.PlayerNameOverride = name)' in entry
assert entry.index('_baseClient.RunLevelChanged +=') < entry.index('DreamUserInterfaceStateManager>().Initialize()')
with tempfile.TemporaryDirectory(prefix='native-client-identity-') as directory:
    temp = pathlib.Path(directory)
    linked = source
    if args.control:
        text = source.read_text()
        old, new, expected = controls[args.control]
        if text.count(old) != 1:
            raise SystemExit('Omission target is not unique')
        linked = temp / 'NativeIdentityCoordinator.cs'
        linked.write_text(text.replace(old, new))
    (temp / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '" />' for path in [linked, root / 'tests/native_client_identity/Program.cs']) + '</ItemGroup></Project>')
    build = subprocess.run(['dotnet', 'build', str(temp / 'Probe.csproj'), '-c', 'Release'], text=True, capture_output=True, timeout=120)
    print(build.stdout, build.stderr)
    if build.returncode:
        raise SystemExit('Compilation failure is not accepted as an omission result')
    run = subprocess.run(['dotnet', str(temp / 'bin/Release/net10.0/Probe.dll')], text=True, capture_output=True, timeout=30)
    print(run.stdout, run.stderr)
    if args.control:
        if run.returncode == 0 or 'IDENTITY ASSERTION: ' + expected not in run.stderr:
            raise SystemExit('Omission did not fail its intended assertion')
        print('INTENDED IDENTITY OMISSION REJECTED:', args.control)
    elif run.returncode or 'NATIVE CLIENT IDENTITY PASS:' not in run.stdout:
        raise SystemExit('Client identity probe failed')
