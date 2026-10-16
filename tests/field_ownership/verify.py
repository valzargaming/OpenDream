import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import re
NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
MARKER = 'FIELD_OWNERSHIP_COMPLETE: 1000 setter and getter errors, valid/peek ownership, final buckets'
FAILURES = ('FIELD_WRITE_OWNER_ASSERT_1000', 'FIELD_READ_OWNER_ASSERT_1000', 'FIELD_PEEK_OWNER_ASSERT')
UNRELATED_ERROR = re.compile(r'\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|exit)', re.IGNORECASE)

def assertion_frames(index):
    # NUnit 4 includes each assertion's stack inside the aggregate Message.
    # Admit only the observed ownership fixture -> integration thread sequence.
    helper = ('FieldMissingOwners1000(DreamObjectTree tree, DreamRefManager refs, Boolean read)'
              if index < 3 else 'FieldSuccessAndPeekOwnership(DreamObjectTree tree, DreamRefManager refs)')
    frames = [
        re.escape('Content.IntegrationTests.GameTests.' + helper),
        r'Content\.IntegrationTests\.GameTests\.<>c__DisplayClass\d+_\d+\.<FieldReferencesReleaseOwners>b__\d+\(\)',
        re.escape('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)'),
        re.escape('Content.IntegrationTests.GameTests.FieldReferencesReleaseOwners(DreamObjectTree tree, DreamRefManager refs)'),
        r'Content\.IntegrationTests\.GameTests\.<>c__DisplayClass\d+_\d+\.<NoRuntimesTest>b__\d+\(\)',
        re.escape('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.SingleThreadRunUntilEmpty()'),
        re.escape('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.Run()'),
        re.escape('Robust.UnitTesting.RobustIntegrationTest.ServerIntegrationInstance._serverMain()'),
        re.escape('System.Threading.Thread.StartHelper.Callback(Object state)'),
    ]
    files = ['Content.IntegrationTests/GameTests.FieldOwnership.cs',
             'Content.IntegrationTests/GameTests.FieldOwnership.cs', None,
             'Content.IntegrationTests/GameTests.FieldOwnership.cs',
             'Content.IntegrationTests/GameTests.cs'] + ['RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'] * 3 + [None]
    return ''.join(r'\s+at ' + frame +
                   (r' in [^\r\n]+/' + re.escape(file) + r':line \d+' if file else '')
                   for frame, file in zip(frames, files))
def verify(path, mode, exit_code, log=''):
    tree = ET.parse(path)
    counters = tree.find('.//t:ResultSummary/t:Counters', NS)
    rows = tree.findall('.//t:UnitTestResult', NS)
    assert counters is not None and len(rows) == 1, 'missing or extra results'
    row = rows[0]
    assert row.get('testName') == 'NoRuntimesTest', 'wrong connected test'
    definitions = tree.findall('.//t:TestDefinitions/t:UnitTest', NS)
    assert len(definitions) == 1 and definitions[0].get('id') == row.get('testId'), 'wrong definition'
    method = definitions[0].find('t:TestMethod', NS)
    assert method is not None and method.get('className') == 'Content.IntegrationTests.GameTests' and method.get('name') == 'NoRuntimesTest'
    assert counters.get('total') == counters.get('executed') == '1', 'wrong counters'
    for key in ('error','timeout','aborted','inconclusive','notRunnable','disconnected'):
        assert int(counters.get(key, '0')) == 0, 'runner error'
    assert not tree.findall('.//t:RunInfo[@outcome="Error"]', NS), 'runner error info'
    assert not UNRELATED_ERROR.search(log+'\n'+'\n'.join(tree.getroot().itertext())), 'unrelated engine/runtime error'
    if mode == 'positive':
        assert exit_code == 0 and counters.get('passed') == '1' and counters.get('failed') == '0'
        assert row.get('outcome') == 'Passed'
        stdout = row.find('t:Output/t:StdOut', NS)
        assert stdout is not None and MARKER in (stdout.text or ''), 'fixture never completed'
        assert not tree.findall('.//t:ErrorInfo', NS), 'positive error info'
    else:
        assert mode in ('baseline', 'omitted-release') and exit_code != 0
        assert counters.get('failed') == '1' and counters.get('passed') == '0'
        message = row.find('t:Output/t:ErrorInfo/t:Message', NS)
        assert row.get('outcome') == 'Failed' and message is not None
        assert len(tree.findall('.//t:ErrorInfo', NS)) == 1
        # Admit only the three exact aggregate ownership assertions, without arbitrary extra failures.
        blocks = []
        for index, marker in enumerate(FAILURES, 1):
            constraint = r'Is\.EqualTo\(1\)' if index < 3 else r'Is\.EqualTo\(peek \? 2 : 1\)'
            actual = 1001 if index < 3 else 2
            blocks.append(r'\s*'+str(index)+r'\)\s*'+re.escape(marker)+r'\s*Assert\.That\(owner\.RefCount, '+constraint+r'\)\s*Expected:\s*1\s*But was:\s*'+str(actual) + r'(?:' + assertion_frames(index) + r')?')
        wanted = r'\AMultiple failures or warnings in test:'+''.join(blocks)+r'\s*\Z'
        assert re.fullmatch(wanted, message.text or ''), 'not exact intended ownership failures'
        stack = row.findtext('t:Output/t:ErrorInfo/t:StackTrace', '', NS)
        assert 'FieldReferencesReleaseOwners' in stack and 'GameTests.FieldOwnership.cs' in stack, 'wrong fixture stack'
    return True
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('trx', type=Path)
    p.add_argument('mode', choices=['positive','baseline','omitted-release'])
    p.add_argument('exit_code', type=int)
    p.add_argument('--log',type=Path)
    a = p.parse_args()
    verify(a.trx, a.mode, a.exit_code,a.log.read_text() if a.log else '')
    print('strict connected TRX verification passed')
