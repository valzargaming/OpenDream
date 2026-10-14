"""Synthetic timing-oracle adversaries, not compiled/runtime evidence."""
import copy
import unittest
import test_controls as T
import test_native_adapter as A

V = T.V


class TimingControls(unittest.TestCase):
    check = T.Controls.check

    def test_exact_two_failures_and_adapter(self):
        for embedded in (False, True):
            tree, log = T.evidence('timing-negative', embedded)
            self.assertTrue(self.check(tree, log, 'timing-negative'))
            stdout = tree.findtext('.//t:StdOut', '', V.NS)
            reprint = '  Standard Output Messages:\n' + '\n'.join(' ' + line for line in stdout.splitlines()) + '\n\nResults File: /repo/assoc-results/assoc.trx\n\n'
            log = log.replace('Test Run Failed.', reprint + 'Test Run Failed.') + A.FOOTER
            self.assertTrue(self.check(tree, log, 'timing-negative'))

    def test_timing_markers_exact_order_trace_and_workload(self):
        for mode in ('positive', 'baseline', 'timing-negative'):
            for change in ('missing', 'extra', 'duplicate', 'order', 'unknown', 'trace', 'iterations', 'expected', 'placement'):
                tree, log = T.evidence(mode)
                node = tree.find('.//t:StdOut', V.NS)
                rows = node.text.splitlines()
                if change == 'missing': rows.pop(0)
                elif change == 'extra': rows.append('ASSOC_TIMING_FOREIGN: trace=BA; expected=BA; iterations=1000')
                elif change == 'duplicate': rows.insert(1, rows[0])
                elif change == 'order': rows[0], rows[1] = rows[1], rows[0]
                elif change == 'unknown': rows[0] = rows[0].replace('DATUM', 'FOREIGN')
                elif change == 'trace': rows[0] = rows[0].replace('trace=AB', 'trace=BA') if mode == 'timing-negative' else rows[0].replace('trace=BA', 'trace=AB')
                elif change == 'iterations': rows[0] = rows[0].replace('1000', '999')
                elif change == 'expected': rows[0] = rows[0].replace('expected=BA', 'expected=AB')
                else: rows.append(rows.pop(0))
                node.text = '\n'.join(rows)
                with self.subTest(mode=mode, change=change), self.assertRaises(AssertionError):
                    self.check(tree, log, mode)

    def test_timing_failure_structure_counts_and_expression(self):
        for change in ('missing', 'extra', 'order', 'duplicate', 'marker', 'expression', 'expected', 'actual', 'foreign-frame'):
            tree, log = T.evidence('timing-negative', embedded=True)
            node = tree.find('.//t:Message', V.NS)
            if change == 'missing': node.text = node.text.split('\n2)')[0]
            elif change == 'extra': node.text += '\n3) unrelated failure'
            elif change == 'order': node.text = node.text.replace('ASSOC_TIMING_DATUM', 'ASSOC_TIMING_LIST', 1)
            elif change == 'duplicate': node.text = node.text.replace('2)', '1)', 1)
            elif change == 'marker': node.text = node.text.replace(V.TIMING_SUFFIX, '_UNKNOWN', 1)
            elif change == 'expression': node.text = node.text.replace('Assert.That(correct,', 'Assert.That(other,', 1)
            elif change == 'expected': node.text = node.text.replace('Expected: True', 'Expected: False', 1)
            elif change == 'actual': node.text = node.text.replace('But was: False', 'But was: True', 1)
            else: node.text = node.text.replace(T.FRAME, 'at Foreign.Bad()', 1)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                self.check(tree, log, 'timing-negative')

    def test_timing_mode_never_accepts_ownership_failure_or_completion(self):
        tree, log = T.evidence('timing-negative')
        for extra in (V.SPEC[0]['id'] + '_OWNERS_1000', V.MARKER, 'ASSOC_TIMING_DATUM_UNKNOWN', 'at Foreign.Bad()', 'Build FAILED.', 'fixture.cs: error CS1001'):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                self.check(tree, log + '\n' + extra, 'timing-negative')
        tree, log = T.evidence('baseline')
        with self.assertRaises(AssertionError): self.check(tree, log, 'timing-negative')
        tree, log = T.evidence('timing-negative')
        with self.assertRaises(AssertionError): self.check(tree, log, 'baseline')

    def test_timing_negative_log_must_match_and_ids_are_unique(self):
        tree, log = T.evidence('timing-negative')
        for bad in (log.replace('trace=AB', 'trace=BA', 1), log + '\nASSOC_TIMING_DATUM' + V.TIMING_SUFFIX, log.replace('But was: False', 'But was: True', 1)):
            with self.assertRaises(AssertionError): self.check(tree, bad, 'timing-negative')

    def test_numbered_timing_stack_appendix_requires_two_matching_stacks(self):
        tree, log = T.evidence('timing-negative', embedded=True)
        stack = tree.find('.//t:StackTrace', V.NS)
        stack.text = T.FRAME + '\n1) ' + T.FRAME + '\n2) ' + T.FRAME
        self.assertTrue(self.check(tree, log, 'timing-negative'))
        for suffix in ('\n3) ' + T.FRAME, '\n2) at Foreign.Bad()'):
            changed = copy.deepcopy(tree)
            changed.find('.//t:StackTrace', V.NS).text += suffix
            with self.assertRaises(AssertionError): self.check(changed, log, 'timing-negative')


if __name__ == '__main__': unittest.main()
