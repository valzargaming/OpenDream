"""Apply only the declared fork patch to the exact pinned engine revision."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
robust = root / 'RobustToolbox'
pin = 'af2a7d0406b410c4d960f0f4b34513651c6dc742'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=robust, text=True).strip()
if head != pin:
    raise SystemExit('Trusted native host requires the pinned Robust revision')
patch = (root / 'tools/civ13-provenance/robust-auth.patch').read_bytes().replace(b'\r\n', b'\n')
with tempfile.TemporaryDirectory(prefix='declared-robust-patch-') as directory:
    path = Path(directory) / 'declared.patch'
    path.write_bytes(patch)
    reverse = subprocess.run(['git', 'apply', '--reverse', '--check', str(path)], cwd=robust, capture_output=True)
    if reverse.returncode:
        subprocess.run(['git', 'apply', '--check', str(path)], cwd=robust, check=True)
        subprocess.run(['git', 'apply', str(path)], cwd=robust, check=True)
effective = subprocess.check_output(['git', 'diff', '--no-ext-diff', '--no-color', '--binary',
                                     '--abbrev=7', '--no-renames', 'HEAD'], cwd=robust)
if effective.replace(b'\r\n', b'\n') != patch:
    raise SystemExit('Robust effective diff differs from the exact declared fork patch')
print('PASS pinned trusted client host patch')
