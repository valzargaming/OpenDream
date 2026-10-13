"""Pure-file strict oracle and mutation tests; no engine/build invocation."""
import json
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from control import OPTIONS, FIXTURE_HASHES, CANDIDATE_HASH, BASELINE_HASH, verify, mutation, receipt, check_receipt, verify_positive

NS='http://microsoft.com/schemas/VisualStudio/TeamTest/2010'
def tag(name): return '{'+NS+'}'+name

def document(options, *, expression='payload.RefCount', actual=None, marker=None, stack=None, extra=False):
    root=ET.Element(tag('TestRun'))
    result=ET.SubElement(ET.SubElement(root,tag('Results')),tag('UnitTestResult'),testName='NoRuntimesTest',outcome='Failed',testId='fixture')
    error=ET.SubElement(ET.SubElement(result,tag('Output')),tag('ErrorInfo'))
    ET.SubElement(error,tag('Message')).text=f"{marker or options['marker']}\nAssert.That({expression}, Is.EqualTo({options['expected']}))\nExpected: {options['expected']}\nBut was: {options['actual'] if actual is None else actual}"
    ET.SubElement(error,tag('StackTrace')).text=stack or 'ExternalCallRejectionsReleaseArguments in GameTests.CallExt.cs:line22'
    definition=ET.SubElement(ET.SubElement(root,tag('TestDefinitions')),tag('UnitTest'),id='fixture')
    ET.SubElement(definition,tag('TestMethod'),className='Content.IntegrationTests.GameTests',name='NoRuntimesTest')
    summary=ET.SubElement(root,tag('ResultSummary'))
    ET.SubElement(summary,tag('Counters'),total='1',executed='1',passed='0',failed='1')
    if extra: ET.SubElement(result,tag('ErrorInfo'))
    return root

class OracleTests(unittest.TestCase):
    def run_case(self,control,log='',exit_code=1,**changes):
        with tempfile.TemporaryDirectory() as directory:
            p=pathlib.Path(directory)/'synthetic.trx';ET.ElementTree(document(OPTIONS[control],**changes)).write(p)
            return verify(control,p,log,exit_code)
    def test_all_exact_negative_shapes(self):
        for control in OPTIONS:
            with self.subTest(control=control):self.assertTrue(self.run_case(control))
    def test_wrong_assertion_or_stack_or_extra_error(self):
        for control in OPTIONS:
            for change in [dict(expression='other.RefCount'),dict(actual=9),dict(marker='wrong marker'),dict(stack='Other in Other.cs'),dict(extra=True)]:
                with self.subTest(control=control,change=change),self.assertRaises(ValueError):self.run_case(control,**change)
    def test_unrelated_logs_and_exit_codes(self):
        for control in OPTIONS:
            for log,code in [('[ERRO] other',1),('Unhandled exception',1),('',0),('',2)]:
                with self.subTest(control=control,code=code),self.assertRaises(ValueError):self.run_case(control,log,code)


    def test_production_mutations_and_receipts_are_exact(self):
        source=(pathlib.Path(__file__).resolve().parents[2]/'OpenDreamRuntime/Procs/DMOpcodeHandlers.CallExt.cs').read_bytes()
        for control in ['positive',*OPTIONS]:
            changed=mutation(source,control)
            data=receipt(control,'a'*40,source,changed,FIXTURE_HASHES)
            self.assertTrue(check_receipt(data,control,changed,FIXTURE_HASHES,changed))
            if control!='positive':
                self.assertNotEqual(changed,source)
                untouched=b'using var byondArguments' if control=='string-omit' else b'using var stringArguments'
                self.assertIn(untouched,changed)
            for key in ('baseline_commit','baseline_git_blob','reviewed_candidate_sha256','mutated_sha256','actual_checkout_head','expected_assertion'):
                bad=dict(data);bad[key]='wrong'
                with self.subTest(control=control,key=key),self.assertRaises(ValueError):
                    check_receipt(bad,control,changed,FIXTURE_HASHES,changed)
        with self.assertRaises(ValueError):mutation(source+b'changed','string-omit')
        with self.assertRaises(ValueError):mutation(source,'unknown')

    def test_current_master_hooks_and_dm_sources_preserved(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        hooks=(root/'Content.IntegrationTests/GameTests.cs').read_text()
        for name in ('NativeArgumentsReleaseOwnedValues','ObjectInitializationReleasesOwnedValues',
                     'ProcInitializationReleasesOwnedValues','ExternalCallRejectionsReleaseArguments'):
            self.assertEqual(hooks.count(name+'('),1)
        self.assertNotIn('MissingOperatorArgumentsReleaseOwners(',hooks)
        dm=(root/'Content.IntegrationTests/DMProject/code.dm').read_text()
        self.assertIn('object_initialization_new_probe',dm)
        self.assertIn('proc_initialization_arglist_probe',dm)
        self.assertEqual(dm.count('/proc/call_ext_string_rejection_probe('),1)
        self.assertEqual(dm.count('/proc/call_ext_byond_rejection_probe('),1)

    def test_positive_shape_and_completion_markers(self):
        root=document(OPTIONS['string-omit'])
        result=root.find(tag('Results')).find(tag('UnitTestResult'));result.set('outcome','Passed')
        result.remove(result.find(tag('Output')))
        counters=root.find(tag('ResultSummary')).find(tag('Counters'));counters.set('passed','1');counters.set('failed','0')
        log='External call ownership: 1000 caught string and BYOND ABI resolver rejections passed'
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'positive.trx';ET.ElementTree(root).write(path)
            self.assertTrue(verify_positive(path,log,0))
            for output,code in [('',0),(log+'[ERRO] other',0),(log,1)]:
                with self.assertRaises(ValueError):verify_positive(path,output,code)
            counters.set('failed','1');ET.ElementTree(root).write(path)
            with self.assertRaises(ValueError):verify_positive(path,log,0)

if __name__=='__main__':unittest.main()
