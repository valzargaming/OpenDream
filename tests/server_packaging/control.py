"""Strict source omission controls for the actual linked packaging helper."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HELPER = 'OpenDreamPackageTool/ContentAssemblySelection.cs'
BASE_HEAD = 'ebc7a8289e7aea4ca1d2ed7c6c296ba97706649d'
BASE_HASH = '20d0cf5b2cb6adc070d27b71098fe37c62c3209ffbbc970cc1a24dcb0d10ec42'
MARKERS = {'dedup': 'unique-overlap', 'prefix': 'source-relative-prefix',
           'required': 'required-missing-retained'}
SUCCESS = ('PACKAGING SELECTION PASSED: actual linked production helper; overlap, '
           'prefix, exclusions, order, copy, required missing, optional PDB')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return data.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')


def replace_unique(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Mutation anchor must occur exactly once')
    return source.replace(old, new, 1)


def mutate(source, control):
    if control == 'dedup':
        source = replace_unique(source,
            '        var seen = new HashSet<string>(StringComparer.Ordinal);\n', '')
        source = replace_unique(source,
            '!excluded.Any(prefix => filename.StartsWith(prefix, StringComparison.Ordinal)) &&\n'
            '                seen.Add(filename))',
            '!excluded.Any(prefix => filename.StartsWith(prefix, StringComparison.Ordinal)))')
        source = replace_unique(source, 'if (seen.Add(dll))', 'if (true)')
        return replace_unique(source, ' && seen.Add(pdb)', '')
    if control == 'prefix':
        return replace_unique(source, '.Select(Path.GetFileName)', '.Select(path => path)')
    if control == 'required':
        return replace_unique(source, 'if (seen.Add(dll))',
            'if (File.Exists(Path.Combine(sourceDir, dll)) && seen.Add(dll))')
    if control == 'positive':
        return source
    raise ValueError('Unknown control')


def verify_receipt(receipt, control, head, after_hash):
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise ValueError('Exact candidate commit required')
    if receipt.get('control') != control or receipt.get('candidateHead') != head:
        raise ValueError('Wrong control or candidate head')
    if receipt.get('baselineHead') != BASE_HEAD or receipt.get('baselineSourceSha256') != BASE_HASH:
        raise ValueError('Wrong immutable source baseline')
    for field in ('candidateHelperSha256', 'mutatedHelperSha256'):
        if not re.fullmatch('[0-9a-f]{64}', receipt.get(field, '')):
            raise ValueError('Full source hashes required')
    if receipt['mutatedHelperSha256'] != after_hash:
        raise ValueError('Receipt does not match actual tested helper')
    if (receipt['candidateHelperSha256'] == after_hash) != (control == 'positive'):
        raise ValueError('Control mutation identity mismatch')
    sources = receipt.get('candidateSourceHashes', {})
    required = (HELPER, 'OpenDreamPackageTool/ServerPackaging.cs',
                'tests/server_packaging/SelectionProbe.cs',
                'tests/server_packaging/SelectionProbe.csproj')
    if set(sources) != set(required) or any(not re.fullmatch('[0-9a-f]{64}', value)
                                           for value in sources.values()):
        raise ValueError('Full linked candidate source hashes required')
    if sources[HELPER] != receipt['candidateHelperSha256']:
        raise ValueError('Inconsistent candidate helper hash')


def verify_result(log, exit_code, control):
    lines = [line for line in log.splitlines() if line.strip()]
    if control == 'positive':
        if exit_code != 0 or lines != [SUCCESS]:
            raise ValueError('Positive run must succeed exactly, without extra errors/output')
        return
    expected = 'System.InvalidOperationException: PACKAGING ASSERTION: ' + MARKERS[control]
    if exit_code != 1 or not lines or lines[0] != expected:
        raise ValueError('Intended assertion and exact failing process exit required')
    if log.count('PACKAGING ASSERTION:') != 1 or SUCCESS in log:
        raise ValueError('Exactly one intended assertion required')
    if len(lines) != 3 or not re.fullmatch(
            r'   at SelectionProbe.Require\(Boolean condition, String marker\) in .*[\\/]SelectionProbe.cs:line [1-9][0-9]*', lines[1]) or not re.fullmatch(
            r'   at SelectionProbe.Main\(\) in .*[\\/]SelectionProbe.cs:line [1-9][0-9]*', lines[2]):
        raise ValueError('Only the intended Require/Main assertion stack is permitted')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('control', choices=['positive', *MARKERS])
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--exit-code', type=int)
    parser.add_argument('--head', required=True)
    parser.add_argument('--receipt', type=Path, default=ROOT / 'packaging-control-source.json')
    args = parser.parse_args()
    actual_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if actual_head != args.head:
        raise ValueError('Checkout differs from requested exact candidate head')
    helper = ROOT / HELPER
    if args.verify:
        receipt = json.loads(args.receipt.read_text())
        verify_receipt(receipt, args.control, args.head, digest(helper.read_bytes()))
        # The remote workflow uses Linux checkout bytes (no CRLF conversion).
        # Authenticate every pre-mutation hash against the exact commit object.
        for path, expected in receipt['candidateSourceHashes'].items():
            committed = subprocess.check_output(['git', 'show', args.head + ':' + path], cwd=ROOT)
            if digest(committed) != expected:
                raise ValueError('Candidate receipt differs from immutable commit source: ' + path)
        contract = json.loads((ROOT / 'tests/server_packaging/source-contract.json').read_text())
        if digest(canonical(helper.read_bytes())) != contract['canonicalControlHashes'][args.control]:
            raise ValueError('Actual mutation does not match the frozen control source')
        for path, expected in contract['canonicalSourceHashes'].items():
            if path != HELPER and digest(canonical((ROOT / path).read_bytes())) != expected:
                raise ValueError('Linked probe/caller source changed: ' + path)
        verify_result(args.verify.read_text(errors='strict'), args.exit_code, args.control)
        print('STRICT PACKAGING RESULT ACCEPTED:', args.control)
        return
    contract = json.loads((ROOT / 'tests/server_packaging/source-contract.json').read_text())
    paths = [HELPER, 'OpenDreamPackageTool/ServerPackaging.cs',
             'tests/server_packaging/SelectionProbe.cs', 'tests/server_packaging/SelectionProbe.csproj']
    for path in paths:
        if digest(canonical((ROOT / path).read_bytes())) != contract['canonicalSourceHashes'][path]:
            raise ValueError('Candidate source drift or stacked mutation: ' + path)
    before = helper.read_bytes()
    changed = mutate(canonical(before).decode(), args.control)
    if args.control != 'positive':
        helper.write_bytes(changed.encode())
    receipt = dict(control=args.control, candidateHead=args.head, baselineHead=BASE_HEAD,
                   baselineSourceSha256=BASE_HASH, candidateHelperSha256=digest(before),
                   mutatedHelperSha256=digest(helper.read_bytes()),
                   candidateSourceHashes={path: digest((ROOT / path).read_bytes()) for path in paths})
    receipt['candidateSourceHashes'][HELPER] = digest(before)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print('PACKAGING SOURCE RECEIPT:', args.control)


if __name__ == '__main__':
    main()
