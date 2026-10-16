"""Exact-head decoder-only source control; CRLF->LF is the sole allowed transform."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = 'OpenDreamShared/Dream/StringFormatDecoder.cs'
def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(raw): return raw.replace(b'\r\n', b'\n')
def blob(raw): return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def git(root, *args): return subprocess.run(['git','-C',str(root),*args], check=True, capture_output=True).stdout

def prepare(root, mode, head, git_read=git):
    manifest_path = 'tests/string_format_decoder/source-manifest.json'
    manifest_raw = (root/manifest_path).read_bytes()
    spec = json.loads(manifest_raw)
    assert git_read(root,'rev-parse','HEAD').decode().strip() == head and len(head) == 40, 'wrong exact head'
    assert canonical(manifest_raw) == git_read(root,'cat-file','blob',head+':'+manifest_path), 'uncommitted manifest'
    reviewed = {}
    for path, expected in spec['expected_sources'].items():
        raw = (root/path).read_bytes()
        committed = git_read(root,'cat-file','blob',head+':'+path)
        assert canonical(raw) == committed and sha(committed) == expected, 'source/head drift: '+path
        reviewed[path] = {'raw_sha256':sha(raw),'lf_sha256':sha(committed),'git_blob_oid':blob(committed)}
    original = git_read(root,'cat-file','blob',spec['base_commit']+':'+PRODUCTION)
    assert sha(canonical(original)) == spec['baseline_lf_sha256'], 'wrong immutable baseline'
    initial = (root/PRODUCTION).read_bytes()
    prepared = canonical(initial) if mode == 'positive' else canonical(original)
    (root/PRODUCTION).write_bytes(prepared)
    return {'schema':1,'mode':mode,'head':head,'base_commit':spec['base_commit'],
            'transform':'CRLF to LF only','manifest_lf_sha256':sha(canonical(manifest_raw)),
            'reviewed_sources':reviewed,'baseline_raw_sha256':sha(original),
            'baseline_lf_sha256':sha(canonical(original)),'baseline_git_blob_oid':blob(original),
            'prepared_sha256':sha(prepared),'prepared_git_blob_oid':blob(prepared)}

def verify_receipt(root, mode, head, receipt):
    spec = json.loads((root/'tests/string_format_decoder/source-manifest.json').read_bytes())
    assert receipt['schema'] == 1 and receipt['mode'] == mode and receipt['head'] == head
    assert receipt['base_commit'] == spec['base_commit']
    assert receipt['manifest_lf_sha256'] == sha(canonical((root/'tests/string_format_decoder/source-manifest.json').read_bytes()))
    assert set(receipt['reviewed_sources']) == set(spec['expected_sources'])
    for path, expected in spec['expected_sources'].items():
        recorded = receipt['reviewed_sources'][path]
        assert recorded['lf_sha256'] == expected
        raw = (root/path).read_bytes()
        wanted = spec['baseline_lf_sha256'] if path == PRODUCTION and mode == 'baseline' else expected
        assert sha(canonical(raw)) == wanted, 'post-build source drift: '+path
        if path == PRODUCTION:
            assert sha(raw) == receipt['prepared_sha256'] and blob(raw) == receipt['prepared_git_blob_oid']
    assert receipt['baseline_lf_sha256'] == spec['baseline_lf_sha256']
    return True

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode', choices=['positive','baseline'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--expected-head',required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    if a.verify:
        assert git(a.root,'rev-parse','HEAD').decode().strip() == a.expected_head
        receipt=json.loads(a.receipt.read_bytes())
        verify_receipt(a.root,a.mode,a.expected_head,receipt)
        original=git(a.root,'cat-file','blob',receipt['base_commit']+':'+PRODUCTION)
        assert sha(original)==receipt['baseline_raw_sha256'] and blob(original)==receipt['baseline_git_blob_oid']
        for path, recorded in receipt['reviewed_sources'].items():
            committed=git(a.root,'cat-file','blob',a.expected_head+':'+path)
            assert sha(committed)==recorded['lf_sha256'] and blob(committed)==recorded['git_blob_oid']
    else:
        data=prepare(a.root,a.mode,a.expected_head)
        a.receipt.parent.mkdir(parents=True,exist_ok=True)
        (a.receipt.parent/'baseline-original.cs').write_bytes(git(a.root,'cat-file','blob',data['base_commit']+':'+PRODUCTION))
        (a.receipt.parent/'production-prepared.cs').write_bytes((a.root/PRODUCTION).read_bytes())
        (a.receipt.parent/'StringFormatDecoderTests.cs').write_bytes((a.root/'Content.IntegrationTests/StringFormatDecoderTests.cs').read_bytes())
        (a.receipt.parent/'source-manifest.json').write_bytes((a.root/'tests/string_format_decoder/source-manifest.json').read_bytes())
        a.receipt.write_text(json.dumps(data,indent=2)+'\n',newline='\n')
