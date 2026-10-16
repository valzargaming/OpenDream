"""Pure archive adversaries; synthetic logs never prove native success."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import archive_logs as A
import extract_logs as E

class ArchiveControls(unittest.TestCase):
    def setup(self,root):
        for name in A.NAMES:(root/name).write_bytes(('synthetic '+name+'\r\n').encode())
        record=A.archive(root)
        return root/'original-runner-logs.zip',root/'original-runner-logs.json',record

    def test_roundtrip_exact_bytes_and_fresh_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,receipt,_=self.setup(root)
            E.extract(archive,receipt,root/'extracted')
            for name in A.NAMES:self.assertEqual((root/name).read_bytes(),(root/'extracted'/name).read_bytes())
            with self.assertRaises(ValueError):E.extract(archive,receipt,root/'extracted')
            with self.assertRaises(FileExistsError):A.archive(root)

    def test_missing_empty_oversized_logs(self):
        for value in (None,b'',b'x'*(A.MAX_BYTES+1)):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                for name in A.NAMES:(root/name).write_bytes(b'synthetic')
                if value is None:(root/A.NAMES[0]).unlink()
                else:(root/A.NAMES[0]).write_bytes(value)
                with self.assertRaises(ValueError):A.archive(root)

    def test_archive_hash_receipt_member_hash_and_size(self):
        for field,value in (('archive_sha256','0'*64),('sha256','0'*64),('bytes',0),('bytes',A.MAX_BYTES+1)):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,receipt,record=self.setup(root)
                if field=='archive_sha256':record[field]=value
                else:record['files'][A.NAMES[0]][field]=value
                receipt.write_text(json.dumps(record))
                with self.assertRaises(ValueError):E.extract(archive,receipt,root/'extracted')

    def test_foreign_missing_duplicate_traversal_symlink_and_oversized_members(self):
        for kind in ('foreign','missing','duplicate','traversal','symlink','oversized'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,receipt,record=self.setup(root)
                forged=root/'forged.zip'
                with zipfile.ZipFile(forged,'w') as bundle:
                    for name in A.NAMES:
                        if kind=='missing' and name==A.NAMES[-1]:continue
                        info=zipfile.ZipInfo(name)
                        if kind=='symlink' and name==A.NAMES[0]:info.external_attr=0o120777<<16
                        raw=(root/name).read_bytes()
                        if kind=='oversized' and name==A.NAMES[0]:raw=b'x'*(A.MAX_BYTES+1)
                        bundle.writestr(info,raw)
                    if kind in ('foreign','duplicate','traversal'):bundle.writestr(A.NAMES[0] if kind=='duplicate' else '../escape' if kind=='traversal' else 'foreign.log',b'x')
                record['archive_sha256']=hashlib.sha256(forged.read_bytes()).hexdigest();receipt.write_text(json.dumps(record))
                with self.subTest(kind=kind),self.assertRaises(ValueError):E.extract(forged,receipt,root/'extracted')
                self.assertFalse((root/'extracted').exists())

    def test_duplicate_receipt_unknown_schema_and_scope(self):
        for kind in ('duplicate','schema','scope','extra'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,receipt,record=self.setup(root)
                if kind=='duplicate':receipt.write_text('{"schema":1,"schema":1}')
                else:
                    record[{'schema':'schema','scope':'scope','extra':'foreign'}[kind]]=2
                    receipt.write_text(json.dumps(record))
                with self.assertRaises(ValueError):E.extract(archive,receipt,root/'extracted')

if __name__=='__main__':unittest.main()
