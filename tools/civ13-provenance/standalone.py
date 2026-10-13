"""Reproducible Tools-loader layout and sandboxed, account-free startup check."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import zipfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): {'sha256': digest(p), 'bytes': p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file()}


def package_layout(package, source):
    """All inputs are the coherent build outputs or its pinned source resources."""
    layout = package / 'standalone'
    if layout.exists():
        raise ValueError('Standalone layout already exists')
    shutil.copytree(package / 'auth-loader', layout / 'RobustToolbox/bin/Client')
    shutil.copytree(package / 'auth-webview', layout / 'auth-webview')
    shutil.copytree(source / 'RobustToolbox/Resources', layout / 'RobustToolbox/Resources')
    (layout / 'Resources').mkdir()
    assemblies = layout / 'bin/Content.Client'
    assemblies.mkdir(parents=True)
    with zipfile.ZipFile(package / 'Content.Client-provenance.zip') as archive:
        names = set()
        for entry in archive.infolist():
            relative = PurePosixPath(entry.filename)
            if (relative.is_absolute() or '..' in relative.parts or '\\' in entry.filename
                    or ':' in entry.filename or entry.filename in names
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe or duplicate client archive entry')
            names.add(entry.filename)
            if entry.is_dir():
                continue
            if relative.parts[0] == 'Assemblies':
                if len(relative.parts) != 2 or relative.name not in {
                    'OpenDreamClient.dll', 'OpenDreamClient.pdb', 'OpenDreamShared.dll', 'OpenDreamShared.pdb'}:
                    raise ValueError('Unexpected client assembly')
                target = assemblies / relative.name
            else:
                target = layout / 'Resources' / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as stream, target.open('wb') as output:
                shutil.copyfileobj(stream, output)
    files = inventory(layout)
    for required in ['RobustToolbox/bin/Client/Robust.Client.dll', 'Resources/manifest.yml',
                     'bin/Content.Client/OpenDreamClient.dll', 'bin/Content.Client/OpenDreamShared.dll']:
        if required not in files:
            raise ValueError('Missing standalone input: ' + required)
    if not any(p.startswith('RobustToolbox/Resources/') for p in files):
        raise ValueError('Missing pinned engine Resources')
    receipt = {'schema': 1, 'loader': 'RobustToolbox/bin/Client/Robust.Client.dll',
               'webview': 'auth-webview', 'files': files}
    (package / 'standalone-layout.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def verify_layout(root, receipt):
    if receipt.get('schema') != 1 or inventory(root) != receipt['files']:
        raise ValueError('Standalone layout differs from the complete build inventory')


def smoke(package, dotnet, receipt):
    """No server connection, native observation, saved account or graphical acceptance."""
    verify_layout(package / 'standalone', receipt)
    with tempfile.TemporaryDirectory(prefix='sandboxed-client-startup-') as directory:
        isolated = Path(directory) / 'standalone'
        shutil.copytree(package / 'standalone', isolated)
        environment = {k: v for k, v in os.environ.items()
                       if k.upper() != 'ROBUST_DISABLE_SANDBOX' and not k.upper().startswith('ROBUST_AUTH_')
                       and not k.upper().startswith('ROBUST_CVAR_')}
        environment['ROBUST_MODULE_ROBUST_CLIENT_WEBVIEW'] = str(isolated / receipt['webview'])
        command = [dotnet, str(isolated / receipt['loader']), '--self-contained', '--headless', '--exec', 'quit']
        try:
            result = subprocess.run(command, cwd=isolated, env=environment, text=True,
                                    capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('Sandboxed client startup did not exit within 60 seconds') from error
        text = result.stdout + result.stderr
        (package / 'standalone-startup.log').write_text(text, encoding='utf-8')
        if (result.returncode or 'PASS native identity content sandbox type checks' not in text
                or any(marker in text for marker in ['[ERRO]', '[FATL]', 'Unhandled exception', 'not whitelisted'])):
            raise RuntimeError('Standalone client startup or sandbox verification failed; see standalone-startup.log')
    return {'sandboxed_headless_startup': 'passed', 'native_observation': 'not run',
            'authenticated_join': 'not run', 'rendering': 'not run', 'save_acceptance': 'not run'}
