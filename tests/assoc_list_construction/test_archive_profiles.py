"""Pure archive adversarial tests; no native/runtime claim."""
import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from archive_logs import archive,verify_archive,replay,PROFILES,MAX_BYTES,load
class ArchiveProfiles(unittest.TestCase):
 def test_matrix_replay_uses_original_bytes_and_rejects_foreign_errors(self):
  matrix=Path(__file__).resolve().parent.parent/'native_matrix_ownership'
  fixture=load(matrix/'test_pure.py','archive_synthetic_matrix')
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);raw,log=fixture.evidence();ctor,ctorlog=fixture.evidence(constructor=True)
   values={'sdk-info.log':b'10.0.401\n','build.log':b'Build succeeded.\n0 Warning(s)\n0 Error(s)\n','matrix.log':log.encode() or b'fixture stdout in TRX\n','constructors.log':ctorlog.encode(),'runtime.log':b'Savefile cleanup: 200 native failed/uninitialized disposals and shared-file preservation passed\n'}
   for name,value in values.items():(root/name).write_bytes(value)
   for name in ('build','test','constructors','runtime'):(root/(name+'-exit-code.txt')).write_text('0\n')
   (root/'matrix.trx').write_text(raw);(root/'constructors.trx').write_text(ctor)
   runtime=raw.replace('FastRejectionsAndTransfers','NoRuntimesTest').replace('Content.IntegrationTests.NativeMatrixOwnershipTests','Content.IntegrationTests.GameTests')
   (root/'runtime.trx').write_text(runtime)
   archive(root,'matrix');self.assertTrue(replay(root,'matrix','positive')['archived_original_logs_replayed'])
   # Replaying reads the ZIP originals, even if loose logs subsequently differ.
   (root/'constructors.log').write_text('[ERRO] loose altered bytes')
   self.assertTrue(replay(root,'matrix','positive')['archived_original_logs_replayed'])
   (root/'runtime.trx').write_text(runtime.replace('outcome="Passed"','outcome="Failed"'))
   with self.assertRaises(AssertionError):replay(root,'matrix','positive')
 def inputs(self,root,profile):
  values={name:b'\xef\xbb\xbfbytes\r\n\t'+name.encode() for name in PROFILES[profile]}
  for name,raw in values.items():(root/name).write_bytes(raw)
  return values
 def test_matrix_profile_retains_all_five_originals(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);values=self.inputs(root,'matrix');r=archive(root,'matrix')
   self.assertTrue(r['complete']);self.assertEqual(verify_archive(root,'matrix'),values)
   self.assertEqual({name:(root/name).read_bytes() for name in values},values)
 def test_partial_failure_retention_is_explicit(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'build.log').write_bytes(b'original failed build')
   r=archive(root,'matrix',True);self.assertFalse(r['complete']);self.assertEqual(list(verify_archive(root,'matrix')),['build.log'])
 def test_corruption_and_forged_member_list_rejected(self):
  for mutation in ('raw-hash','foreign','duplicate','oversized'):
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);self.inputs(root,'matrix');archive(root,'matrix');rp=root/'original-runner-logs.json';r=json.loads(rp.read_text())
    if mutation=='raw-hash':r['files']['build.log']['sha256']='0'*64
    else:
     path=root/'original-runner-logs.zip'
     with zipfile.ZipFile(path,'w') as z:
      for name in PROFILES['matrix']:z.writestr(name,b'bad')
      if mutation=='foreign':z.writestr('../foreign.log',b'bad')
      if mutation=='duplicate':z.writestr('build.log',b'bad')
      if mutation=='oversized':z.writestr('large.log',b'x'*(MAX_BYTES+1))
     r['archive_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    rp.write_text(json.dumps(r))
    with self.assertRaises(ValueError):verify_archive(root,'matrix')
 def test_wrong_profile_and_incomplete_member_metadata_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.inputs(root,'assoc');archive(root)
   with self.assertRaises(ValueError):verify_archive(root,'matrix')
   p=root/'original-runner-logs.json';r=json.loads(p.read_text());r['missing']=['runtime.log'];p.write_text(json.dumps(r))
   with self.assertRaises(ValueError):verify_archive(root)
if __name__=='__main__':unittest.main()
