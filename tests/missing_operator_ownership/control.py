"""Strict source mutations and structured assertion oracle; no engine invocation."""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = '38c2ca104a2151e4223e1f889e2fc754a921921b'
PRODUCTION = 'OpenDreamRuntime/Objects/DreamObject.cs'
BASELINE_BLOB = 'ba857682c8627c530aa70405141024da6ec5e4a8'
BASELINE_HASH = 'f44279ad182b66f0eed33ad09d2e32a9e2e82a4b71e826f624c15a9f74e6f824'
CANDIDATE_HASH = '0338a6aaa6a8b1391bb2240117756076c2ee23809308dc078c04659fe72b7ed4'
FIXTURE_HASHES = {'Content.IntegrationTests/GameTests.cs': '2e57e4ee43f384647721017b1123d8a155a5a5e7660c7d9f60d5dc86841b35f3', 'Content.IntegrationTests/GameTests.MissingOperators.cs': '6889e1105578334707162f77f8b04d737e26e2c3f90944001545480b2d5f46a1', 'Content.IntegrationTests/DMProject/code.dm': 'f682a1b3ed2946205cdf292a6b5f9670770274e81df538650061842677e4712f', 'tests/native_argument_ownership/verify.py': 'ff9ba7da2224604cd45d170e15aa3131061ef7aef56a367ea93f204e278be960'}
OPTIONS = {
    'baseline': dict(marker='Supported operator releases payload owner: operator_multiply_fallback_probe', expected=1, actual=2),
    'missing-dispose': dict(marker='Supported operator releases payload owner: operator_divide_fallback_probe', expected=1, actual=2),
    'divide-reuse': dict(marker='Supported operator releases payload owner: operator_divide_fallback_probe', expected=1, actual=0),
}
spec = importlib.util.spec_from_file_location('native_verify', ROOT / 'tests/native_argument_ownership/verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def digest(data): return hashlib.sha256(data).hexdigest()

def verify(control, trx, log, exit_code):
    return module.verify(trx, log, exit_code, **OPTIONS[control], expressions=('payload.RefCount',),
        fixture_method='SupportedOperatorFallbacksReleaseOwners', fixture_file='GameTests.MissingOperators.cs')

def verify_positive(trx, log, exit_code):
    if exit_code != 0: raise ValueError('Positive test did not exit0')
    root=ET.parse(trx).getroot();ns=module.NS
    results=root.findall('t:Results/t:UnitTestResult',ns)
    if len(results)!=1 or results[0].get('testName')!='NoRuntimesTest' or results[0].get('outcome')!='Passed':
        raise ValueError('Positive must contain one passed NoRuntimesTest')
    definitions=root.findall('t:TestDefinitions/t:UnitTest',ns)
    if len(definitions)!=1 or definitions[0].get('id')!=results[0].get('testId'):
        raise ValueError('Wrong positive definition')
    method=definitions[0].find('t:TestMethod',ns)
    if method is None or method.get('className')!='Content.IntegrationTests.GameTests' or method.get('name')!='NoRuntimesTest':
        raise ValueError('Wrong positive test method')
    counters=root.find('t:ResultSummary/t:Counters',ns)
    if counters is None: raise ValueError('Missing positive counters')
    for key,value in dict(total=1,executed=1,passed=1,failed=0).items():
        if int(counters.get(key,'-1'))!=value: raise ValueError('Wrong positive counters')
    for key in ('error','timeout','aborted','inconclusive','notRunnable','disconnected'):
        if int(counters.get(key,'0'))!=0: raise ValueError('Positive runner error')
    if root.findall('.//t:ErrorInfo',ns) or root.findall('t:ResultSummary/t:RunInfos/t:RunInfo[@outcome="Error"]',ns):
        raise ValueError('Positive contains error')
    combined=log+'\n'+'\n'.join(root.itertext())
    if module.UNRELATED_ERROR.search(combined): raise ValueError('Unrelated positive engine/runner error')
    for marker in ('Supported operator ownership: 1000 division/multiplication fallbacks and defined precedence/index branches passed',
                   'Missing operator ownership: 1000 direct missing-overload iterations passed'):
        if marker not in combined: raise ValueError('Missing completed production fixture marker')
    return True

def mutation(source, control, baseline_bytes=None):
    if digest(source) != CANDIDATE_HASH:
        raise ValueError('Not the exact reviewed production candidate')
    if control == 'positive': return source
    if control == 'baseline':
        if baseline_bytes is None or digest(baseline_bytes) != BASELINE_HASH:
            raise ValueError('Not the immutable baseline bytes')
        # Restore only the two operator portions. Keep constructor validation and
        # every other production byte from the reviewed current-master candidate.
        restored = mutation(source, 'divide-reuse')
        restored = restored.replace(
            b'        if (!TryGetProc(operatorName, out var proc)) {\n            arguments.Dispose();\n',
            b'        if (!TryGetProc(operatorName, out var proc)) {\n')
        if restored != baseline_bytes:
            raise ValueError('Narrow operator baseline does not equal immutable current-master source')
        return restored
    content = source.decode('utf-8')
    if control == 'missing-dispose':
        old = '        if (!TryGetProc(operatorName, out var proc)) {\n            arguments.Dispose();\n'
        new = '        if (!TryGetProc(operatorName, out var proc)) {\n'
    elif control == 'divide-reuse':
        old = '''        if (TryExecuteOperatorOverload(state, "operator/=", new DreamProcArguments(b), out var result))
            return result;

        if (TryExecuteOperatorOverload(state, "operator/", new DreamProcArguments(b), out result))'''
        new = '''        var args = new DreamProcArguments(b);
        if (TryExecuteOperatorOverload(state, "operator/=", args, out var result))
            return result;

        if (TryExecuteOperatorOverload(state, "operator/", args, out result))'''
    else: raise ValueError('Unknown control')
    if content.count(old) != 1: raise ValueError('Mutation target is not unique')
    return content.replace(old, new).encode('utf-8')

def receipt(control, head, source, mutated, fixture_hashes):
    return dict(control=control, baseline_commit=BASELINE, baseline_git_blob=BASELINE_BLOB,
        baseline_sha256=BASELINE_HASH, actual_checkout_head=head, production_path=PRODUCTION,
        reviewed_candidate_sha256=digest(source), mutated_sha256=digest(mutated),
        fixture_sha256=fixture_hashes, expected_assertion=OPTIONS.get(control),
        scope='file-only source mutation; engine execution recorded separately in TRX/log')

def check_receipt(data, control, current_source, fixture_hashes, expected_mutated=None):
    expected = dict(control=control, baseline_commit=BASELINE, baseline_git_blob=BASELINE_BLOB,
        baseline_sha256=BASELINE_HASH, production_path=PRODUCTION,
        reviewed_candidate_sha256=CANDIDATE_HASH, fixture_sha256=FIXTURE_HASHES,
        expected_assertion=OPTIONS.get(control))
    if any(data.get(key) != value for key,value in expected.items()):
        raise ValueError('Wrong control provenance')
    if len(data.get('actual_checkout_head','')) != 40 or any(char not in '0123456789abcdef' for char in data['actual_checkout_head']):
        raise ValueError('Missing exact checkout head')
    if fixture_hashes != FIXTURE_HASHES:
        raise ValueError('Fixture source changed')
    if data.get('mutated_sha256') != digest(current_source):
        raise ValueError('Mutation receipt does not match current source')
    if expected_mutated is not None and digest(current_source) != digest(expected_mutated):
        raise ValueError('Unexpected mutation bytes')
    return True

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('control',choices=['positive',*OPTIONS])
    parser.add_argument('--root',type=pathlib.Path,default=ROOT)
    parser.add_argument('--verify',type=pathlib.Path)
    parser.add_argument('--trx',type=pathlib.Path)
    parser.add_argument('--exit-code',type=int)
    args=parser.parse_args()
    root=args.root
    hashes={name:digest((root/name).read_bytes()) for name in FIXTURE_HASHES}
    if hashes != FIXTURE_HASHES: raise SystemExit('Fixture source differs from reviewed candidate')
    source=(root/PRODUCTION).read_bytes()
    receipt_path=root/'missing-operator-control-source.json'
    baseline_bytes=subprocess.check_output(['git','-C',str(root),'show',BASELINE+':'+PRODUCTION])
    if digest(baseline_bytes) != BASELINE_HASH:
        raise SystemExit('Immutable baseline source hash mismatch')
    if args.verify:
        if args.trx is None or args.exit_code is None:
            parser.error('Verification requires --trx and --exit-code')
        data=json.loads(receipt_path.read_text())
        # Rebuild exact expected mutation from the reviewed blob, rather than trusting a self-reported hash.
        current_head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        if data.get('actual_checkout_head') != current_head:
            raise SystemExit('Receipt head differs from actual checkout')
        reviewed=subprocess.check_output(['git','-C',str(root),'show',data['actual_checkout_head']+':'+PRODUCTION])
        expected=mutation(reviewed,args.control,baseline_bytes)
        check_receipt(data,args.control,source,hashes,expected)
        if args.control == 'positive':
            verify_positive(args.trx,args.verify.read_text(errors='replace'),args.exit_code)
            print('ACTUAL MISSING-OPERATOR OWNERSHIP FIXTURE PASSED')
        else:
            verify(args.control,args.trx,args.verify.read_text(errors='replace'),args.exit_code)
            print('EXACT INTENDED MISSING-OPERATOR CONTROL REJECTED:',args.control)
    else:
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        mutated=mutation(source,args.control,baseline_bytes)
        (root/PRODUCTION).write_bytes(mutated)
        receipt_path.write_text(json.dumps(receipt(args.control,head,source,mutated,hashes),indent=2)+'\n',encoding='utf-8')
