from pathlib import Path
import hashlib, json, sys

root = Path(__file__).resolve().parents[2]
path = root/'OpenDreamRuntime/Procs/DMProc.cs'
spec = json.loads(Path(__file__).with_name('controls.json').read_text())
source = path.read_text()
assert hashlib.sha256(source.encode()).hexdigest() == spec['candidate_sha256'], 'unexpected control input'
mode = sys.argv[1]
assert mode in ('baseline', 'omitted-release')
for fixed, baseline in spec['replacements']:
    assert source.count(fixed) == 1
    replacement = baseline if mode == 'baseline' else fixed.replace('owner.Dispose();', 'owner.ToString(); // Negative control: no release')
    source = source.replace(fixed, replacement)
if mode == 'baseline':
    assert hashlib.sha256(source.encode()).hexdigest() == spec['base_sha256']
path.write_text(source, newline='\n')
