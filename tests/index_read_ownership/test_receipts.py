import json
from pathlib import Path
import shutil
import tempfile
import unittest
from control import prepare, check_receipt, PRODUCTION, mutation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HEAD = 'a'*40

class ReceiptTests(unittest.TestCase):
    def stage(self, directory):
        root=Path(directory)/'stage'
        shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('__pycache__'))
        path=root/'tests/index_read_ownership/source-manifest.json'
        spec=json.loads(path.read_text())
        # Unit tests use one known frozen production input and an injected fake Git adapter.
        spec['original_inputs']=[r for r in spec['original_inputs'] if r['path']==PRODUCTION]
        path.write_text(json.dumps(spec))
        control=json.loads((HERE/'controls.json').read_text())
        # Reproduce Linux checkout bytes in the temporary fake-Git stage.
        for name in spec['expected_sources']:
            item=root/name
            item.write_bytes(item.read_bytes().replace(b'\r\n',b'\n'))
        committed={p:(root/p).read_bytes() for p in spec['expected_sources']}
        committed['tests/index_read_ownership/source-manifest.json']=path.read_bytes()
        baseline=mutation(committed[PRODUCTION],'baseline',control)
        def git(unused,*args):
            if args==('rev-parse','HEAD'):return (HEAD+'\n').encode()
            self.assertEqual(args[:2],('cat-file','blob'))
            rev,name=args[2].split(':',1)
            return baseline if rev==spec['base_commit'] else committed[name]
        return root,git

    def test_each_mode_receipt_and_actual_source(self):
        for mode in ('positive','baseline','omitted-release'):
            with tempfile.TemporaryDirectory() as d:
                root,git=self.stage(d)
                data=prepare(root,mode,HEAD,git)
                self.assertTrue(check_receipt(root,data,mode,HEAD))
                self.assertEqual(data['actual_checkout_head'],HEAD)
    def test_wrong_head_and_source_before_mutation(self):
        for tamper in ('head','source'):
            with tempfile.TemporaryDirectory() as d:
                root,git=self.stage(d)
                if tamper=='source':(root/PRODUCTION).write_text('not reviewed')
                with self.assertRaises(AssertionError): prepare(root,'positive','b'*40 if tamper=='head' else HEAD,git)
    def test_receipt_wrong_mode_or_source_after_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root,git=self.stage(d)
            data=prepare(root,'baseline',HEAD,git)
            with self.assertRaises(AssertionError):check_receipt(root,data,'positive',HEAD)
            (root/PRODUCTION).write_text('unrelated bytes')
            with self.assertRaises(AssertionError):check_receipt(root,data,'baseline',HEAD)
    def test_receipt_wrong_blob(self):
        with tempfile.TemporaryDirectory() as d:
            root,git=self.stage(d)
            data=prepare(root,'positive',HEAD,git)
            data['reviewed_sources'][PRODUCTION]['git_blob_oid']='b'*40
            with self.assertRaises(AssertionError):check_receipt(root,data,'positive',HEAD)

if __name__=='__main__':unittest.main()
