import unittest
from control import mutate

class Controls(unittest.TestCase):
    def test_positive_identical(self):
        raw=b'writer.Write("\\r\\n");'
        self.assertEqual(mutate(raw,'positive'),raw)
    def test_platform_newline_only(self):
        self.assertEqual(mutate(b'prefix writer.Write("\\r\\n"); suffix','platform-newline'),b'prefix writer.WriteLine(); suffix')
    def test_missing_guard_rejected(self):
        with self.assertRaises(AssertionError): mutate(b'no terminator','platform-newline')
    def test_duplicate_guard_rejected(self):
        with self.assertRaises(AssertionError): mutate(b'writer.Write("\\r\\n");'*2,'platform-newline')
