"""Pure provenance/mutation controls with an injected Git reader; no real Git invocation."""
from pathlib import Path
import copy
import json
import tempfile
import unittest
import control as C

HERE=Path(__file__).resolve().parent
PACKET=HERE.parents[1]
HEAD='a'*40

class SourceControls(unittest.TestCase):
    def setup_root(self, temporary):
        root=Path(temporary)
        spec=json.loads((HERE/'source-manifest.json').read_text())
        committed={}
        for name in spec['expected_sources']:
            source=PACKET/name
            if not source.exists(): source=PACKET.parent/'dependencies'/name
            raw=source.read_bytes()
            self.assertEqual(C.sha(raw),spec['expected_sources'][name])
            (root/name).parent.mkdir(parents=True,exist_ok=True)
            (root/name).write_bytes(raw)
            committed[name]=raw
        name='tests/typesof_ownership/source-manifest.json'
        raw=(HERE/'source-manifest.json').read_bytes()
        (root/name).write_bytes(raw);committed[name]=raw
        baseline=(HERE/'original-native-root.raw.txt').read_bytes()
        def git(_, *args):
            if args==('rev-parse','HEAD'):return (HEAD+'\n').encode()
            if len(args)==3 and args[:2]==('cat-file','blob'):
                rev,path=args[2].split(':',1)
                if rev==HEAD:return committed[path]
                if rev==spec['base_commit'] and path==C.PRODUCTION:return baseline
            raise AssertionError('Unexpected fake-Git request: '+repr(args))
        return root,committed,git

    def test_exact_modes_and_bounded_composed_restoration(self):
        for mode in ('positive','baseline'):
            with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
                root,_,git=self.setup_root(t)
                data=C.prepare(root,mode,HEAD,git)
                self.assertTrue(C.check_receipt(root,data,mode,HEAD))
                if mode=='baseline':
                    self.assertEqual((root/C.PRODUCTION).read_bytes(),(HERE/'composed-baseline-native-root.txt').read_bytes())

    def test_wrong_head_or_uncommitted_manifest(self):
        with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
            root,_,git=self.setup_root(t)
            with self.assertRaises(AssertionError): C.prepare(root,'positive','b'*40,git)
            manifest=root/'tests/typesof_ownership/source-manifest.json'
            manifest.write_bytes(manifest.read_bytes()+b' ')
            with self.assertRaises(AssertionError): C.prepare(root,'positive',HEAD,git)

    def test_checkout_dependency_or_handler_drift(self):
        for name in ('Content.IntegrationTests/TypesOfOwnershipTests.cs',C.PRODUCTION,'OpenDreamRuntime/Procs/NativeProc.cs'):
            with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
                root,_,git=self.setup_root(t)
                source=root/name;source.write_bytes(source.read_bytes()+b'\n')
                with self.subTest(name=name),self.assertRaises(AssertionError): C.prepare(root,'baseline',HEAD,git)

    def test_wrong_historical_raw_blob(self):
        with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
            root,_,git=self.setup_root(t)
            def bad(reader,*args):
                raw=git(reader,*args)
                return raw+b'\n' if args[:2]==('cat-file','blob') and args[2].startswith('644') else raw
            with self.assertRaises(AssertionError): C.prepare(root,'baseline',HEAD,bad)

    def test_control_hash_method_and_output_tampering(self):
        ctrl=json.loads((HERE/'controls.json').read_text())
        candidate=(PACKET/C.PRODUCTION).read_bytes()
        for kind in ('input','candidate_pin','duplicate','replacement','output_pin','mode'):
            tampered=copy.deepcopy(ctrl);raw=candidate;mode='baseline'
            if kind=='input':raw+=b'\n'
            elif kind=='candidate_pin':tampered['candidate_sha256']='0'*64
            elif kind=='duplicate':
                raw+=tampered['replacements'][0][0].encode();tampered['candidate_sha256']=C.sha(raw)
            elif kind=='replacement':tampered['replacements'][0][1]+='\n'
            elif kind=='output_pin':tampered['base_sha256']='0'*64
            else:mode='foreign'
            with self.subTest(kind=kind),self.assertRaises(AssertionError): C.mutation(raw,mode,tampered)

    def test_receipt_mutations(self):
        for key in ('mode','actual_checkout_head','base_commit','mutated_production_sha256','production_path','source_manifest_sha256'):
            with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
                root,_,git=self.setup_root(t);data=C.prepare(root,'baseline',HEAD,git)
                data[key]='foreign'
                with self.subTest(key=key),self.assertRaises(AssertionError):C.check_receipt(root,data,'baseline',HEAD)

    def test_prepared_bytes_must_match_receipt(self):
        with tempfile.TemporaryDirectory(prefix='typesof-source-pure-') as t:
            root,_,git=self.setup_root(t);data=C.prepare(root,'baseline',HEAD,git)
            source=root/C.PRODUCTION;source.write_bytes(source.read_bytes()+b' ')
            with self.assertRaises(AssertionError): C.check_receipt(root,data,'baseline',HEAD)

if __name__=='__main__':unittest.main()
