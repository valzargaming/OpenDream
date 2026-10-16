from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

class SourceControlTests(unittest.TestCase):
    def test_controls_use_exact_production_input(self):
        here = Path(__file__).resolve().parent
        root = here.parents[1]
        spec = json.loads((here/'controls.json').read_text())
        for mode in ('baseline','omitted-release'):
            with tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                tools = stage/'tests/field_ownership'
                tools.mkdir(parents=True)
                for name in ('prepare_control.py','controls.json'):
                    shutil.copyfile(here/name,tools/name)
                source = stage/'OpenDreamRuntime/Procs/DMProc.cs'
                source.parent.mkdir(parents=True)
                shutil.copyfile(root/'OpenDreamRuntime/Procs/DMProc.cs',source)
                result = subprocess.run([sys.executable,str(tools/'prepare_control.py'),mode],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                actual = source.read_text()
                if mode == 'baseline':
                    self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(),spec['base_sha256'])
                else:
                    self.assertEqual(actual.count('Negative control: no release'),2)
                repeat = subprocess.run([sys.executable,str(tools/'prepare_control.py'),mode],capture_output=True,text=True)
                self.assertNotEqual(repeat.returncode,0,'guard rejects already-mutated input')

if __name__ == '__main__': unittest.main()
