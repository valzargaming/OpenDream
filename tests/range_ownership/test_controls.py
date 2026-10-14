import json, unittest, hashlib
from pathlib import Path
from control import mutation,PRODUCTION
HERE=Path(__file__).resolve().parent
class ControlTests(unittest.TestCase):
 def test_exact_three_modes(self):
  c=json.loads((HERE/'controls.json').read_text());raw=(HERE.parents[1]/PRODUCTION).read_bytes().replace(b'\r\n',b'\n')
  self.assertEqual(mutation(raw,'positive',c),raw)
  base=mutation(raw,'baseline',c);omit=mutation(raw,'omitted-release',c)
  self.assertEqual(hashlib.sha256(base).hexdigest(),c['base_sha256'])
  self.assertEqual(omit,raw.replace(c['fixed'].encode(),c['omitted_value_release'].encode(),1))
  self.assertEqual(omit.replace(c['omitted_value_release'].encode(),c['fixed'].encode(),1),raw)
  self.assertEqual(len(c['baseline_failures']),8);self.assertEqual(len(c['omitted_value_failures']),4)
 def test_source_drift_rejected(self):
  c=json.loads((HERE/'controls.json').read_text())
  with self.assertRaises(AssertionError):mutation(b'wrong source','baseline',c)
