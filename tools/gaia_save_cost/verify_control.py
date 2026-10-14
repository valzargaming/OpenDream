"""Classify expected small compiled fixture outcomes after root execution.
No native launches. Wrong assertion/boot/timeout failure is not a control pass.
"""
import argparse,json,xml.etree.ElementTree as ET
from pathlib import Path
TEST='Content.IntegrationTests.GaiaSaveCostHostTests.FullGaiaSaveWindow'
NEEDLES={
 'return-failure':'Assert.That(saved.MustGetValueAsFloat(), Is.EqualTo(1)',
 'missing-shard':'Assert.That(File.Exists(shardPaths[i]), Is.True)',
 'late-write':'Assert.That(shardPaths.Select(DiskSha).ToArray(), Is.EqualTo(sealedHashes)',
 'cap':'Assert.That(snapshot.GetProperty("capExcluded").GetInt64(), Is.Zero)',
}

def result_for_test(trx,expected):
    root=ET.parse(trx).getroot()
    elements=lambda name:[x for x in root.iter() if x.tag.split('}')[-1]==name]
    results=elements('UnitTestResult');definitions=elements('UnitTest')
    assert len(results)==len(definitions)==1,'exactly one actual test result and definition required'
    result,definition=results[0],definitions[0]
    assert result.attrib.get('testId') and result.attrib['testId']==definition.attrib.get('id'),'TRX definition ID mismatch'
    methods=[x for x in definition if x.tag.split('}')[-1]=='TestMethod']
    assert len(methods)==1
    method=methods[0]
    assert method.attrib.get('className','')+'.'+method.attrib.get('name','')==expected,'wrong TRX class or method'
    assert result.attrib.get('testName')==method.attrib['name'],'wrong TRX result name'
    assert method.attrib.get('adapterTypeName')=='executor://nunit3testexecutor/'
    return result
def verify(case,source,trx,log):
    text=Path(log).read_text(encoding='utf-8-sig')
    if case!='reader-rejection':assert 'GAIA_CONTROL_CASE:'+case in text,'actual DM case marker missing'
    expected=TEST if case!='reader-rejection' else 'Content.IntegrationTests.GaiaSaveCostReaderControlTests.RejectWrongShardPayload'
    result=result_for_test(trx,expected)
    if case=='reader-rejection':
        assert result.attrib['outcome']=='Passed' and 'GAIA_READER_REJECTION_COMPLETE' in text
    elif case in ['close','yield']:
        assert result.attrib['outcome']=='Passed'
        assert 'GAIA_SAVE_STOPPED_AUDIT ' in text
    else:
        assert result.attrib['outcome']=='Failed'
        lines=Path(source).read_text().splitlines()
        selected=[i+1 for i,x in enumerate(lines) if NEEDLES[case] in x]
        assert len(selected)==1
        stack='\n'.join(x.text or '' for x in result.iter() if x.tag.endswith('StackTrace'))
        assert 'GaiaSaveCostHostTests.cs:line '+str(selected[0]) in stack,'negative failed outside intended assertion'
        assert 'GAIA_SAVE_PARTIAL ' in text,'managed failure partial snapshot must survive'
    return dict(case=case,native_control_result_classified=True,scope='small compiled seam only; no full Gaia acceptance')
def main():
    p=argparse.ArgumentParser()
    for key in ['case','source','trx','log','receipt']:p.add_argument('--'+key,required=True)
    a=p.parse_args()
    with Path(a.receipt).open('x') as out:json.dump(verify(a.case,a.source,a.trx,a.log),out,indent=2);out.write('\n')
if __name__=='__main__':main()
