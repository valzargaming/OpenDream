"""Apply, or read-only authenticate, only the declared pinned-engine patch."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PIN = 'af2a7d0406b410c4d960f0f4b34513651c6dc742'
PATCH = 'tools/civ13-provenance/robust-auth.patch'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def declared_patch(root):
    committed = git(root, 'cat-file', 'blob', 'HEAD:' + PATCH).replace(b'\r\n', b'\n')
    patch = (root / PATCH).read_bytes().replace(b'\r\n', b'\n')
    if patch != committed:
        raise AssertionError('Declared Robust patch differs from committed source')
    return patch


def verify_prepared(root):
    """Verify exact engine identity and diff without applying or reverting anything."""
    robust = root / 'RobustToolbox'
    if git(robust, 'rev-parse', 'HEAD').decode().strip() != PIN:
        raise AssertionError('Trusted native host requires the pinned Robust revision')
    patch = declared_patch(root)
    effective = git(robust, 'diff', '--ignore-submodules=none', '--no-ext-diff', '--no-color',
                    '--binary', '--abbrev=7', '--no-renames', 'HEAD')
    if effective.replace(b'\r\n', b'\n') != patch:
        raise AssertionError('Robust effective diff differs from the exact declared fork patch')
    if git(robust, 'ls-files', '--others', '--exclude-standard', '-z'):
        raise AssertionError('Unexpected untracked Robust source')


def verify_root_changes(root, changed, allowed):
    """Retain each control's own dirty-source allowance plus the exact host patch."""
    changed, allowed = set(changed), set(allowed)
    if not changed <= allowed | {'RobustToolbox'}:
        raise AssertionError('Unreviewed tracked changes')
    if 'RobustToolbox' in changed:
        verify_prepared(root)


def prepare(root=ROOT):
    robust = root / 'RobustToolbox'
    if git(robust, 'rev-parse', 'HEAD').decode().strip() != PIN:
        raise AssertionError('Trusted native host requires the pinned Robust revision')
    patch = declared_patch(root)
    with tempfile.TemporaryDirectory(prefix='declared-robust-patch-') as directory:
        path = Path(directory) / 'declared.patch'
        path.write_bytes(patch)
        reverse = subprocess.run(['git', 'apply', '--reverse', '--check', str(path)],
                                 cwd=robust, capture_output=True)
        if reverse.returncode:
            subprocess.run(['git', 'apply', '--check', str(path)], cwd=robust, check=True)
            subprocess.run(['git', 'apply', str(path)], cwd=robust, check=True)
    verify_prepared(root)
    print('PASS pinned trusted client host patch')


if __name__ == '__main__':
    prepare()
