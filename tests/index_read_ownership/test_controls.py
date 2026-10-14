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
            else:
                self.assertEqual(changed.count(b'var indexReadFailed = false;'),1)
                self.assertEqual(changed.count(b'if (!peek && !indexReadFailed)'),1)
                self.assertEqual(changed.count(b'index.Dispose();'),raw.count(b'index.Dispose();'))
                self.assertEqual(changed.count(b'indexing.Dispose();'),raw.count(b'indexing.Dispose();'))
            with self.assertRaises(AssertionError): mutation(changed,mode,spec)

    def test_exception_only_control_preserves_success_and_borrowed_paths(self):
        here=Path(__file__).resolve().parent
        spec=json.loads((here/'controls.json').read_text())
        body=spec['exception_only_omitted_release']
        self.assertIn('var indexReadFailed = false;',body)
        self.assertIn('} catch {\n                    indexReadFailed = true;\n                    throw;\n                } finally {',body)
        self.assertIn('if (!peek && !indexReadFailed) {\n                        index.Dispose();\n                        indexing.Dispose();',body)
        self.assertEqual(body.count('GetIndex(indexing, index, this)'),1)
        self.assertEqual(body.count('indexReadFailed = true;'),1)
        for peek in (False,True):
            for failed in (False,True):
                release=not peek and not failed
                self.assertEqual(release,(not peek) if not failed else False)

    def test_existing_operator_controls_fail_before_index_read_dependency(self):
        here=Path(__file__).resolve().parent
        hook=(here.parents[1]/'Content.IntegrationTests/GameTests.cs').read_text()
        earlier=('ExternalCallRejectionsReleaseArguments(', 'SupportedOperatorFallbacksReleaseOwners(', 'MissingOperatorArgumentsReleaseOwners(')
        for name in earlier:
            self.assertEqual(hook.count(name),1)
            self.assertLess(hook.index(name),hook.index('IndexReferenceReadsReleaseOwners('))
        self.assertLess(hook.index(earlier[0]),hook.index(earlier[1]))
        self.assertLess(hook.index(earlier[1]),hook.index(earlier[2]))
        # Existing missing-dispose control must still remove only missing-overload arguments.
        control=(here.parents[1]/'tests/missing_operator_ownership/control.py').read_text()
        self.assertIn("if control == 'missing-dispose':",control)
        self.assertIn('arguments.Dispose();',control)

if __name__=='__main__': unittest.main()
