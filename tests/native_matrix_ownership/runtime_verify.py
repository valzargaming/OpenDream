"""Reject missing/unrelated TRX results; baseline must fail only both memory markers."""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET
NS={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
CLASS='Content.IntegrationTests.StringFormatDecoderTests'
CONTENT={'AllUtf16CodeUnitsPreserveContent','SeededRandomContentMatchesOracle','RealSavefileTreeOutputMatchesByteOracle','RealResourcePreservesPathsCacheAndAppendFailure'}
FAILURES={
 'NoFormattingAvoidsCopy':r'DECODER_FASTPATH_ALLOCATION: expected <=4096 bytes; observed ([0-9]+)',
 'LargeFormattedInputIsNotRetained':r'DECODER_RETAINED_CAPACITY: expected <=4194304 bytes; observed ([0-9]+)'}
UNRELATED=re.compile(r'\[ERRO\]|Unhandled exception|test run aborted|testhost.*(?:crash|exit)|OutOfMemoryException|runtime error',re.I)

def verify(path, mode, exit_code, log=''):
    root=ET.parse(path).getroot()
    rows=root.findall('.//t:UnitTestResult',NS)
    wanted=CONTENT|set(FAILURES)|( {'ConcurrentCallsPreserveContent'} if mode=='positive' else set())
    assert mode in ('positive','baseline')
    assert len(rows)==len(wanted) and {r.get('testName') for r in rows}==wanted, 'missing/extra/duplicate tests'
    counters=root.find('.//t:ResultSummary/t:Counters',NS)
    assert counters is not None and counters.get('total')==counters.get('executed')==str(len(wanted))
    for key in ('error','timeout','aborted','inconclusive','notRunnable','disconnected','warning'):
        assert int(counters.get(key,'0'))==0, 'runner error'
    assert not root.findall('.//t:RunInfo[@outcome="Error"]',NS)
    assert not UNRELATED.search(log+'\n'+'\n'.join(root.itertext())), 'unrelated failure'
    definitions=root.findall('.//t:TestDefinitions/t:UnitTest',NS)
    assert len(definitions)==len(wanted)
    by_id={d.get('id'):d.find('t:TestMethod',NS) for d in definitions}
    assert len(by_id)==len(wanted)
    for row in rows:
        name=row.get('testName')
        method=by_id.get(row.get('testId'))
        assert method is not None and method.get('className')==CLASS and method.get('name')==name
        errors=row.findall('t:Output/t:ErrorInfo',NS)
        if mode=='baseline' and name in FAILURES:
            assert row.get('outcome')=='Failed' and len(errors)==1
            message=errors[0].findtext('t:Message','',NS).strip()
            match=re.fullmatch(FAILURES[name],message)
            assert match, 'wrong intended failure marker/message'
            assert int(match.group(1))>(4096 if name=='NoFormattingAvoidsCopy' else 4194304)
            stack=errors[0].findtext('t:StackTrace','',NS)
            assert CLASS+'.'+name+'()' in stack and 'StringFormatDecoderTests.cs' in stack
            # Every frame must be this fixture or NUnit assertion infrastructure.
            frames=re.findall(r'^\s*at ([^\r\n]+)',stack,re.M)
            assert frames and all(f.startswith((CLASS+'.'+name+'()', 'NUnit.Framework.')) for f in frames), 'foreign failure stack'
        else:
            assert row.get('outcome')=='Passed' and not errors
    expected_failed=0 if mode=='positive' else 2
    assert counters.get('failed')==str(expected_failed) and counters.get('passed')==str(len(wanted)-expected_failed)
    assert (exit_code==0) == (mode=='positive')
    assert len(root.findall('.//t:ErrorInfo',NS))==expected_failed
    return True

def verify_runtime(path, exit_code, log=''):
    root=ET.parse(path).getroot()
    rows=root.findall('.//t:UnitTestResult',NS)
    definitions=root.findall('.//t:TestDefinitions/t:UnitTest',NS)
    counters=root.find('.//t:ResultSummary/t:Counters',NS)
    assert exit_code==0 and len(rows)==len(definitions)==1
    row=rows[0]; definition=definitions[0]; method=definition.find('t:TestMethod',NS)
    assert row.get('testName')=='NoRuntimesTest' and row.get('outcome')=='Passed'
    assert definition.get('id')==row.get('testId')
    assert method is not None and method.get('className')=='Content.IntegrationTests.GameTests' and method.get('name')=='NoRuntimesTest'
    assert counters is not None and counters.get('total')==counters.get('executed')==counters.get('passed')=='1' and counters.get('failed')=='0'
    assert all(int(counters.get(key,'0'))==0 for key in ('error','timeout','aborted','inconclusive','notRunnable','disconnected','warning'))
    assert not root.findall('.//t:ErrorInfo',NS) and not root.findall('.//t:RunInfo[@outcome="Error"]',NS)
    combined=log+'\n'+'\n'.join(root.itertext())
    assert not UNRELATED.search(combined)
    assert 'Savefile cleanup: 200 native failed/uninitialized disposals and shared-file preservation passed' in combined, 'savefile runtime fixture did not complete'
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('trx',type=Path); p.add_argument('mode',choices=['positive','baseline']); p.add_argument('exit_code',type=int)
    p.add_argument('--log',type=Path)
    p.add_argument('--runtime',action='store_true')
    a=p.parse_args(); (verify_runtime if a.runtime else lambda path,code,log:verify(path,a.mode,code,log))(a.trx,a.exit_code,a.log.read_text() if a.log else '')
    print('strict decoder TRX verification passed')
