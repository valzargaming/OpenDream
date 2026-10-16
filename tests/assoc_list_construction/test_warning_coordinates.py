"""Pure exact Git source/coordinate composition adversaries; no native execution."""
import importlib.util, json, tempfile, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
W=load('warning_coordinates');A=load('archive_logs')

class WarningCoordinates(unittest.TestCase):
    def test_native_identity_moves_only_unchanged_diagnostic_lines(self):
        paths={'OpenDreamClient/States/MainMenu/MainMenuState.cs',
               'OpenDreamRuntime/DreamConnection.cs', 'OpenDreamRuntime/DreamManager.cs'}
        spec=json.loads((HERE/'inherited-build-warnings.json').read_text())
        original=spec['cases']['matrix']['positive']['warnings']
        selected=[row for row in original if any(row.startswith(path+'(') for path in paths)]
        self.assertEqual(len(selected),16)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);W.capture(folder)
            composed=W.compose(selected,folder)
            self.assertEqual(sum(old!=new for old,new in zip(selected,composed)),10)
            # A coordinate translation must preserve the entire diagnostic payload.
            self.assertEqual([row.split('): warning ',1)[1] for row in selected],
                             [row.split('): warning ',1)[1] for row in composed])
            for path in paths:
                with self.assertRaises(AssertionError):
                    W.compose([path+'(2147483647,1): warning CS0000: foreign'],folder)

    def test_exact_source_map_and_all_diagnostic_identity(self):
        spec=json.loads((HERE/'inherited-build-warnings.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);W.capture(folder)
            for profile,modes in spec['cases'].items():
                for mode,case in modes.items():
                    rows=W.compose(case['warnings'],folder)
                    self.assertEqual(len(rows),1044)
                    build='\n'.join(rows)+'\nBuild succeeded.\n522 Warning(s)\n0 Error(s)\n'
                    self.assertTrue(A.verify_build(build,profile,mode,case['prepared_source_sha256'],folder)['inherited'])
                    for bad in (build.replace(rows[0],rows[0]+' changed',1),build+'\n'+rows[0],build.replace(rows[0],'',1),
                                build.replace(rows[0],rows[0].replace(': warning',': foreign warning'),1)):
                        with self.assertRaises(AssertionError):A.verify_build(bad,profile,mode,case['prepared_source_sha256'],folder)
                    moved=next(row for row,old in zip(rows,case['warnings']) if row!=old)
                    for badrow in (moved.replace(',22)',',23)'),moved.replace('DreamList.cs','Foreign.cs')):
                        if badrow!=moved:
                            with self.assertRaises(AssertionError):A.verify_build(build.replace(moved,badrow,1),profile,mode,case['prepared_source_sha256'],folder)

    def test_source_helper_receipt_and_unmapped_line_drift_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);W.capture(folder)
            for name in list(W.SOURCES)+['warning_coordinates.py','source-pins.json']:
                path=folder/name;raw=path.read_bytes();path.write_bytes(raw+b' drift')
                with self.assertRaises((AssertionError,json.JSONDecodeError)):W.compose([],folder)
                path.write_bytes(raw)
            extra=folder/'foreign';extra.write_text('x')
            with self.assertRaises(AssertionError):W.compose([],folder)
            extra.unlink()
            with self.assertRaises(AssertionError):W.compose(['OpenDreamRuntime/Objects/Types/DreamList.cs(2147483647,22): warning CS0000: foreign'],folder)

if __name__=='__main__':unittest.main()
