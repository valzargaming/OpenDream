"""Authenticate exact committed inputs and immutable Git original; no native tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '31b11b063e4b10be15472de8a566d9a466781e4c'
RESOURCE = 'OpenDreamRuntime/Resources/DreamResource.cs'
PATHS = [RESOURCE, 'OpenDreamRuntime/Resources/SaveCostProfile.cs',
         'OpenDreamRuntime/Objects/Types/DreamObjectSavefile.cs',
         'OpenDreamShared/Dream/StringFormatDecoder.cs',
         'Content.IntegrationTests/ResourceOutputAllocationTests.cs',
         'Content.IntegrationTests/DMProject/Fixtures/resource-output-allocation.dm']

CACHE_HELPER = b'    internal void ReleaseFileDataCache() {\n        // In-memory resources own their bytes; only disk-backed data can be reloaded.\n        if (string.IsNullOrEmpty(filePath))\n            return;\n\n        ResourceData = null; // The setter also balances TOOLS memory accounting.\n    }\n\n'

def compose_cache_resource(original):
    anchor=b"    public void Clear() {"
    assert original.count(anchor)==1 and b"ReleaseFileDataCache" not in original
    return original.replace(anchor,CACHE_HELPER+anchor)

def git(*args): return subprocess.check_output(['git', '-C', str(ROOT), *args])
def sha(raw): return hashlib.sha256(raw).hexdigest()
def mutate(raw, mode):
    if mode == 'positive': return raw
    if mode == 'no-small-path':
        needle = b'if (text.Length <= 4096) {'
        assert raw.count(needle) == 1
        return raw.replace(needle, b'if (text.Length < 0) { // negative control: ordinary output pays writer overhead')
    assert mode == 'platform-newline'
    needle = b'writer.Write("\\r\\n");'
    assert raw.count(needle) == 1
    return raw.replace(needle, b'writer.WriteLine();')

def prepare(mode, head, output, verify=False):
    assert git('rev-parse', 'HEAD').decode().strip() == head
    changed = git('diff', '--name-only', 'HEAD').decode().splitlines()
    assert set(changed) <= ({RESOURCE} if verify else set())
    records = {}
    for name in PATHS:
        committed = git('cat-file', 'blob', head + ':' + name)
        wanted = committed
        if name == RESOURCE:
            original = git('cat-file', 'blob', BASE + ':' + name)
            assert original.count(b'File.AppendAllText(ResourcePath, text + "\\r\\n");') == 2
            wanted = compose_cache_resource(original) if mode == 'baseline' else mutate(committed, mode)
            records['immutable_original_sha256'] = sha(original)
        actual = (ROOT / name).read_bytes()
        assert actual == (wanted if verify else committed), 'source drift: ' + name
        records[name] = {'committed': sha(committed), 'prepared': sha(wanted)}
        if not verify:
            target = output / 'prepared-source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(wanted)
            if name == RESOURCE: (ROOT / name).write_bytes(wanted)
    receipt = {'head': head, 'base': BASE, 'mode': mode, 'sources': records, 'prepared_historical_append_with_read_cache':mode=='baseline'}
    output.mkdir(parents=True, exist_ok=True)
    if verify: assert json.loads((output / 'source-receipt.json').read_text()) == receipt
    else: (output / 'source-receipt.json').write_text(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['positive','baseline','platform-newline','no-small-path'])
    p.add_argument('--head', required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verify', action='store_true'); a=p.parse_args()
    prepare(a.mode,a.head,a.output,a.verify)
