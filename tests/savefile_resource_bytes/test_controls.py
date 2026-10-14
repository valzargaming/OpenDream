"""Synthetic classifier/provenance checks, never runtime evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import control
import verify
import archive_logs
from unittest.mock import patch
import zipfile

def evidence(mode):
    n=verify.NS['t'];tag=lambda x:'{'+n+'}'+x
    root=ET.Element(tag('TestRun'));summary=ET.SubElement(root,tag('ResultSummary'))
    positive=mode=='positive'
    ET.SubElement(summary,tag('Counters'),total='1',executed='1',passed='1' if positive else '0',failed='0' if positive else '1',completed='0')
    defs=ET.SubElement(root,tag('TestDefinitions'));d=ET.SubElement(defs,tag('UnitTest'),id='one')
    ET.SubElement(d,tag('TestMethod'),className=verify.CLASS,name=verify.TEST)
    results=ET.SubElement(root,tag('Results'));r=ET.SubElement(results,tag('UnitTestResult'),testId='one',testName=verify.TEST,outcome='Passed' if positive else 'Failed')
    output=ET.SubElement(r,tag('Output'));arrays=3000 if mode=='baseline' else 1
    ET.SubElement(output,tag('StdOut')).text=f'RESOURCE_BYTES_OBSERVATION: reads=3000 arrays={arrays} bytes={arrays*65536} ids=3000\nRESOURCE_BYTES_COLLISION: '+{'positive':'checked','baseline':'historical','hash-only':'mismatch'}[mode]+'\n'+verify.COMPLETE+'\n'
    if not positive:
        error=ET.SubElement(output,tag('ErrorInfo'))
        message='RESOURCE_BYTES_SHARED\nAssert.That(arrays, Is.EqualTo(1))\nExpected: 1\nBut was: 3000' if mode=='baseline' else 'RESOURCE_BYTES_COLLISION_SAFE\nAssert.That(collisionCorrect, Is.True)\nExpected: True\nBut was: False'
        ET.SubElement(error,tag('Message')).text=message
        ET.SubElement(error,tag('StackTrace')).text='at '+verify.CLASS+'.CheckResources(DreamManager manager, DreamObjectTree tree, DreamResourceManager resources, DreamRefManager refs, Byte[] payload) in /checkout/Content.IntegrationTests/SavefileResourceBytesTests.cs:line 1'
    log=('Passed' if positive else 'Failed')+' '+verify.TEST+'\nTest Run '+('Successful.' if positive else 'Failed.')+'\n'
    return root,log,0 if positive else 1

class ParserTests(unittest.TestCase):
    def run_case(self,mode,change=None):
        root,log,code=evidence(mode)
        if change: root,log,code=change(root,log,code)
        return verify.verify(ET.tostring(root),log,mode,code)
    def test_three_intended_cases(self):
        for mode in control.MODES: self.assertTrue(self.run_case(mode))
    def test_reject_runtime_error(self):
        with self.assertRaises(AssertionError): self.run_case('positive',lambda r,l,c:(r,l+'[ERRO] Bad ref',c))
    def test_reject_compile_error(self):
        with self.assertRaises(AssertionError): self.run_case('baseline',lambda r,l,c:(r,l+' error CS1000',c))
    def test_reject_arbitrary_build_failure(self):
        with self.assertRaises(AssertionError): self.run_case('baseline',lambda r,l,c:(r,l+'Build FAILED.\n1 Warning(s)\n1 Error(s)\nTime Elapsed 00:00:01',c))
    def test_exact_vstest_zero_error_footer(self):
        self.assertTrue(self.run_case('baseline',lambda r,l,c:(r,l+'Build FAILED.\n0 Warning(s)\n0 Error(s)\nTime Elapsed 00:00:01',c)))
    def test_reject_duplicate_marker(self):
        def mutate(r,l,c):
            out=r.find('.//t:StdOut',verify.NS);out.text+='\n'+verify.COMPLETE;return r,l,c
        with self.assertRaises(AssertionError): self.run_case('positive',mutate)
    def test_reject_extra_test(self):
        def mutate(r,l,c):
            r.find('t:Results',verify.NS).append(copy.deepcopy(r.find('.//t:UnitTestResult',verify.NS)));return r,l,c
        with self.assertRaises(AssertionError): self.run_case('positive',mutate)
    def test_reject_counter_change(self):
        def mutate(r,l,c): r.find('.//t:Counters',verify.NS).set('executed','0');return r,l,c
        with self.assertRaises(AssertionError): self.run_case('positive',mutate)
    def test_reject_foreign_frame(self):
        def mutate(r,l,c):
            r.find('.//t:StackTrace',verify.NS).text+='\nat Foreign.Work()';return r,l,c
        with self.assertRaises(AssertionError): self.run_case('baseline',mutate)
    def test_reject_changed_observation(self):
        def mutate(r,l,c):
            out=r.find('.//t:StdOut',verify.NS);out.text=out.text.replace('ids=3000','ids=2999');return r,l,c
        with self.assertRaises(AssertionError): self.run_case('positive',mutate)
    def test_reject_wrong_exit(self):
        with self.assertRaises(AssertionError): self.run_case('baseline',lambda r,l,c:(r,l,0))
    def test_reject_unknown_assertion(self):
        def mutate(r,l,c):
            out=r.find('.//t:Message',verify.NS);out.text+='\nOTHER_FAILURE';return r,l,c
        with self.assertRaises(AssertionError): self.run_case('hash-only',mutate)

class SourceTests(unittest.TestCase):
    def test_all_pins(self):
        manifest=json.loads((control.HERE/'source-manifest.json').read_text())
        for path,pin in manifest['sources'].items(): self.assertEqual(control.sha((control.ROOT/path).read_bytes()),pin,path)
    def test_historical_raw_blobs(self):
        spec=json.loads((control.HERE/'controls.json').read_text())
        for path,item in spec['production'].items():
            raw=bytes.fromhex(item['original_hex'])
            self.assertEqual(control.sha(raw),item['original_sha256'])
            self.assertEqual(control.blob(raw),item['original_blob'])
    def test_collision_control_is_one_guard(self):
        spec=json.loads((control.HERE/'controls.json').read_text())['production'][control.MANAGER]
        raw=(control.ROOT/control.MANAGER).read_bytes();changed=control.mutate(raw,'hash-only',spec)
        self.assertEqual(changed.replace(b'if (true) // Negative control: digest alone is insufficient',b'if (data.AsSpan().SequenceEqual(candidate))'),raw)
    def test_dirty_source_rejected(self):
        spec=json.loads((control.HERE/'controls.json').read_text())['production'][control.MANAGER]
        with self.assertRaises(AssertionError): control.mutate((control.ROOT/control.MANAGER).read_bytes()+b'\n','hash-only',spec)
    def test_baseline_is_exact_original(self):
        for path,spec in json.loads((control.HERE/'controls.json').read_text())['production'].items():
            raw=(control.ROOT/path).read_bytes();self.assertEqual(control.mutate(raw,'baseline',spec),bytes.fromhex(spec['original_hex']))
    def test_original_logs_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in archive_logs.NAMES: (root/name).write_bytes(b'original\r\n')
            archive_logs.archive(root);self.assertTrue(archive_logs.verify(root))
            (root/'resource.log').write_bytes(b'changed')
            with self.assertRaises(AssertionError): archive_logs.verify(root)

    def test_committed_pin_tamper_rejected_before_mutation(self):
        manifest=json.loads((control.HERE/'source-manifest.json').read_text())
        head='a'*40
        def read_git(root,*args):
            if args==('rev-parse','HEAD'): return (head+'\n').encode()
            if args==('diff','--name-only','HEAD'): return b''
            path=args[-1].split(':',1)[1]
            if path=='tests/savefile_resource_bytes/source-manifest.json': return (control.HERE/'source-manifest.json').read_bytes()
            raw=(control.ROOT/path).read_bytes()
            return raw+b'changed' if path==control.MANAGER else raw
        with tempfile.TemporaryDirectory() as d, patch.object(control,'git',read_git):
            with self.assertRaises(AssertionError): control.prepare(control.ROOT,'positive',head,Path(d)/'receipt.json')
            self.assertFalse((Path(d)/'receipt.json').exists())
    def test_duplicate_zip_members_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in archive_logs.NAMES: (root/name).write_bytes(b'original')
            archive_logs.archive(root)
            archive=root/'original-logs.zip'
            with zipfile.ZipFile(archive,'a') as z: z.writestr('resource.log',b'original')
            receipt=json.loads((root/'original-logs.json').read_text())
            receipt['zip_sha256']=control.sha(archive.read_bytes())
            (root/'original-logs.json').write_text(json.dumps(receipt))
            with self.assertRaises(AssertionError): archive_logs.verify(root)

    def test_fixture_api_and_exact_head_workflow_contract(self):
        host=(control.ROOT/'Content.IntegrationTests/SavefileResourceBytesTests.cs').read_text()
        self.assertNotIn('new DreamProcArguments',host)
        self.assertIn('options.CVarOverrides[OpenDreamCVars.TopicPort.Name] = "0";',host)
        thread=(control.ROOT/'OpenDreamRuntime/DreamThread.cs').read_text()
        self.assertIn('Run(DreamProc proc, DreamObject src, DreamObject? usr, params DreamValue[] arguments)',thread)
        workflow=(control.ROOT/'.github/workflows/savefile-resource-bytes.yml').read_text()
        self.assertNotIn('pull_request_target',workflow)
        self.assertNotIn('contents: write',workflow)
        self.assertIn('permissions:\n  contents: read',workflow)
        self.assertIn('ref: ${{ github.event.pull_request.head.sha || github.sha }}',workflow)
        self.assertEqual(workflow.count('EXPECTED_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}'),2)
        self.assertIn('matrix:\n        mode: [positive, baseline, hash-only]',workflow)
