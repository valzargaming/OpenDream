import copy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from verify import verify, verify_runtime, NS, CLASS, CONTENT, FAILURES
from control import canonical, sha, prepare, verify_receipt, PRODUCTION
import json

def fixture(mode):
    tag=lambda n:'{'+NS['t']+'}'+n
    root=ET.Element(tag('TestRun'))
    results=ET.SubElement(root,tag('Results'))
    definitions=ET.SubElement(root,tag('TestDefinitions'))
    names=sorted(CONTENT|set(FAILURES)|({'ConcurrentCallsPreserveContent'} if mode=='positive' else set()))
    for name in names:
        failed=mode=='baseline' and name in FAILURES
        row=ET.SubElement(results,tag('UnitTestResult'),testId=name,testName=name,outcome='Failed' if failed else 'Passed')
        definition=ET.SubElement(definitions,tag('UnitTest'),id=name)
        ET.SubElement(definition,tag('TestMethod'),className=CLASS,name=name)
        if failed:
            error=ET.SubElement(ET.SubElement(row,tag('Output')),tag('ErrorInfo'))
            marker='DECODER_FASTPATH_ALLOCATION: expected <=4096 bytes; observed 8388704' if name=='NoFormattingAvoidsCopy' else 'DECODER_RETAINED_CAPACITY: expected <=4194304 bytes; observed 14680064'
            ET.SubElement(error,tag('Message')).text=marker
            ET.SubElement(error,tag('StackTrace')).text=f'   at {CLASS}.{name}() in /src/Content.IntegrationTests/StringFormatDecoderTests.cs:line 42'
    summary=ET.SubElement(root,tag('ResultSummary'))
    failures=0 if mode=='positive' else 2
    ET.SubElement(summary,tag('Counters'),total=str(len(names)),executed=str(len(names)),passed=str(len(names)-failures),failed=str(failures))
    return root

class StrictTrxTests(unittest.TestCase):
    def check(self, root, mode, code, log=''):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.trx'; ET.ElementTree(root).write(path)
            return verify(path,mode,code,log)
    def test_accept_exact_results(self):
        self.assertTrue(self.check(fixture('positive'),'positive',0))
        self.assertTrue(self.check(fixture('baseline'),'baseline',1))
    def test_reject_corruption(self):
        original=fixture('baseline')
        mutations=[
            lambda r:r.find('.//t:ErrorInfo/t:Message',NS).__setattr__('text','compiler failed'),
            lambda r:r.find('.//t:ErrorInfo/t:Message',NS).__setattr__('text','DECODER_RETAINED_CAPACITY: expected <=4194304 bytes; observed 1'),
            lambda r:r.find('.//t:ErrorInfo/t:StackTrace',NS).__setattr__('text','at OtherTest()'),
            lambda r:r.find('.//t:ErrorInfo/t:StackTrace',NS).__setattr__('text',r.find('.//t:ErrorInfo/t:StackTrace',NS).text+'\n at System.Exception.Throw()'),
            lambda r:r.find('.//t:Counters',NS).set('error','1'),
            lambda r:r.find('.//t:TestMethod',NS).set('className','OtherClass'),
            lambda r:r.find('.//t:UnitTestResult',NS).set('outcome','NotExecuted'),
            lambda r:r.find('.//t:Results',NS).append(copy.deepcopy(r.find('.//t:UnitTestResult',NS))),
            lambda r:r.find('.//t:Results',NS).remove(r.find('.//t:UnitTestResult',NS)),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                root=copy.deepcopy(original); mutation(root)
                with self.assertRaises(AssertionError): self.check(root,'baseline',1)
        for log in ('Unhandled exception','test run aborted','[ERRO] engine broke'):
            with self.assertRaises(AssertionError): self.check(original,'baseline',1,log)
        with self.assertRaises(AssertionError): self.check(original,'baseline',0)
        with self.assertRaises(AssertionError): self.check(fixture('positive'),'positive',1)
    def test_reject_empty_or_malformed(self):
        with self.assertRaises(AssertionError): self.check(ET.Element('TestRun'),'positive',0)
        with self.assertRaises(FileNotFoundError): verify(Path('__missing__'),'baseline',1)
    def test_runtime_requires_only_successful_existing_fixture(self):
        tag=lambda n:'{'+NS['t']+'}'+n
        root=ET.Element(tag('TestRun'))
        results=ET.SubElement(root,tag('Results'))
        row=ET.SubElement(results,tag('UnitTestResult'),testId='runtime',testName='NoRuntimesTest',outcome='Passed')
        definition=ET.SubElement(ET.SubElement(root,tag('TestDefinitions')),tag('UnitTest'),id='runtime')
        ET.SubElement(definition,tag('TestMethod'),className='Content.IntegrationTests.GameTests',name='NoRuntimesTest')
        ET.SubElement(ET.SubElement(root,tag('ResultSummary')),tag('Counters'),total='1',executed='1',passed='1',failed='0')
        marker='Savefile cleanup: 200 native failed/uninitialized disposals and shared-file preservation passed'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'runtime.trx'; ET.ElementTree(root).write(path)
            self.assertTrue(verify_runtime(path,0,marker))
            with self.assertRaises(AssertionError): verify_runtime(path,0,'')
            with self.assertRaises(AssertionError): verify_runtime(path,1,marker)
            row.set('outcome','Failed'); ET.ElementTree(root).write(path)
            with self.assertRaises(AssertionError): verify_runtime(path,0,marker)

class SourceReceiptTests(unittest.TestCase):
    def test_crlf_only_transform(self):
        self.assertEqual(canonical(b'a\r\nb\rc\n'),b'a\nb\rc\n')
    def test_preparation_and_post_build_drift(self):
        for mode in ('positive','baseline'):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder); head='a'*40; base='b'*40
                candidate=b'candidate\n'; original=b'original\n'; test=b'test\n'
                files={PRODUCTION:candidate,'Content.IntegrationTests/StringFormatDecoderTests.cs':test}
                spec={'base_commit':base,'baseline_lf_sha256':sha(original),'expected_sources':{p:sha(v) for p,v in files.items()}}
                manifest='tests/string_format_decoder/source-manifest.json'
                files[manifest]=(json.dumps(spec)+'\n').encode()
                for path,data in files.items():
                    target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data.replace(b'\n',b'\r\n'))
                def fake_git(root,*args):
                    if args==('rev-parse','HEAD'): return (head+'\n').encode()
                    revision,path=args[-1].split(':',1)
                    return original if revision==base else files[path]
                receipt=prepare(root,mode,head,fake_git)
                self.assertTrue(verify_receipt(root,mode,head,receipt))
                (root/'Content.IntegrationTests/StringFormatDecoderTests.cs').write_bytes(b'drift\n')
                with self.assertRaises(AssertionError): verify_receipt(root,mode,head,receipt)
    def test_reject_unreviewed_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); head='a'*40; base='b'*40
            candidate=b'candidate\n'; original=b'original\n'
            spec={'base_commit':base,'baseline_lf_sha256':sha(original),'expected_sources':{PRODUCTION:sha(candidate)}}
            manifest='tests/string_format_decoder/source-manifest.json'
            manifest_raw=(json.dumps(spec)+'\n').encode()
            (root/manifest).parent.mkdir(parents=True,exist_ok=True); (root/manifest).write_bytes(manifest_raw)
            (root/PRODUCTION).parent.mkdir(parents=True,exist_ok=True); (root/PRODUCTION).write_bytes(candidate+b' ')
            def fake_git(root,*args):
                if args==('rev-parse','HEAD'): return (head+'\n').encode()
                revision,path=args[-1].split(':',1)
                return manifest_raw if path==manifest else original if revision==base else candidate
            with self.assertRaises(AssertionError): prepare(root,'positive',head,fake_git)

if __name__=='__main__': unittest.main()
