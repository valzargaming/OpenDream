"""Pure ownership-free source/clock/evidence checks; never launch the engine."""
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
import control
import verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def f32(value): return struct.unpack('f', struct.pack('f', value))[0]

def smoke(before=400000, after=400012, before_lower=None, after_lower=None):
    before_lower = before if before_lower is None else before_lower
    after_lower = after if after_lower is None else after_lower
    return '\n'.join(f'TIMEOFDAY_SMOKE_{route} before={before} beforeLower={before_lower} beforeUpper={before_lower} after={after} afterLower={after_lower} afterUpper={after_lower} advance={(after-before)%864000} elapsedLower=10 elapsedUpper=17 stopwatch=12 utc=12' for route in ('PUBLIC','COMPILED'))+'\n'+verify.SMOKE_MARKER+'\n'

def trx(mode):
    ns = '{' + verify.NS['t'] + '}'
    root = ET.Element(ns+'TestRun')
    definitions = ET.SubElement(root, ns+'TestDefinitions')
    definition = ET.SubElement(definitions, ns+'UnitTest', id='one')
    ET.SubElement(definition, ns+'TestMethod', className=verify.CLASS, name=verify.TEST)
    results = ET.SubElement(root, ns+'Results')
    positive = mode == 'positive'
    row = ET.SubElement(results, ns+'UnitTestResult', testId='one', testName=verify.TEST, outcome='Passed' if positive else 'Failed')
    output = ET.SubElement(row, ns+'Output')
    samples = '\n'.join('REALTIME_SAMPLE_'+route+' actual='+('8400000000' if positive else '5')+' lower=8400000000 upper=8400000000' for route in ('PUBLIC','COMPILED'))
    ET.SubElement(output, ns+'StdOut').text = smoke() + samples + ('\n'+verify.MARKER if positive else '')
    if not positive:
        error = ET.SubElement(output, ns+'ErrorInfo')
        blocks = []
        for i, (route, kind, variable) in enumerate([('PUBLIC','EPOCH_MAGNITUDE','largeEpoch'),('PUBLIC','UTC_BRACKET','inBracket'),('COMPILED','EPOCH_MAGNITUDE','largeEpoch'),('COMPILED','UTC_BRACKET','inBracket')], 1):
            blocks.append(f'\n {i}) REALTIME_{route}_{kind}\n Assert.That({variable}, Is.True)\n Expected: True\n But was: False\n')
        ET.SubElement(error, ns+'Message').text = 'Multiple failures or warnings in test:'+''.join(blocks)
        ET.SubElement(error, ns+'StackTrace').text = 'at '+verify.CLASS+'.UtcEpochDeciseconds() in /repo/Content.IntegrationTests/WorldRealtimeClockTests.cs:line 40'
    summary = ET.SubElement(root, ns+'ResultSummary')
    ET.SubElement(summary, ns+'Counters', total='1', executed='1', passed='1' if positive else '0', failed='0' if positive else '1')
    return root

class Controls(unittest.TestCase):
    def accept(self, root, mode, code=None, log=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'original.trx'
            ET.ElementTree(root).write(path)
            return verify.verify(path, mode, (0 if mode=='positive' else 1) if code is None else code,
                log or (('Passed' if mode=='positive' else 'Failed')+' '+verify.TEST+' [1 s]\nTest Run '+('Successful.' if mode=='positive' else 'Failed.')))

    def test_utc_elapsed_float_bracket_and_component_control(self):
        epoch = datetime(2000,1,1,tzinfo=timezone.utc)
        before = datetime(2026,10,14,12,34,56,789000,tzinfo=timezone.utc)
        after = before+timedelta(milliseconds=20)
        lower, upper = [f32((stamp-epoch).total_seconds()*10) for stamp in (before,after)]
        actual = f32(((before+timedelta(milliseconds=10))-epoch).total_seconds()*10)
        self.assertLessEqual(lower, actual); self.assertLessEqual(actual, upper)
        self.assertGreater(actual, 1e9)
        baseline = ((before-epoch).microseconds//1000)//100
        self.assertIn(baseline, range(10)); self.assertFalse(lower <= baseline <= upper)
        # Float UTC epochs may remain equal across many seconds: no movement test.
        self.assertEqual(lower, upper)
        local = before.astimezone(timezone(timedelta(hours=-4)))
        wrong_local_elapsed = f32((local.replace(tzinfo=None)-epoch.replace(tzinfo=None)).total_seconds()*10)
        self.assertFalse(lower <= wrong_local_elapsed <= upper)

    def test_mutation_byteexact_and_drift_rejected(self):
        spec = json.loads((HERE/'controls.json').read_text())
        candidate = (ROOT/control.PRODUCTION).read_bytes()
        self.assertEqual(control.mutation(candidate,'positive',spec), candidate)
        baseline = control.mutation(candidate,'baseline',spec)
        self.assertEqual(control.sha(baseline),spec['base_sha256'])
        with self.assertRaises(AssertionError): control.mutation(candidate+b' ', 'baseline',spec)
        self.assertEqual(candidate.count(b'DateTime.UtcNow'),baseline.count(b'DateTime.UtcNow')+1)

    def test_receipt_prepare_both_modes_and_postrun_tamper(self):
        original_spec=json.loads((HERE/'source-manifest.json').read_text())
        candidate=(ROOT/control.PRODUCTION).read_bytes()
        controls=json.loads((HERE/'controls.json').read_text())
        baseline=control.mutation(candidate,'baseline',controls)
        head='a'*40
        for mode in ('positive','baseline'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); folder=root/'tests/world_realtime_clock'; folder.mkdir(parents=True)
                prod=root/control.PRODUCTION; prod.parent.mkdir(parents=True); prod.write_bytes(candidate)
                spec=copy.deepcopy(original_spec)
                spec['original_inputs']=[next(item for item in spec['original_inputs'] if item['path']==control.PRODUCTION)]
                spec['expected_sources']={control.PRODUCTION:control.sha(candidate)}
                raw=(json.dumps(spec)+'\n').encode(); (folder/'source-manifest.json').write_bytes(raw)
                (folder/'controls.json').write_text(json.dumps(controls))
                def git(_, *args):
                    if args==('rev-parse','HEAD'): return head.encode()
                    ref=args[-1]
                    if ref==head+':tests/world_realtime_clock/source-manifest.json': return raw
                    if ref==head+':'+control.PRODUCTION: return candidate
                    if ref==spec['base_commit']+':'+control.PRODUCTION: return baseline
                    raise AssertionError(args)
                receipt=control.prepare(root,mode,head,git)
                self.assertTrue(control.check_receipt(root,receipt,mode,head))
                prod.write_bytes(prod.read_bytes()+b' ')
                with self.assertRaises(AssertionError): control.check_receipt(root,receipt,mode,head)

    def test_positive_and_exact_four_failure_baseline(self):
        self.assertTrue(self.accept(trx('positive'),'positive'))
        self.assertTrue(self.accept(trx('baseline'),'baseline'))

    def test_unrelated_failure_wrong_exit_or_original_log_rejected(self):
        for mode in ('positive','baseline'):
            with self.subTest(mode=mode):
                with self.assertRaises(AssertionError): self.accept(trx(mode),mode,code=2)
                with self.assertRaises(AssertionError): self.accept(trx(mode),mode,log='[ERRO] unrelated failure')
        root=trx('baseline')
        node=root.find('.//t:Message',verify.NS); node.text+='\n 5) unrelated failure'
        with self.assertRaises(AssertionError): self.accept(root,'baseline')
        root=trx('baseline'); root.find('.//t:Message',verify.NS).text=root.find('.//t:Message',verify.NS).text.replace('PUBLIC_EPOCH_MAGNITUDE','PUBLIC_FINITE')
        with self.assertRaises(AssertionError): self.accept(root,'baseline')

    def test_samples_outside_bounds_and_foreign_failures_rejected(self):
        for old,new,mode in [('actual=8400000000','actual=8399856000','positive'),('actual=5','actual=500','baseline'),('lower=8400000000','lower=0','baseline'),('actual=5','actual=NaN','baseline')]:
            root=trx(mode); node=root.find('.//t:StdOut',verify.NS); node.text=node.text.replace(old,new)
            with self.subTest(new=new), self.assertRaises(AssertionError): self.accept(root,mode)
        root=trx('positive'); root.find('.//t:TestMethod',verify.NS).set('className','Unrelated.Tests')
        with self.assertRaises(AssertionError): self.accept(root,'positive')
        root=trx('positive'); root.find('.//t:Counters',verify.NS).set('aborted','1')
        with self.assertRaises(AssertionError): self.accept(root,'positive')

    def test_public_compiled_routes_and_no_shared_hook(self):
        fixture=(ROOT/'Content.IntegrationTests/WorldRealtimeClockTests.cs').read_text()
        self.assertIn('manager.WorldInstance.GetVariable("realtime")',fixture)
        self.assertIn('DreamThread.Run(proc!, manager.WorldInstance, null)',fixture)
        self.assertIn('using var value = getter();',fixture)
        self.assertEqual(fixture.count('DateTime.UtcNow'),6)
        self.assertIn('world.realtime',(ROOT/'Content.IntegrationTests/DMProject/Fixtures/world-realtime-clock.dm').read_text())
        manifest=json.loads((HERE/'source-manifest.json').read_text())
        self.assertFalse(any('GameTests' in name for name in manifest['expected_sources']))

    def test_every_candidate_source_pin_matches(self):
        manifest=json.loads((HERE/'source-manifest.json').read_text())
        self.assertEqual(len(manifest['original_inputs']),7)
        for name, expected in manifest['expected_sources'].items():
            with self.subTest(source=name): self.assertEqual(control.sha((ROOT/name).read_bytes()),expected)


    def test_explicit_fixture_separate_host_and_no_skipped_evidence(self):
        fixture=(ROOT/'Content.IntegrationTests/WorldRealtimeClockTests.cs').read_text()
        self.assertIn('[Explicit("Requires a separate test host because BYOND API initialization is process-global")]',fixture)
        workflow=(ROOT/'.github/workflows/world-realtime-clock.yml').read_text()
        self.assertEqual(workflow.count('-- NUnit.ExplicitMode=Relaxed'),1)
        for mode in ('positive','baseline'):
            root=trx(mode)
            root.find('.//t:UnitTestResult',verify.NS).set('outcome','NotExecuted')
            root.find('.//t:Counters',verify.NS).set('executed','0')
            with self.subTest(mode=mode), self.assertRaises(AssertionError): self.accept(root,mode)

    def test_timeofday_midnight_wrap_and_frozen_component_rejected(self):
        for mode in ('positive','baseline'):
            root=trx(mode); node=root.find('.//t:StdOut',verify.NS)
            realtime=node.text[len(smoke()):]
            node.text=smoke(863995,7)+realtime
            self.assertTrue(self.accept(root,mode))
            for sample in (smoke(400000,400000),smoke(5,7),smoke(5,7,400000,400012)):
                node.text=sample+realtime
                with self.subTest(mode=mode,sample=sample), self.assertRaises(AssertionError): self.accept(root,mode)

    def test_timeofday_jitter_and_sample_bracket_midnight_wrap(self):
        for sample in (smoke().replace('stopwatch=12','stopwatch=12.3').replace('utc=12','utc=12.4').replace('elapsedUpper=17','elapsedUpper=17.4'),
                       smoke(0,12,863999,12).replace('beforeUpper=863999','beforeUpper=0')):
            root=trx('positive'); node=root.find('.//t:StdOut',verify.NS)
            node.text=sample+node.text[len(smoke()):]
            self.assertTrue(self.accept(root,'positive'))

    def test_timeofday_host_bounds_missing_or_forged_evidence_rejected(self):
        for old,new in [(verify.SMOKE_MARKER,''),('stopwatch=12','stopwatch=0'),('advance=12','advance=11'),
                        ('elapsedUpper=17','elapsedUpper=999'),('before=400000','before=NaN'),
                        ('TIMEOFDAY_SMOKE_PUBLIC','TIMEOFDAY_SMOKE_COMPILED')]:
            root=trx('baseline'); node=root.find('.//t:StdOut',verify.NS); node.text=node.text.replace(old,new)
            with self.subTest(new=new), self.assertRaises((AssertionError,ValueError)): self.accept(root,'baseline')

    def test_timeofday_connected_before_realtime_and_owned_values(self):
        fixture=(ROOT/'Content.IntegrationTests/WorldRealtimeClockTests.cs').read_text()
        self.assertLess(fixture.index('AssertTimeOfDaySmoke(() =>'),fixture.index('Assert.Multiple(() =>'))
        self.assertIn('Thread.Sleep(1200);',fixture)
        self.assertIn('Stopwatch.StartNew()',fixture)
        self.assertIn('manager.WorldInstance.GetVariable("timeofday")',fixture)
        self.assertIn('DreamThread.Run(timeofdayProc!, manager.WorldInstance, null)',fixture)
        self.assertIn('(after.Actual - before.Actual + 864000) % 864000',fixture)
        self.assertIn('using var value = getter();',fixture)
        self.assertIn('return world.timeofday',(ROOT/'Content.IntegrationTests/DMProject/Fixtures/world-realtime-clock.dm').read_text())

if __name__=='__main__': unittest.main()
