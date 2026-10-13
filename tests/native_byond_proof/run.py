"""Build linked real ledger source in temporary storage; no engine/client/listener/native launch."""
import argparse
import pathlib
import re
import subprocess
import tempfile
from xml.sax.saxutils import escape

root = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--control', choices=['epoch', 'replay', 'disconnect', 'deadline'])
args = parser.parse_args()
source = root / 'OpenDreamRuntime/NativeByondBridge/NativeClientReportLedger.cs'
controls = {
    'epoch': ('epoch != Epoch', 'false', 'wrong bridge epoch rejected'),
    'replay': ('_pending.Remove(nonce);\n            return _isCurrent!', '// OMIT completed ownership release\n            return _isCurrent!', 'delivery replay rejected'),
    'disconnect': ('return _isCurrent!(selected.Binding) && deliverIfCurrent', 'return deliverIfCurrent', 'disconnected session delivery rejected'),
    'deadline': ('if (_time.GetElapsedTime(pair.Value.Started) < Lifetime) continue;', 'continue;', 'callback at total deadline rejected'),
}
helper = (root / 'OpenDreamRuntime/Procs/Native/DreamProcNativeHelpers.cs').read_text()
body = re.search(r'public static string Ckey\(string input\) \{(.*?)\n    \}', helper, re.S)
regex = re.search(r'(\[GeneratedRegex\([^\n]+\)\]\s*private static partial Regex CkeyRegex\(\);)', helper)
if not body or not regex:
    raise SystemExit('Production Ckey extraction failed')
with tempfile.TemporaryDirectory(prefix='native-proof-') as directory:
    temp = pathlib.Path(directory)
    linked = source
    if args.control:
        text = source.read_text()
        old, new, expected = controls[args.control]
        if text.count(old) != 1:
            raise SystemExit('Omission control target is not unique')
        linked = temp / 'NativeClientReportLedger.cs'
        linked.write_text(text.replace(old, new))
    (temp / 'ProductionCkey.cs').write_text('using System.Text.RegularExpressions;\npublic static partial class ProductionCkey {\npublic static string Ckey(string input) {' + body.group(1) + '\n}\n' + regex.group(1) + '\n}\n')
    (temp / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '" />' for path in [linked, root / 'tests/native_byond_proof/Program.cs', temp / 'ProductionCkey.cs']) + '</ItemGroup></Project>')
    build = subprocess.run(['dotnet', 'build', str(temp / 'Probe.csproj'), '-c', 'Release'], text=True, capture_output=True, timeout=120)
    print(build.stdout, build.stderr)
    if build.returncode:
        raise SystemExit('Compilation failure is not accepted as an omission-control result')
    run = subprocess.run(['dotnet', str(temp / 'bin/Release/net10.0/Probe.dll')], text=True, capture_output=True, timeout=30)
    print(run.stdout, run.stderr)
    if args.control:
        if run.returncode == 0 or 'PROOF ASSERTION: ' + expected not in run.stderr:
            raise SystemExit('Omission did not fail its intended assertion')
        print('INTENDED OMISSION REJECTED:', args.control)
    elif run.returncode != 0 or 'NATIVE REPORT LEDGER PASS:' not in run.stdout:
        raise SystemExit('Local ledger probe failed')
