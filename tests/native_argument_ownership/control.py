"""Omit one actual production guard in a disposable connected-engine CI checkout."""
import argparse
import json
import pathlib
import subprocess
from verify import verify

root = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('control', choices=['baseline', 'sync-finally', 'async-replace'])
parser.add_argument('--verify', type=pathlib.Path)
parser.add_argument('--exit-code', type=int)
parser.add_argument('--trx', type=pathlib.Path)
args = parser.parse_args()
markers = {
    'baseline': 'Native call argument ownership balanced: native_argument_failure_probe',
    'sync-finally': 'Native call argument ownership balanced: native_argument_failure_probe',
    'async-replace': 'Async slot replacement releases original owner',
}
if args.verify:
    log = args.verify.read_text(errors='replace')
    if not args.trx:
        raise SystemExit('Structured TRX result required')
    verify(args.trx, log, args.exit_code, markers[args.control])
    print('INTENDED NATIVE ARGUMENT OMISSION REJECTED:', args.control)
    raise SystemExit(0)
paths = ['OpenDreamRuntime/Procs/NativeProc.cs', 'OpenDreamRuntime/Procs/AsyncNativeProc.cs']
if args.control == 'baseline':
    for path in paths:
        content = subprocess.check_output(['git', 'show', 'df99ae89ca4cccc34325d99b0779ac4e569d8de5:' + path])
        (root / path).write_bytes(content)
elif args.control == 'sync-finally':
    path = root / paths[0]
    content = path.read_text()
    old = '''        try {
            return _handler(bundle, src, usr); // TODO: Include this call in the thread's stack in error traces
        } finally {
            arguments.Dispose();
        }'''
    new = '''        var result = _handler(bundle, src, usr);
        arguments.Dispose();
        return result;'''
    if content.count(old) != 1: raise SystemExit('Native finally target not unique')
    path.write_text(content.replace(old, new))
else:
    path = root / paths[1]
    content = path.read_text()
    old = '                value.IncRef();\n                _arguments[id].Dispose();\n'
    if content.count(old) != 1: raise SystemExit('Async replacement target not unique')
    path.write_text(content.replace(old, ''))
(root / 'native-argument-control-source.json').write_text(json.dumps({'control': args.control, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), 'expected': markers[args.control]}, indent=2))
