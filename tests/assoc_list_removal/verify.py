"""Strict evidence classification for the dedicated, connected engine test."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
CLASS = 'Content.IntegrationTests.AssocListRemovalTests'
TEST = 'PairedOwnersRelease'
MARKER = 'ASSOC_REMOVE_COMPLETE: public API aliases, no-op/order, five compiled routes and final reference buckets'
SPEC = json.loads(Path(__file__).with_name('controls.json').read_text())
ERROR = re.compile(r'\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|exit)|Isolated DM fixture compilation failed', re.I)

def assertion_frames(failure):
    # NUnit may include per-assertion stacks in its aggregate Message. Admit only
    # our fixture's assertion chain and the observed integration thread chain.
    if '_DIRECT_' in failure['marker']:
        helper = 'AssocRemovalDirect(DreamObjectTree tree, DreamRefManager refs, Boolean list, String keyKind)'
    elif '_SELF_' in failure['marker']:
        helper = 'AssocRemovalSelf(DreamObjectTree tree, DreamRefManager refs, Boolean keyIsSelf)'
    else:
        helper = 'AssocRemovalCompiled(DreamManager manager, DreamObjectTree tree, DreamRefManager refs, DreamProc proc, Boolean list, String route)'
    frames = [
        re.escape(CLASS + '.' + helper),
        r'Content\.IntegrationTests\.AssocListRemovalTests\.<>c__DisplayClass\d+_\d+\.<AssocListRemovalReleasesOwners>b__\d+\(\)',
        r'NUnit\.Framework\.Assert\.Multiple\(TestDelegate testDelegate\)',
        re.escape(CLASS + '.AssocListRemovalReleasesOwners(DreamManager manager, DreamObjectTree tree, DreamRefManager refs)'),
        r'Content\.IntegrationTests\.AssocListRemovalTests\.<>c__DisplayClass\d+_\d+\.<PairedOwnersRelease>b__\d+\(\)',
        r'Robust\.UnitTesting\.RobustIntegrationTest\.IntegrationGameLoop\.SingleThreadRunUntilEmpty\(\)',
        r'Robust\.UnitTesting\.RobustIntegrationTest\.IntegrationGameLoop\.Run\(\)',
        r'Robust\.UnitTesting\.RobustIntegrationTest\.ServerIntegrationInstance\._serverMain\(\)',
        r'System\.Threading\.Thread\.StartHelper\.Callback\(Object state\)',
    ]
    files = ['Content.IntegrationTests/AssocListRemovalTests.cs'] * 2 + [None] + ['Content.IntegrationTests/AssocListRemovalTests.cs'] * 2 + ['RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'] * 3 + [None]
    return ''.join(r'\s+at ' + frame + (r' in [^\r\n]+/' + re.escape(file) + r':line \d+' if file else '') for frame, file in zip(frames, files))

def verify(path, mode, exit_code, log):
    assert mode in ('positive', 'baseline', 'omitted-release')
    assert log, 'original test log is required'
    outcome = 'Passed' if mode == 'positive' else 'Failed'
    summary = 'Test Run Successful.' if mode == 'positive' else 'Test Run Failed.'
    assert re.search(r'\b' + outcome + r' ' + TEST + r'(?:\s|\[)', log) and summary in log, 'original log does not identify the dedicated result'
    tree = ET.parse(path)
    rows = tree.findall('.//t:UnitTestResult', NS)
    counters = tree.find('.//t:ResultSummary/t:Counters', NS)
    assert len(rows) == 1 and counters is not None, 'missing or extra test results'
    row = rows[0]
    assert row.get('testName') == TEST
    definitions = tree.findall('.//t:TestDefinitions/t:UnitTest', NS)
    assert len(definitions) == 1 and definitions[0].get('id') == row.get('testId')
    method = definitions[0].find('t:TestMethod', NS)
    assert method is not None and method.get('className') == CLASS and method.get('name') == TEST
    assert counters.get('total') == counters.get('executed') == '1'
    for key in ('error', 'timeout', 'aborted', 'inconclusive', 'notRunnable', 'disconnected', 'warning'):
        assert int(counters.get(key, '0')) == 0, 'runner error counter'
    assert not tree.findall('.//t:RunInfo[@outcome="Error"]', NS)
    assert not ERROR.search(log + '\n' + '\n'.join(tree.getroot().itertext())), 'unrelated runtime/compile/runner failure'
    if mode == 'positive':
        assert exit_code == 0 and row.get('outcome') == 'Passed'
        assert counters.get('passed') == '1' and counters.get('failed') == '0'
        assert not tree.findall('.//t:ErrorInfo', NS)
        stdout = row.findtext('t:Output/t:StdOut', '', NS)
        assert stdout.count(MARKER) == 1, 'fixture completion missing or duplicated'
    else:
        assert exit_code == 1 and row.get('outcome') == 'Failed'
        assert counters.get('failed') == '1' and counters.get('passed') == '0'
        assert len(tree.findall('.//t:ErrorInfo', NS)) == 1
        message = row.findtext('t:Output/t:ErrorInfo/t:Message', '', NS)
        blocks = []
        failures = SPEC['baseline_failures' if mode == 'baseline' else 'omitted_value_failures']
        assert len(failures) == 18
        for number, failure in enumerate(failures, 1):
            blocks.append(r'\s*' + str(number) + r'\)\s*' + re.escape(failure['marker']) +
                          r'\s*Assert\.That\(' + failure['owner'] + r'\.RefCount, Is\.EqualTo\(1\)\)' +
                          r'\s*Expected:\s*1\s*But was:\s*' + str(failure['actual']) +
                          r'(?:' + assertion_frames(failure) + r')?')
        assert re.fullmatch(r'Multiple failures or warnings in test:' + ''.join(blocks) + r'\s*', message), 'not the exact eighteen ownership failures'
        stack = row.findtext('t:Output/t:ErrorInfo/t:StackTrace', '', NS)
        assert CLASS + '.AssocListRemovalReleasesOwners' in stack and 'Content.IntegrationTests/AssocListRemovalTests.cs' in stack, 'wrong fixture stack'
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('trx', type=Path)
    parser.add_argument('mode', choices=['positive', 'baseline', 'omitted-release'])
    parser.add_argument('exit_code', type=int)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    verify(args.trx, args.mode, args.exit_code, args.log.read_text())
    print('Strict dedicated associative removal TRX and original log accepted')
