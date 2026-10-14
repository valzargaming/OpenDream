"""CI exact-commit preparation. Not invoked by detached packet worker."""
import argparse,hashlib,json,subprocess
from pathlib import Path
MODES=('positive','baseline','omit-creator','omit-arguments')
NATIVE='OpenDreamRuntime/Procs/Native/DreamProcNativeRoot.cs'
OBJECT='OpenDreamRuntime/Objects/DreamObject.cs'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def mutate(raw,mode,path,controls):
 assert mode in MODES
 c=controls[path];assert sha(raw)==c['candidate_sha256']
 omitted=mode=='baseline' or (path==NATIVE and mode=='omit-creator') or (path==OBJECT and mode=='omit-arguments')
 old=c['candidate'].encode();new=c['original'].encode()
 assert raw.count(old)==1
 result=raw.replace(old,new) if omitted else raw
 assert sha(result)==c['baseline_sha256' if omitted else 'candidate_sha256']
 return result
def git(root,*args):return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout
def prepare(root,mode,head):
 assert len(head)==40 and all(c in '0123456789abcdef' for c in head)
 assert git(root,'rev-parse','HEAD').decode().strip()==head
 manifest_path='tests/native_matrix_ownership/source-manifest.json'
 raw=(root/manifest_path).read_bytes();assert raw==git(root,'cat-file','blob',head+':'+manifest_path)
 spec=json.loads(raw);controls=json.loads((root/'tests/native_matrix_ownership/controls.json').read_text())
 assert spec['historical_creator_base']=='644a0eca75c7a5a5d74b16de04ec589cf0ac1faa'
 historical=git(root,'cat-file','blob',spec['historical_creator_base']+':'+NATIVE)
 assert sha(historical)==spec['historical_native_root_sha256']=='ce29b09ba46d16edb858f8569290651a75436815cdea18f3055b554bc3abe3fa'
 assert historical==(root/'tests/native_matrix_ownership/historical-native-root.raw.txt').read_bytes()
 for original_path in (NATIVE,OBJECT):
  original=git(root,'cat-file','blob',spec['historical_creator_base']+':'+original_path).replace(b'\r\n',b'\n')
  assert original.count(controls[original_path]['original'].encode())==1
 for p,h in spec['expected_sources'].items():
  actual=(root/p).read_bytes();assert sha(actual)==h and actual==git(root,'cat-file','blob',head+':'+p),p
 changed={}
 for p in (NATIVE,OBJECT):
  out=mutate((root/p).read_bytes(),mode,p,controls);(root/p).write_bytes(out);changed[p]=sha(out)
 return {'head':head,'mode':mode,'manifest_sha256':sha(raw),'sources':spec['expected_sources'],'prepared':changed}
def verify(root,receipt,mode,head):
 assert git(root,'rev-parse','HEAD').decode().strip()==head
 raw=(root/'tests/native_matrix_ownership/source-manifest.json').read_bytes();spec=json.loads(raw)
 assert receipt['head']==head and receipt['mode']==mode and receipt['manifest_sha256']==sha(raw)
 assert receipt['sources']==spec['expected_sources'] and set(receipt['prepared'])=={NATIVE,OBJECT}
 controls=json.loads((root/'tests/native_matrix_ownership/controls.json').read_text())
 for p,h in receipt['sources'].items():
  actual=(root/p).read_bytes()
  if p in (NATIVE,OBJECT):
   c=controls[p];omitted=mode=='baseline' or (p==NATIVE and mode=='omit-creator') or (p==OBJECT and mode=='omit-arguments')
   candidate=actual.replace(c['original'].encode(),c['candidate'].encode()) if omitted else actual
   assert sha(candidate)==h and mutate(candidate,mode,p,controls)==actual and sha(actual)==receipt['prepared'][p]
  else:assert sha(actual)==h,p
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=MODES);p.add_argument('--expected-head',required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
 root=Path(__file__).resolve().parents[2]
 if a.verify:verify(root,json.loads(a.receipt.read_text()),a.mode,a.expected_head)
 else:a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(prepare(root,a.mode,a.expected_head),indent=2)+'\n')
