"""Offline regressions: real Git divergence, path selection, and job guard controls."""
from pathlib import Path
import tempfile
import unittest

import native_selection as selection


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / selection.WORKFLOW).read_text()
SHA = '1234567890abcdef1234567890abcdef12345678'


class NativeSelectionTests(unittest.TestCase):
    def jobs(self, event='pull_request', sha_input=None, text=TEXT):
        return selection.selected_jobs(text, event, SHA, sha_input)

    def test_pr_blocks_native_even_with_matching_input(self):
        for value in (None, '', SHA, '0' * 40):
            self.assertFalse(self.jobs(sha_input=value)['native-compile'])

    def test_manual_default_is_empty_and_blocks_native(self):
        self.assertEqual(selection.native_input_default(TEXT), '')
        self.assertFalse(self.jobs('workflow_dispatch')['native-compile'])

    def test_manual_wrong_sha_blocks_native(self):
        self.assertFalse(self.jobs('workflow_dispatch', '0' * 40)['native-compile'])

    def test_manual_exact_sha_selects_only_as_hypothetical_source_check(self):
        self.assertTrue(self.jobs('workflow_dispatch', SHA)['native-compile'])

    def test_other_automatic_events_block_native(self):
        for event in ('push', 'schedule', 'pull_request_target'):
            self.assertFalse(self.jobs(event, SHA)['native-compile'])

    def test_injected_jobs_remain_selected(self):
        for event in ('pull_request', 'workflow_dispatch'):
            jobs = self.jobs(event)
            self.assertEqual(set(jobs), {'integration', 'client-identity', 'ledger', 'native-compile'})
            for job in ('integration', 'client-identity', 'ledger'):
                self.assertTrue(jobs[job])

    def test_removing_guard_negative_control_selects_vendor_job(self):
        guard = selection.condition(TEXT, 'native-compile')
        mutated = TEXT.replace('    if: ' + guard + '\n', '')
        self.assertTrue(self.jobs(text=mutated)['native-compile'])

    def test_omitting_event_guard_negative_control(self):
        mutated = TEXT.replace("github.event_name == 'workflow_dispatch' && ", '')
        self.assertTrue(self.jobs(sha_input=SHA, text=mutated)['native-compile'])

    def test_omitting_sha_guard_negative_control(self):
        mutated = TEXT.replace(' && inputs.native_compile_authorized_sha == github.sha', '')
        self.assertTrue(self.jobs('workflow_dispatch', text=mutated)['native-compile'])

    def test_paths_include_regression_and_native_sources(self):
        patterns = selection.pr_patterns(TEXT)
        for path in (selection.WORKFLOW, 'tests/workflow_routing/test_native_selection.py',
                     'tools/native-byond-bridge/bridge.dm',
                     'OpenDreamRuntime/NativeByondBridge/NativeIdentityAdmissionGate.cs',
                     'Content.IntegrationTests/GameTests.NativeIdentity.cs'):
            self.assertTrue(any(selection.path_matches(path, p) for p in patterns), path)
        self.assertFalse(any(selection.path_matches('Content.Tests/Text2FileTests.cs', p)
                             for p in patterns))

    def test_single_star_does_not_cross_directory(self):
        self.assertTrue(selection.path_matches('OpenDreamRuntime/DreamManager.cs',
                                               'OpenDreamRuntime/DreamManager*.cs'))
        self.assertFalse(selection.path_matches('OpenDreamRuntime/DreamManager/extra.cs',
                                                'OpenDreamRuntime/DreamManager*.cs'))

    def test_unknown_expression_fails_closed(self):
        with self.assertRaises(ValueError):
            selection.evaluate('${{ contains(inputs.sha, github.sha) }}', {})

    def test_three_dot_retains_earlier_branch_changes(self):
        # The safety regression: old PR head..successor misses the workflow, while
        # the actual base...successor diff includes it after default advances.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return selection.git(root, '-c', 'user.name=Offline Test', '-c',
                                     'user.email=offline@example.invalid', *args)
            git('init', '-q')
            (root / 'base.txt').write_text('base')
            git('add', 'base.txt'); git('commit', '-qm', 'base')
            original = git('rev-parse', 'HEAD')
            workflow = root / selection.WORKFLOW
            workflow.parent.mkdir(parents=True)
            workflow.write_text(TEXT)
            git('add', selection.WORKFLOW); git('commit', '-qm', 'existing PR workflow')
            old_head = git('rev-parse', 'HEAD')
            (root / 'successor.txt').write_text('composition only')
            git('add', 'successor.txt'); git('commit', '-qm', 'successor')
            head = git('rev-parse', 'HEAD')
            git('checkout', '-q', '--detach', original)
            (root / 'default.txt').write_text('default advanced')
            git('add', 'default.txt'); git('commit', '-qm', 'default advanced')
            base = git('rev-parse', 'HEAD')
            self.assertNotIn(selection.WORKFLOW, git('diff', '--name-only', old_head, head).splitlines())
            result = selection.report(root, base, head)
            self.assertEqual(result['merge_base'], original)
            self.assertIn(selection.WORKFLOW, result['changed_paths'])
            self.assertTrue(result['workflow_selected'])
            self.assertFalse(result['pull_request_jobs']['native-compile'])
            self.assertTrue(result['pull_request_jobs']['integration'])


if __name__ == '__main__':
    unittest.main()
