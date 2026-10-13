"""Accept only one intended NUnit ownership assertion, not coincident failures."""
import re
import xml.etree.ElementTree as ET

NS = {'t': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
UNRELATED_ERROR = re.compile(r'\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|exit)', re.I)


def verify(trx_path, log, exit_code, marker, *, expressions=('payload.RefCount', 'original.RefCount'), expected=1, actual=2, fixture_method='NativeArgumentsReleaseOwnedValues', fixture_file='GameTests.NativeArguments.cs'):
    if exit_code != 1:
        raise ValueError('Expected test assertion exit1')
    root = ET.parse(trx_path).getroot()
    results = root.findall('t:Results/t:UnitTestResult', NS)
    if len(results) != 1:
        raise ValueError('Expected exactly one test result')
    result = results[0]
    if result.get('testName') != 'NoRuntimesTest' or result.get('outcome') != 'Failed':
        raise ValueError('Unexpected failing test')
    definitions = root.findall('t:TestDefinitions/t:UnitTest', NS)
    if len(definitions) != 1 or definitions[0].get('id') != result.get('testId'):
        raise ValueError('Unexpected test definition')
    method = definitions[0].find('t:TestMethod', NS)
    if method is None or method.get('className') != 'Content.IntegrationTests.GameTests' or method.get('name') != 'NoRuntimesTest':
        raise ValueError('Unexpected failing test method')
    counters = root.find('t:ResultSummary/t:Counters', NS)
    if counters is None:
        raise ValueError('Missing result counters')
    for field, counter_expected in {'total': 1, 'executed': 1, 'passed': 0, 'failed': 1}.items():
        if int(counters.get(field, '-1')) != counter_expected:
            raise ValueError('Unexpected test counters')
    for field in ('error', 'timeout', 'aborted', 'inconclusive', 'notRunnable', 'disconnected'):
        if int(counters.get(field, '0')) != 0:
            raise ValueError('Additional test runner error')
    if root.findall('t:ResultSummary/t:RunInfos/t:RunInfo[@outcome="Error"]', NS):
        raise ValueError('Additional test runner error info')
    errors = root.findall('.//t:ErrorInfo', NS)
    if len(errors) != 1:
        raise ValueError('Expected exactly one assertion error')
    message = errors[0].findtext('t:Message', default='', namespaces=NS).strip()
    # NUnit may wrap the single assertion copied from the owning game thread.
    message = re.sub(r'\AMultiple failures or warnings in test:\s*1\)\s*', '', message)
    stack = errors[0].findtext('t:StackTrace', default='', namespaces=NS)
    # Require the entire assertion shape, so a coincident message fragment is not enough.
    expression = '(?:' + '|'.join(re.escape(item) for item in expressions) + ')'
    wanted = r'\A' + re.escape(marker) + r'\s*Assert\.That\(' + expression + r', Is\.EqualTo\(' + str(expected) + r'\)\)\s*Expected:\s*' + str(expected) + r'\s*But was:\s*' + str(actual) + r'\s*\Z'
    if not re.fullmatch(wanted, message):
        raise ValueError('Failure is not the exact intended ownership assertion: ' + repr(message[:4096]))
    if fixture_method not in stack or fixture_file not in stack:
        raise ValueError('Missing actual ownership fixture stack')
    combined = log + '\n' + '\n'.join(root.itertext())
    if UNRELATED_ERROR.search(combined):
        raise ValueError('Unrelated engine or runner error')
    return True
