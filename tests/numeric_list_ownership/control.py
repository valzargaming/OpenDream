"""Strict source mutations and structured assertion oracle; no engine invocation."""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = '2e057d36085b0a26d7993f5f8468a8b2c7d1a921'
PRODUCTION = 'OpenDreamRuntime/Objects/Types/DreamList.cs'
BASELINE_BLOB = 'd1d3269785bb5fe8a38fcaa95e01e972296b12d8'
BASELINE_HASH = '872ec67089489fc1f3fdd044a8635131bda293efc96a1648b8a1a8a4083dd48e'
COMPOSED_CANDIDATE_HASH = '380196bc158ade1044094bb414b46bb36266e43e6f6cff5bfa12c9b6e6edb156'
CANDIDATE_HASH = 'c5c3baed5e30333ce63fcd38e2be40d5b3cc07bda4c900171e8da84d0a588e55'
FIXTURE_HASHES = {'Content.IntegrationTests/GameTests.cs': '8890b994a6b8aae212f414262503e3b45925694f79469f181c0285af8140f25b', 'Content.IntegrationTests/GameTests.NumericLists.cs': '9f944b642cc6ec06c01e8085ffec2bcbb757a391496da4c40b114b11a97d542d', 'tests/native_argument_ownership/verify.py': 'ff9ba7da2224604cd45d170e15aa3131061ef7aef56a367ea93f204e278be960'}
OPTIONS = {
    'baseline': dict(marker='Invalid numeric list assignment releases incoming owner', expected=1, actual=2),
    'replace-acquire-omit': dict(marker='Numeric replacement retains incoming owner', expected=2, actual=1),
}

spec = importlib.util.spec_from_file_location('native_verify', ROOT / 'tests/native_argument_ownership/verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def digest(data): return hashlib.sha256(data).hexdigest()

def verify(control, trx, log, exit_code):
    return module.verify(trx, log, exit_code, **OPTIONS[control], expressions=('payload.RefCount',),
        fixture_method='NumericListAssignmentsReleaseOwners', fixture_file='GameTests.NumericLists.cs')

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
    marker='Numeric list ownership: 1000 invalid-index and replacement iterations plus append/sole-owner self-assignment passed'
    if marker not in combined: raise ValueError('Missing completed production fixture marker')
    return True

# Exact additive pool-cap composition. Frozen numeric originals remain authenticated.
CAP_DECL = b'    // Bound idle backing storage without limiting the size of live DM lists.\n    private const int MaximumPooledCapacity = 65_536;\n'
OLD_GUARD = b'_values.Capacity > DreamManager.ListPoolThreshold && ListPool.Count < DreamManager.ListPoolSize'
CAP_GUARD = b'_values.Capacity > DreamManager.ListPoolThreshold && _values.Capacity <= MaximumPooledCapacity\n            && ListPool.Count < DreamManager.ListPoolSize'
POOL_DECL = b'    private static readonly Stack<List<DreamValue>> ListPool = new();\n'

def compose_pool_cap(original):
    if original.count(POOL_DECL) != 1 or original.count(OLD_GUARD) != 1 or b'MaximumPooledCapacity' in original:
        raise ValueError('Unexpected frozen pool source')
    return original.replace(POOL_DECL, POOL_DECL + CAP_DECL, 1).replace(OLD_GUARD, CAP_GUARD, 1)

def frozen_candidate(source):
    if source.count(CAP_DECL) != 1 or source.count(CAP_GUARD) != 1:
        raise ValueError('Missing exact pool-cap composition')
    original = source.replace(CAP_DECL, b'', 1).replace(CAP_GUARD, OLD_GUARD, 1)
    if digest(original) != CANDIDATE_HASH or compose_pool_cap(original) != source or digest(source) != COMPOSED_CANDIDATE_HASH:
        raise ValueError('Not the exact reviewed candidate plus pool cap')
    return original

def mutation(source, control, baseline_bytes=None):
    frozen_candidate(source)
    if control == 'positive': return source
    if control == 'baseline':
        if baseline_bytes is None or digest(baseline_bytes) != BASELINE_HASH: raise ValueError('Wrong immutable baseline')
        return compose_pool_cap(baseline_bytes)
    if control != 'replace-acquire-omit': raise ValueError('Unknown control')
    target=b'                value.IncRef();\n                oldValue.DecRef();'
    if source.count(target)!=1: raise ValueError('Mutation target is not unique')
    return source.replace(target,b'                oldValue.DecRef();',1)

def receipt(control, head, source, mutated, fixture_hashes):
    return dict(control=control, baseline_commit=BASELINE, baseline_git_blob=BASELINE_BLOB,
        baseline_sha256=BASELINE_HASH, actual_checkout_head=head, production_path=PRODUCTION,
        reviewed_candidate_sha256=digest(source), frozen_candidate_sha256=CANDIDATE_HASH,
        pool_cap_composition_sha256=digest(CAP_DECL + CAP_GUARD), mutated_sha256=digest(mutated),
        fixture_sha256=fixture_hashes, expected_assertion=OPTIONS.get(control),
        scope='file-only source mutation; engine execution recorded separately in TRX/log')

def check_receipt(data, control, current_source, fixture_hashes, expected_mutated=None):
    expected = dict(control=control, baseline_commit=BASELINE, baseline_git_blob=BASELINE_BLOB,
        baseline_sha256=BASELINE_HASH, production_path=PRODUCTION,
        reviewed_candidate_sha256=COMPOSED_CANDIDATE_HASH, frozen_candidate_sha256=CANDIDATE_HASH, pool_cap_composition_sha256=digest(CAP_DECL + CAP_GUARD), fixture_sha256=FIXTURE_HASHES,
        expected_assertion=OPTIONS.get(control))
    if any(data.get(key) != value for key,value in expected.items()):
        raise ValueError('Wrong control provenance')
    if len(data.get('actual_checkout_head','')) != 40 or any(char not in '0123456789abcdef' for char in data['actual_checkout_head']):
        raise ValueError('Missing exact checkout head')
    if fixture_hashes != FIXTURE_HASHES:
        raise ValueError('Fixture source changed')
    if data.get('mutated_sha256') != digest(current_source):
        raise ValueError('Mutation receipt does not match current source')
    if len(data.get('reviewed_candidate_sha256', '')) != 64:
        raise ValueError('Missing composed candidate hash')
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
    receipt_path=root/'numeric-list-control-source.json'
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
            print('ACTUAL NUMERIC LIST OWNERSHIP FIXTURE PASSED')
        else:
            verify(args.control,args.trx,args.verify.read_text(errors='replace'),args.exit_code)
            print('EXACT INTENDED NUMERIC LIST CONTROL REJECTED:',args.control)
    else:
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        mutated=mutation(source,args.control,baseline_bytes)
        (root/PRODUCTION).write_bytes(mutated)
        receipt_path.write_text(json.dumps(receipt(args.control,head,source,mutated,hashes),indent=2)+'\n',encoding='utf-8')
