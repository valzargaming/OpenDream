"""Exact committed-source controls. Does not build or launch the runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODES = ('positive', 'baseline', 'hash-only')
MANAGER = 'OpenDreamRuntime/Resources/DreamResourceManager.cs'
SAVEFILE = 'OpenDreamRuntime/Objects/Types/DreamObjectSavefile.cs'
BASE = '5075c426b2f6f37dccb14b0902bb98780bbd62e1'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def blob(raw): return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout

def mutate(raw, mode, spec):
    assert mode in MODES and sha(raw) == spec['candidate_sha256'], 'unreviewed candidate'
    if mode == 'positive': return raw
    if mode == 'baseline':
        original = bytes.fromhex(spec['original_hex'])
        assert sha(original) == spec['original_sha256'] and blob(original) == spec['original_blob']
        return original
    needle = b'if (data.AsSpan().SequenceEqual(candidate))'
    assert raw.count(needle) == 1, 'unexpected equality guard'
    return raw.replace(needle, b'if (true) // Negative control: digest alone is insufficient')

def prepare(root, mode, head, receipt, verify=False):
    assert mode in MODES and git(root, 'rev-parse', 'HEAD').decode().strip() == head
    changed = git(root, 'diff', '--name-only', 'HEAD').decode().splitlines()
    assert set(changed) <= ({MANAGER, SAVEFILE} if verify else set()), 'unreviewed tracked changes'
    manifest_path = root/'tests/savefile_resource_bytes/source-manifest.json'
    raw_manifest = manifest_path.read_bytes()
    assert raw_manifest == git(root, 'cat-file', 'blob', head+':tests/savefile_resource_bytes/source-manifest.json')
    manifest = json.loads(raw_manifest)
    controls = json.loads((root/'tests/savefile_resource_bytes/controls.json').read_text())
    records = {}
    for path, expected in manifest['sources'].items():
        committed = git(root, 'cat-file', 'blob', head+':'+path)
        assert sha(committed) == expected, 'unreviewed committed input: '+path
        actual = (root/path).read_bytes()
        wanted = committed
        if path in controls['production']:
            spec = controls['production'][path]
            historical = git(root, 'cat-file', 'blob', BASE+':'+path)
            assert historical.hex() == spec['original_hex'], 'wrong historical bytes'
            wanted = historical if mode == 'baseline' else mutate(committed, mode, spec) if path == MANAGER else committed
        if verify:
            assert actual == wanted, 'prepared source drift: '+path
        else:
            assert actual == committed, 'dirty source: '+path
        records[path] = {'original_sha256':sha(committed), 'prepared_sha256':sha(wanted), 'git_blob':blob(committed)}
    data = {'schema':1, 'head':head, 'mode':mode, 'base':BASE, 'manifest_sha256':sha(raw_manifest), 'sources':records}
    if verify:
        assert json.loads(receipt.read_text()) == data, 'receipt drift'
    else:
        for path in controls['production']:
            committed = git(root, 'cat-file', 'blob', head+':'+path)
            wanted = bytes.fromhex(controls['production'][path]['original_hex']) if mode == 'baseline' else mutate(committed,mode,controls['production'][path]) if path == MANAGER else committed
            (root/path).write_bytes(wanted)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(data,indent=2)+'\n')
    return data

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=MODES);p.add_argument('--head',required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    prepare(ROOT,a.mode,a.head,a.receipt,a.verify)
