"""File-only mutations and strict TRX oracle for a separately authorized engine checkout."""
import argparse
import hashlib
import json
import subprocess
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_argument_verify', HERE.parent / 'native_argument_ownership' / 'verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BASELINE_COMMIT = 'e96f60769ae38e05599119b4f5ed1fcb2cb8a91b'
EXPECTED_CANDIDATE_HASHES = {
    'OpenDreamRuntime/Objects/DreamObject.cs': 'f44279ad182b66f0eed33ad09d2e32a9e2e82a4b71e826f624c15a9f74e6f824',
    'OpenDreamRuntime/Procs/DMOpcodeHandlers.cs': '7f3ffd180fa5facbce09bd661524b22bc673d922de461c8bde6897eb0c66fba0',
    'OpenDreamRuntime/Procs/InitDreamObject.cs': 'b76207eaf0fa47e3063d0b4022f809f23c0bff82cc317719d01e1b1d4e1b87d5',
}
CONTROL_OPTIONS = {
    'rejected-dispose': dict(marker='Rejected object initialization releases input owner', expressions=('payload.RefCount',), expected=1, actual=2),
    'factory-guard': dict(marker='Rejected object initialization releases input owner', expressions=('payload.RefCount',), expected=1, actual=2),
    'opcode-guard': dict(marker='Rejected new opcode retains no creator owner', expressions=('retainedCreatorCount',), expected=0, actual=1),
}

def verify(control, trx, log, exit_code):
    return module.verify(trx, log, exit_code, **CONTROL_OPTIONS[control],
        fixture_method='ObjectInitializationReleasesOwnedValues', fixture_file='GameTests.ObjectInitialization.cs')

def mutate(root, control):
    actual_head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in EXPECTED_CANDIDATE_HASHES}
    if before != EXPECTED_CANDIDATE_HASHES:
        raise ValueError('Control requires exact reviewed production candidate bytes')
    if control == 'rejected-dispose':
        path = root / 'OpenDreamRuntime/Procs/InitDreamObject.cs'
        old = '        arguments.Dispose();\n        throw new ArgumentException("Destination is too short.", "destination");'
        new = '        // Strict negative control: omit rejected-input disposal.\n        throw new ArgumentException("Destination is too short.", "destination");'
    elif control == 'factory-guard':
        path = root / 'OpenDreamRuntime/Objects/DreamObject.cs'
        old = '        InitDreamObjectState.ValidateArguments(arguments);\n'
        new = ''
    else:
        factory = (root / 'OpenDreamRuntime/Objects/DreamObject.cs').read_text()
        if factory.count('        InitDreamObjectState.ValidateArguments(arguments);\n') != 1:
            raise ValueError('Opcode control requires intact factory guard')
        path = root / 'OpenDreamRuntime/Procs/DMOpcodeHandlers.cs'
        old = '            InitDreamObjectState.ValidateArguments(newArguments);\n'
        new = ''
    content = path.read_text()
    if content.count(old) != 1:
        raise ValueError('Control target is not unique')
    path.write_text(content.replace(old, new), encoding='utf-8', newline='\n')
    receipt = {
        'control': control,
        'baseline_commit': BASELINE_COMMIT,
        'actual_checkout_head': actual_head,
        'reviewed_candidate_sha256': before,
        'mutated_path': path.relative_to(root).as_posix(),
        'mutated_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'expected_assertion': CONTROL_OPTIONS[control],
        'execution': 'file mutation only; engine test must have its own TRX/log receipt',
    }
    (root / ('object-initialization-control-' + control + '.json')).write_text(
        json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('control', choices=CONTROL_OPTIONS)
    parser.add_argument('--root', type=pathlib.Path)
    parser.add_argument('--trx', type=pathlib.Path)
    parser.add_argument('--log', type=pathlib.Path)
    parser.add_argument('--exit-code', type=int)
    args = parser.parse_args()
    if args.trx:
        if not args.log or args.exit_code is None:
            parser.error('--trx requires --log and --exit-code')
        verify(args.control, args.trx, args.log.read_text(errors='replace'), args.exit_code)
        print('EXACT INTENDED OBJECT INITIALIZATION OMISSION REJECTED:', args.control)
    elif args.root:
        mutate(args.root, args.control)
    else:
        parser.error('Supply --root for a file-only mutation, or --trx for verification')
