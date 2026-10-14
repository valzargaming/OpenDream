"""Source-only controls for the actual map manager; no runtime launch."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='31b11b063e4b10be15472de8a566d9a466781e4c'
MANAGER='OpenDreamRuntime/Map/DreamMapManager.cs'
MODES=('positive','baseline','unsafe-dedup')
def sha(raw): return hashlib.sha256(raw).hexdigest()
def git(root,*args): return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout

def mutate(raw,mode,original):
    assert mode in MODES
    if mode=='positive': return raw
    if mode=='baseline': return original
    needle=b'if (update.Tile.IsEmpty) {\n                _pendingNonEmptyTiles.Remove(update.Position);\n            } else if'
    assert raw.count(needle)==1, 'wrong candidate empty barrier'
    return raw.replace(needle,b'if')

def prepare(root,mode,head,receipt,verify=False):
    assert git(root,'rev-parse','HEAD').decode().strip()==head
    changed=git(root,'diff','--name-only','HEAD').decode().splitlines()
    assert set(changed)<=({MANAGER} if verify else set()), 'unreviewed changes'
    manifest_path='tests/turf_tile_queue/source-manifest.json'
    raw_manifest=(root/manifest_path).read_bytes()
    assert raw_manifest==git(root,'cat-file','blob',head+':'+manifest_path)
    manifest=json.loads(raw_manifest)
    original=git(root,'cat-file','blob',BASE+':'+MANAGER)
    assert sha(original)==manifest['baseline_sha256']
    records={}
    for path,expected in manifest['sources'].items():
        committed=git(root,'cat-file','blob',head+':'+path)
        assert sha(committed)==expected, 'unreviewed committed source '+path
        actual=(root/path).read_bytes()
        wanted=mutate(committed,mode,original) if path==MANAGER else committed
        assert actual==(wanted if verify else committed), 'source drift '+path
        records[path]={'committed_sha256':sha(committed),'prepared_sha256':sha(wanted)}
    data={'schema':1,'head':head,'mode':mode,'base':BASE,'manifest_sha256':sha(raw_manifest),'sources':records}
    if verify: assert json.loads(receipt.read_text())==data
    else:
        (root/MANAGER).write_bytes(mutate(git(root,'cat-file','blob',head+':'+MANAGER),mode,original))
        receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(data,indent=2)+'\n')
    return data
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=MODES);p.add_argument('--head',required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();prepare(ROOT,a.mode,a.head,a.receipt,a.verify)
