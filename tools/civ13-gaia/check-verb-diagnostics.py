"""Compile spatial verb selectors and verify only supported diagnostics disappear."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dotnet', required=True)
parser.add_argument('--compiler', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []


def compile_case(name, source, expected_error=None, expected_code='OD2800'):
    with tempfile.TemporaryDirectory(prefix='opendream-verb-diagnostics-') as temporary:
        dme = Path(temporary) / 'probe.dme'
        dme.write_text(source)
        run = subprocess.run([args.dotnet, str(args.compiler.resolve()), '--version=516.1681', str(dme)],
                             cwd=temporary, text=True, capture_output=True, timeout=30)
        log = run.stdout + run.stderr
        (args.output / f'{name}.log').write_text(log)
        if expected_error:
            matching_diagnostic = any(f'Error {expected_code}' in line and expected_error in line
                                      for line in log.splitlines())
            assert run.returncode != 0 and matching_diagnostic, log
            assert not dme.with_suffix('.json').exists(), 'Failed fixture must not publish JSON'
            results.append({'case': name, 'result': 'intended diagnostic rejected compilation'})
            print(f'PASS retained {name} diagnostic')
            return None
        assert run.returncode == 0 and 'Warning OD' not in log and 'Error OD' not in log, log
        compiled = json.loads(dme.with_suffix('.json').read_text())
        (args.output / f'{name}.json').write_text(json.dumps(compiled, indent=2))
        return compiled


source = '#pragma UnimplementedAccess error\n'
expected = {}
for keyword_index, keyword in enumerate(('view', 'oview', 'range', 'orange')):
    for membership in (False, True):
        name = f'case_{keyword}_{"in" if membership else "equal"}'
        radius = '1.25' if membership else '0'
        source += f'/mob/verb/{name}()\n\tset src {"in" if membership else "="} {keyword}({radius})\n\treturn\n'
        expected[name] = (keyword_index * 2 + int(membership), 2 if membership else 0)
compiled = compile_case('explicit-radii', source)
verbs = {proc['Name']: proc for proc in compiled['Procs'] if proc.get('IsVerb')}
assert set(expected) <= set(verbs), 'Expected all eight spatial verb declarations'
for name, (accessibility, radius) in expected.items():
    assert verbs[name]['VerbSrc'] == accessibility, (name, verbs[name])
    assert verbs[name]['VerbRange'] == radius, (name, verbs[name])
results.append({'case': 'explicit-radii', 'result': 'eight verb families emit expected IDs and rounded radii without warnings'})
print('PASS eight compiled spatial selectors and fractional-radius rounding')

compile_case('default-radius', '#pragma UnimplementedAccess error\n/mob/verb/check_default()\n\tset src = view()\n\treturn\n',
             'Default view() verb radius does not yet use world.view')
compile_case('nonconstant-radius', '#pragma BadArgument error\n/mob/var/radius = 2\n/mob/verb/check_dynamic()\n\tset src = view(radius)\n\treturn\n',
             'Range must be a constant value', 'OD0100')
compile_case('too-many-arguments', '#pragma BadArgument error\n/mob/verb/check_arguments()\n\tset src = view(1, usr, usr)\n\treturn\n',
             'Cannot specify more than two arguments', 'OD0100')
compile_case('instant', '#pragma UnimplementedAccess error\n/mob/verb/check_instant()\n\tset instant = 1\n\treturn\n',
             'set instant is not implemented')
compile_case('crop', '#pragma UnimplementedAccess error\n/proc/check_crop()\n\tvar/icon/I = new\n\tI.Crop(1, 1, 2, 2)\n',
             '/icon.Crop() is not implemented')
compile_case('run', '#pragma UnimplementedAccess error\n/proc/check_run()\n\trun("unused.txt")\n',
             '/.run() is not implemented')
receipt = {'compiler_sha256': hashlib.sha256(args.compiler.read_bytes()).hexdigest(), 'results': results,
           'scope': 'Actual compiler and emitted verb metadata; no server, client, filesystem run builtin or gameplay execution.'}
(args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
