"""Exact source preparation and provenance receipts; no compiler/runtime invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = 'OpenDreamRuntime/Procs/Native/DreamProcNativeRoot.cs'

def require(condition, message='source validation failed'):
    if not condition: raise AssertionError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def real_git(root, *args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout

def mutation(raw, mode, control):
    require(sha(raw) == control['candidate_sha256'], 'unreviewed production source')
    if mode == 'positive': return raw
    require(mode == 'baseline')
    text = raw.decode()
    for fixed, original in control['replacements']:
        require(text.count(fixed) == 1)
        replacement = original
        text = text.replace(fixed,replacement)
    result = text.encode()
    require(sha(result) == control['base_sha256'], 'wrong bounded control output')
    return result

def authenticate_dependencies(root, spec):
    import runpy
    helper = root/'tests/list_pool_capacity/dependency_composition.py'
    runpy.run_path(str(helper))['validate'](root, spec)

def prepare(root, mode, expected_head, git=real_git):
    spec = json.loads((root/'tests/typesof_ownership/source-manifest.json').read_text())
    authenticate_dependencies(root, spec)
    control = json.loads((root/'tests/typesof_ownership/controls.json').read_text())
    head = git(root,'rev-parse','HEAD').decode().strip()
    require(len(head) == 40 and all(c in '0123456789abcdef' for c in head) and head == expected_head, 'wrong exact head')
    manifest_raw = (root/'tests/typesof_ownership/source-manifest.json').read_bytes()
    require(manifest_raw == git(root,'cat-file','blob',head+':tests/typesof_ownership/source-manifest.json'), 'uncommitted source manifest')
    originals = []
    for source in spec['original_inputs']:
        raw = git(root,'cat-file','blob',source.get('commit', spec['base_commit'])+':'+source['path'])
        require(sha(raw) == source['sha256'] and blob(raw) == source['git_blob_oid'], 'wrong frozen original')
        originals.append({**source,'actual_raw_sha256':sha(raw),'actual_git_blob_oid':blob(raw)})
    actual = {}
    for path, expected_sha in spec['expected_sources'].items():
        raw = (root/path).read_bytes()
        committed = git(root,'cat-file','blob',head+':'+path)
        require(sha(raw) == sha(committed) == expected_sha, 'checkout/head source drift: '+path)
        actual[path] = {'sha256':sha(raw),'git_blob_oid':blob(committed)}
    raw = (root/PRODUCTION).read_bytes()
    mutated = mutation(raw, mode, control)
    (root/PRODUCTION).write_bytes(mutated)
    return {'schema':1,'mode':mode,'actual_checkout_head':head,'original_inputs':originals,
            'source_manifest_sha256':sha(manifest_raw),'source_manifest_git_blob_oid':blob(manifest_raw),
            'base_commit':spec['base_commit'],'reviewed_sources':actual,'production_path':PRODUCTION,
            'initial_production_sha256':sha(raw),'mutated_production_sha256':sha(mutated),
            'scope':'exact committed sources and source mutation; runtime evidence remains in original TRX/log'}

def check_receipt(root, data, mode, head):
    spec = json.loads((root/'tests/typesof_ownership/source-manifest.json').read_text())
    authenticate_dependencies(root, spec)
    manifest_raw = (root/'tests/typesof_ownership/source-manifest.json').read_bytes()
    require(data['source_manifest_sha256'] == sha(manifest_raw) and data['source_manifest_git_blob_oid'] == blob(manifest_raw))
    control = json.loads((root/'tests/typesof_ownership/controls.json').read_text())
    require(data['schema'] == 1 and data['mode'] == mode and data['actual_checkout_head'] == head)
    require(data['base_commit'] == spec['base_commit'] and len(data['original_inputs']) == len(spec['original_inputs']))
    for actual, expected in zip(data['original_inputs'],spec['original_inputs']):
        require(all(actual.get(key) == value for key,value in expected.items()))
        require(actual['actual_git_blob_oid'] == expected['git_blob_oid'])
        require(actual['actual_raw_sha256'] == expected['sha256'])
    require(data['production_path'] == PRODUCTION and data['initial_production_sha256'] == control['candidate_sha256'])
    require(set(data['reviewed_sources']) == set(spec['expected_sources']))
    for path, expected_sha in spec['expected_sources'].items():
        recorded = data['reviewed_sources'][path]
        require(recorded['sha256'] == expected_sha)
        require(len(recorded['git_blob_oid']) == 40)
        actual = (root/path).read_bytes()
        if path == PRODUCTION:
            # Reconstruct reviewed candidate from this exact control output.
            text = actual.decode()
            if mode != 'positive':
                for fixed, original in control['replacements']:
                    changed = original
                    require(text.count(changed) == 1)
                    text = text.replace(changed,fixed)
            candidate = text.encode()
            require(sha(candidate) == expected_sha and blob(candidate) == recorded['git_blob_oid'])
            require(actual == mutation(candidate,mode,control))
            require(sha(actual) == data['mutated_production_sha256'])
        else:
            require(sha(actual) == expected_sha and blob(actual) == recorded['git_blob_oid'])
    return True

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['positive','baseline'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--expected-head',required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    if a.verify:
        require(real_git(a.root,'rev-parse','HEAD').decode().strip() == a.expected_head)
        check_receipt(a.root,json.loads(a.receipt.read_text()),a.mode,a.expected_head)
    else:
        data=prepare(a.root,a.mode,a.expected_head)
        a.receipt.parent.mkdir(parents=True,exist_ok=True)
        a.receipt.write_text(json.dumps(data,indent=2)+'\n',newline='\n')
