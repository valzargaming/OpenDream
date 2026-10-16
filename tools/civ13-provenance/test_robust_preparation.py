"""Read-only dependency admission adversaries; no SDK, engine or patch application."""
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = runpy.run_path(str(ROOT / 'tools/civ13-provenance/prepare-robust.py'))


class RobustPreparation(unittest.TestCase):
    def verify(self, *, head=None, declared=b'reviewed patch\n', committed=b'reviewed patch\n',
               effective=b'reviewed patch\n', untracked=b''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / HELPER['PATCH']
            path.parent.mkdir(parents=True)
            path.write_bytes(declared)
            calls = []

            def git(folder, *args):
                calls.append((folder, args))
                if args == ('rev-parse', 'HEAD'):
                    return (head or HELPER['PIN']).encode()
                if args[0] == 'cat-file':
                    self.assertEqual(args, ('cat-file', 'blob', 'HEAD:' + HELPER['PATCH']))
                    return committed
                if args[0] == 'diff':
                    self.assertIn('--ignore-submodules=none', args)
                    return effective
                self.assertEqual(args, ('ls-files', '--others', '--exclude-standard', '-z'))
                return untracked

            with patch.dict(HELPER['verify_prepared'].__globals__, git=git):
                HELPER['verify_prepared'](root)
            self.assertEqual(len(calls), 4)

    def test_exact_declared_patch_and_windows_line_endings(self):
        self.verify()
        self.verify(declared=b'reviewed patch\r\n', effective=b'reviewed patch\r\n')

    def test_wrong_engine_patch_drift_extra_edit_and_untracked_rejected(self):
        for values in [dict(head='foreign'), dict(declared=b'drift'),
                       dict(effective=b''), dict(effective=b'reviewed patch\nextra edit'),
                       dict(effective=b'reviewed patch\nSubproject commit ' + HELPER['PIN'].encode() + b'-dirty\n'),
                       dict(untracked=b'Unexpected.cs\0')]:
            with self.subTest(values=values), self.assertRaises(AssertionError):
                self.verify(**values)

    def test_only_explicit_control_changes_and_authenticated_host_patch(self):
        verify = HELPER['verify_root_changes']
        with patch.dict(verify.__globals__, verify_prepared=lambda root: None):
            verify(ROOT, [], set())
            verify(ROOT, ['control.cs'], {'control.cs'})
            verify(ROOT, ['control.cs', 'RobustToolbox'], {'control.cs'})
            for changed in [['foreign.cs'], ['RobustToolbox', 'foreign.cs']]:
                with self.assertRaises(AssertionError):
                    verify(ROOT, changed, {'control.cs'})
        def reject(root):
            raise AssertionError('unreviewed engine diff')
        with patch.dict(verify.__globals__, verify_prepared=reject), self.assertRaises(AssertionError):
            verify(ROOT, ['RobustToolbox'], set())

    def test_all_source_guards_admit_host_only_after_tracked_change_gate(self):
        for folder in ['list_pool_capacity', 'resource_output_allocation', 'savefile_resource_bytes',
                       'savefile_raw_cache', 'turf_tile_queue']:
            source = (ROOT / 'tests' / folder / 'control.py').read_text()
            with self.subTest(folder=folder):
                self.assertLess(source.index("assert set(changed) <= allowed | {'RobustToolbox'}"),
                                source.index("['verify_root_changes']"))
                self.assertIn("'--ignore-submodules=none'", source)


if __name__ == '__main__':
    unittest.main()
