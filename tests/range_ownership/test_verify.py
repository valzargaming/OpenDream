"""Synthetic oracle checks; these do not execute the engine fixture."""
import tempfile
from pathlib import Path
import unittest
from xml.sax.saxutils import escape
from verify import verify, MARKER, failures

FAILURES = tuple(f['marker'] for f in failures('baseline'))
def message(frames=False, mode='baseline'):
    blocks=[]
    for i,failure in enumerate(failures(mode),1):
        marker=failure['marker']; actual=failure['actual']
        owner='owner'
        block=f' {i}) {marker}\nAssert.That({owner}.RefCount, Is.EqualTo(1))\nExpected: 1\nBut was: {actual}\n'
        if frames:
            # Same NUnit per-assertion stack format observed in PR29, with this fixture's methods.
            methods=[
                ('Content.IntegrationTests.GameTests.RangeOperandsOwnExactlyOneCaller(DreamObjectTree tree, DreamRefManager refs, Boolean list, Int32 role)','Content.IntegrationTests/GameTests.RangeOwnership.cs'),
                ('Content.IntegrationTests.GameTests.<>c__DisplayClass15_0.<InRangeOperandsReleaseOwners>b__0()','Content.IntegrationTests/GameTests.RangeOwnership.cs'),
                ('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)',None),
                ('Content.IntegrationTests.GameTests.InRangeOperandsReleaseOwners(DreamManager manager, DreamObjectTree tree, DreamRefManager refs)','Content.IntegrationTests/GameTests.RangeOwnership.cs'),
                ('Content.IntegrationTests.GameTests.<>c__DisplayClass8_0.<NoRuntimesTest>b__3()','Content.IntegrationTests/GameTests.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.SingleThreadRunUntilEmpty()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.Run()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.ServerIntegrationInstance._serverMain()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('System.Threading.Thread.StartHelper.Callback(Object state)',None)]
            for method,file in methods:
                block+='   at '+method+(f' in /runner/work/OpenDream/{file}:line 60' if file else '')+'\n'
        blocks.append(block)
    return 'Multiple failures or warnings in test:\n'+''.join(blocks)

def trx(positive=False, frames=False, failure=None, mode='baseline'):
    error='' if positive else '<ErrorInfo><Message>'+escape(failure if failure is not None else message(frames,mode))+'</Message><StackTrace>GameTests.InRangeOperandsReleaseOwners in GameTests.RangeOwnership.cs</StackTrace></ErrorInfo>'
    return f'''<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><Results>
<UnitTestResult testId="case1" testName="NoRuntimesTest" outcome="{'Passed' if positive else 'Failed'}"><Output><StdOut>{MARKER}</StdOut>{error}</Output></UnitTestResult>
</Results><TestDefinitions><UnitTest id="case1"><TestMethod className="Content.IntegrationTests.GameTests" name="NoRuntimesTest"/></UnitTest></TestDefinitions><ResultSummary><Counters total="1" executed="1" passed="{1 if positive else 0}" failed="{0 if positive else 1}"/></ResultSummary></TestRun>'''

class OracleTests(unittest.TestCase):
    def check(self,xml,mode='baseline',code=1,log=''):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.trx';p.write_text(xml)
            return verify(p,mode,code,log)
    def test_positive_completion(self): self.assertTrue(self.check(trx(True),'positive',0))
    def test_both_controls_and_nunit_frames(self):
        for mode in ('baseline','omitted-release'):
            for frames in (False,True): self.assertTrue(self.check(trx(frames=frames,mode=mode),mode))
    def test_exact_failure_markers_counts_expressions(self):
        m=message(True)
        for bad in [m.replace(FAILURES[0],FAILURES[1]),m.replace('But was: 1001','But was: 1002'),
                    m.replace('Expected: 1','Expected: 2'),m.replace('owner.RefCount','unrelated.RefCount'),
                    m+'4) another failure',m.replace('RangeOperandsOwnExactlyOneCaller','OtherFixture')]:
            with self.assertRaises(AssertionError): self.check(trx(failure=bad))
    def test_runner_errors_and_wrong_result_rejected(self):
        for bad in [trx().replace('total="1"','error="1" total="1"'),trx().replace('NoRuntimesTest','OtherTest'),
                    trx().replace('Failed','NotExecuted'),trx().replace('GameTests.RangeOwnership.cs','OtherFixture.cs')]:
            with self.assertRaises(AssertionError):self.check(bad)
        with self.assertRaises(AssertionError):self.check(trx(),log='[ERRO] unexpected runtime')
    def test_exit_and_missing_completion(self):
        with self.assertRaises(AssertionError): self.check(trx(),code=0)
        with self.assertRaises(AssertionError): self.check(trx(True).replace(MARKER,'incomplete'),'positive',0)
    def test_extra_result_rejected(self):
        with self.assertRaises(AssertionError):self.check(trx().replace('</Results>','<UnitTestResult/></Results>'))
    def test_unrelated_inline_frames_rejected(self):
        for bad in [message(True).replace('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)','System.Exception.Throw()'),
                    message(True).replace('/Content.IntegrationTests/GameTests.RangeOwnership.cs','/OtherFixture.cs'),
                    message(True)+'Unhandled exception']:
            with self.assertRaises(AssertionError):self.check(trx(failure=bad))
    def test_controls_cannot_accept_each_others_failures(self):
        for mode,other in [('baseline','omitted-release'),('omitted-release','baseline')]:
            with self.assertRaises(AssertionError):self.check(trx(mode=other),mode)
    def test_alias_counts_and_truncated_controls_rejected(self):
        with self.assertRaises(AssertionError):
            self.check(trx(failure=message().replace('But was: 3001','But was: 1001')))
        for mode in ('baseline','omitted-release'):
            rows=message(mode=mode).splitlines(True)
            # Remove the final four-line assertion block from the aggregate.
            with self.assertRaises(AssertionError):
                self.check(trx(failure=''.join(rows[:-4])),mode)

if __name__=='__main__':unittest.main()
