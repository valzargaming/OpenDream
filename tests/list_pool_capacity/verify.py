"""Reject faults and classify only exact named native assertions."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
CLASS='Content.IntegrationTests.ListPoolCapacityTests'
TESTS={'RetiredCapacityAndWeakRelease','SemanticsReferencesAndMediumReuse','ComparableWorkloads'}
FAILURES={'positive':{}, 'baseline':{'RetiredCapacityAndWeakRelease':'POOL_CAPACITY_BOUND'},
          'nonclearing':{'SemanticsReferencesAndMediumReuse':'POOL_CLEAR_AND_RELEASE'},
          'no-pooling':{'RetiredCapacityAndWeakRelease':'POOL_CAPACITY_BOUND boundary', 'SemanticsReferencesAndMediumReuse':'POOL_MEDIUM_REUSE'}}

def load_outputs(directory, mode):
    # Combine only in memory. The three raw TRX/logs remain original artifacts.
    combined=ET.Element('{'+NS['t']+'}TestRun')
    logs=[]
    for name in sorted(TESTS):
        root=ET.fromstring((directory/('pool-'+name+'.trx')).read_text(encoding='utf-8-sig'))
        rows=root.findall('.//t:UnitTestResult',NS)
        assert len(rows)==1 and rows[0].attrib['testName']==name
        definitions=root.findall('.//t:UnitTest/t:TestMethod',NS)
        assert len(definitions)==1 and definitions[0].attrib['className']==CLASS
        assert int((directory/('pool-'+name+'-exit-code.txt')).read_text())==int(name in FAILURES[mode])
        combined.append(root)
        log=(directory/('pool-'+name+'.log')).read_text()
        assert ('Test Run Failed.' if name in FAILURES[mode] else 'Test Run Successful.') in log
        logs.append(log)
    return ET.tostring(combined,encoding='unicode'),'\n'.join(logs),int(bool(FAILURES[mode]))

def verify(trx, log, mode, exit_code, output):
    assert not re.search(r'\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|exit)|error (?:CS|MSB|NU)\d+',log,re.I)
    tree=ET.fromstring(trx);rows=tree.findall('.//t:UnitTestResult',NS)
    assert len(rows)==3 and {row.attrib['testName'] for row in rows}==TESTS
    definitions=tree.findall('.//t:UnitTest/t:TestMethod',NS)
    assert len(definitions)==3 and all(row.attrib['className']==CLASS for row in definitions)
    failures=FAILURES[mode]
    assert exit_code==(1 if failures else 0)
    assert ('Test Run Failed.' if failures else 'Test Run Successful.') in log
    assert len(tree.findall('.//t:ErrorInfo',NS))==len(failures)
    for row in rows:
        name=row.attrib['testName'];failed=name in failures
        assert row.attrib['outcome']==('Failed' if failed else 'Passed')
        if failed:
            message=row.findtext('t:Output/t:ErrorInfo/t:Message','',NS)
            stack=row.findtext('t:Output/t:ErrorInfo/t:StackTrace','',NS)
            assert failures[name] in message and 'Assert.That(' in message and 'Expected:' in message and 'But was:' in message
            assert CLASS in stack and name in stack
            assert not re.search(r'Exception|timeout|Multiple failures',message,re.I)
    def data(name, marker):
        row=next(row for row in rows if row.attrib['testName']==name)
        return [json.loads(value) for value in re.findall(marker+r' (\{[^\r\n]+\})', row.findtext('t:Output/t:StdOut','',NS))]
    retention=data('RetiredCapacityAndWeakRelease','POOL_RETENTION')
    assert len(retention)==1
    retained=retention[0]
    assert retained['retired']==32 and retained['valueBytes']>0
    assert retained['backingPayloadBytes']==retained['slots']*retained['valueBytes']
    assert (retained['count'],retained['slots'],retained['maximum'],retained['alive']) == ((32,32*131072,131072,32) if mode=='baseline' else (0,0,0,0))
    child=data('SemanticsReferencesAndMediumReuse','POOL_CHILD')
    assert len(child)==1
    assert child[0]==({'count':0,'childAlive':False,'entries':[]} if mode=='no-pooling' else
                      {'count':1,'childAlive':True,'entries':[2]} if mode=='nonclearing' else
                      {'count':1,'childAlive':False,'entries':[0]})
    metrics=data('ComparableWorkloads','POOL_METRIC')
    assert [row['size'] for row in metrics]==[32,4096,65536,65537,131072,350000]
    assert all(row['count']==8 and row['allocated']>0 and row['seconds']>=0 and len(row['collections'])==3 and row['valueBytes']==retained['valueBytes'] for row in metrics)
    for row in metrics:
        expected=1 if mode=='baseline' and row['size']>2048 or mode!='no-pooling' and 2048<row['size']<=65536 else 0
        assert row['poolCount']==expected and row['slots']==(row['size'] if expected else 0)
    mixed=data('ComparableWorkloads','POOL_MIXED')
    assert mixed==([{'beforeMedium':350000,'afterMedium':350000,'poolCount':1}] if mode=='baseline' else
                   [{'beforeMedium':0,'afterMedium':0,'poolCount':0}] if mode=='no-pooling' else
                   [{'beforeMedium':0,'afterMedium':4096,'poolCount':1}])
    output.mkdir(parents=True,exist_ok=True)
    (output/'verified-metrics.json').write_text(json.dumps({'mode':mode,'retention':retained,'child':child[0],'metrics':metrics,'mixed':mixed[0],'expected_failures':failures},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input',type=Path);parser.add_argument('mode');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    trx,log,code=load_outputs(args.input,args.mode)
    verify(trx,log,args.mode,code,args.output or args.input)
