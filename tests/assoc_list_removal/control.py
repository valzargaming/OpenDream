"""Exact source preparation and provenance receipts; no compiler/runtime invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = 'OpenDreamRuntime/Objects/Types/DreamAssocList.cs'

def sha(data): return hashlib.sha256(data).hexdigest()
def blob(data): return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def real_git(root, *args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout

def mutation(raw, mode, control):
    assert sha(raw) == control['candidate_sha256'], 'unreviewed production source'
    if mode == 'positive': return raw
    assert mode in ('baseline','omitted-release')
    text = raw.decode()
    for fixed, original in control['replacements']:
        assert text.count(fixed) == 1
        replacement = original if mode == 'baseline' else control['omitted_value_release']
        text = text.replace(fixed,replacement)
    result = text.encode()
    if mode == 'baseline': assert sha(result) == control['base_sha256']
    return result

def prepare(root, mode, expected_head, git=real_git):
    spec = json.loads((root/'tests/assoc_list_removal/source-manifest.json').read_text())
    control = json.loads((root/'tests/assoc_list_removal/controls.json').read_text())
    head = git(root,'rev-parse','HEAD').decode().strip()
    assert len(head) == 40 and all(c in '0123456789abcdef' for c in head) and head == expected_head, 'wrong exact head'
    manifest_raw = (root/'tests/assoc_list_removal/source-manifest.json').read_bytes()
    assert manifest_raw == git(root,'cat-file','blob',head+':tests/assoc_list_removal/source-manifest.json'), 'uncommitted source manifest'
    originals = []
    for source in spec['original_inputs']:
        raw = git(root,'cat-file','blob',spec['base_commit']+':'+source['path'])
        assert sha(raw.replace(b'\r\n',b'\n')) == source['sha256'] and blob(raw) == source['git_blob_oid'], 'wrong frozen original'
        originals.append({**source,'actual_raw_sha256':sha(raw),'actual_git_blob_oid':blob(raw)})
    actual = {}
    for path, expected_sha in spec['expected_sources'].items():
        raw = (root/path).read_bytes()
        committed = git(root,'cat-file','blob',head+':'+path)
        assert sha(raw) == sha(committed) == expected_sha, 'checkout/head source drift: '+path
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
    spec = json.loads((root/'tests/assoc_list_removal/source-manifest.json').read_text())
    manifest_raw = (root/'tests/assoc_list_removal/source-manifest.json').read_bytes()
    assert data['source_manifest_sha256'] == sha(manifest_raw) and data['source_manifest_git_blob_oid'] == blob(manifest_raw)
    control = json.loads((root/'tests/assoc_list_removal/controls.json').read_text())
    assert data['schema'] == 1 and data['mode'] == mode and data['actual_checkout_head'] == head
    assert data['base_commit'] == spec['base_commit'] and len(data['original_inputs']) == len(spec['original_inputs'])
    for actual, expected in zip(data['original_inputs'],spec['original_inputs']):
        assert all(actual.get(key) == value for key,value in expected.items())
        assert actual['actual_git_blob_oid'] == expected['git_blob_oid']
        assert len(actual['actual_raw_sha256']) == 64
    assert data['production_path'] == PRODUCTION and data['initial_production_sha256'] == control['candidate_sha256']
    assert set(data['reviewed_sources']) == set(spec['expected_sources'])
    for path, expected_sha in spec['expected_sources'].items():
        recorded = data['reviewed_sources'][path]
        assert recorded['sha256'] == expected_sha
        assert len(recorded['git_blob_oid']) == 40
        actual = (root/path).read_bytes()
        if path == PRODUCTION:
            # Reconstruct reviewed candidate from this exact control output.
            text = actual.decode()
            if mode != 'positive':
                for fixed, original in control['replacements']:
                    changed = original if mode == 'baseline' else control['omitted_value_release']
                    assert text.count(changed) == 1
                    text = text.replace(changed,fixed)
            candidate = text.encode()
            assert sha(candidate) == expected_sha and blob(candidate) == recorded['git_blob_oid']
            assert actual == mutation(candidate,mode,control)
            assert sha(actual) == data['mutated_production_sha256']
        else:
            assert sha(actual) == expected_sha and blob(actual) == recorded['git_blob_oid']
    return True

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['positive','baseline','omitted-release'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--expected-head',required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    if a.verify:
        assert real_git(a.root,'rev-parse','HEAD').decode().strip() == a.expected_head
        check_receipt(a.root,json.loads(a.receipt.read_text()),a.mode,a.expected_head)
    else:
        data=prepare(a.root,a.mode,a.expected_head)
        a.receipt.parent.mkdir(parents=True,exist_ok=True)
        a.receipt.write_text(json.dumps(data,indent=2)+'\n',newline='\n')
