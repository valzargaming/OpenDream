"""Retain byte-exact original runner logs inside a bounded artifact archive."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

NAMES = ('sdk-info.log', 'build.log', 'typesof.log', 'runtime.log')
MAX_BYTES = 8 * 1024 * 1024

def archive(results):
    raw = {}
    for name in NAMES:
        path = results / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise ValueError('missing, symlinked or oversized original log: ' + name)
        raw[name] = path.read_bytes()
        if len(raw[name]) != path.stat().st_size:
            raise ValueError('original log changed during capture: ' + name)
    rows = {name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest()) for name, value in raw.items()}
    output = results / 'original-runner-logs.zip'
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, value in raw.items():
            bundle.writestr(name, value)
    with zipfile.ZipFile(output) as bundle:
        if tuple(bundle.namelist()) != NAMES or any(bundle.read(name) != value for name, value in raw.items()):
            raise ValueError('archive does not preserve exact originals')
    receipt = dict(schema=1, files=rows, archive_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                   scope='byte retention only; test acceptance remains strict TRX and original-log replay')
    with (results / 'original-runner-logs.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    print(json.dumps(archive(parser.parse_args().results)))
