import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from verify import NS, verify

MARKER = 'Native call argument ownership balanced: native_argument_failure_probe'
URI = NS['t']


def node(parent, name, attrs=None, text=None):
    child = ET.SubElement(parent, '{' + URI + '}' + name, attrs or {})
    child.text = text
    return child


def fixture():
    root = ET.Element('{' + URI + '}TestRun')
    results = node(root, 'Results')
    result = node(results, 'UnitTestResult', {'testName': 'NoRuntimesTest', 'outcome': 'Failed', 'testId': 'one'})
    output = node(result, 'Output')
    error = node(output, 'ErrorInfo')
    node(error, 'Message', text=MARKER + '\nAssert.That(payload.RefCount, Is.EqualTo(1))\n  Expected: 1\n  But was:  2\n')
    node(error, 'StackTrace', text='at NativeArgumentsReleaseOwnedValues in GameTests.NativeArguments.cs:line 25')
    definition = node(node(root, 'TestDefinitions'), 'UnitTest', {'id': 'one'})
    node(definition, 'TestMethod', {'className': 'Content.IntegrationTests.GameTests', 'name': 'NoRuntimesTest'})
    summary = node(root, 'ResultSummary')
    node(summary, 'Counters', {'total': '1', 'executed': '1', 'passed': '0', 'failed': '1', 'error': '0'})
    return root


class VerifierTests(unittest.TestCase):
    def check(self, root, accepted=False, log='Failed NoRuntimesTest', exit_code=1):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'fixture.trx'
            ET.ElementTree(root).write(path)
            if accepted:
                self.assertTrue(verify(path, log, exit_code, MARKER))
            else:
                with self.assertRaises(ValueError): verify(path, log, exit_code, MARKER)

    def test_exact_expected_assertion(self):
        self.check(fixture(), accepted=True)

    def test_single_thread_assertion_wrapper(self):
        root = fixture()
        message = root.find('.//t:ErrorInfo/t:Message', NS)
        message.text = 'Multiple failures or warnings in test:\n  1) ' + message.text
        self.check(root, accepted=True)

    def test_multiple_thread_assertion_wrapper(self):
        root = fixture()
        message = root.find('.//t:ErrorInfo/t:Message', NS)
        message.text = 'Multiple failures or warnings in test:\n  1) ' + message.text + '\n 2) unrelated failure'
        self.check(root)

    def test_intended_marker_plus_unrelated_test_failure(self):
        root = fixture()
        node(root.find('t:Results', NS), 'UnitTestResult', {'testName': 'OtherTest', 'outcome': 'Failed', 'testId': 'two'})
        root.find('t:ResultSummary/t:Counters', NS).set('failed', '2')
        self.check(root)

    def test_intended_marker_plus_unrelated_runtime_error(self):
        self.check(fixture(), log='Failed NoRuntimesTest\n[ERRO] dream: unrelated engine failure')

    def test_intended_marker_plus_additional_assertion_message(self):
        root = fixture()
        message = root.find('.//t:ErrorInfo/t:Message', NS)
        message.text += '\nUnrelated assertion failed'
        self.check(root)

    def test_wrong_test_or_method(self):
        root = fixture()
        root.find('t:Results/t:UnitTestResult', NS).set('testName', 'OtherTest')
        self.check(root)

    def test_runner_error(self):
        root = fixture()
        root.find('t:ResultSummary/t:Counters', NS).set('error', '1')
        self.check(root)

    def test_incorrect_reference_delta(self):
        root = fixture()
        message = root.find('.//t:ErrorInfo/t:Message', NS)
        message.text = message.text.replace('But was:  2', 'But was:  100')
        self.check(root)

    def test_compile_or_crash_exit(self):
        self.check(fixture(), exit_code=2)


if __name__ == '__main__': unittest.main()
