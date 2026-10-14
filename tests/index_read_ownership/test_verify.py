"""Synthetic oracle checks; these do not execute the engine fixture."""
import tempfile
from pathlib import Path
import unittest
from xml.sax.saxutils import escape
from verify import verify, MARKER, FAILURES

def message(frames=False):
    blocks=[]
    for i,marker in enumerate(FAILURES,1):
        owner='owner' if i<3 else 'indexOwner'
        block=f' {i}) {marker}\nAssert.That({owner}.RefCount, Is.EqualTo(1))\nExpected: 1\nBut was: 1001\n'
        if frames:
            # Same NUnit per-assertion stack format observed in PR29, with this fixture's methods.
            methods=[
                ('Content.IntegrationTests.GameTests.IndexReadMissingOwners1000(DreamObjectTree tree, DreamRefManager refs, Boolean missingOperator)','Content.IntegrationTests/GameTests.IndexReadOwnership.cs'),
                ('Content.IntegrationTests.GameTests.<>c__DisplayClass15_0.<IndexReferenceReadsReleaseOwners>b__0()','Content.IntegrationTests/GameTests.IndexReadOwnership.cs'),
                ('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)',None),
                ('Content.IntegrationTests.GameTests.IndexReferenceReadsReleaseOwners(DreamObjectTree tree, DreamRefManager refs)','Content.IntegrationTests/GameTests.IndexReadOwnership.cs'),
                ('Content.IntegrationTests.GameTests.<>c__DisplayClass8_0.<NoRuntimesTest>b__3()','Content.IntegrationTests/GameTests.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.SingleThreadRunUntilEmpty()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.IntegrationGameLoop.Run()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('Robust.UnitTesting.RobustIntegrationTest.ServerIntegrationInstance._serverMain()','RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs'),
                ('System.Threading.Thread.StartHelper.Callback(Object state)',None)]
            for method,file in methods:
                block+='   at '+method+(f' in /runner/work/OpenDream/{file}:line 60' if file else '')+'\n'
        blocks.append(block)
    return 'Multiple failures or warnings in test:\n'+''.join(blocks)

def trx(positive=False, frames=False, failure=None):
    error='' if positive else '<ErrorInfo><Message>'+escape(failure if failure is not None else message(frames))+'</Message><StackTrace>GameTests.IndexReferenceReadsReleaseOwners in GameTests.IndexReadOwnership.cs</StackTrace></ErrorInfo>'
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
            for frames in (False,True): self.assertTrue(self.check(trx(frames=frames),mode))
    def test_exact_failure_markers_counts_expressions(self):
        m=message(True)
        for bad in [m.replace(FAILURES[0],FAILURES[1]),m.replace('But was: 1001','But was: 1002'),
                    m.replace('Expected: 1','Expected: 2'),m.replace('indexOwner.RefCount','owner.RefCount'),
                    m+'4) another failure',m.replace('IndexReadMissingOwners1000','OtherFixture')]:
            with self.assertRaises(AssertionError): self.check(trx(failure=bad))
    def test_runner_errors_and_wrong_result_rejected(self):
        for bad in [trx().replace('total="1"','error="1" total="1"'),trx().replace('NoRuntimesTest','OtherTest'),
                    trx().replace('Failed','NotExecuted'),trx().replace('GameTests.IndexReadOwnership.cs','OtherFixture.cs')]:
            with self.assertRaises(AssertionError):self.check(bad)
        with self.assertRaises(AssertionError):self.check(trx(),log='[ERRO] unexpected runtime')
    def test_exit_and_missing_completion(self):
        with self.assertRaises(AssertionError): self.check(trx(),code=0)
        with self.assertRaises(AssertionError): self.check(trx(True).replace(MARKER,'incomplete'),'positive',0)
    def test_extra_result_rejected(self):
        with self.assertRaises(AssertionError):self.check(trx().replace('</Results>','<UnitTestResult/></Results>'))
    def test_unrelated_inline_frames_rejected(self):
        for bad in [message(True).replace('NUnit.Framework.Assert.Multiple(TestDelegate testDelegate)','System.Exception.Throw()'),
                    message(True).replace('/Content.IntegrationTests/GameTests.IndexReadOwnership.cs','/OtherFixture.cs'),
                    message(True)+'Unhandled exception']:
            with self.assertRaises(AssertionError):self.check(trx(failure=bad))

if __name__=='__main__':unittest.main()
