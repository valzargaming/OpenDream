"""Omit one production ownership guard only in a disposable remote CI checkout."""
import argparse
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tests/native_argument_ownership'))
from verify import verify

controls = {
    'baseline': ('Filtered empty prompt releases snapshot owners', 'payload.RefCount', 2, 3),
    'finally': ('Cancelled prompt releases snapshot owners', 'payload.RefCount', 2, 3),
    'negative-index': ('Negative prompt index is handled without an exception', 'failures', 0, 1),
    'filter-index': ('Filtered prompt index selects the displayed item', 'wrongSelection', 0, 1),
    'stat-replace': ('StatObj self assignment owns one reference', 'payload.RefCount', 3, 4),
    'eye-release': ('Disconnect releases custom Eye owner', 'retainedEye', 0, 1),
    'prompt-cancel': ('Disconnect completes pending prompts', 'unfinished', 0, 1),
}
parser = argparse.ArgumentParser()
parser.add_argument('control', choices=controls)
parser.add_argument('--verify', type=pathlib.Path)
parser.add_argument('--trx', type=pathlib.Path)
parser.add_argument('--exit-code', type=int)
args = parser.parse_args()
marker, expression, expected, actual = controls[args.control]
if args.verify:
    if not args.trx:
        raise SystemExit('Structured TRX result required')
    verify(args.trx, args.verify.read_text(errors='replace'), args.exit_code, marker,
           expressions=(expression,), expected=expected, actual=actual,
           fixture_method='ClientPromptsReleaseOwnedValues', fixture_file='GameTests.ClientPrompts.cs')
    print('INTENDED CLIENT PROMPT OMISSION REJECTED:', args.control)
    raise SystemExit(0)

path = root / 'OpenDreamRuntime/DreamConnection.cs'
source = path.read_text()
if args.control == 'baseline':
    historical = subprocess.check_output(['git', 'show', '1b8406798c3a907d14aca0d15ddcc8357aa62718:OpenDreamRuntime/DreamConnection.cs'], text=True)
    start = '    public async Task<DreamValue> PromptList('
    end = '    public Task<DreamValue> WinExists('
    def method(content):
        if content.count(start) != 1 or content.count(end) != 1:
            raise SystemExit('Historical prompt method boundaries not unique')
        return content[content.index(start):content.index(end)]
    source = source.replace(method(source), method(historical))
else:
    targets = {
        'finally': ('            foreach (var value in listValues)\n                value.Dispose();', '            // Omit snapshot release.'),
        'negative-index': ('index >= 0 && index < listValues.Count', 'index < listValues.Count'),
        'filter-index': ('var selected = listValues[index];', 'var selected = list.CopyToArray()[index];'),
        'stat-replace': ('            field.Dispose();', '            // Omit StatObj replacement release.'),
        'eye-release': ('            Eye = null;', '            // Omit custom Eye release.'),
        'prompt-cancel': ('            foreach (var prompt in prompts)\n                prompt.TrySetResult(DreamValue.Null);', '            // Omit pending prompt completion.'),
    }
    old, new = targets[args.control]
    if source.count(old) != 1:
        raise SystemExit('Omission target not unique: ' + args.control)
    source = source.replace(old, new)
path.write_text(source)
(root / 'client-prompt-control-source.json').write_text(json.dumps({
    'control': args.control, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'expected': marker, 'expected_count': expected, 'actual_count': actual,
}, indent=2))
