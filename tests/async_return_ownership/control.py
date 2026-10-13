import argparse
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tests/native_argument_ownership'))
from verify import verify

parser = argparse.ArgumentParser()
parser.add_argument('control', choices=['baseline', 'acquire', 'replacement', 'dispose', 'reentry', 'refused-release'])
parser.add_argument('--verify', type=pathlib.Path)
parser.add_argument('--trx', type=pathlib.Path)
parser.add_argument('--exit-code', type=int)
args = parser.parse_args()
cases = {
    'baseline': ('Async returned value acquires an awaited owner', 'observed', 2, 1),
    'acquire': ('Async returned value acquires an awaited owner', 'observed', 2, 1),
    'replacement': ('Replacing pending return releases its prior owner', 'payload.RefCount', 2, 3),
    'dispose': ('Canceled pending async return releases its owner', 'payload.RefCount', 1, 2),
    'reentry': ('Reentrant async call preserves the earlier awaited owner', 'reentrant', 3, 0),
    'refused-release': ('Canceled live async delivery releases refused owner', 'payload.RefCount', 1, 2),
}
if args.verify:
    marker, expression, expected, actual = cases[args.control]
    if not args.trx: raise SystemExit('Structured TRX required')
    verify(args.trx, args.verify.read_text(errors='replace'), args.exit_code, marker,
           expressions=(expression,), expected=expected, actual=actual,
           fixture_method='AsyncReturnsOwnValues', fixture_file='GameTests.AsyncReturns.cs')
    print('INTENDED ASYNC RETURN OMISSION REJECTED:', args.control)
    raise SystemExit(0)

path = root / 'OpenDreamRuntime/Procs/AsyncNativeProc.cs'
if args.control == 'baseline':
    path.write_bytes(subprocess.check_output(['git', 'show', '103d12b8826af1f553da296d109441aca82ee8e7:OpenDreamRuntime/Procs/AsyncNativeProc.cs']))
else:
    content = path.read_text()
    if args.control == 'acquire':
        old = '                value.IncRef();\n                _callResult?.Dispose();'
        new = '                _callResult?.Dispose();'
    elif args.control == 'replacement':
        old = '                value.IncRef();\n                _callResult?.Dispose();'
        new = '                value.IncRef();'
    elif args.control == 'dispose':
        old = '                _callTcs = null!;\n                _callResult?.Dispose();'
        new = '                _callTcs = null!;'
    elif args.control == 'refused-release':
        old = '''                    if (callTcs?.TrySetResult(callResult) != true)
                        callResult.Dispose();'''
        new = '                    callTcs?.TrySetResult(callResult);'
    else:
        old = '''                if (_callProcNotify != null) {
                    var callProcNotify = _callProcNotify;
                    _callProcNotify = null;
                    Thread.PushProcState(callProcNotify);
                    return ProcStatus.Called;
                }'''
        new = ''
        # Restore the original check before the continuation consumes the result.
        before = '                // We\'ve just finished calling a proc, notify our task'
        if content.count(before) != 1: raise SystemExit('Reentry anchor not unique')
        content = content.replace(before, old + '\n\n' + before)
        # The inserted check is deliberately retained, remove only the late check.
        position = content.rfind(old)
        content = content[:position] + new + content[position+len(old):]
        path.write_text(content)
        raise SystemExit(0)
    if content.count(old) != 1: raise SystemExit('Omission target not unique')
    path.write_text(content.replace(old, new))
