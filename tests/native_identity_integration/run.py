"""Compile actual provider/admission source; inject all process/file/native-client effects."""
import argparse
import pathlib
import re
import subprocess
import tempfile
from xml.sax.saxutils import escape

root = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--control', choices=['consume', 'current', 'deadline', 'provider-binding', 'provider-disposal', 'channel-replay'])
args = parser.parse_args()
files = [root / path for path in [
    'OpenDreamRuntime/NativeByondBridge/NativeClientReportLedger.cs',
    'OpenDreamRuntime/NativeByondBridge/NativeIdentityAdmissionGate.cs',
    'OpenDreamClient/NativeByond/NativeIdentityCoordinator.cs',
    'OpenDreamClient/NativeByond/NativeIdentityObserverProvider.cs',
    'OpenDreamClient/NativeByond/FileNativeObserverHost.cs',
    'tests/native_identity_integration/Program.cs']]
controls = {
    'consume': (1, '_attempts.Remove(binding, out var attempt)', '_attempts.TryGetValue(binding, out var attempt)', 'admission replay rejected'),
    'current': (1, 'Expired(attempt) || !_current(binding) || attempt.Claim', 'Expired(attempt) || false || attempt.Claim', 'disconnected channel cannot create DM client'),
    'deadline': (1, '_time.GetElapsedTime(attempt.Started) >= NativeClientReportLedger.Lifetime', 'false', 'expired completed report cannot create DM client'),
    'provider-binding': (3, 'observed.Epoch != request.Epoch || observed.Nonce != request.Nonce', 'false', 'provider rejects stale local observation'),
    'provider-disposal': (3, 'await using var observation =', 'var observation =', 'successful observation disposes owned world'),
    'channel-replay': (2, '_disposed || !_handshakeUsed || _channelUsed || _identity', '_disposed || !_handshakeUsed || false || _identity', 'local native report cannot cross two channels'),
}
helper = (root / 'OpenDreamRuntime/Procs/Native/DreamProcNativeHelpers.cs').read_text()
body = re.search(r'public static string Ckey\(string input\) \{(.*?)\n    \}', helper, re.S)
regex = re.search(r'(\[GeneratedRegex\([^\n]+\)\]\s*private static partial Regex CkeyRegex\(\);)', helper)
if not body or not regex:
    raise SystemExit('Production Ckey extraction failed')
with tempfile.TemporaryDirectory(prefix='native-integration-') as directory:
    temp = pathlib.Path(directory)
    if args.control:
        index, old, new, expected = controls[args.control]
        text = files[index].read_text()
        if text.count(old) != 1: raise SystemExit('Control target is not unique')
        replacement = temp / files[index].name
        # Replay control must retain the local report too; otherwise the independent release guard rejects replay.
        if args.control == 'channel-replay':
            anchor = '        _identity = null;\n        return true;'
            if text.count(anchor) != 1: raise SystemExit('Channel release target is not unique')
            text = text.replace(anchor, '        // omitted channel report release\n        return true;')
        replacement.write_text(text.replace(old, new))
        files[index] = replacement
    production_ckey = temp / 'ProductionCkey.cs'
    production_ckey.write_text('using System.Text.RegularExpressions;\nnamespace OpenDreamRuntime.Procs.Native;\npublic static partial class DreamProcNativeHelpers {\npublic static string Ckey(string input) {' + body.group(1) + '\n}\n' + regex.group(1) + '\n}\n')
    files.append(production_ckey)
    (temp / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>14</LangVersion><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '" />' for path in files) + '</ItemGroup></Project>')
    build = subprocess.run(['dotnet', 'build', str(temp / 'Probe.csproj'), '-c', 'Release'], text=True, capture_output=True, timeout=120)
    print(build.stdout, build.stderr)
    if build.returncode: raise SystemExit('Compilation failure cannot prove a control')
    run = subprocess.run(['dotnet', str(temp / 'bin/Release/net10.0/Probe.dll')], text=True, capture_output=True, timeout=30)
    print(run.stdout, run.stderr)
    if args.control:
        headline = 'Unhandled exception. System.InvalidOperationException: INTEGRATION ASSERTION: ' + expected
        lines = run.stderr.strip().splitlines()
        if run.returncode == 0 or not lines or lines[0] != headline or any(not line.lstrip().startswith('at ') for line in lines[1:]):
            raise SystemExit('Control did not fail only its intended assertion')
        print('INTENDED NATIVE INTEGRATION OMISSION REJECTED:', args.control)
    elif run.returncode or 'NATIVE INTEGRATION PASS:' not in run.stdout:
        raise SystemExit('Native integration probe failed')
