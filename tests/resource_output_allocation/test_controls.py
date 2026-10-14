import unittest
from control import mutate, compose_cache_resource, CACHE_HELPER, ROOT, RESOURCE, git

class Controls(unittest.TestCase):
    def test_small_path_control_only_and_missing_duplicate_rejected(self):
        needle=b'if (text.Length <= 4096) {'
        changed=mutate(b'before '+needle+b' after','no-small-path')
        self.assertEqual(changed,b'before if (text.Length < 0) { // negative control: ordinary output pays writer overhead after')
        for raw in (b'missing',needle*2):
            with self.assertRaises(AssertionError):mutate(raw,'no-small-path')
    def test_positive_identical(self):
        raw=b'writer.Write("\\r\\n");'
        self.assertEqual(mutate(raw,'positive'),raw)
    def test_platform_newline_only(self):
        self.assertEqual(mutate(b'prefix writer.Write("\\r\\n"); suffix','platform-newline'),b'prefix writer.WriteLine(); suffix')
    def test_missing_guard_rejected(self):
        with self.assertRaises(AssertionError): mutate(b'no terminator','platform-newline')
    def test_duplicate_guard_rejected(self):
        with self.assertRaises(AssertionError): mutate(b'writer.Write("\\r\\n");'*2,'platform-newline')

    def test_historical_append_keeps_exact_cache_helper_only(self):
        original=git('cat-file','blob','31b11b063e4b10be15472de8a566d9a466781e4c:'+RESOURCE)
        prepared=compose_cache_resource(original)
        self.assertEqual(prepared.replace(CACHE_HELPER,b''),original)
        self.assertEqual(prepared.count(b'File.AppendAllText(ResourcePath, text + "\\r\\n");'),2)
        self.assertIn(b'ResourceData = null;',prepared)
    def test_current_helper_matches_authenticated_historical_addition(self):
        current=(ROOT/RESOURCE).read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(current.count(CACHE_HELPER),1)
        for raw in (b'no anchor',b'    public void Clear() {'*2,b'ReleaseFileDataCache    public void Clear() {'):
            with self.assertRaises(AssertionError):compose_cache_resource(raw)
