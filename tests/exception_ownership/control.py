"""CI-only omissions in a disposable checkout; never run against a live engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '746c85c609d6c67b047ba7979e47cb59d0ded662'
PATHS = ['OpenDreamRuntime/DreamThread.cs', 'OpenDreamRuntime/DreamManager.cs',
         'OpenDreamRuntime/Procs/DMProc.cs',
         'OpenDreamRuntime/Objects/Types/DreamObjectException.cs']
EXPECTED = {
    'baseline': 'Exception ownership balanced: exception_discard_probe',
    'discard-release': 'Exception ownership balanced: exception_discard_probe',
    'transfer-clear': 'Exception ownership balanced: exception_bound_probe',
    'field-release': 'Exception native fields release original owner',
}


def replace(path, old, new):
    target = ROOT / path
    text = target.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Control source drift: {path}')
    target.write_text(text.replace(old, new))


def prepare(control):
    if control == 'baseline':
        for path in PATHS:
            historical = subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT)
            if path == 'OpenDreamRuntime/Procs/DMProc.cs':
                # Preserve independent argument conversion fixes in this file.
                target = ROOT / path
                current = target.read_text()
                signature = '    public override void CatchException(Exception exception, string file, int line) {'
                def method(source):
                    if source.count(signature) != 1:
                        raise RuntimeError('Exception baseline catch method not unique')
                    start = source.index(signature)
                    end = source.index('\n    public override void Dispose()', start)
                    return source[start:end]
                target.write_text(current.replace(method(current), method(historical.decode().replace('\r\n', '\n'))))
            else:
                (ROOT / path).write_bytes(historical)
    elif control == 'discard-release':
        replace(PATHS[0], '// A catch without a binding still consumes the thrown value.\n'
                '                (exception as DMThrowException)?.Dispose();',
                '// Control: discard release omitted.')
    elif control == 'transfer-clear':
        replace(PATHS[0], '_value = DreamValue.Null;\n            return value;', 'return value;')
    elif control == 'field-release':
        path = PATHS[3]
        text = (ROOT / path).read_text()
        start = text.index('    protected override void HandleDeletion() {')
        end = text.index('    protected override void SetVar', start)
        (ROOT / path).write_text(text[:start] + text[end:])
    receipt = {'control': control, 'baseline': BASELINE,
               'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'sources': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PATHS}}
    (ROOT / 'exception-control-source.json').write_text(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('control', choices=EXPECTED)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--exit-code', type=int)
    args = parser.parse_args()
    if args.verify:
        log = args.verify.read_text()
        if args.exit_code != 1 or EXPECTED[args.control] not in log or 'Failed NoRuntimesTest' not in log:
            raise SystemExit('Control failed to reject the intended native assertion')
        print('PASS rejected ' + args.control + ': ' + EXPECTED[args.control])
    else:
        prepare(args.control)
