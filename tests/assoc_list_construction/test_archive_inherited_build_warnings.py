"""Pure adversaries for the inherited cold-build diagnostic adapter; no native evidence."""
import importlib.util,json,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('inherited_archive',HERE/'archive_logs.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
class InheritedBuildWarnings(unittest.TestCase):
 def setUp(self):self.spec=json.loads((HERE/'inherited-build-warnings.json').read_text())
 def test_each_exact_source_bound_inherited_mode(self):
  for profile,modes in self.spec['cases'].items():
   for mode,c in modes.items():
    with self.subTest(profile=profile,mode=mode):
     build='\n'.join(c['warnings'])+'\nBuild succeeded.\n 522 Warning(s)\n 0 Error(s)\n'
     self.assertTrue(A.verify_build(build,profile,mode,c['prepared_source_sha256'])['inherited'])
 def test_unknown_changed_duplicate_missing_warning_and_errors(self):
  for profile,modes in self.spec['cases'].items():
   for mode,c in modes.items():
    build='\n'.join(c['warnings'])+'\nBuild succeeded.\n 522 Warning(s)\n 0 Error(s)\n'
    for bad in (build+'\nwarning arbitrary',build+'\nBuild FAILED.',build+'\nerror CS9999: fail',
                build.replace('522 Warning(s)','521 Warning(s)'),build.replace('0 Error(s)','1 Error(s)'),
                build+'\n'+c['warnings'][0],build.replace(c['warnings'][0],'',1),
                build.replace(c['warnings'][0],c['warnings'][0]+' altered',1)):
     with self.subTest(profile=profile,mode=mode),self.assertRaises(AssertionError):A.verify_build(bad,profile,mode,c['prepared_source_sha256'])
 def test_wrong_source_mode_or_missing_provenance(self):
  c=self.spec['cases']['matrix']['positive'];build='\n'.join(c['warnings'])+'\nBuild succeeded.\n 522 Warning(s)\n 0 Error(s)\n'
  for pins in (None,{},dict(c['prepared_source_sha256'],**{'DreamObject.cs':'0'*64})):
   with self.assertRaises(AssertionError):A.verify_build(build,'matrix','positive',pins)
  with self.assertRaises(AssertionError):A.verify_build(build,'matrix','foreign',c['prepared_source_sha256'])
 def test_clean_build_stays_strict(self):
  self.assertFalse(A.verify_build('Build succeeded.\n0 Warning(s)\n0 Error(s)\n','assoc','positive')['inherited'])
  for bad in ('Build succeeded.\n0 Warning(s)\n0 Error(s)\nwarning unknown', 'Build FAILED.\n0 Warning(s)\n0 Error(s)\n'):
   with self.assertRaises(AssertionError):A.verify_build(bad,'assoc','positive')
