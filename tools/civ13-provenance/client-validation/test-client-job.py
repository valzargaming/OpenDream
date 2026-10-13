"""Inert Python-only controls. Run only within a fresh explicit resource lease."""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
if len(sys.argv)>1 and sys.argv[1]=='--grandchild':
    time.sleep(50)
    sys.exit(0)
if len(sys.argv)>1 and sys.argv[1]=='--root':
    output = Path.cwd()
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--grandchild'],creationflags=0x08000000)
    try:
        escaped = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--grandchild'],
                                   creationflags=0x09000000)
    except OSError:
        (output/'breakaway-denied.json').write_text(json.dumps({'denied':True}))
    else:
        # A regression must never leave the attempted test-owned escape alive.
        escaped.terminate()
        escaped.wait(timeout=3)
        (output/'breakaway-denied.json').write_text(json.dumps({'denied':False}))
    time.sleep(50)
    sys.exit(0)

if len(sys.argv)!=2:
    raise SystemExit('Unique output directory required; execution requires a fresh lease')
output = Path(sys.argv[1]).resolve()
if output.exists():
    raise SystemExit('Refuse reused test output')
spec = importlib.util.spec_from_file_location('owned_guard',root/'client-job.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
start = time.monotonic()
if guard.free_bytes()<6*1024**3+128*1024**2+32*1024**2:
    raise SystemExit('Fresh preflight failed; no owned process started')
output.mkdir()
for value in ('',' ','\n'):
    try:
        guard.selector(value)
    except ValueError:
        pass
    else:
        raise AssertionError('Empty/invalid identity was accepted')
identity = 'INERT_SYNTHETIC_IDENTITY_NOT_A_REAL_ACCOUNT'
assert guard.selector(identity)==identity
assert identity not in json.dumps(guard.redacted_arguments(['+launchauth',identity],identity))
assert guard.stop_reason(0,3,1,2,6,5,[]) is None
assert guard.stop_reason(3,3,1,2,6,5,[])=='deadline'
assert guard.stop_reason(0,3,3,2,6,5,[])=='owned-private-cap'
assert guard.stop_reason(0,3,1,2,4,5,[])=='host-free-floor'
assert guard.stop_reason(0,3,1,2,6,5,[123])=='unmeasured-owned-process'
receipts = []
for control,expected in ((None,'deadline'),('private','owned-private-cap'),('floor','host-free-floor'),
                         ('unknown','unmeasured-owned-process'),('assignment','guard-error:OSError'),
                         ('cleanup-query','deadline')):
    assert time.monotonic()-start<20, 'Preserve cleanup budget inside 60-second outer lease'
    result = guard.run_owned([sys.executable,str(Path(__file__).resolve()),'--root'],
                             output/(control or 'containment'),timeout=2,
                             cap=128*1024**2,floor=6*1024**3,
                             preflight=6*1024**3+128*1024**2+32*1024**2,
                             inert_control=control)
    assert result['stop_reason']==expected
    assert not result['remaining_owned_pids'] and result['held_process_exit_confirmed']
    if control=='assignment':
        assert not result['root_resumed']
    else:
        assert result['assigned_before_resume']
    if control=='cleanup-query':
        assert result['cleanup_error'] and not result['all_owned_exit_confirmed']
    else:
        assert result['cleanup_error'] is None and result['all_owned_exit_confirmed']
    if control is None:
        assert len(result['owned_pids_seen'])>=2, 'Actual descendant must be seen in Job'
        assert json.loads((output/'containment/breakaway-denied.json').read_text())['denied']
    receipts.append({'control':control or 'containment','receipt':result})
report = {'elapsed':time.monotonic()-start,'controls':receipts,'selector_refusal':'passed',
          'selector_redaction':'passed','candidate_client_launched':False,
          'dotnet_server_database_access':False,'all_known_test_processes_exited':True}
assert report['elapsed']<60
(output/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'elapsed':report['elapsed'],'controls':len(receipts),'candidate_launched':False}))
