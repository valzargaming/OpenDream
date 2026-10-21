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
PRODUCTION = 'OpenDreamRuntime/Procs/DMOpcodeHandlers.CallExt.cs'
BASELINE_BLOB = '2f785444c267e1eb00486934c948a79fd1ed3405'
BASELINE_HASH = '46b6cce48a56a23deeb7dccabff2132100e3407acd6dd2c508809931e960cfb2'
CANDIDATE_HASH = '90a62947bd570231faad0b24efed87f189d1d7453cb9c519ff0b8f16c5ef6d01'
FIXTURE_HASHES = {'Content.IntegrationTests/GameTests.cs': '8890b994a6b8aae212f414262503e3b45925694f79469f181c0285af8140f25b', 'Content.IntegrationTests/GameTests.CallExt.cs': '45368e7375120862fc3a237c5ab85a4dc573a9a54030bf9b76a3bc7b5943b22d', 'Content.IntegrationTests/DMProject/code.dm': '446623e93b65fd8ca3a5d1ca9fe219cf8ca0ef909e97321489dc389dd051d840', 'tests/native_argument_ownership/verify.py': 'ff9ba7da2224604cd45d170e15aa3131061ef7aef56a367ea93f204e278be960'}
OPTIONS = {
    'string-omit': dict(marker='External call releases argument owner: call_ext_string_rejection_probe', expected=1, actual=2),
    'byond-omit': dict(marker='External call releases argument owner: call_ext_byond_rejection_probe', expected=1, actual=2),
}
spec = importlib.util.spec_from_file_location('native_verify', ROOT / 'tests/native_argument_ownership/verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def digest(data): return hashlib.sha256(data).hexdigest()

def verify(control, trx, log, exit_code):
    return module.verify(trx, log, exit_code, **OPTIONS[control], expressions=('payload.RefCount',),
        fixture_method='ExternalCallRejectionsReleaseArguments', fixture_file='GameTests.CallExt.cs')

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
    marker='External call ownership: 1000 caught string and BYOND ABI resolver rejections passed'
    if marker not in combined: raise ValueError('Missing completed production fixture marker')
    return True

def mutation(source, control, baseline_bytes=None):
    if digest(source) != CANDIDATE_HASH:
        raise ValueError('Not the exact reviewed production candidate')
    if control == 'positive': return source
    names={'string-omit':'stringArguments','byond-omit':'byondArguments'}
    if control not in names: raise ValueError('Unknown control')
    target=('        using var '+names[control]+' = arguments;\n').encode()
    if source.count(target)!=1: raise ValueError('Mutation target is not unique')
    return source.replace(target,b'',1)

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
    receipt_path=root/'call-ext-control-source.json'
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
            print('ACTUAL CALL-EXT OWNERSHIP FIXTURE PASSED')
        else:
            verify(args.control,args.trx,args.verify.read_text(errors='replace'),args.exit_code)
            print('EXACT INTENDED CALL-EXT CONTROL REJECTED:',args.control)
    else:
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        mutated=mutation(source,args.control,baseline_bytes)
        (root/PRODUCTION).write_bytes(mutated)
        receipt_path.write_text(json.dumps(receipt(args.control,head,source,mutated,hashes),indent=2)+'\n',encoding='utf-8')
