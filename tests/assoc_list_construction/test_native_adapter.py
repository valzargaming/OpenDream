"""Synthetic checks for exact observed NUnit/VSTest adapter spellings, not runtime evidence."""
import unittest
import test_controls as T
evidence, FRAME, V = T.evidence, T.FRAME, T.V

FOOTER = '''
Total tests: 1
     Failed: 1
 Total time: 2.8309 Seconds
     1>Project "/repo/Content.IntegrationTests/Content.IntegrationTests.csproj" on node 1 (VSTest target(s)).
     1>_VSTestConsole:
         MSB4181: The "VSTestTask" task returned false but did not log an error.
     1>Done Building Project "/repo/Content.IntegrationTests/Content.IntegrationTests.csproj" (VSTest target(s)) -- FAILED.

Build FAILED.
    0 Warning(s)
    0 Error(s)

Time Elapsed 00:00:03.70
'''

def adapter():
    tree, log = evidence('baseline', embedded=True)
    tree.find('.//t:Counters', V.NS).set('completed','0')
    stdout=tree.findtext('.//t:StdOut','',V.NS)
    reprint='  Standard Output Messages:\n'+'\n'.join(' '+line for line in stdout.splitlines())+'\n\nResults File: /repo/assoc-results/assoc.trx\n\n'
    log=log.replace('Test Run Failed.', reprint+'Test Run Failed.')+FOOTER
    stack=tree.find('.//t:StackTrace',V.NS)
    stack.text=FRAME+'\n'+V.ASYNC_BOUNDARY+'\n'+'at Robust.UnitTesting.RobustIntegrationTest.IntegrationInstance.WaitAssertion(Action assertion) in /repo/RobustToolbox/Robust.UnitTesting/RobustIntegrationTest.cs:line 693\n'
    stack.text+='\n'.join(f'{i+1}) {FRAME}\n' for i in range(96))
    return tree,log

class NativeAdapter(unittest.TestCase):
    check=T.Controls.check

    def test_observed_completed_zero_and_exact_negative_adapter(self):
        tree,log=adapter()
        self.assertTrue(self.check(tree,log,'baseline'))
        tree,log=evidence('positive')
        tree.find('.//t:Counters',V.NS).set('completed','0')
        self.assertTrue(self.check(tree,log))

    def test_counter_zero_does_not_authorize_unexecuted_or_unknown_counts(self):
        for field,value in [('completed','2'),('completed','-1'),('executed','0'),('total','2'),('notExecuted','1'),('passed','1'),('failed','0'),('foreign','0')]:
            tree,log=adapter();tree.find('.//t:Counters',V.NS).set(field,value)
            with self.subTest(field=field,value=value),self.assertRaises(AssertionError):self.check(tree,log,'baseline')

    def test_build_failure_footer_is_only_exact_zero_error_vstest_suffix(self):
        tree,log=adapter()
        for bad in [log+'\nBuild FAILED.', 'Build FAILED.\n'+log, log.replace('0 Error(s)','1 Error(s)'),log.replace('0 Warning(s)','1 Warning(s)'),log.replace('MSB4181:', 'error MSB4181:'),log.replace('VSTestTask','CompilerTask'),log.replace('(VSTest target(s))','(Build target(s))'),log+'\nCompilation: error CS1001',log+'\nfile.dm: error unknown',log+'\n[ERRO] unknown',log.replace('Time Elapsed 00:00:03.70','Time Elapsed unknown')]:
            with self.subTest(tail=bad[-70:]),self.assertRaises(AssertionError):self.check(tree,bad,'baseline')
        tree,log=evidence('positive')
        with self.assertRaises(AssertionError):self.check(tree,log+'\nTest Run Failed.'+FOOTER)

    def test_reprinted_stdout_must_be_identical_bounded_adapter_section(self):
        tree,log=adapter()
        at=log.index('  Standard Output Messages:')
        for bad in [log[:at]+log[at:].replace('owners=[','owners=[999,',1),log+log[at:],log.replace('  Standard Output Messages:','  Standard Output Messages:\n  Standard Output Messages:'),log.replace('Results File: /repo/assoc-results/assoc.trx','Results File: /repo/foreign.trx'),log+'\n'+tree.findtext('.//t:StdOut','',V.NS),log+ '\n'+V.MARKER]:
            with self.subTest(tail=bad[-40:]),self.assertRaises(AssertionError):self.check(tree,bad,'baseline')

    def test_numbered_stack_appendix_is_exact_ordered_message_mirror(self):
        for change in ['missing','duplicate','order','foreign','different-source','unknown-boundary']:
            tree,log=adapter();stack=tree.find('.//t:StackTrace',V.NS)
            if change=='missing':stack.text=stack.text.replace('96) '+FRAME,'')
            elif change=='duplicate':stack.text+='\n96) '+FRAME
            elif change=='order':stack.text=stack.text.replace('2) '+FRAME,'1) '+FRAME,1)
            elif change=='foreign':stack.text=stack.text.replace('96) '+FRAME,'96) at Foreign.Frame()',1)
            elif change=='different-source':stack.text=stack.text.replace('96) '+FRAME,'96) '+FRAME.replace('line 51','line 999'),1)
            else:stack.text=stack.text.replace(V.ASYNC_BOUNDARY,'--- Foreign boundary ---')
            with self.subTest(change=change),self.assertRaises(AssertionError):self.check(tree,log,'baseline')

    def test_log_message_and_marker_duplication_are_not_hidden_by_footer(self):
        tree,log=adapter()
        marker=V.SPEC[0]['id']+'_OWNERS_1000'
        for bad in [log+'\n'+marker,log.replace('But was: 1001','But was: 9999',1),log+'\nat NUnit.Framework.Internal.ForeignMethod()',log+'\nat Foreign.Frame()']:
            with self.assertRaises(AssertionError):self.check(tree,bad,'baseline')

if __name__=='__main__':unittest.main()
