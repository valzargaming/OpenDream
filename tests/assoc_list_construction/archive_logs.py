"""Retain and replay byte-exact original logs; retention alone is not acceptance."""
import argparse,hashlib,importlib.util,json,re,zipfile
from pathlib import Path
NAMES=('sdk-info.log','build.log','assoc.log','runtime.log')
PROFILES={'assoc':NAMES,'matrix':('sdk-info.log','build.log','matrix.log','constructors.log','runtime.log')}
MAX_BYTES=8*1024*1024
def sha(raw):return hashlib.sha256(raw).hexdigest()
def archive(results,profile='assoc',allow_incomplete=False):
 names=PROFILES[profile];raw={};missing=[]
 for name in names:
  path=results/name
  if not path.exists() and allow_incomplete:missing.append(name);continue
  if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=MAX_BYTES:raise ValueError('missing, symlinked or oversized original log: '+name)
  before=path.stat();value=path.read_bytes();after=path.stat()
  if len(value)!=before.st_size or before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:raise ValueError('original log changed during capture: '+name)
  raw[name]=value
 if not raw:raise ValueError('no original logs to retain')
 rows={name:{'bytes':len(value),'sha256':sha(value)} for name,value in raw.items()}
 output=results/'original-runner-logs.zip'
 with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
  for name,value in raw.items():
   info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;bundle.writestr(info,value)
 receipt={'schema':2,'profile':profile,'complete':not missing,'missing':missing,'files':rows,'archive_sha256':sha(output.read_bytes()),'scope':'raw byte retention only; acceptance requires original TRX/log replay'}
 with (results/'original-runner-logs.json').open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')
 if verify_archive(results,profile)!=raw:raise ValueError('archive did not preserve exact originals')
 return receipt
def verify_archive(results,profile='assoc'):
 receipt_path=results/'original-runner-logs.json';path=results/'original-runner-logs.zip'
 if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size>64*1024:raise ValueError('invalid receipt')
 receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
 names=PROFILES[profile]
 if receipt.get('schema')!=2 or receipt.get('profile')!=profile or type(receipt.get('complete')) is not bool:raise ValueError('wrong receipt identity')
 expected=[name for name in names if name not in receipt['missing']]
 if receipt['missing']!=[name for name in names if name not in expected] or receipt['complete']!=(len(expected)==len(names)) or set(receipt['files'])!=set(expected):raise ValueError('wrong completeness/members')
 if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=len(names)*MAX_BYTES+65536:raise ValueError('invalid archive size/path')
 if sha(path.read_bytes())!=receipt['archive_sha256']:raise ValueError('archive SHA mismatch')
 raw={}
 with zipfile.ZipFile(path) as bundle:
  if bundle.namelist()!=expected:raise ValueError('duplicate/foreign/reordered archive member')
  for info in bundle.infolist():
   if not 0<info.file_size<=MAX_BYTES or info.filename not in names:raise ValueError('invalid member size/path')
   value=bundle.read(info.filename);row=receipt['files'][info.filename]
   if len(value)!=row['bytes'] or sha(value)!=row['sha256']:raise ValueError('raw SHA/size mismatch')
   raw[info.filename]=value
 return raw
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def replay(results,profile,mode):
 raw=verify_archive(results,profile);assert set(raw)==set(PROFILES[profile]),'incomplete archive cannot establish acceptance'
 def code(name):
  value=(results/name).read_text().strip();assert re.fullmatch(r'[01]',value);return int(value)
 build=raw['build.log'].decode('utf-8');assert code('build-exit-code.txt')==0
 assert 'Build succeeded.' in build and re.search(r'\b0 Warning\(s\)',build) and re.search(r'\b0 Error\(s\)',build)
 assert not re.search(r'Build FAILED|(?:error|warning) (?:CS|DM|MSB)\d+|\[ERRO\]',build,re.I)
 assert '10.0.401' in raw['sdk-info.log'].decode('utf-8')
 here=Path(__file__).resolve().parent
 if profile=='assoc':
  v=load(here/'verify.py','assoc_archive_replay');v.verify(results/'assoc.trx',mode,code('test-exit-code.txt'),raw['assoc.log'].decode('utf-8'))
  runtime=load(here.parent/'string_format_decoder/verify.py','assoc_runtime_replay')
 else:
  matrix=here.parent/'native_matrix_ownership';v=load(matrix/'verify.py','matrix_archive_replay')
  v.classify((results/'matrix.trx').read_text(),raw['matrix.log'].decode('utf-8'),code('test-exit-code.txt'),mode)
  v.classify((results/'constructors.trx').read_text(),raw['constructors.log'].decode('utf-8'),code('constructors-exit-code.txt'),mode,True)
  runtime=load(matrix/'runtime_verify.py','matrix_runtime_replay')
 runtime.verify_runtime(results/'runtime.trx',code('runtime-exit-code.txt'),raw['runtime.log'].decode('utf-8'))
 return {'archived_original_logs_replayed':True,'profile':profile,'mode':mode,'scope':'strict classification of original bytes; no new runtime execution'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--profile',choices=PROFILES,default='assoc');p.add_argument('--allow-incomplete',action='store_true');p.add_argument('--replay',action='store_true');p.add_argument('--mode',default='positive');a=p.parse_args()
 print(json.dumps(replay(a.results,a.profile,a.mode) if a.replay else archive(a.results,a.profile,a.allow_incomplete)))
