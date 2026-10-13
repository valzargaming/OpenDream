"""Package-free production-body savefile teardown regression; never attaches to a server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PATHS = ['OpenDreamRuntime/Objects/DreamObject.cs',
         'OpenDreamRuntime/Objects/Types/DreamObjectSavefile.cs',
         'OpenDreamRuntime/Objects/DreamRefManager.cs']
BASELINE = 'ac6fc2f065734a56c47c4e8ec8e78f70f29727c7'


def body(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    level, end = 1, brace + 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', *args],
                                   cwd=ROOT, text=True, timeout=10).strip()


def run(args, control):
    sources = {path: (ROOT / path).read_text(encoding='utf-8-sig') for path in PATHS}
    receipt = {'head': git('rev-parse', 'HEAD'), 'control': control,
               'sources': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS},
               'harness': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in HERE.iterdir() if path.suffix in ('.cs', '.py')},
               'scope': 'Production Initialize/Close/Flush/savefile and base teardown/refcount bodies '
                        'and complete ref bucket; inert object/type/proc adapters and disk-backed '
                        'resource/JSON adapters. Not the complete interpreter or Gaia retained-root evidence.'}
    savefile = sources[PATHS[1]]
    if control == 'baseline':
        savefile = git('show', f'{BASELINE}:{PATHS[1]}')
        receipt['baseline'] = BASELINE
    methods = '\n'.join(body(savefile, marker) for marker in (
        'public override void Initialize(', 'protected override void HandleDeletion()',
        'public void Close()', 'public void Flush()'))
    if control == 'close-detach':
        old_close = body(git('show', f'{BASELINE}:{PATHS[1]}'), 'public void Close()')
        # Preserve the candidate's null-resource behavior to isolate the old
        # failed-flush detachment defect from the separate initializer defect.
        old_close = old_close.replace('{', '{\n        if (Resource is null) return;', 1)
        methods = methods.replace(body(savefile, 'public void Close()'), old_close)
    if control == 'base-cleanup':
        fragment = 'base.HandleDeletion();'
        assert methods.count(fragment) == 1
        methods = methods.replace(fragment, '')
    if control == 'directory-removal':
        fragment = 'SavefileDirectories.Remove(Resource.ResourcePath);'
        assert methods.count(fragment) == 1
        methods = methods.replace(fragment, '{}')
    with tempfile.TemporaryDirectory(prefix='savefile-cleanup-', dir=args.work) as tmp:
        temp = Path(tmp)
        (temp / 'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        (temp / 'Probe.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
            '<TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings>'
            '<Nullable>enable</Nullable><TreatWarningsAsErrors>true</TreatWarningsAsErrors>'
            '</PropertyGroup></Project>')
        for name in ('Stubs.cs', 'Program.cs'):
            (temp / name).write_bytes((HERE / name).read_bytes())
        base = '\n'.join(body(sources[PATHS[0]], marker) for marker in (
            'protected virtual void HandleDeletion()', 'public void IncRef()',
            'public void DecRef()', 'public void Delete()'))
        bucket = body(sources[PATHS[2]], 'private sealed class Bucket')
        (temp / 'Production.cs').write_text(
            'using System.Text.Json;\npublic partial class DreamObject {\n' + base + '\n}\n'
            'public sealed partial class DreamObjectSavefile {\n' + methods + '\n}\n'
            'public sealed class Registry {\n'
            'public static readonly Registry Instance = new(); private readonly Bucket _bucket = new();\n'
            'public uint Add(DreamObject value) => (uint)_bucket.Add(value);\n'
            'public void DeleteRef(uint id) => _bucket.Remove((int)id);\n'
            'public int Count => _bucket.FilledCount;\n' + bucket + '\n}\n')
        env = dict(os.environ, DOTNET_CLI_HOME=str(temp / 'cli'), DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                   DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1',
                   DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true', MSBUILDDISABLENODEREUSE='1',
                   TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
        commands = [
            [args.dotnet, 'restore', str(temp / 'Probe.csproj'), '--configfile', str(temp / 'NuGet.Config'), '--disable-parallel'],
            [args.dotnet, 'build', str(temp / 'Probe.csproj'), '-c', 'Release', '--no-restore',
             '--disable-build-servers', '-m:1', '-p:UseSharedCompilation=false', '-nodeReuse:false'],
            [args.dotnet, str(temp / 'bin/Release/net10.0/Probe.dll')],
        ]
        for index, command in enumerate(commands):
            remaining = args.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Overall fixture deadline exhausted')
            result = subprocess.run(command, cwd=temp, env=env, capture_output=True, text=True,
                                    timeout=min(60, remaining))
            log = result.stdout + result.stderr
            (args.output / f'{control or "positive"}-{index}.log').write_text(log)
            if index < 2 and result.returncode:
                raise RuntimeError('Preparation/compilation failed: ' + log)
        expected = {'baseline': 'FAIL: null-resource deletion releases object variables',
                    'base-cleanup': 'FAIL: null-resource deletion releases object variables',
                    'close-detach': 'FAIL: flush failure retains dirty handle',
                    'directory-removal': 'FAIL: shared close retains directory cache'}
        if control:
            if result.returncode != 1 or expected[control] not in log:
                raise RuntimeError('Control did not reject the intended omission: ' + log)
            receipt['result'] = 'expected teardown failure detected'
            receipt['expected_failure'] = expected[control]
        else:
            if result.returncode or ' production savefile cleanup assertions' not in log:
                raise RuntimeError('Positive fixture failed: ' + log)
            receipt['result'] = 'passed'
            receipt['assertions'] = int(log.split('PASS ', 1)[1].split(' ', 1)[0])
        (args.output / f'{control or "positive"}-receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps({'control': control, 'result': receipt['result']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dotnet', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--control', choices=['baseline', 'base-cleanup', 'close-detach', 'directory-removal'])
    parser.add_argument('--all-controls', action='store_true')
    parser.add_argument('--start-gated', action='store_true')
    parser.add_argument('--deadline-seconds', type=int, default=300)
    args = parser.parse_args()
    if args.start_gated and input().strip() != 'start':
        raise RuntimeError('Resource owner did not release execution gate')
    if args.control and args.all_controls:
        parser.error('Choose one control or all-controls')
    if not Path(args.dotnet).is_absolute() or not Path(args.dotnet).is_file() or not 1 <= args.deadline_seconds <= 360:
        parser.error('Existing absolute SDK executable and deadline <=360 seconds required')
    args.deadline = time.monotonic() + args.deadline_seconds
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    for control in ([None, 'baseline', 'base-cleanup', 'close-detach', 'directory-removal']
                    if args.all_controls else [args.control]):
        run(args, control)
