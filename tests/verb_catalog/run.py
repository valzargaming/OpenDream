"""Run production client verb handlers with inert UI and exact omission controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def definition(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run_case(dotnet, control, output):
    client_path = ROOT / 'OpenDreamClient/ClientVerbSystem.cs'
    event_path = ROOT / 'OpenDreamShared/Dream/VerbSystem.cs'
    client, events = client_path.read_text(), event_path.read_text()
    methods = '\n'.join(definition(client, marker) for marker in (
        'private void OnAllVerbsEvent(', 'private void OnRegisterVerbEvent(',
        'private void OnUpdateClientVerbsEvent(', 'public override void Shutdown()'))
    methods = methods.replace('public override void Shutdown()', 'public void Shutdown()')
    replacements = {
        'catalog-add': ('_verbs[i] = verb;', '_verbs.Add(i, verb);'),
        'register-add': ('_verbs[e.VerbId] = e.VerbInfo;', '_verbs.Add(e.VerbId, e.VerbInfo);'),
        'shutdown-retain': ('_verbs.Clear();', '// deliberately omitted by control'),
    }
    if control:
        before, after = replacements[control]
        if methods.count(before) != 1:
            raise RuntimeError(f'control source guard failed: {control}')
        methods = methods.replace(before, after)
    event_definitions = '\n'.join(definition(events, 'public sealed class ' + name + '(')
                                  for name in ('AllVerbsEvent', 'RegisterVerbEvent', 'UpdateClientVerbsEvent'))
    event_definitions = event_definitions.replace(' : EntityEventArgs', '')
    program = (ROOT / 'tests/verb_catalog/Program.cs').read_text()
    program = program.replace('    EVENTS', event_definitions).replace('    METHODS', methods)
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    with tempfile.TemporaryDirectory(prefix='opendream-verb-catalog-') as temporary:
        work = Path(temporary)
        environment['DOTNET_CLI_HOME'] = str(work / 'dotnet-home')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable>
<ImplicitUsings>enable</ImplicitUsings><TreatWarningsAsErrors>true</TreatWarningsAsErrors>
</PropertyGroup></Project>''')
        (work / 'Program.cs').write_text(program)
        build_logs = []
        for command in (
            [dotnet, 'restore', '--configfile', str(work / 'NuGet.Config')],
            [dotnet, 'build', '--no-restore', '--disable-build-servers', '-m:1', '-p:UseSharedCompilation=false'],
        ):
            result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                                    timeout=120)
            build_logs.append(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError('Build failure cannot count as a regression control:\n' + build_logs[-1])
        result = subprocess.run([dotnet, str(work / 'bin/Debug/net10.0/Probe.dll')], cwd=work,
                                env=environment, capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr
    if control:
        expected = ('shutdown must release previous-session catalog' if control == 'shutdown-retain'
                    else 'An item with the same key has already been added')
        if result.returncode != 1 or 'REGRESSION:' not in log or expected not in log:
            raise RuntimeError(f'{control} did not fail its intended assertion:\n{log}')
        print(f'PASS rejected {control}: intended regression')
    elif result.returncode != 0 or 'PASS 13 production verb catalog assertions' not in log:
        raise RuntimeError(log)
    else:
        print(log.strip())
    receipt = {
        'control': control, 'exit_code': result.returncode, 'expected_result_verified': True,
        'client_sha256': hashlib.sha256(client.encode()).hexdigest(),
        'events_sha256': hashlib.sha256(events.encode()).hexdigest(),
        'scope': 'Extracted production catalog handlers, Shutdown and event definitions; inert UI/VerbInfo adapters. '
                 'No connected client, networking, full interpreter or live server.',
    }
    if output:
        output.mkdir(parents=True, exist_ok=True)
        name = control or 'positive'
        (output / f'{name}.log').write_text(log)
        (output / f'{name}.json').write_text(json.dumps(receipt, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--all-controls', action='store_true')
    args = parser.parse_args()
    if not Path(args.dotnet).is_absolute() or not Path(args.dotnet).is_file():
        parser.error('--dotnet must be an existing absolute SDK path')
    run_case(args.dotnet, None, args.output)
    if args.all_controls:
        for control in ('catalog-add', 'register-add', 'shutdown-retain'):
            run_case(args.dotnet, control, args.output)


if __name__ == '__main__':
    main()
