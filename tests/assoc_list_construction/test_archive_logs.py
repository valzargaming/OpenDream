"""Pure byte-retention and missing-input controls; no engine execution."""
from pathlib import Path
import tempfile
import unittest
import zipfile
from archive_logs import NAMES, archive

class OriginalLogArchive(unittest.TestCase):
    def test_exact_crlf_and_utf8_bytes_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals = {name: b'\xef\xbb\xbfOriginal\r\n\tbytes \r\n' + name.encode() for name in NAMES}
            for name, raw in originals.items():
                (root / name).write_bytes(raw)
            result = archive(root)
            self.assertEqual(set(result['files']), set(NAMES))
            with zipfile.ZipFile(root / 'original-runner-logs.zip') as bundle:
                self.assertEqual({name: bundle.read(name) for name in NAMES}, originals)
            for name, raw in originals.items():
                self.assertEqual((root / name).read_bytes(), raw)
            with self.assertRaises(FileExistsError):
                archive(root)

    def test_missing_or_empty_input_is_rejected_before_archive(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name in NAMES:
                    (root / name).write_bytes(b'original')
                if missing:
                    (root / NAMES[-1]).unlink()
                else:
                    (root / NAMES[-1]).write_bytes(b'')
                with self.assertRaisesRegex(ValueError, 'original log'):
                    archive(root)
                self.assertFalse((root / 'original-runner-logs.zip').exists())
