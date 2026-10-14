"""Pure source preparation and adversarial TRX classification checks."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location('assoc_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
CONTROL = load('control')
VERIFY = load('verify')
SPEC = json.loads((HERE / 'controls.json').read_text())
MANIFEST = json.loads((HERE / 'source-manifest.json').read_text())
HEAD = 'a' * 40

def result(mode='positive'):
    tag = lambda name: '{' + VERIFY.NS['t'] + '}' + name
    tree = ET.Element(tag('TestRun'))
    results = ET.SubElement(tree, tag('Results'))
    row = ET.SubElement(results, tag('UnitTestResult'), testId='one', testName=VERIFY.TEST,
                        outcome='Passed' if mode == 'positive' else 'Failed')
    output = ET.SubElement(row, tag('Output'))
    if mode == 'positive':
        ET.SubElement(output, tag('StdOut')).text = VERIFY.MARKER
    else:
        error = ET.SubElement(output, tag('ErrorInfo'))
        text = 'Multiple failures or warnings in test:'
        for index, failure in enumerate(SPEC['baseline_failures'], 1):
            text += f"\n{index}) {failure['marker']}\nAssert.That({failure['owner']}.RefCount, Is.EqualTo(1))\nExpected: 1\nBut was: {failure['actual']}\n"
        ET.SubElement(error, tag('Message')).text = text
        ET.SubElement(error, tag('StackTrace')).text = VERIFY.CLASS + '.AssocListRemovalReleasesOwners in Content.IntegrationTests/AssocListRemovalTests.cs:line 99'
    definitions = ET.SubElement(tree, tag('TestDefinitions'))
    definition = ET.SubElement(definitions, tag('UnitTest'), id='one')
    ET.SubElement(definition, tag('TestMethod'), className=VERIFY.CLASS, name=VERIFY.TEST)
    summary = ET.SubElement(tree, tag('ResultSummary'))
    ET.SubElement(summary, tag('Counters'), total='1', executed='1',
                  passed='1' if mode == 'positive' else '0', failed='0' if mode == 'positive' else '1')
    return ET.ElementTree(tree)

class ControlsTests(unittest.TestCase):
    def check(self, tree, mode='positive', code=None, log=None):
        if log is None:
            log = 'Passed PairedOwnersRelease [1 ms]\nTest Run Successful.' if mode == 'positive' else 'Failed PairedOwnersRelease [1 ms]\nTest Run Failed.'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.trx'
            tree.write(path)
            return VERIFY.verify(path, mode, (0 if mode == 'positive' else 1) if code is None else code, log)

    def test_all_exact_modes_and_owner_count(self):
        self.assertEqual(len(SPEC['baseline_failures']), 18)
        self.assertEqual(SPEC['baseline_failures'], SPEC['omitted_value_failures'])
        for mode in ('positive', 'baseline', 'omitted-release'):
            self.assertTrue(self.check(result(mode), mode))

    def test_reject_wrong_test_or_definition(self):
        for attribute in ('className', 'name'):
            tree = result()
            tree.find('.//t:TestMethod', VERIFY.NS).set(attribute, 'Unrelated')
            with self.assertRaises(AssertionError): self.check(tree)

    def test_reject_unrelated_engine_compile_and_runner_failures(self):
        for mode in ('positive', 'baseline', 'omitted-release'):
            for error in ('[ERRO] unrelated', 'Unhandled exception', 'runtime error',
                          'test run aborted', 'Isolated DM fixture compilation failed'):
                with self.subTest(mode=mode, error=error), self.assertRaises(AssertionError):
                    self.check(result(mode), mode, log=error)

    def test_reject_extra_or_missing_results(self):
        for count in (0, 2):
            tree = result()
            parent = tree.find('t:Results', VERIFY.NS)
            row = parent[0]
            parent.remove(row)
            for _ in range(count): parent.append(copy.deepcopy(row))
            with self.assertRaises(AssertionError): self.check(tree)

    def test_reject_missing_duplicate_positive_marker(self):
        for text in ('', VERIFY.MARKER + '\n' + VERIFY.MARKER):
            tree = result()
            tree.find('.//t:StdOut', VERIFY.NS).text = text
            with self.assertRaises(AssertionError): self.check(tree)

    def test_reject_extra_failure_wrong_count_or_owner(self):
        for change in ('extra', 'count', 'owner', 'missing'):
            tree = result('baseline')
            message = tree.find('.//t:Message', VERIFY.NS)
            if change == 'extra': message.text += '\n19) unrelated scalar failure'
            elif change == 'count': message.text = message.text.replace('But was: 1001', 'But was: 1000', 1)
            elif change == 'owner': message.text = message.text.replace('payload.RefCount', 'unrelated.RefCount', 1)
            else: message.text = message.text.split('\n18)')[0]
            with self.subTest(change=change), self.assertRaises(AssertionError): self.check(tree, 'baseline')

    def test_reject_wrong_exit_code_missing_log_and_stack(self):
        for mode in ('positive', 'baseline'):
            with self.assertRaises(AssertionError): self.check(result(mode), mode, code=2)
            with self.assertRaises(AssertionError): self.check(result(mode), mode, log='')
        tree = result('baseline')
        tree.find('.//t:StackTrace', VERIFY.NS).text = 'AnotherFixture.cs'
        with self.assertRaises(AssertionError): self.check(tree, 'baseline')

    def test_reject_unrelated_embedded_assertion_frame(self):
        tree = result('baseline')
        message = tree.find('.//t:Message', VERIFY.NS)
        message.text = message.text.replace('But was: 1001', 'But was: 1001\n at UnrelatedFixture.BadAssertion()', 1)
        with self.assertRaises(AssertionError): self.check(tree, 'baseline')

    def test_reject_log_for_unrelated_test(self):
        with self.assertRaises(AssertionError):
            self.check(result(), log='Passed Unrelated [1 ms]\nTest Run Successful.')

    def test_mutations_exact_and_candidate_drift_rejected(self):
        raw = (ROOT / CONTROL.PRODUCTION).read_bytes()
        self.assertEqual(CONTROL.mutation(raw, 'positive', SPEC), raw)
        self.assertEqual(CONTROL.sha(CONTROL.mutation(raw, 'baseline', SPEC)), SPEC['base_sha256'])
        omitted = CONTROL.mutation(raw, 'omitted-release', SPEC)
        self.assertNotEqual(omitted, CONTROL.mutation(raw, 'baseline', SPEC))
        self.assertIn(SPEC['omitted_value_release'].encode(), omitted)
        with self.assertRaises(AssertionError): CONTROL.mutation(raw + b'\n', 'baseline', SPEC)

    def test_prepare_receipt_all_modes_and_postrun_drift(self):
        for mode in ('positive', 'baseline', 'omitted-release'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                committed = {}
                for name in list(MANIFEST['expected_sources']) + ['tests/assoc_list_removal/source-manifest.json']:
                    raw = (ROOT / name).read_bytes()
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    committed[name] = raw
                baseline = CONTROL.mutation(committed[CONTROL.PRODUCTION], 'baseline', SPEC)
                def git(_, *args):
                    if args == ('rev-parse', 'HEAD'): return (HEAD + '\n').encode()
                    self.assertEqual(args[:2], ('cat-file', 'blob'))
                    revision, name = args[2].split(':', 1)
                    return baseline if revision == MANIFEST['base_commit'] else committed[name]
                receipt = CONTROL.prepare(root, mode, HEAD, git)
                self.assertTrue(CONTROL.check_receipt(root, receipt, mode, HEAD))
                with self.assertRaises(AssertionError): CONTROL.prepare(root, mode, 'b' * 40, git)
                target = root / CONTROL.PRODUCTION
                target.write_bytes(target.read_bytes() + b'\n')
                with self.assertRaises(AssertionError): CONTROL.check_receipt(root, receipt, mode, HEAD)

    def test_new_class_and_isolated_compile_are_connected(self):
        fixture = (ROOT / 'Content.IntegrationTests/AssocListRemovalTests.cs').read_text()
        for text in ('public sealed class AssocListRemovalTests : ContentIntegrationTest',
                     '[Test]', 'public async Task PairedOwnersRelease()', 'compiler.Compile(',
                     'options.CVarOverrides[OpenDreamCVars.JsonPath.Name] = json',
                     'server.WaitAssertion(', 'AssocListRemovalReleasesOwners(manager,',
                     'iteration < 1000', 'DreamThread.Run(proc,', 'ASSOC_REMOVE_FINAL_BUCKET'):
            self.assertIn(text, fixture)
        self.assertEqual(fixture.count('Assert.Multiple('), 1)
        self.assertNotIn('frame.Result.', fixture)
        self.assertNotIn('GameTests.', fixture)
        expected = MANIFEST['expected_sources']
        self.assertNotIn('Content.IntegrationTests/GameTests.cs', expected)
        self.assertNotIn('Content.IntegrationTests/DMProject/code.dm', expected)
        workflow = (ROOT / '.github/workflows/assoc-list-removal.yml').read_text()
        self.assertIn('FullyQualifiedName=' + VERIFY.CLASS + '.' + VERIFY.TEST, workflow)
        self.assertIn('mode: [positive, baseline, omitted-release]', workflow)
        self.assertIn('--verify', workflow)
        self.assertIn('--log assoc-results/assoc.log', workflow)
        self.assertIn('if: always()', workflow)


    def test_explicit_fixture_separate_host_and_no_skipped_evidence(self):
        fixture=(ROOT/'Content.IntegrationTests/AssocListRemovalTests.cs').read_text()
        self.assertIn('[Explicit("Requires a separate test host because BYOND API initialization is process-global")]',fixture)
        workflow=(ROOT/'.github/workflows/assoc-list-removal.yml').read_text()
        self.assertEqual(workflow.count('-- NUnit.ExplicitMode=Relaxed'),1)
        for mode in ('positive','baseline','omitted-release'):
            tree=result(mode)
            tree.find('.//t:UnitTestResult',VERIFY.NS).set('outcome','NotExecuted')
            tree.find('.//t:Counters',VERIFY.NS).set('executed','0')
            with self.subTest(mode=mode), self.assertRaises(AssertionError): self.check(tree,mode)

if __name__ == '__main__': unittest.main(verbosity=2)
