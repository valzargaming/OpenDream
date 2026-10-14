"""Synthetic console duplication adversaries; these are not runtime evidence."""
import unittest
from verify import logs_clean, without_authenticated_stdout_copy

class ConsoleStdoutCopyTests(unittest.TestCase):
    def setUp(self):
        self.method = 'EnabledCloseAndDirtyFailure'
        path = '/tmp/opendream-save-cost-host-' + 'a' * 32 + '/data/dirty.json'
        self.stdout = ('SAVE_COST_ACTUAL_LOG [Error] opendream.res: Error flushing savefile ' + path +
                       ': System.Text.Json.JsonException: cycle\nDreamObjectSavefile.Flush\n' +
                       'SAVE_COST_EXPECTED_DIRTY_JSON_ERROR_CLASSIFIED ' + path)
        self.copy = '  Standard Output Messages:\n' + ''.join(' ' + line + '\n' for line in self.stdout.splitlines())
        self.log = self.stdout + '\nFailed ' + self.method + '\n' + self.copy + '\n\nResults File: synthetic.trx\nTest Run Failed.\n'

    def test_exact_failed_copy_checks_canonical_and_remaining_logs(self):
        logs_clean(self.stdout, self.method)
        remaining = without_authenticated_stdout_copy(self.log, self.stdout, True)
        logs_clean(remaining, self.method)
        self.assertNotIn('  Standard Output Messages:', remaining)
        self.assertIn('Failed ' + self.method, remaining)
        self.assertEqual(without_authenticated_stdout_copy(self.log.replace('\n', '\r\n'), self.stdout, True), remaining)
        self.assertEqual(without_authenticated_stdout_copy(self.stdout, self.stdout, True), self.stdout)

    def test_copy_mismatch_extra_duplicate_and_positive_rejected(self):
        for log in (self.log.replace(' SAVE_COST_ACTUAL_LOG [Error]', ' SAVE_COST_ACTUAL_LOG [Fatal]'),
                    self.log.replace('\n\nResults File:', '\n [Error] extra\n\nResults File:'),
                    self.log.replace('  Standard Output Messages:\n', '  Standard Output Messages:\n' * 2),
                    self.log.replace('\n\nResults File:', '\nResults File:')):
            with self.subTest(log=log), self.assertRaises(ValueError):
                without_authenticated_stdout_copy(log, self.stdout, True)
        with self.assertRaises(ValueError):without_authenticated_stdout_copy(self.log, self.stdout, False)

    def test_extra_diagnostics_and_missing_classification_still_rejected(self):
        for bad in ('[Error] unrelated', '[Fatal] unrelated', '[ERRO] runtime', 'Runtime occurred', 'Unhandled exception'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                logs_clean(without_authenticated_stdout_copy(self.log + bad, self.stdout, True), self.method)
            with self.subTest(channel='canonical', bad=bad), self.assertRaises(ValueError):
                logs_clean(self.stdout + '\n' + bad, self.method)
        with self.assertRaises(ValueError):
            logs_clean(self.stdout.replace('SAVE_COST_EXPECTED_DIRTY_JSON_ERROR_CLASSIFIED', 'OTHER'), self.method)

if __name__ == '__main__':unittest.main(verbosity=2)
