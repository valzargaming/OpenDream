"""Require exact public/compiled clock evidence; unrelated failure never passes."""
import argparse
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
CLASS = 'Content.IntegrationTests.WorldRealtimeClockTests'
TEST = 'UtcEpochDeciseconds'
MARKER = 'WORLD_REALTIME_COMPLETE: public and compiled UTC epoch bounds with float precision'
ERROR = re.compile(r'\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|exit)|Isolated clock DM fixture compilation failed', re.I)
NUMBER = r'[-+\d.eE]+'
SMOKE_MARKER = 'TIMEOFDAY_SMOKE_COMPLETE: public and compiled UTC day-clock advancement'

def verify_smoke(stdout):
    fields = ('before', 'beforeLower', 'beforeUpper', 'after', 'afterLower', 'afterUpper',
              'advance', 'elapsedLower', 'elapsedUpper', 'stopwatch', 'utc')
    pattern = r'^TIMEOFDAY_SMOKE_(PUBLIC|COMPILED)' + ''.join(' '+field+'=('+NUMBER+')' for field in fields) + '$'
    rows = re.findall(pattern, stdout, re.M)
    assert [row[0] for row in rows] == ['PUBLIC', 'COMPILED']
    assert stdout.count('TIMEOFDAY_SMOKE_PUBLIC') == stdout.count('TIMEOFDAY_SMOKE_COMPILED') == 1
    assert stdout.count(SMOKE_MARKER) == 1
    assert stdout.index('TIMEOFDAY_SMOKE_PUBLIC') < stdout.index('TIMEOFDAY_SMOKE_COMPILED') < stdout.index(SMOKE_MARKER) < stdout.index('REALTIME_SAMPLE_PUBLIC')
    prior_host = None
    def bracket(value, lower, upper):
        return lower <= value <= upper if lower <= upper else value >= lower or value <= upper
    for row in rows:
        values = dict(zip(fields, map(float, row[1:])))
        assert all(map(math.isfinite, values.values()))
        for field in fields[:6]: assert values[field].is_integer() and 0 <= values[field] < 864000
        assert bracket(values['before'], values['beforeLower'], values['beforeUpper'])
        assert bracket(values['after'], values['afterLower'], values['afterUpper'])
        watch, utc = values['stopwatch'], values['utc']
        assert 11.5 <= watch < 864000 and 11.5 <= utc < 864000 and abs(watch-utc) <= 5
        host = (watch, utc)
        assert prior_host is None or host == prior_host
        prior_host = host
        assert abs(values['elapsedLower']-max(10,min(watch,utc)-5)) < 1e-6
        assert abs(values['elapsedUpper']-(max(watch,utc)+5)) < 1e-6
        advance = (values['after']-values['before']) % 864000
        assert values['advance'] == advance
        assert values['elapsedLower'] <= advance <= values['elapsedUpper'], 'frozen or component timeofday smoke'

def frames():
    names = [r'Content\.IntegrationTests\.WorldRealtimeClockTests\.AssertRealtimeSample\(String route, Func[^\r\n]* getter\)',
             r'Content\.IntegrationTests\.WorldRealtimeClockTests\.<>c__DisplayClass\d+_\d+\.<UtcEpochDeciseconds>b__\d+\(\)',
             r'NUnit\.Framework\.Assert\.Multiple\(TestDelegate testDelegate\)',
             r'Content\.IntegrationTests\.WorldRealtimeClockTests\.<>c__DisplayClass\d+_\d+\.<UtcEpochDeciseconds>b__\d+\(\)',
             r'Robust\.UnitTesting\.RobustIntegrationTest\.IntegrationGameLoop\.SingleThreadRunUntilEmpty\(\)',
             r'Robust\.UnitTesting\.RobustIntegrationTest\.IntegrationGameLoop\.Run\(\)',
             r'Robust\.UnitTesting\.RobustIntegrationTest\.ServerIntegrationInstance\._serverMain\(\)',
             r'System\.Threading\.Thread\.StartHelper\.Callback\(Object state\)']
    files = ['Content.IntegrationTests/WorldRealtimeClockTests.cs'] * 2 + [None, 'Content.IntegrationTests/WorldRealtimeClockTests.cs'] + ['RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'] * 3 + [None]
    return ''.join(r'\s+at ' + name + (r' in [^\r\n]+/' + re.escape(file) + r':line \d+' if file else '') for name, file in zip(names, files))

def verify(path, mode, exit_code, log):
    assert mode in ('positive', 'baseline') and log
    outcome = 'Passed' if mode == 'positive' else 'Failed'
    summary = 'Test Run Successful.' if mode == 'positive' else 'Test Run Failed.'
    assert re.search(r'\b' + outcome + ' ' + TEST + r'(?:\s|\[)', log) and summary in log
    tree = ET.parse(path)
    rows = tree.findall('.//t:UnitTestResult', NS)
    definitions = tree.findall('.//t:TestDefinitions/t:UnitTest', NS)
    counters = tree.find('.//t:ResultSummary/t:Counters', NS)
    assert len(rows) == len(definitions) == 1 and counters is not None
    row = rows[0]
    assert row.get('testName') == TEST and definitions[0].get('id') == row.get('testId')
    method = definitions[0].find('t:TestMethod', NS)
    assert method is not None and method.get('className') == CLASS and method.get('name') == TEST
    assert counters.get('total') == counters.get('executed') == '1'
    for key in ('error', 'timeout', 'aborted', 'inconclusive', 'notRunnable', 'disconnected', 'warning'):
        assert int(counters.get(key, '0')) == 0
    assert not tree.findall('.//t:RunInfo[@outcome="Error"]', NS)
    assert not ERROR.search(log + '\n' + '\n'.join(tree.getroot().itertext()))
    stdout = row.findtext('t:Output/t:StdOut', '', NS)
    verify_smoke(stdout)
    pattern = r'^REALTIME_SAMPLE_(PUBLIC|COMPILED) actual=(' + NUMBER + r') lower=(' + NUMBER + r') upper=(' + NUMBER + r')$'
    samples = re.findall(pattern, stdout, re.M)
    assert [sample[0] for sample in samples] == ['PUBLIC', 'COMPILED'], 'missing, extra or reordered clock samples'
    assert stdout.count('REALTIME_SAMPLE_') == 2
    for route, actual, lower, upper in samples:
        actual, lower, upper = map(float, (actual, lower, upper))
        assert all(map(math.isfinite, (actual, lower, upper))) and 1e9 < lower <= upper
        if mode == 'positive': assert lower <= actual <= upper
        else: assert 0 <= actual <= 9 and actual.is_integer(), 'baseline not the immutable millisecond component result'
    if mode == 'positive':
        assert exit_code == 0 and row.get('outcome') == 'Passed'
        assert counters.get('passed') == '1' and counters.get('failed') == '0'
        assert stdout.count(MARKER) == 1 and not tree.findall('.//t:ErrorInfo', NS)
    else:
        assert exit_code == 1 and row.get('outcome') == 'Failed'
        assert counters.get('failed') == '1' and counters.get('passed') == '0'
        assert MARKER not in stdout and len(tree.findall('.//t:ErrorInfo', NS)) == 1
        blocks = []
        for index, (route, kind, variable) in enumerate([
                ('PUBLIC', 'EPOCH_MAGNITUDE', 'largeEpoch'), ('PUBLIC', 'UTC_BRACKET', 'inBracket'),
                ('COMPILED', 'EPOCH_MAGNITUDE', 'largeEpoch'), ('COMPILED', 'UTC_BRACKET', 'inBracket')], 1):
            blocks.append(r'\s*' + str(index) + r'\)\s*REALTIME_' + route + '_' + kind +
                          r'\s*Assert\.That\(' + variable + r', Is\.True\)\s*Expected:\s*True\s*But was:\s*False(?:' + frames() + r')?')
        message = row.findtext('t:Output/t:ErrorInfo/t:Message', '', NS)
        assert re.fullmatch(r'Multiple failures or warnings in test:' + ''.join(blocks) + r'\s*', message), 'not exactly the four epoch/component failures'
        stack = row.findtext('t:Output/t:ErrorInfo/t:StackTrace', '', NS)
        assert CLASS in stack and 'Content.IntegrationTests/WorldRealtimeClockTests.cs' in stack
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('trx', type=Path)
    parser.add_argument('mode', choices=['positive', 'baseline'])
    parser.add_argument('exit_code', type=int)
    parser.add_argument('--log', required=True, type=Path)
    args = parser.parse_args()
    verify(args.trx, args.mode, args.exit_code, args.log.read_text())
    print('Strict world.realtime dedicated TRX and original log accepted')
