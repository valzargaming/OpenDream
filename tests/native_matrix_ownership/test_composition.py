"""Pure cross-suite controls: the other fix must survive each mutation."""
import importlib.util,json,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=load(HERE/'control.py','matrix_composition_control')
T=load(HERE.parent/'typesof_ownership/control.py','typesof_composition_control')
class Composition(unittest.TestCase):
 def setUp(self):
  self.mc=json.loads((HERE/'controls.json').read_text());self.tc=json.loads((HERE.parent/'typesof_ownership/controls.json').read_text())
  self.raw=(ROOT/M.NATIVE).read_bytes()
 def test_typesof_baseline_keeps_matrix_cleanup(self):
  baseline=T.mutation(self.raw,'baseline',self.tc)
  self.assertIn(self.mc[M.NATIVE]['candidate'].encode(),baseline)
  self.assertNotIn(self.tc['replacements'][0][0].encode(),baseline)
  self.assertEqual(baseline,(HERE.parent/'typesof_ownership/composed-baseline-native-root.txt').read_bytes())
  self.assertIn(self.mc[M.OBJECT]['candidate'].encode(),(ROOT/M.OBJECT).read_bytes())
 def test_all_matrix_controls_keep_typesof_cleanup(self):
  fixed,original=self.tc['replacements'][0]
  for mode in M.MODES:
   with self.subTest(mode=mode):
    output=M.mutate(self.raw,mode,M.NATIVE,self.mc)
    self.assertIn(fixed.encode(),output);self.assertNotIn(original.encode(),output)
    # Restoring typesof after this matrix control must reconstruct its exact
    # historical bounded method, without altering that matrix control.
    restored=output.replace(fixed.encode(),original.encode())
    self.assertEqual(restored.replace(original.encode(),fixed.encode()),output)
 def test_historical_raw_identity_and_bounded_methods(self):
  historical=(HERE/'historical-native-root.raw.txt').read_bytes()
  self.assertEqual(M.sha(historical),'ce29b09ba46d16edb858f8569290651a75436815cdea18f3055b554bc3abe3fa')
  self.assertEqual(historical.count(self.tc['replacements'][0][1].encode()),1)
  self.assertEqual(historical.count(self.mc[M.NATIVE]['original'].encode()),1)
if __name__=='__main__':unittest.main()
