"""File-only acceptance distribution of already-built, receipt-bound inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time
import zipfile

ROBUST = 'af2a7d0406b410c4d960f0f4b34513651c6dc742'
TREES = ('bin/Content.Server', 'RobustToolbox/bin/Server', 'Resources', 'RobustToolbox/Resources')
REQUIRED = ('bin/Content.Server/OpenDreamServer.dll', 'bin/Content.Server/OpenDreamRuntime.dll',
            'bin/Content.Server/OpenDreamShared.dll', 'bin/Content.Server/DMCompiler.dll',
            'bin/Content.Server/OpenDreamServer.deps.json', 'bin/Content.Server/OpenDreamServer.runtimeconfig.json',
            'bin/Content.Server/server_config.toml', 'RobustToolbox/bin/Server/Robust.Server.dll',
            'RobustToolbox/bin/Server/Robust.Server.deps.json',
            'RobustToolbox/bin/Server/Robust.Server.runtimeconfig.json',
            'Resources/manifest.yml')


class Budget:
    def __init__(self, timeout=300, files=100000, bytes_limit=16 * 1024**3):
        self.deadline = time.monotonic() + timeout
        self.files, self.bytes_limit = files, bytes_limit
        self.used_files = self.used_bytes = 0

    def charge(self, length=0):
        self.used_files += 1
        self.used_bytes += length
        if time.monotonic() >= self.deadline or self.used_files > self.files or self.used_bytes > self.bytes_limit:
            raise ValueError('Acceptance export resource bound exceeded')


def regular(path):
    info = path.lstat()
    if path.resolve() != path.absolute() or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Symlink/reparse input rejected: ' + str(path))
    if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
        raise ValueError('Non-file input rejected: ' + str(path))
    return info


def safe(name):
    path = PurePosixPath(name)
    if not name or name == '.' or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or path.as_posix() != name:
        raise ValueError('Unsafe inventory path: ' + name)
    return path


def file_record(path, budget):
    before = regular(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Required regular file missing: ' + str(path))
    budget.charge(before.st_size)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            if time.monotonic() >= budget.deadline:
                raise ValueError('Acceptance export deadline exceeded')
            h.update(chunk)
    after = regular(path)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Input changed while hashing')
    return {'sha256': h.hexdigest(), 'bytes': before.st_size}


def inventory(root, budget):
    if not stat.S_ISDIR(regular(root).st_mode):
        raise ValueError('Required input tree missing: ' + str(root))
    result = {}
    folded = set()
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders:
            budget.charge()
            regular(Path(directory)/name)
        for name in sorted(files):
            path = Path(directory)/name
            relative = path.relative_to(root).as_posix()
            safe(relative)
            if relative.casefold() in folded:
                raise ValueError('Case-overlapping inventory input')
            folded.add(relative.casefold())
            result[relative] = file_record(path, budget)
    return dict(sorted(result.items()))


def capture_inputs(root, output, budget=None):
    """Called by build.py before marking its coherent build passed."""
    budget = budget or Budget()
    result = {name: inventory(root/name, budget) for name in TREES}
    result['Content.Client-provenance.zip'] = file_record(output/'Content.Client-provenance.zip', budget)
    return result


def identity(root, budget):
    def git(*args, cwd=root):
        remaining = budget.deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Acceptance export deadline exceeded')
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, timeout=min(30, remaining)).strip()

    def sources(directory):
        result = {}
        for name in git('ls-files', '-z', cwd=directory).split('\0'):
            if not name:
                continue
            safe(name)
            path = directory/name
            regular(path)
            if path.is_file():
                result[name] = file_record(path, budget)['sha256']
        return result

    def dependencies(directory):
        result = []
        for entry in git('ls-tree', '-r', '-z', 'HEAD', cwd=directory).split('\0'):
            if not entry.startswith('160000 '):
                continue
            metadata, name = entry.split('\t', 1)
            safe(name)
            child = directory/name
            if git('rev-parse', 'HEAD', cwd=child) != metadata.split()[2]:
                raise ValueError('Nested dependency head drift')
            result.append({'path': child.relative_to(root).as_posix(), 'head': metadata.split()[2],
                           'sources': sources(child)})
            result.extend(dependencies(child))
        return result

    patch = root/'tools/civ13-provenance/robust-auth.patch'
    effective = git('diff', '--no-ext-diff', '--no-color', '--binary', '--abbrev=7', '--no-renames', 'HEAD',
                    cwd=root/'RobustToolbox')
    if effective.replace('\r\n', '\n').strip() != patch.read_text(encoding='utf-8').replace('\r\n', '\n').strip():
        raise ValueError('Robust effective patch drift')
    return {'engine_head': git('rev-parse', 'HEAD'), 'engine_tree': git('rev-parse', 'HEAD^{tree}'),
            'robust_head': git('rev-parse', 'HEAD', cwd=root/'RobustToolbox'),
            'robust_auth_patch_sha256': file_record(patch, budget)['sha256'],
            'engine_sources': sources(root), 'robust_sources': sources(root/'RobustToolbox'),
            'submodules': dependencies(root/'RobustToolbox')}


def check_proof(root, output, proof, head, budget, identity_reader):
    if not re.fullmatch('[0-9a-f]{40}', head) or proof.get('engine_head') != head or proof.get('build') != 'passed' or 'error' in proof:
        raise ValueError('Passed exact-head build receipt required')
    file_record(output/'sdk.log', budget)
    if proof.get('sdk_required') != '10.0.401' or (output/'sdk.log').read_text().strip() != '10.0.401':
        raise ValueError('Exact SDK proof missing')
    checks = proof.get('checks', [])
    for name in ('sdk', 'build-0', 'build-1', 'build-2'):
        matching = [check for check in checks if check.get('name') == name]
        if len(matching) != 1 or matching[0].get('exit') != 0:
            raise ValueError('Successful coherent build check missing: ' + name)
    if proof.get('standalone_startup', {}).get('sandboxed_headless_startup') != 'passed':
        raise ValueError('Prior coherent client proof missing')
    actual = identity_reader(root, budget)
    if actual.get('robust_head') != ROBUST:
        raise ValueError('Pinned Robust head drift')
    for key, value in actual.items():
        expected = proof.get(key)
        if key == 'submodules':
            expected = [{**entry, 'path': entry['path'].replace('\\', '/')} for entry in expected or []]
        if value != expected:
            raise ValueError('Build source provenance drift: ' + key)
    if not re.fullmatch('[0-9a-f]{40}', actual.get('engine_tree', '')):
        raise ValueError('Exact engine tree required')


def check_inputs(root, output, proof, inputs, budget):
    files = {tree + '/' + name: record for tree in TREES for name, record in inputs[tree].items()}
    for name in REQUIRED:
        if name not in files:
            raise ValueError('Required acceptance file missing: ' + name)
    if not inputs['RobustToolbox/Resources']:
        raise ValueError('Required Robust resources missing')
    # Resource trees must contain precisely the versioned, receipt-bound resources.
    for tree, source_key in [('Resources', 'engine_sources'), ('RobustToolbox/Resources', 'robust_sources')]:
        prefix = 'Resources/'
        expected = {name[len(prefix):]: sha for name, sha in proof[source_key].items() if name.startswith(prefix)}
        if {name: record['sha256'] for name, record in inputs[tree].items()} != expected:
            raise ValueError('Unexpected/unversioned source resource: ' + tree)
    config_sha = proof['engine_sources'].get('OpenDreamServer/server_config.toml')
    if files['bin/Content.Server/server_config.toml']['sha256'] != config_sha:
        raise ValueError('Built configuration differs from versioned config')
    for directory, assembly in [('bin/Content.Server', 'OpenDreamServer'),
                                ('RobustToolbox/bin/Server', 'Robust.Server')]:
        deps = json.loads((root/directory/(assembly + '.deps.json')).read_text())
        runtime = json.loads((root/directory/(assembly + '.runtimeconfig.json')).read_text())
        if not isinstance(deps, dict) or not isinstance(deps.get('runtimeTarget'), dict) or \
                not deps['runtimeTarget'].get('name') or not isinstance(deps.get('targets'), dict) or \
                not deps['targets'] or not isinstance(deps.get('libraries'), dict) or not deps['libraries'] or \
                not isinstance(runtime, dict) or not isinstance(runtime.get('runtimeOptions'), dict) or \
                not runtime['runtimeOptions'].get('tfm'):
            raise ValueError('Invalid required runtime metadata')
    artifacts = {name.replace('\\', '/'): record for name, record in proof['artifacts'].items()}
    def attested(path):
        key = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
        if artifacts.get(key) != file_record(path, budget):
            raise ValueError('Coherent artifact hash drift: ' + key)
    for path in (output/'Content.Client-provenance.zip', output/'OpenDreamRuntime.dll', output/'OpenDreamShared.dll',
                 root/'bin/Content.Server/OpenDreamShared.dll', root/'bin/Content.Client/OpenDreamShared.dll'):
        attested(path)
    if file_record(output/'OpenDreamRuntime.dll', budget) != files['bin/Content.Server/OpenDreamRuntime.dll']:
        raise ValueError('Runtime DLL differs from coherent candidate')
    shared = files['bin/Content.Server/OpenDreamShared.dll']
    if file_record(root/'bin/Content.Client/OpenDreamShared.dll', budget) != shared or file_record(output/'OpenDreamShared.dll', budget) != shared:
        raise ValueError('Client/server/candidate Shared mismatch')
    with zipfile.ZipFile(output/'Content.Client-provenance.zip') as archive:
        names = set()
        zip_shared = None
        for entry in archive.infolist():
            safe(entry.filename.rstrip('/'))
            if entry.filename in names or stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError('Unsafe/duplicate client ZIP entry')
            names.add(entry.filename)
            budget.charge(entry.file_size)
            if entry.filename.startswith('Assemblies/') and entry.filename not in {
                    'Assemblies/OpenDreamClient.dll', 'Assemblies/OpenDreamClient.pdb',
                    'Assemblies/OpenDreamShared.dll', 'Assemblies/OpenDreamShared.pdb'}:
                raise ValueError('Unexpected client ZIP assembly')
            if entry.filename == 'Assemblies/OpenDreamShared.dll':
                with archive.open(entry) as stream:
                    h = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1048576), b''):
                        if time.monotonic() >= budget.deadline:
                            raise ValueError('ZIP verification deadline exceeded')
                        h.update(chunk)
                    zip_shared = {'sha256': h.hexdigest(), 'bytes': entry.file_size}
        if zip_shared != shared or not {'manifest.yml', 'Assemblies/OpenDreamClient.dll',
                'Assemblies/OpenDreamClient.pdb', 'Assemblies/OpenDreamShared.pdb'}.issubset(names):
            raise ValueError('Coherent client ZIP contract mismatch')
    natives = {name: record for name, record in files.items() if '/native/' in name and name.lower().endswith(('.dll', '.so', '.dylib'))}
    required_native = 'byondcore.dll' if os.name == 'nt' else 'libbyond.so'
    if not any(Path(name).name == required_native for name in natives):
        raise ValueError('BYOND trampoline native inventory missing')
    return files, natives


def export(root, output, head, receipt_sha256, budget=None, identity_reader=identity):
    root, output = root.absolute(), output.absolute()
    budget = budget or Budget()
    regular(root); regular(output)
    layout = output/'server-acceptance'
    if layout.exists() or layout.is_symlink() or (output/'server-acceptance-layout.json').exists():
        raise ValueError('Acceptance output already exists')
    for tree in TREES:
        source = root/tree
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Acceptance input/output overlap')
    proof_path = output/'receipt.json'
    file_record(proof_path, budget)
    proof_bytes = proof_path.read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', receipt_sha256) or hashlib.sha256(proof_bytes).hexdigest() != receipt_sha256:
        raise ValueError('Frozen successful-build receipt hash mismatch')
    proof = json.loads(proof_bytes)
    check_proof(root, output, proof, head, budget, identity_reader)
    inputs = capture_inputs(root, output, budget)
    if inputs != proof.get('server_acceptance_inputs'):
        raise ValueError('Complete coherent input inventory drift')
    files, natives = check_inputs(root, output, proof, inputs, budget)
    layout.mkdir()
    expected = dict(files)
    expected['Content.Client-provenance.zip'] = inputs['Content.Client-provenance.zip']
    expected['server_config.toml'] = files['bin/Content.Server/server_config.toml']
    for name, record in sorted(expected.items()):
        budget.charge(record['bytes'])
        target = layout/name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = (output/name if name == 'Content.Client-provenance.zip' else
                  root/'bin/Content.Server/server_config.toml' if name == 'server_config.toml' else root/name)
        regular(source)
        with source.open('rb') as stream, target.open('xb') as destination:
            for chunk in iter(lambda: stream.read(1048576), b''):
                if time.monotonic() >= budget.deadline:
                    raise ValueError('Acceptance copy deadline exceeded')
                destination.write(chunk)
    if inventory(layout, budget) != dict(sorted(expected.items())) or capture_inputs(root, output, budget) != inputs or proof_path.read_bytes() != proof_bytes:
        raise ValueError('Acceptance copy/source/proof changed during export')
    result = {'schema': 1, 'kind': 'source-layout acceptance distribution; not official RID/FullRelease package',
              'engine_head': head, 'engine_tree': proof['engine_tree'], 'robust_head': proof['robust_head'],
              'sdk': proof['sdk_required'], 'receipt_sha256': hashlib.sha256(proof_bytes).hexdigest(),
              'robust_auth_patch_sha256': proof['robust_auth_patch_sha256'],
              'entrypoint': ['dotnet', 'bin/Content.Server/OpenDreamServer.dll'], 'cwd': 'server-acceptance',
              'declared_client_zip': 'Content.Client-provenance.zip', 'config': 'server_config.toml',
              'native_files': natives, 'files': expected, 'runtime_acceptance': 'not run', 'installed': False}
    (output/'server-acceptance-layout.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--receipt-sha256', required=True)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    export(Path(__file__).resolve().parents[2], args.output, args.head, args.receipt_sha256, Budget(args.timeout))
    print('PASS receipt-bound server acceptance distribution; runtime acceptance not run')
