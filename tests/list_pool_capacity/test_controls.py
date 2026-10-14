import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from control import LIST, ROOT, mutate
from verify import CLASS, FAILURES, NS, TESTS, verify

def fixture(mode):
    tag=lambda value:'{'+NS['t']+'}'+value
    root=ET.Element(tag('TestRun'));results=ET.SubElement(root,tag('Results'));definitions=ET.SubElement(root,tag('TestDefinitions'))
    def text(parent,name,value):ET.SubElement(parent,tag(name)).text=value
    baseline=mode=='baseline'
    retained={'count':32 if baseline else 0,'slots':32*131072 if baseline else 0,'maximum':131072 if baseline else 0,
              'alive':32 if baseline else 0,'retired':32,'valueBytes':24,'backingPayloadBytes':32*131072*24 if baseline else 0}
    child={'count':0,'childAlive':False,'entries':[]} if mode=='no-pooling' else {'count':1,'childAlive':mode=='nonclearing','entries':[2 if mode=='nonclearing' else 0]}
    metrics=[]
    for size in [32,4096,65536,65537,131072,350000]:
        pooled=baseline and size>2048 or mode!='no-pooling' and 2048<size<=65536
        metrics.append({'size':size,'count':8,'allocated':100,'seconds':0.1,'collections':[0,0,0],'poolCount':int(pooled),'slots':size if pooled else 0,'valueBytes':24})
    mixed={'beforeMedium':350000,'afterMedium':350000,'poolCount':1} if baseline else {'beforeMedium':0,'afterMedium':0 if mode=='no-pooling' else 4096,'poolCount':0 if mode=='no-pooling' else 1}
    stdout={'RetiredCapacityAndWeakRelease':'POOL_RETENTION '+json.dumps(retained),
            'SemanticsReferencesAndMediumReuse':'POOL_CHILD '+json.dumps(child),
            'ComparableWorkloads':'\n'.join('POOL_METRIC '+json.dumps(row) for row in metrics)+'\nPOOL_MIXED '+json.dumps(mixed)}
    for name in sorted(TESTS):
        failed=name in FAILURES[mode]
        row=ET.SubElement(results,tag('UnitTestResult'),{'testName':name,'outcome':'Failed' if failed else 'Passed'})
        output=ET.SubElement(row,tag('Output'));text(output,'StdOut',stdout[name])
        if failed:
            error=ET.SubElement(output,tag('ErrorInfo'))
            text(error,'Message',FAILURES[mode][name]+' Assert.That(value, constraint) Expected: expected But was: actual')
            text(error,'StackTrace',CLASS+'.'+name+'()')
        unit=ET.SubElement(definitions,tag('UnitTest'));ET.SubElement(unit,tag('TestMethod'),{'className':CLASS})
    return ET.tostring(root,encoding='unicode'),('Test Run Failed.' if FAILURES[mode] else 'Test Run Successful.'),int(bool(FAILURES[mode]))

class Controls(unittest.TestCase):
    def test_positive_identical(self):
        self.assertEqual(mutate(b'arbitrary','positive'),b'arbitrary')
    def test_nonclearing_exact_and_guards(self):
        needle=b'            _values.Clear();'
        changed=mutate(b'before\n'+needle+b'\nafter','nonclearing')
        self.assertNotIn(b'_values.Clear();',changed)
        for raw in (b'missing',needle*2):
            with self.assertRaises(AssertionError):mutate(raw,'nonclearing')
    def test_no_pooling_exact_and_guards(self):
        needle=b'ListPool.Count < DreamManager.ListPoolSize'
        self.assertIn(b'ListPool.Count < 0',mutate(needle,'no-pooling'))
        for raw in (b'missing',needle*2):
            with self.assertRaises(AssertionError):mutate(raw,'no-pooling')
    def test_production_bound_is_return_only(self):
        raw=(ROOT/LIST).read_bytes()
        self.assertEqual(raw.count(b'private const int MaximumPooledCapacity = 65_536;'),1)
        self.assertEqual(raw.count(b'_values.Capacity <= MaximumPooledCapacity'),1)
        self.assertIn(b'if (size >= DreamManager.ListPoolThreshold && ListPool.TryPop',raw)
    def test_all_classifications(self):
        with tempfile.TemporaryDirectory() as temp:
            for mode in FAILURES:verify(*fixture(mode)[:2],mode,fixture(mode)[2],Path(temp))
    def test_fault_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            for mode in FAILURES:
                trx,log,code=fixture(mode)
                for fault in ['[ERRO] fixture fault','Unhandled exception','error CS0123','runtime error']:
                    with self.assertRaises(AssertionError):verify(trx,log+'\n'+fault,mode,code,Path(temp))
                with self.assertRaises(AssertionError):verify(trx,log,mode,2,Path(temp))
    def test_metrics_and_class_drift_rejected(self):
        trx,log,code=fixture('positive')
        with tempfile.TemporaryDirectory() as temp:
            for drift in [trx.replace(CLASS,CLASS+'Other'),trx.replace('"retired": 32','"retired": 31'),trx.replace('"slots": 65536','"slots": 99999')]:
                with self.assertRaises(AssertionError):verify(drift,log,'positive',code,Path(temp))

if __name__=='__main__':unittest.main()
