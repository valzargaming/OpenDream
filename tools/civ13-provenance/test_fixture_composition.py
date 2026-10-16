"""File-only tests of the reviewed shared-driver pin composition."""
import ast
import hashlib
import pathlib
import re
import runpy
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSITION = runpy.run_path(str(ROOT / 'tests/list_pool_capacity/dependency_composition.py'))


class NativeFixtureCompositionTests(unittest.TestCase):
    def test_client_dependent_build_workflows_prepare_trusted_host(self):
        checked = []
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            source = path.read_text()
            builds = [match.start() for match in re.finditer(r'^.*dotnet build.*$', source, re.M)
                      if ('Content.IntegrationTests/' in match.group() or 'OpenDream.slnx' in match.group()
                          or 'dotnet build --configuration' in match.group())]
            if not builds:
                continue
            with self.subTest(workflow=path.name):
                self.assertIn('run: python tools/civ13-provenance/prepare-robust.py', source)
                self.assertLess(source.index('run: python tools/civ13-provenance/prepare-robust.py'), min(builds))
                checked.append(path.name)
        self.assertIn('field-ownership.yml', checked)
        self.assertIn('numeric-list-ownership.yml', checked)

    def test_combined_driver_matches_reviewed_pin(self):
        raw = (ROOT / 'Content.IntegrationTests/GameTests.cs').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest().encode(), COMPOSITION['IDENTITY_FIXTURE_CURRENT'])

    def test_only_fixture_pin_changes_frozen_dependency_candidates(self):
        values = COMPOSITION['frozen']()
        for path, frozen in [('tests/numeric_list_ownership/control.py', 'numeric-composed.py'),
                             ('tests/missing_operator_ownership/control.py', 'missing-composed.py')]:
            with self.subTest(path=path):
                candidate = COMPOSITION['compositions']()[path][1]
                expected = values[frozen].replace(COMPOSITION['IDENTITY_FIXTURE_PREVIOUS'],
                                                  COMPOSITION['IDENTITY_FIXTURE_CURRENT'], 1)
                self.assertEqual(candidate, expected)
                self.assertEqual((ROOT / path).read_bytes(), candidate)

    def test_unknown_or_duplicate_fixture_pin_is_rejected(self):
        old = COMPOSITION['IDENTITY_FIXTURE_PREVIOUS']
        for raw in [b'unknown', old + old, COMPOSITION['IDENTITY_FIXTURE_CURRENT']]:
            with self.subTest(raw=raw), self.assertRaises(AssertionError):
                COMPOSITION['identity_fixture_pin'](raw)

    def test_all_three_control_fixture_maps_bind_combined_driver(self):
        for folder in ['call_ext_ownership', 'numeric_list_ownership', 'missing_operator_ownership']:
            tree = ast.parse((ROOT / 'tests' / folder / 'control.py').read_text())
            assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == 'FIXTURE_HASHES'
                                   for target in node.targets)]
            self.assertEqual(len(assignments), 1)
            pins = ast.literal_eval(assignments[0].value)
            self.assertEqual(pins['Content.IntegrationTests/GameTests.cs'],
                             COMPOSITION['IDENTITY_FIXTURE_CURRENT'].decode())


if __name__ == '__main__':
    unittest.main()
