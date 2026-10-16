"""Pure source/receipt/TRX tests; no engine or build execution."""
import copy,hashlib,pathlib,tempfile,unittest,xml.etree.ElementTree as ET
from control import OPTIONS,FIXTURE_HASHES,CANDIDATE_HASH,BASELINE_HASH,PRODUCTION,mutation,receipt,check_receipt,verify,verify_positive,frozen_candidate,compose_pool_cap,CAP_DECL,CAP_GUARD
ROOT=pathlib.Path(__file__).resolve().parents[2]
NS='http://microsoft.com/schemas/VisualStudio/TeamTest/2010'
tag=lambda n:'{'+NS+'}'+n
def document(option,positive=False):
 root=ET.Element(tag('TestRun'));r=ET.SubElement(ET.SubElement(root,tag('Results')),tag('UnitTestResult'),testName='NoRuntimesTest',outcome='Passed' if positive else 'Failed',testId='fixture')
 if not positive:
  e=ET.SubElement(ET.SubElement(r,tag('Output')),tag('ErrorInfo'));o=OPTIONS[option]
  ET.SubElement(e,tag('Message')).text=f"{o['marker']}\nAssert.That(payload.RefCount, Is.EqualTo({o['expected']}))\nExpected: {o['expected']}\nBut was: {o['actual']}"
  ET.SubElement(e,tag('StackTrace')).text='NumericListAssignmentsReleaseOwners in GameTests.NumericLists.cs:line25'
 d=ET.SubElement(ET.SubElement(root,tag('TestDefinitions')),tag('UnitTest'),id='fixture');ET.SubElement(d,tag('TestMethod'),className='Content.IntegrationTests.GameTests',name='NoRuntimesTest')
 ET.SubElement(ET.SubElement(root,tag('ResultSummary')),tag('Counters'),total='1',executed='1',passed='1' if positive else '0',failed='0' if positive else '1')
 return root
class Tests(unittest.TestCase):
 def test_actual_candidate_baseline_and_omission_exact(self):
  source=(ROOT/PRODUCTION).read_bytes()
  fixed=b'''            if (allowGrowth && keyInteger == _values.Count + 1) {
                value.IncRef();
                _values.Add(value);
            } else {
                // Validate the index before acquiring an incoming owner. Keep acquisition
                // before release so a sole list-owned value survives self-replacement.
                var oldValue = _values[keyInteger - 1];
                value.IncRef();
                oldValue.DecRef();
                _values[keyInteger - 1] = value;
            }'''
  original=b'''            value.IncRef();

            if (allowGrowth && keyInteger == _values.Count + 1) {
                _values.Add(value);
            } else {
                _values[keyInteger - 1].DecRef();
                _values[keyInteger - 1] = value;
            }'''
  self.assertEqual(source.count(fixed),1);baseline=source.replace(fixed,original,1)
  self.assertEqual(hashlib.sha256(frozen_candidate(source)).hexdigest(),CANDIDATE_HASH);baseline=frozen_candidate(source).replace(fixed,original,1);self.assertEqual(hashlib.sha256(baseline).hexdigest(),BASELINE_HASH)
  for option in ['positive',*OPTIONS]:
   changed=mutation(source,option,baseline);data=receipt(option,'a'*40,source,changed,FIXTURE_HASHES)
   self.assertTrue(check_receipt(data,option,changed,FIXTURE_HASHES,changed))
   if option=='baseline':self.assertEqual(changed,compose_pool_cap(baseline))
   if option=='replace-acquire-omit':self.assertNotEqual(changed,baseline)
   for key in ['control','baseline_commit','baseline_git_blob','reviewed_candidate_sha256','frozen_candidate_sha256','pool_cap_composition_sha256','mutated_sha256','actual_checkout_head','fixture_sha256','expected_assertion']:
    bad=copy.deepcopy(data);bad[key]='wrong'
    with self.assertRaises(ValueError):check_receipt(bad,option,changed,FIXTURE_HASHES,changed)
  for changed in [source+b'changed',source.replace(b'65_536',b'65_537'),source.replace(CAP_DECL,b''),source.replace(CAP_GUARD,b'wrong')]:
   with self.assertRaises(ValueError):mutation(changed,'baseline',baseline)
  with self.assertRaises(ValueError):mutation(source,'baseline',b'wrong')
 def test_exact_fixture_bindings_and_validation_order(self):
  for p,h in FIXTURE_HASHES.items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h)
  source=(ROOT/PRODUCTION).read_text();needle='var oldValue = _values[keyInteger - 1];\n                value.IncRef();\n                oldValue.DecRef();'
  self.assertEqual(source.count(needle),1)
  fixture=(ROOT/'Content.IntegrationTests/GameTests.NumericLists.cs').read_text()
  for snippet in ['iteration < 1000','new[] { 0, -1, 3 }','new[] { false, true }','sole.DecRef();','refs.LocateRef(id)','RefType.DreamObjectList','Numeric replacement retains incoming owner']:
   self.assertIn(snippet,fixture)
  hook=(ROOT/'Content.IntegrationTests/GameTests.cs').read_text();self.assertEqual(hook.count('NumericListAssignmentsReleaseOwners('),1)
 def test_strict_negative_shapes(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'synthetic.trx'
   for option in OPTIONS:
    ET.ElementTree(document(option)).write(p);self.assertTrue(verify(option,p,'',1))
    for log,code in [('[ERRO] unrelated',1),('',0),('',2)]:
     with self.assertRaises(ValueError):verify(option,p,log,code)
 def test_wrong_assertion_stack_and_extra_errors_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'synthetic.trx'
   for option in OPTIONS:
    for kind in ['expression','marker','actual','stack','extra']:
     root=document(option);e=root.find('.//'+tag('ErrorInfo'))
     if kind=='stack':e.find(tag('StackTrace')).text='Other in Other.cs'
     elif kind=='extra':ET.SubElement(root,tag('ErrorInfo'))
     else:
      t=e.find(tag('Message'));t.text=t.text.replace('payload.RefCount','other.RefCount') if kind=='expression' else ('wrong marker' if kind=='marker' else t.text.replace('But was: '+str(OPTIONS[option]['actual']),'But was: 999'))
     ET.ElementTree(root).write(p)
     with self.assertRaises(ValueError):verify(option,p,'',1)
 def test_positive_marker_and_structured_outcome_required(self):
  marker='Numeric list ownership: 1000 invalid-index and replacement iterations plus append/sole-owner self-assignment passed'
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'synthetic.trx';root=document('baseline',True);ET.ElementTree(root).write(p)
   self.assertTrue(verify_positive(p,marker,0))
   for log,code in [('',0),(marker+'[ERRO] other',0),(marker,1)]:
    with self.assertRaises(ValueError):verify_positive(p,log,code)
   root.find('.//'+tag('Counters')).set('failed','1');ET.ElementTree(root).write(p)
   with self.assertRaises(ValueError):verify_positive(p,marker,0)
if __name__=='__main__':unittest.main()
