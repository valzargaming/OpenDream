import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1] / 'native_argument_ownership'
sys.path.insert(0, str(SOURCE))
from verify import verify, NS
spec = importlib.util.spec_from_file_location('native_verifier_fixture', SOURCE / 'test_verify.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class InitializationVerifierTests(unittest.TestCase):
    def check(self, actual, observed, accepted):
        root = helper.fixture()
        marker = 'Rejected DM initialization releases input and partial owners'
        root.find('.//t:ErrorInfo/t:Message', NS).text = (
            marker + '\nAssert.That(payload.RefCount, Is.EqualTo(1))\n'
            '  Expected: 1\n  But was:  ' + str(observed) + '\n')
        root.find('.//t:ErrorInfo/t:StackTrace', NS).text = (
            'at ProcInitializationReleasesOwnedValues in GameTests.ProcInitialization.cs:line 65')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.trx'
            ET.ElementTree(root).write(path)
            def run():
                return verify(path, 'Failed NoRuntimesTest', 1, marker, expressions=('payload.RefCount',),
                              actual=actual, fixture_method='ProcInitializationReleasesOwnedValues',
                              fixture_file='GameTests.ProcInitialization.cs')
            if accepted:
                self.assertTrue(run())
            else:
                with self.assertRaises(ValueError):
                    run()

    def test_input_omission_exact_two(self):
        self.check(2, 2, True)

    def test_historical_partial_frame_exact_three(self):
        self.check(3, 3, True)

    def test_historical_control_rejects_input_only_failure(self):
        self.check(3, 2, False)

    def test_input_control_rejects_partial_frame_failure(self):
        self.check(2, 3, False)
