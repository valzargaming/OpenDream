"""Strict observation-only client front-end; a lease file never grants authority.

The exclusive runtime operator must already have a fresh main/capture grant.
No target execution occurs on import or validation failure. Username is supplied
privately in the process environment and excluded from receipts.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import time
from datetime import datetime,timezone

SDK = Path('D:/GitHub/Civ13/data/opendream-trial/sdk/dotnet.exe')
REVIEWED_GUARD_SHA256 = '9CE415A82294288EE950A928B2DB9FBF41255648AE32098AF4EA30EE3DD679E0'
def auth_command(expected_username):
    if not expected_username or not expected_username.strip() or any(c in expected_username for c in '\0\r\n'):
        raise ValueError('Private explicit expected username is required')
    escaped=expected_username.replace('\\','\\\\').replace('"','\\"')
    return '+launchauth "'+escaped+'"'

def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):
            digest.update(chunk)
    return digest.hexdigest()

def local_file(root,name):
    relative=Path(name)
    target=root/relative
    if relative.is_absolute() or '..' in relative.parts or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Review input must stay within the fixed artifact root')
    for item in (target,*target.parents):
        if item.exists() and getattr(item.lstat(),'st_file_attributes',0)&0x400:
            raise ValueError('Reparse points are forbidden in reviewed inputs')
    return target

def validate(proposal,lease,private_selector,root):
    """Pure file/record validation; no client, account or native target loading."""
    if not private_selector or not private_selector.strip() or any(c in private_selector for c in '\0\r\n'):
        raise ValueError('Private explicit expected username is required')
    if lease.get('scope')!='baseline-auth-observation-only' or not lease.get('main_and_capture_grant_confirmed'):
        raise ValueError('Fresh separate observation-only lease is required')
    if lease['source_head']!=proposal['source_head'] or not lease.get('native_paths_reviewed'):
        raise ValueError('Exact source/native-path review is required')
    if not re.fullmatch('[0-9a-f]{40}',proposal['source_head']):
        raise ValueError('Full immutable source SHA required')
    if not lease.get('private_expected_identity_confirmed') or not lease.get('session_config_paths_reviewed'):
        raise ValueError('Private identity and configuration-path review is required')
    end=datetime.fromisoformat(lease['absolute_end_utc'].replace('Z','+00:00')).timestamp()
    remaining=end-time.time()
    if not 30<remaining<=210:
        raise ValueError('Lease must have a remaining execution and cleanup bound <=210 seconds')
    stage=json.loads(local_file(root,lease['staged_receipt']).read_text(encoding='utf-8-sig'))
    if stage['source_head']!=proposal['source_head'] or stage['process_launched']:
        raise ValueError('Exact unused staged receipt required')
    profile=Path(stage['profile']).resolve()
    if profile != (root/('client-only-profile-'+proposal['source_head'][:8])).resolve():
        raise ValueError('Unexpected candidate profile path')
    if not profile.is_relative_to(root.resolve()) or profile.is_symlink():
        raise ValueError('Profile must be a separate local reviewed directory')
    for name,expected in stage['files'].items():
        relative=Path(name)
        target=profile/relative
        if relative.is_absolute() or '..' in relative.parts or target.is_symlink() or not target.resolve().is_relative_to(profile):
            raise ValueError('Unsafe staged path')
        if file_hash(target)!=expected['sha256'] or target.stat().st_size!=expected['bytes']:
            raise ValueError('Staged hash mismatch')
    actual={p.relative_to(profile).as_posix() for p in profile.rglob('*') if p.is_file()}
    if actual!=set(stage['files']):
        raise ValueError('Unexpected staged input/user data')
    executable=Path(proposal['launch_specification_for_review_only']['program']).resolve()
    if executable != SDK.resolve():
        raise ValueError('Executable is outside the fixed SDK allowlist')
    if file_hash(executable).upper()!=proposal['sdk_executable_sha256'].upper():
        raise ValueError('SDK executable hash mismatch')
    guard=root/'client-job.py'
    if file_hash(guard).upper()!=REVIEWED_GUARD_SHA256 or lease['guard_sha256'].upper()!=REVIEWED_GUARD_SHA256:
        raise ValueError('Reviewed containment helper hash mismatch')
    bundle_path=local_file(root,lease['package_receipt'])
    bundle=json.loads(bundle_path.read_text(encoding='utf-8-sig'))
    if file_hash(bundle_path).upper()!=lease['independently_reviewed_package_receipt_sha256'].upper():
        raise ValueError('Package receipt is outside the immutable reviewed allowlist')
    if bundle['engine_head']!=proposal['source_head'] or bundle.get('build')!='passed':
        raise ValueError('Exact successful package required')
    if bundle['authentication_loader'].get('native_path_contract')!='passed; target native loading not run':
        raise ValueError('Module native-path contract is missing')
    if bundle['authentication_loader'].get('named_launch_contract')!='passed; account/database target not accessed':
        raise ValueError('Fail-closed named-auth contract is missing')
    expected_files={}
    for name,expected in bundle['authentication_bundle_files'].items():
        path=Path(name.replace('\\','/'))
        if path.parts[0] not in ('auth-loader','auth-webview') or '..' in path.parts:
            raise ValueError('Unexpected package bundle path')
        prefix='loader' if path.parts[0]=='auth-loader' else 'webview'
        expected_files[Path(prefix).joinpath(*path.parts[1:]).as_posix()]=expected
    mount=[expected for name,expected in bundle['artifacts'].items()
           if name.replace('\\','/').split('/')[-1]=='Content.Client-provenance.zip']
    if len(mount)!=1:
        raise ValueError('Exactly one verified client mount required')
    expected_files['Content.Client.zip']=mount[0]
    if stage['files']!=expected_files:
        raise ValueError('Complete staged profile must match the immutable package inventory')
    command=[str(executable),str(profile/'loader/Robust.Client.dll'),'--self-contained','--mount-zip',
             str(profile/'Content.Client.zip'),'--connect','--connect-address','udp://127.0.0.1:18452',
             auth_command(private_selector)]
    environment=dict(os.environ)
    environment.pop('CIV13_AUTH_EXPECTED_USERNAME',None)
    # The named saved lookup must be the sole source of connection credentials.
    environment.pop('ROBUST_AUTH_USERID',None)
    environment.pop('ROBUST_AUTH_TOKEN',None)
    environment['DOTNET_ROOT']=str(executable.parent)
    environment['ROBUST_MODULE_ROBUST_CLIENT_WEBVIEW']=str(profile/'webview')
    return command,environment,end

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--proposal',type=Path,required=True)
    parser.add_argument('--lease',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    proposal=json.loads(args.proposal.read_text(encoding='utf-8-sig'))
    lease=json.loads(args.lease.read_text(encoding='utf-8-sig'))
    expected=os.environ.get('CIV13_AUTH_EXPECTED_USERNAME','')
    command,environment,end=validate(proposal,lease,expected,root)
    # Baseline PID/start/loaded files/port and absence of competitors must be
    # freshly checked by the runtime owner and pinned in the reviewed lease.
    if not lease.get('fresh_baseline_identity_ports_and_competitor_preflight_confirmed'):
        raise SystemExit('Fresh baseline identity/port/process preflight is required')
    spec=importlib.util.spec_from_file_location('owned_guard',root/'client-job.py')
    guard=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    timeout=min(180,end-time.time()-30)
    if timeout<=0:
        raise SystemExit('Lease exhausted during preflight; no launch')
    receipt=guard.run_owned(command,args.output,timeout=timeout,cap=1024**3,floor=6*1024**3,
                            preflight=int(7.25*1024**3),env=environment,
                            redacted_command=guard.redacted_arguments(command,expected))
    print(json.dumps({'stop_reason':receipt['stop_reason'],'cleanup_error':receipt['cleanup_error']}))
    raise SystemExit(1 if receipt['stop_reason'] or receipt['cleanup_error'] else 0)
