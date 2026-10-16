"""Exact unchanged-line diagnostic composition; never suppress diagnostics."""
import argparse, difflib, hashlib, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = '52df08ee4e5711df1c3fd5e907c81f87a986e371'
CANDIDATE = '7497005929f2972efd112fd792b873a06ca1364a'
SOURCES = {
    'OpenDreamRuntime/Objects/Types/DreamList.cs': ('c5c3baed5e30333ce63fcd38e2be40d5b3cc07bda4c900171e8da84d0a588e55', '380196bc158ade1044094bb414b46bb36266e43e6f6cff5bfa12c9b6e6edb156'),
    'OpenDreamRuntime/Objects/Types/DreamObjectSavefile.cs': ('151a92e3a2691adf0a85787fa15dbe9ff669f4a94309019d6e7e523993b8ee6d', '565b7d86e547ddf96d28cc33ef85e38bde0c771da69d7f2a88807f805395547f'),
    'OpenDreamRuntime/Resources/DreamResourceManager.cs': ('88afaba4893e4a64904328483c02b091867087f3ef4e79848d32045e6b204ea4', 'ad62b66bfa26039da65ce38ae282d9edefb9fd7392877ae4dcd765f4c9ad84a3'),
    'OpenDreamRuntime/Map/DreamMapManager.cs': ('e50c7257001405285ab0ebc6293cb5f971dc603a3ab6e480bebcabf13b813c09', '7756a5276f625fc8c66a6dc30005212054888462c4040f51f8c4ff648d73bf59'),
    'OpenDreamClient/States/MainMenu/MainMenuState.cs': ('7cb075f3678beee6f7279a447caf9cdcaf0b54ccba349538c73b6fa9f4e8c4c6', 'f99c51f12f148e9e62eae679c7d22765bfbdd8f0308f3dd1ccd2fd7fd3c38384'),
    'OpenDreamRuntime/DreamConnection.cs': ('09c684570619c69b1d582ca1a3621ac407154eeb2a8a3442bd29193de04daefa', '5938f66866b911f268db30d96d44b1554718befa5697c118d4edebf537215453'),
    'OpenDreamRuntime/DreamManager.cs': ('a5f27183dc4013ce2f23cb10934ec330339501065d133ac388b385f152de19f7', '973ba18d864b81da6621aac71c10d6df24715d36a06a0ffaafa199fee79788ea'),
}

def sha(raw): return hashlib.sha256(raw).hexdigest()

def source(commit, path, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', commit + ':' + path])

def inputs(root=ROOT):
    result = {}
    for path, (old_hash, new_hash) in SOURCES.items():
        old, new = source(ORIGINAL, path, root), source(CANDIDATE, path, root)
        assert (sha(old), sha(new)) == (old_hash, new_hash), 'immutable warning source drift: ' + path
        result[path] = (old, new)
    return result

def capture(folder, root=ROOT):
    folder.mkdir(parents=True, exist_ok=True)
    for path, (_, new) in inputs(root).items():
        assert (root / path).read_bytes() == new, 'build warning source drift: ' + path
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new)
    (folder / 'warning_coordinates.py').write_bytes(Path(__file__).read_bytes())
    (folder / 'source-pins.json').write_text(json.dumps({'original': ORIGINAL, 'candidate': CANDIDATE, 'sources': SOURCES}, indent=2) + '\n')

def compose(warnings, folder, root=ROOT):
    assert json.loads((folder / 'source-pins.json').read_text()) == {'original': ORIGINAL, 'candidate': CANDIDATE, 'sources': {p: list(v) for p, v in SOURCES.items()}}
    assert {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == set(SOURCES) | {'source-pins.json', 'warning_coordinates.py'}
    assert (folder / 'warning_coordinates.py').read_bytes() == Path(__file__).read_bytes(), 'captured coordinate helper drift'
    mappings = {}
    for path, (old, new) in inputs(root).items():
        assert (folder / path).read_bytes() == new, 'captured warning source drift: ' + path
        before, after = old.splitlines(), new.splitlines()
        mappings[path] = {i+k+1: j+k+1 for i, j, count in difflib.SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks() for k in range(count)}
    result = []
    for warning in warnings:
        match = re.match(r'(.+?)\((\d+),(\d+)\): warning ', warning)
        if match is None:
            result.append(warning) # Original package diagnostics keep every byte.
            continue
        path, line, column = match.groups()
        if path in mappings:
            assert int(line) in mappings[path], 'diagnostic source line changed: ' + warning
            warning = path + '(' + str(mappings[path][int(line)]) + ',' + column + warning[match.end(3):]
        result.append(warning)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--capture', type=Path, required=True)
    capture(parser.parse_args().capture)
