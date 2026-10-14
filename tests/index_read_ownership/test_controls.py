from pathlib import Path
import json
import unittest
from control import mutation, sha

class SourceControlTests(unittest.TestCase):
    def test_controls_bind_only_index_read_hunk(self):
        here=Path(__file__).resolve().parent
        spec=json.loads((here/'controls.json').read_text())
        raw=(here.parents[1]/'OpenDreamRuntime/Procs/DMProc.cs').read_bytes()
        for mode in ('baseline','omitted-release'):
            changed=mutation(raw,mode,spec)
            self.assertNotEqual(changed,raw)
            self.assertEqual(changed.count(b'owner.Dispose();'),raw.count(b'owner.Dispose();'))
            if mode=='baseline': self.assertEqual(sha(changed),spec['base_sha256'])
            else: self.assertEqual(changed.count(b'Negative control: no release'),2)
            with self.assertRaises(AssertionError): mutation(changed,mode,spec)

if __name__=='__main__': unittest.main()
