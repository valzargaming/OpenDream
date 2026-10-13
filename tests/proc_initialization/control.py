"""Omit one frame-initialization owner guard in a disposable CI checkout."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/native_argument_ownership'))
from verify import verify

parser = argparse.ArgumentParser()
parser.add_argument('control', choices=['async-input', 'dm-input', 'async-baseline', 'dm-baseline'])
parser.add_argument('--verify', type=Path)
parser.add_argument('--trx', type=Path)
parser.add_argument('--exit-code', type=int)
args = parser.parse_args()
native = args.control.startswith('async-')
marker = ('Rejected async initialization releases input owner' if native else
          'Rejected DM initialization releases input and partial owners')
if args.verify:
    if not args.trx:
        raise SystemExit('Structured TRX required')
    verify(args.trx, args.verify.read_text(errors='replace'), args.exit_code, marker,
           expressions=('payload.RefCount',), actual=3 if args.control == 'dm-baseline' else 2,
           fixture_method='ProcInitializationReleasesOwnedValues', fixture_file='GameTests.ProcInitialization.cs')
    print('INTENDED INITIALIZATION OMISSION REJECTED:', args.control)
    raise SystemExit(0)

path = ROOT / ('OpenDreamRuntime/Procs/AsyncNativeProc.cs' if native else 'OpenDreamRuntime/Procs/DMProc.cs')
content = path.read_text()
signature = 'public override ProcState CreateState('
def factory(source):
    if source.count(signature) != 1:
        raise ValueError('Factory is not unique')
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

current = factory(content)
if args.control.endswith('-baseline'):
    # Restore just the immutable factory, keeping independent async/arglist fixes.
    baseline = subprocess.check_output(['git', 'show', '886c6ea98b61fed7b46a46e9dfb4aca97f06b2c2:' + str(path.relative_to(ROOT)).replace('\\', '/')], cwd=ROOT, text=True)
    replacement = factory(baseline)
else:
    guard = current.index('arguments.Count >' if native else 'Math.Max(arguments.Count')
    disposal = current.index('arguments.Dispose();', guard)
    replacement = current[:disposal] + '// Omitted rejected input disposal.' + current[disposal + len('arguments.Dispose();'):]
path.write_text(content.replace(current, replacement, 1))
(ROOT / 'proc-initialization-control-source.json').write_text(json.dumps({
    'control': args.control, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'baseline': '886c6ea98b61fed7b46a46e9dfb4aca97f06b2c2', 'expected_assertion': marker,
    'expected_retained_refs': 3 if args.control == 'dm-baseline' else 2}, indent=2))
