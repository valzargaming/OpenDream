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
def verify(case,source,trx,log):
    text=Path(log).read_text(encoding='utf-8-sig')
    if case!='reader-rejection':assert 'GAIA_CONTROL_CASE:'+case in text,'actual DM case marker missing'
    results=[x for x in ET.parse(trx).getroot().iter() if x.tag.endswith('UnitTestResult')]
    assert len(results)==1
    result=results[0]
    if case=='reader-rejection':
        assert result.attrib['testName']=='Content.IntegrationTests.GaiaSaveCostReaderControlTests.RejectWrongShardPayload'
        assert result.attrib['outcome']=='Passed' and 'GAIA_READER_REJECTION_COMPLETE' in text
    elif case in ['close','yield']:
        assert result.attrib['testName']==TEST and result.attrib['outcome']=='Passed'
        assert 'GAIA_SAVE_STOPPED_AUDIT ' in text
    else:
        assert result.attrib['testName']==TEST and result.attrib['outcome']=='Failed'
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
