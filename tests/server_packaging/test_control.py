import copy
from pathlib import Path
import unittest
from control import BASE_HEAD, BASE_HASH, HELPER, MARKERS, SUCCESS, mutate, verify_receipt, verify_result

HEAD = 'a' * 40
BEFORE = 'b' * 64
AFTER = 'c' * 64


def failure(marker):
    return ('System.InvalidOperationException: PACKAGING ASSERTION: ' + marker + '\n'
            '   at SelectionProbe.Require(Boolean condition, String marker) in /src/SelectionProbe.cs:line 6\n'
            '   at SelectionProbe.Main() in /src/SelectionProbe.cs:line 26\n')


class Controls(unittest.TestCase):
    def test_exact_failures(self):
        for control, marker in MARKERS.items():
            verify_result(failure(marker), 1, control)

    def test_positive(self):
        verify_result(SUCCESS + '\n', 0, 'positive')

    def test_reject_exit_build_unrun_and_other_errors(self):
        text = failure(MARKERS['dedup'])
        for log, code in [(text, 0), (text, 2), ('', 1), ('Build FAILED.\n' + text, 1),
                          (text + 'error CS0001\n', 1), (text + 'Unhandled exception\n', 1),
                          (text + SUCCESS, 1), (text + text, 1), (SUCCESS, 1),
                          (failure('deterministic-order'), 1),
                          (text.replace('SelectionProbe.Require(', 'Other.Require('), 1),
                          (text.replace('line 6', 'line 6 error CS0001'), 1),
                          (text.replace('/src/SelectionProbe.cs', '/src/Other.cs'), 1)]:
            with self.subTest(log=log, code=code), self.assertRaises(ValueError):
                verify_result(log, code, 'dedup')

    def test_reject_bad_positive(self):
        for log, code in [('', 0), (SUCCESS, 1), (SUCCESS + '\nwarning\n', 0)]:
            with self.assertRaises(ValueError):
                verify_result(log, code, 'positive')

    def test_mutations_are_unique_and_targeted(self):
        source = (Path(__file__).resolve().parents[2] / HELPER).read_text()
        for control in MARKERS:
            changed = mutate(source, control)
            self.assertNotEqual(source, changed)
            with self.assertRaises(ValueError):
                mutate(changed, control)
            with self.assertRaises(ValueError):
                mutate(source + source, control)
        self.assertNotIn('seen.Add(', mutate(source, 'dedup'))
        self.assertIn('.Select(path => path)', mutate(source, 'prefix'))
        self.assertIn('File.Exists(Path.Combine(sourceDir, dll))', mutate(source, 'required'))

    def test_full_receipt_identity(self):
        receipt = dict(control='dedup', candidateHead=HEAD, baselineHead=BASE_HEAD,
            baselineSourceSha256=BASE_HASH, candidateHelperSha256=BEFORE,
            mutatedHelperSha256=AFTER, candidateSourceHashes={HELPER: BEFORE,
                'OpenDreamPackageTool/ServerPackaging.cs': BEFORE,
                'tests/server_packaging/SelectionProbe.cs': BEFORE,
                'tests/server_packaging/SelectionProbe.csproj': BEFORE})
        verify_receipt(receipt, 'dedup', HEAD, AFTER)
        for field, wrong in [('control', 'prefix'), ('candidateHead', 'd' * 40),
                             ('baselineHead', 'e' * 40), ('baselineSourceSha256', 'f' * 64),
                             ('candidateHelperSha256', AFTER), ('mutatedHelperSha256', '123')]:
            altered = copy.deepcopy(receipt)
            altered[field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_receipt(altered, 'dedup', HEAD, AFTER)
        with self.assertRaises(ValueError):
            verify_receipt(receipt, 'dedup', 'short', AFTER)
        with self.assertRaises(ValueError):
            verify_receipt(receipt, 'dedup', HEAD, '0' * 64)
        altered = copy.deepcopy(receipt)
        del altered['candidateSourceHashes'][HELPER]
        with self.assertRaises(ValueError):
            verify_receipt(altered, 'dedup', HEAD, AFTER)


if __name__ == '__main__':
    unittest.main()
