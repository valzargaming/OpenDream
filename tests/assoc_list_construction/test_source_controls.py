"""Pure fake-Git provenance adversaries; no native execution or real Git calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('construction_control', HERE/'control.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
HEAD = 'a'*40

class SourceControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='construction-source-pure-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = json.loads((HERE/'source-manifest.json').read_text())
        package = HERE.parents[1]
        self.committed = {}
        for path in self.manifest['expected_sources']:
            source = package/path
            raw = source.read_bytes().replace(b'\r\n', b'\n')
            target = self.root/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            self.committed[path] = raw
        manifest_path = 'tests/assoc_list_construction/source-manifest.json'
        raw = (HERE/'source-manifest.json').read_bytes()
        (self.root/manifest_path).write_bytes(raw)
        self.committed[manifest_path] = raw
        control = json.loads((HERE/'controls.json').read_text())
        self.original = C.mutation(self.committed[C.PRODUCTION], 'baseline', control)
        self.delayed = C.mutation(self.committed[C.PRODUCTION], 'timing-negative', control)

    def git(self,root,*args):
        if args == ('rev-parse','HEAD'): return (HEAD+'\n').encode()
        self.assertEqual(args[:2],('cat-file','blob'))
        rev,path=args[2].split(':',1)
        if rev == self.manifest['base_commit']:
            self.assertEqual(path,C.PRODUCTION)
            return self.original
        if rev == '5d493264b9fc775b0891a9442f9b95d49740100f':
            self.assertEqual(path,C.PRODUCTION)
            return self.delayed
        self.assertEqual(rev,HEAD)
        return self.committed[path]

    def prepare(self,mode='positive'):
        return C.prepare(self.root,mode,HEAD,git=self.git)

    def test_exact_three_modes_and_postrun_receipt(self):
        for mode in ('positive','baseline','timing-negative'):
            (self.root/C.PRODUCTION).write_bytes(self.committed[C.PRODUCTION])
            receipt=self.prepare(mode)
            self.assertTrue(C.check_receipt(self.root,receipt,mode,HEAD))
            self.assertEqual(receipt['original_inputs'][0]['actual_raw_sha256'],self.manifest['original_inputs'][0]['sha256'])

    def test_wrong_head_and_uncommitted_manifest(self):
        with self.assertRaises(AssertionError): C.prepare(self.root,'positive','b'*40,git=self.git)
        path=self.root/'tests/assoc_list_construction/source-manifest.json'
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaises(AssertionError): self.prepare()

    def test_raw_historical_crlf_and_content_drift(self):
        original=self.original
        for bad in (original.replace(b'\n',b'\r\n'), original+b' '):
            self.original=bad
            with self.assertRaises(AssertionError): self.prepare()

    def test_reviewed_checkout_and_committed_blob_drift(self):
        path='Content.IntegrationTests/AssocListConstructionTests.cs'
        raw=self.committed[path]
        (self.root/path).write_bytes(raw+b' ')
        with self.assertRaises(AssertionError): self.prepare()
        (self.root/path).write_bytes(raw)
        self.committed[path]=raw+b' '
        with self.assertRaises(AssertionError): self.prepare()

    def test_control_body_hash_count_and_unsupported_mode(self):
        control=json.loads((HERE/'controls.json').read_text())
        raw=self.committed[C.PRODUCTION]
        for bad in (raw+b' ',raw.replace(control['replacements'][0][0].encode(),b'')):
            with self.assertRaises(AssertionError): C.mutation(bad,'baseline',control)
        with self.assertRaises(AssertionError): C.mutation(raw,'omitted-release',control)
        changed=copy.deepcopy(control)
        changed['replacements'][0][1]+='\n // unreviewed'
        with self.assertRaises(AssertionError): C.mutation(raw,'baseline',changed)
        changed=copy.deepcopy(control)
        changed['replacements'][0][0]='absent'
        with self.assertRaises(AssertionError): C.mutation(raw,'baseline',changed)

    def test_receipt_tampering_and_postrun_source_drift(self):
        receipt=self.prepare('baseline')
        for field in ('mode','actual_checkout_head','mutated_production_sha256','source_manifest_git_blob_oid'):
            bad=copy.deepcopy(receipt);bad[field]='wrong'
            with self.assertRaises(AssertionError): C.check_receipt(self.root,bad,'baseline',HEAD)
        bad=copy.deepcopy(receipt)
        bad['original_inputs'][0]['actual_raw_sha256']='0'*64
        with self.assertRaises(AssertionError): C.check_receipt(self.root,bad,'baseline',HEAD)
        path=self.root/C.PRODUCTION;path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AssertionError): C.check_receipt(self.root,receipt,'baseline',HEAD)

    def test_timing_control_is_bounded_and_hash_pinned(self):
        control=json.loads((HERE/'controls.json').read_text())
        raw=self.committed[C.PRODUCTION]
        delayed=C.mutation(raw,'timing-negative',control)
        fixed,old=control['timing_negative_replacements'][0]
        self.assertEqual(delayed.replace(old.encode(),fixed.encode(),1),raw)
        self.assertEqual(C.sha(delayed),control['timing_negative_sha256'])
        for field in ('timing_negative_sha256','candidate_sha256'):
            changed=copy.deepcopy(control);changed[field]='0'*64
            with self.assertRaises(AssertionError): C.mutation(raw,'timing-negative',changed)
        for which in (0,1):
            changed=copy.deepcopy(control);changed['timing_negative_replacements'][0][which]+='\n // unreviewed'
            with self.assertRaises(AssertionError): C.mutation(raw,'timing-negative',changed)

    def test_timing_receipt_rejects_mode_crossuse_and_unknown_sources(self):
        receipt=self.prepare('timing-negative')
        for mode in ('positive','baseline'):
            with self.assertRaises(AssertionError): C.check_receipt(self.root,receipt,mode,HEAD)
        bad=copy.deepcopy(receipt);bad['reviewed_sources']['foreign.cs']={'sha256':'0'*64,'git_blob_oid':'0'*40}
        with self.assertRaises(AssertionError): C.check_receipt(self.root,bad,'timing-negative',HEAD)

    def test_prior_positive_raw_git_pin_is_independent_of_historical_baseline(self):
        self.assertEqual(C.sha(self.delayed),'fe68383c725d4aa8c28774f789905fb2b4a77de259001fcdba1fb66976fb9383')
        self.assertEqual(C.blob(self.delayed),'44c675575645d9245efaa5ae3a5349ef085717d5')
        for bad in (self.delayed+b' ',self.delayed.replace(b'\n',b'\r\n')):
            self.delayed=bad
            with self.assertRaises(AssertionError): self.prepare('timing-negative')

if __name__ == '__main__': unittest.main()
