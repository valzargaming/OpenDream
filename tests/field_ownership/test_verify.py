import tempfile
import unittest
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from verify import verify, MARKER, FAILURES, NS

def trx(mode='positive', bad_marker=False, duplicate=False, skip=False):
    positive = mode == 'positive'
    outcome = 'Passed' if positive else 'Failed'
    if skip: outcome = 'NotExecuted'
    message = 'compiler failed' if bad_marker else 'Multiple failures or warnings in test:\n'+''.join(
        f' {i}) {marker}\nAssert.That(owner.RefCount, Is.EqualTo({"1" if i < 3 else "peek ? 2 : 1"}))\nExpected: 1\nBut was: {1001 if i < 3 else 2}\n'
        for i,marker in enumerate(FAILURES,1))
    stdout = 'unrelated output' if bad_marker else MARKER
    error = '' if positive else f'<ErrorInfo><Message>{message}</Message><StackTrace>GameTests.FieldReferencesReleaseOwners in GameTests.FieldOwnership.cs</StackTrace></ErrorInfo>'
    row = f'<UnitTestResult testId="case1" testName="NoRuntimesTest" outcome="{outcome}"><Output><StdOut>{stdout}</StdOut>{error}</Output></UnitTestResult>'
    return ('<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><Results>' + row*(2 if duplicate else 1)
            + '</Results><TestDefinitions><UnitTest id="case1"><TestMethod className="Content.IntegrationTests.GameTests" name="NoRuntimesTest"/></UnitTest></TestDefinitions><ResultSummary><Counters total="1" executed="1" passed="'
            + ('1' if positive else '0')+'" failed="'+('0' if positive else '1')+'"/></ResultSummary></TestRun>')

class VerifyTests(unittest.TestCase):
    def check(self, xml, mode, code):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'results.trx'
            path.write_text(xml)
            return verify(path, mode, code)
    def test_positive(self): self.assertTrue(self.check(trx(), 'positive', 0))
    def test_both_controls(self):
        for mode in ('baseline','omitted-release'):
            self.assertTrue(self.check(trx(mode), mode, 1))
    def test_wrong_failure_exit_completion(self):
        for xml, mode, code in [(trx('baseline',bad_marker=True),'baseline',1),
                                (trx('baseline'),'baseline',0),(trx(),'positive',1),
                                (trx(bad_marker=True),'positive',0)]:
            with self.assertRaises(AssertionError): self.check(xml, mode, code)
    def test_duplicate_missing_skipped_wrong_test(self):
        for xml in [trx(duplicate=True),trx(skip=True),trx().replace('total="1"','total="0"'),
                    trx().replace('NoRuntimesTest','OtherTest')]:
            with self.assertRaises(AssertionError): self.check(xml,'positive',0)
    def test_missing_file_malformed_empty(self):
        with self.assertRaises(FileNotFoundError): verify(Path('__missing__.trx'),'baseline',1)
        with self.assertRaises(Exception): self.check('<broken','positive',0)
        with self.assertRaises(AssertionError): self.check('<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><Results/></TestRun>','positive',0)
    def test_control_requires_each_marker(self):
        for marker in FAILURES:
            with self.assertRaises(AssertionError): self.check(trx('baseline').replace(marker,''),'baseline',1)
    def test_controls_reject_extra_failures_counts_stack_and_runtime(self):
        xml=trx('baseline')
        for bad in [xml.replace('</Message>','Unhandled exception</Message>'),
                    xml.replace('</Message>',' 4) random failure</Message>'),
                    xml.replace('But was: 1001','But was: 1002'),
                    xml.replace('GameTests.FieldOwnership.cs','OtherFixture.cs'),
                    xml.replace('total="1"','error="1" total="1"'),
                    xml.replace('className="Content.IntegrationTests.GameTests"','className="OtherClass"')]:
            with self.assertRaises(AssertionError): self.check(bad,'baseline',1)
    def captured_xml(self, mode):
        capture = json.loads((Path(__file__).parent/'fixtures'/'nunit-aggregate-messages.json').read_text())
        tree = ET.fromstring(trx(mode))
        tree.find('.//t:ErrorInfo/t:Message', NS).text = capture['messages'][mode]
        return ET.tostring(tree, encoding='unicode')
    def test_original_captured_nunit_messages(self):
        for mode in ('baseline', 'omitted-release'):
            self.assertTrue(self.check(self.captured_xml(mode), mode, 1))
    def test_captured_messages_reject_unrelated_or_corrupt_frames(self):
        for mode in ('baseline', 'omitted-release'):
            xml = self.captured_xml(mode)
            for before, after in [
                ('FieldMissingOwners1000(', 'OtherFixture('),
                ('FieldSuccessAndPeekOwnership(', 'OtherFixture('),
                ('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)', 'System.Exception.Throw()'),
                ('/Content.IntegrationTests/GameTests.FieldOwnership.cs:line', '/OtherFixture.cs:line'),
                ('But was:  1001', 'But was:  1002'),
                ('Expected: 1', 'Expected: 2'),
                ('FIELD_READ_OWNER_ASSERT_1000', 'FIELD_WRITE_OWNER_ASSERT_1000'),
                ('</ns0:Message>', ' 4) extra failure</ns0:Message>'),
                ('</ns0:Message>', 'Unhandled exception</ns0:Message>'),
                ('   at System.Threading.Thread.StartHelper.Callback(Object state)', ''),
            ]:
                with self.subTest(mode=mode, corruption=after):
                    self.assertIn(before, xml)
                    with self.assertRaises(AssertionError):
                        self.check(xml.replace(before, after), mode, 1)
if __name__ == '__main__': unittest.main()
