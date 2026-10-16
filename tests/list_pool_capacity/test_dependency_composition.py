"""Pure exact additive dependency authentication; never starts an SDK/runtime."""
import copy, hashlib, json, subprocess, unittest
from pathlib import Path
import dependency_composition as C
ROOT=Path(__file__).resolve().parents[2]
class Tests(unittest.TestCase):
    def test_frozen_inputs_match_immutable_git(self):
        paths={'list-original.cs':(C.BASE,C.LIST),'numeric-original.py':(C.BASE,C.NUMERIC),
               'numeric-composed.py':(C.LIST_HEAD,C.NUMERIC),'attributes-base.txt':(C.BASE,'.gitattributes'),
               'attributes-list.txt':(C.LIST_HEAD,'.gitattributes'),'attributes-cache.txt':(C.CACHE_HEAD,'.gitattributes'),
               'project-original.txt':('4e6e4c4dd523230ca94ffe39d04812592a3b8615','Content.IntegrationTests/Content.IntegrationTests.csproj'),
               'project-composed.txt':(C.BASE,'Content.IntegrationTests/Content.IntegrationTests.csproj'),
               'missing-original.py':('53554597f7b594ea8a75570240d69d7d3003d56f','tests/missing_operator_ownership/control.py'),
               'missing-composed.py':(C.BASE,'tests/missing_operator_ownership/control.py')}
        for name,(commit,path) in paths.items():
            self.assertEqual(C.frozen()[name],subprocess.check_output(['git','-C',str(ROOT),'cat-file','blob',commit+':'+path]))
    def test_exact_dependencies_and_other_drift(self):
        for path,(_,candidate,_,_) in C.compositions().items():
            C.authenticate(path,candidate)
            for wrong in [candidate+b'\n',candidate.replace(b'65_536',b'65_537'),candidate.replace(b'text eol=lf',b'text eol=crlf')]:
                if wrong!=candidate:
                    with self.assertRaises(AssertionError):C.authenticate(path,wrong)
    def test_manifest_pins_and_provenance(self):
        for suite in ['field_ownership','range_ownership','native_matrix_ownership','typesof_ownership','savefile_raw_cache']:
            path=ROOT/'tests'/suite/'source-manifest.json';spec=json.loads(path.read_text())
            C.validate(ROOT,spec)
            for kind in ['missing','original','candidate','pin']:
                changed=copy.deepcopy(spec);entry=next(iter(changed['dependency_compositions']))
                if kind=='missing':changed['dependency_compositions']={}
                elif kind=='pin':changed.get('expected_sources',changed.get('sources'))[entry]='0'*64
                else:changed['dependency_compositions'][entry][kind+'_sha256']='0'*64
                with self.assertRaises(AssertionError):C.validate(ROOT,changed)
    def test_affected_candidate_manifest_closure(self):
        for suite in ['field_ownership','range_ownership','native_matrix_ownership','typesof_ownership','savefile_raw_cache','assoc_list_construction']:
            spec=json.loads((ROOT/'tests'/suite/'source-manifest.json').read_text())
            for path,wanted in spec.get('expected_sources',spec.get('sources',{})).items():
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),wanted,(suite,path))
if __name__=='__main__':unittest.main()
