"""Synthetic file-only oracle checks. They do not build or launch an engine."""
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from control import CONTROL_OPTIONS, EXPECTED_CANDIDATE_HASHES, mutate, verify
from unittest.mock import patch
import hashlib
import shutil

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

class CompositionControls(unittest.TestCase):
    def test_each_control_preserves_initspawn_and_other_files(self):
        package=pathlib.Path(__file__).resolve().parents[2]
        for control in CONTROL_OPTIONS:
            with self.subTest(control=control),tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp);original={}
                for name,h in EXPECTED_CANDIDATE_HASHES.items():
                    raw=(package/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),h)
                    (root/name).parent.mkdir(parents=True,exist_ok=True);(root/name).write_bytes(raw);original[name]=raw
                with patch('control.subprocess.check_output',return_value='a'*40+'\n'):mutate(root,control)
                receipt=__import__('json').loads((root/('object-initialization-control-'+control+'.json')).read_text())
                for name,raw in original.items():
                    actual=(root/name).read_bytes()
                    if name==receipt['mutated_path']:
                        self.assertNotEqual(actual,raw)
                        self.assertEqual(hashlib.sha256(actual).hexdigest(),receipt['mutated_sha256'])
                    else:self.assertEqual(actual,raw)
                obj=(root/'OpenDreamRuntime/Objects/DreamObject.cs').read_bytes()
                self.assertIn(b'            try {\n                Initialize(creationArguments);\n            } finally {\n                creationArguments.Dispose();\n            }',obj)
    def test_wrong_production_bytes_rejected(self):
        package=pathlib.Path(__file__).resolve().parents[2]
        for control in CONTROL_OPTIONS:
            with self.subTest(control=control),tempfile.TemporaryDirectory() as tmp:
                root=pathlib.Path(tmp)
                for name in EXPECTED_CANDIDATE_HASHES:
                    (root/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(package/name,root/name)
                p=root/'OpenDreamRuntime/Objects/DreamObject.cs';p.write_bytes(p.read_bytes()+b'// unknown\n')
                with patch('control.subprocess.check_output',return_value='a'*40+'\n'),self.assertRaises(ValueError):mutate(root,control)

if __name__ == '__main__': unittest.main()
