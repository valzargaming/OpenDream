"""Package-free isolated production-body retention audit; no runtime attachment."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]

def body(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    level = 1
    end = brace + 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def pool_capacity_declaration(source):
    declarations = re.findall(r'^    private const int MaximumPooledCapacity = [0-9_]+;$', source, re.MULTILINE)
    if len(declarations) != 1:
        raise ValueError('Missing unique production pool-cap declaration')
    return declarations[0]

def run(dotnet, output, control, work):
    paths = ['OpenDreamRuntime/Procs/DreamEnumerators.cs', 'OpenDreamRuntime/Procs/DMOpcodeHandlers.cs',
             'OpenDreamRuntime/Procs/AsyncNativeProc.cs', 'OpenDreamRuntime/Procs/ProcScheduler.cs',
             'OpenDreamRuntime/Procs/Native/DreamProcNativeHelpers.cs', 'OpenDreamRuntime/Objects/Types/DreamList.cs']
    sources = {p: (ROOT/p).read_text() for p in paths}
    receipt = {'head': subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'sources': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}, 'control': control,
               'harness': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir() if p.suffix in ('.cs', '.py')},
               'scope': 'Production contents factory/full enumerators/full HandleRange/list AddValue/deletion/async state/scheduler with inert reference, map, type, assignment and thread adapters; not complete interpreter or live retained-root evidence'}
    with tempfile.TemporaryDirectory(prefix='opendream-roots-', dir=work) as tmp:
        temp = Path(tmp)
        (temp/'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        (temp/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup><Compile Include="*.cs"/></ItemGroup></Project>')
        for name in ('Stubs.cs', 'Program.cs'):
            (temp/name).write_bytes((Path(__file__).parent/name).read_bytes())
        enums = sources[paths[0]]
        if control == 'filtered-dispose':
            fragment = 'for (int i = _current + 1; i < values.Length; i++)\n            values[i].Dispose();'
            assert enums.count(fragment) == 1
            enums = enums.replace(fragment, '')
        (temp/'DreamEnumerators.cs').write_text(enums)
        factory = body(sources[paths[1]], 'private static IDreamValueEnumerator GetContentsEnumerator(').replace('private static IDreamValueEnumerator GetContentsEnumerator(', 'public static IDreamValueEnumerator Create(')
        (temp/'ProductionContents.cs').write_text('using OpenDreamRuntime.Objects; using OpenDreamRuntime.Objects.Types; namespace OpenDreamRuntime.Procs; public static class ProductionContents { '+factory+' }')
        native = body(sources[paths[4]], 'public static DreamList HandleRange(')
        if control == 'range-variable':
            assert native.count('centerContents.Dispose();') == 1
            native = native.replace('centerContents.Dispose();', '')
        (temp/'ProductionRange.cs').write_text('using OpenDreamRuntime.Objects.Types; namespace OpenDreamRuntime.Procs.Native; public static partial class DreamProcNativeHelpers { '+native+' }')
        methods = pool_capacity_declaration(sources[paths[5]]) + '\n' + '\n'.join(body(sources[paths[5]], marker) for marker in ('public virtual void AddValue(', 'public Dictionary<DreamValue, DreamValue> CopyAssocValues(', 'protected override void HandleDeletion('))
        if control == 'list-deletion':
            fragment = 'foreach (var value in _values)\n            value.DecRef();'
            assert methods.count(fragment) == 1
            methods = methods.replace(fragment, '')
        (temp/'ProductionList.cs').write_text('namespace OpenDreamRuntime.Objects.Types; public partial class DreamList { '+methods+' }')
        async_source = sources[paths[2]].replace('[Dependency]', '[Robust.Shared.IoC.DependencyAttribute]')
        if control == 'async-slots':
            assert async_source.count('Array.Clear(_arguments, 0, ArgumentCount);') == 1
            async_source = async_source.replace('Array.Clear(_arguments, 0, ArgumentCount);', '')
        (temp/'AsyncNativeProc.cs').write_text(async_source)
        (temp/'ProcScheduler.cs').write_text(sources[paths[3]])
        env = dict(os.environ, DOTNET_CLI_HOME=str(temp/'cli'), DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true', MSBUILDDISABLENODEREUSE='1')
        commands = [
            [dotnet, 'restore', str(temp/'Probe.csproj'), '--configfile', str(temp/'NuGet.Config'), '--disable-parallel'],
            [dotnet, 'build', str(temp/'Probe.csproj'), '-c', 'Release', '--no-restore', '--disable-build-servers', '-m:1', '-p:UseSharedCompilation=false'],
            [dotnet, str(temp/'bin/Release/net10.0/Probe.dll')],
        ]
        logs = []
        for index, command in enumerate(commands):
            result = subprocess.run(command, cwd=temp, env=env, capture_output=True, text=True, timeout=90)
            log = result.stdout + result.stderr
            logs.append(log)
            (output/f'{control or "positive"}-{index}.log').write_text(log)
            if index < 2 and result.returncode:
                raise RuntimeError('Fixture preparation/compilation failed: '+log)
        expected = {'filtered-dispose': 'filtered-break owned reference', 'range-variable': 'range owned reference 3', 'list-deletion': 'range owned reference', 'async-slots': 'pooled arguments retain managed objects'}
        if control:
            assert result.returncode and expected[control] in log, 'Control failed to reject intended omitted release: '+log
            receipt['result'] = 'expected ownership failure detected'
        else:
            assert result.returncode == 0 and 'PASS 80000 ' in log, log
            receipt['result'] = 'passed'
            receipt['batches'] = json.loads(log.splitlines()[-1])
        (output/f'{control or "positive"}-receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps({'control': control, 'result': receipt['result']}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dotnet', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--control', choices=['filtered-dispose', 'range-variable', 'list-deletion', 'async-slots'])
    parser.add_argument('--all-controls', action='store_true')
    parser.add_argument('--work', type=Path, required=True, help='Owner-specific temporary directory, removable after a watchdog abort')
    parser.add_argument('--start-gated', action='store_true', help='Wait for the Windows watchdog to assign its process job')
    args = parser.parse_args()
    if args.start_gated and sys.stdin.readline().strip() != 'start':
        raise RuntimeError('Resource owner did not release execution gate')
    if args.control and args.all_controls:
        parser.error('Choose one control or all-controls')
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    for control in ([None, 'filtered-dispose', 'range-variable', 'list-deletion', 'async-slots'] if args.all_controls else [args.control]):
        run(args.dotnet, args.output, control, args.work)
