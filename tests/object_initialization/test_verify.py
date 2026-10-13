"""Synthetic file-only oracle checks. They do not build or launch an engine."""
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from control import CONTROL_OPTIONS, verify

NS = 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'
def tag(name): return '{' + NS + '}' + name

def document(options, *, expression=None, actual=None, marker=None, stack=None, extra_error=False):
    root = ET.Element(tag('TestRun'))
    results = ET.SubElement(root, tag('Results'))
    result = ET.SubElement(results, tag('UnitTestResult'), testName='NoRuntimesTest', outcome='Failed', testId='fixture')
    error = ET.SubElement(ET.SubElement(result, tag('Output')), tag('ErrorInfo'))
    ET.SubElement(error, tag('Message')).text = f"{marker or options['marker']}\nAssert.That({expression or options['expressions'][0]}, Is.EqualTo({options['expected']}))\nExpected: {options['expected']}\nBut was: {options['actual'] if actual is None else actual}"
    ET.SubElement(error, tag('StackTrace')).text = stack or 'ObjectInitializationReleasesOwnedValues in GameTests.ObjectInitialization.cs:line42'
    defs = ET.SubElement(root, tag('TestDefinitions'))
    definition = ET.SubElement(defs, tag('UnitTest'), id='fixture')
    ET.SubElement(definition, tag('TestMethod'), className='Content.IntegrationTests.GameTests', name='NoRuntimesTest')
    summary = ET.SubElement(root, tag('ResultSummary'))
    ET.SubElement(summary, tag('Counters'), total='1', executed='1', passed='0', failed='1')
    if extra_error:
        ET.SubElement(result, tag('ErrorInfo'))
    return root

class StrictOracleTests(unittest.TestCase):
    def check_document(self, control, **changes):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / 'synthetic.trx'
            ET.ElementTree(document(CONTROL_OPTIONS[control], **changes)).write(path)
            return verify(control, path, '', 1)

    def test_each_exact_control_is_accepted(self):
        for control in CONTROL_OPTIONS:
            with self.subTest(control=control):
                self.assertTrue(self.check_document(control))

    def test_each_control_rejects_coincidental_or_additional_failures(self):
        for control in CONTROL_OPTIONS:
            for changed in [dict(expression='unrelated.RefCount'), dict(actual=9), dict(marker='wrong marker'),
                            dict(stack='OtherFixture in Other.cs'), dict(extra_error=True)]:
                with self.subTest(control=control, changed=changed), self.assertRaises(ValueError):
                    self.check_document(control, **changed)

    def test_engine_errors_and_wrong_exit_are_rejected(self):
        for control in CONTROL_OPTIONS:
            with tempfile.TemporaryDirectory() as temporary:
                path = pathlib.Path(temporary) / 'synthetic.trx'
                ET.ElementTree(document(CONTROL_OPTIONS[control])).write(path)
                for log, exit_code in [('[ERRO] unrelated failure', 1), ('', 0), ('', 2)]:
                    with self.subTest(control=control, log=log, exit_code=exit_code), self.assertRaises(ValueError):
                        verify(control, path, log, exit_code)

if __name__ == '__main__':
    unittest.main()
