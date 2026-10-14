"""Reusable stopped-generation verifier. Read originals; never launch a host.

Invocation is registered in registry.json. Root-owned guarded caller must invoke
this only after all owned processes have exited and before deleting storage.
"""
import argparse,hashlib,json,importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location('gaia_control',Path(__file__).with_name('verify_control.py'))
_control=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_control)
HEAD='5075c426b2f6f37dccb14b0902bb98780bbd62e1'
GAME='9be2a4d6fd42d52c4dc4a75a526b635f5854aee6cce8ab5193f439e82b3fc278'
TEST='Content.IntegrationTests.GaiaSaveCostHostTests.FullGaiaSaveWindow'
HOST_SOURCE_SHA='bf3aa4081fcc08cd4f2bc6aa5f9ae121fd28fb0254c2ca6234621a36cc690125'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rows(log,prefix):
    return [json.loads(line.split(prefix,1)[1]) for line in log.splitlines() if line.startswith(prefix)]
def verify(root,log_path,trx_path,guard_path,pins_path):
    root=Path(root);log=Path(log_path).read_text(encoding='utf-8-sig')
    guard=json.loads(Path(guard_path).read_bytes());pins=json.loads(Path(pins_path).read_bytes())
    assert guard['success'] and guard['failures']==guard['cleanup_errors']==[]
    assert guard['owned_exits'] and all(x['exit_code']==0 for x in guard['owned_exits'])
    assert len({x['pid'] for x in guard['owned_exits']})==len(guard['owned_exits'])
    assert all(x['exit_code']==0 for x in guard['commands'])
    assert pins['engine_head']==HEAD and pins['game_manifest_sha256']==GAME
    assert pins['host_test_name']==TEST and pins['sdk_version']=='10.0.401'
    assert pins['start_gate']=='explicit-root-start' and pins['source_and_binary_build_binding_verified'] is True
    # Caller receipt must enumerate actual compiled/test/runtime/SDK/JSON source
    # dependencies; expected pins are reviewed before native run, never after.
    assert len(pins['files'])>=6
    assert {'test_binary','runtime_binary','sdk_executable','full_game_json','host_source','compiler_binary'} <= {x['role'] for x in pins['files']}
    for item in pins['files']:assert sha(item['path'])==item['sha256'],item['role']
    assert next(x for x in pins['files'] if x['role']=='host_source')['sha256']==HOST_SOURCE_SHA
    assert _control.result_for_test(trx_path,TEST).attrib['outcome']=='Passed'
    profiles=rows(log,'GAIA_SAVE_PROFILE ');assert len(profiles)==1
    profile=profiles[0]
    assert profile['captureEnd']=='Completed' and not profile['captureActive'] and profile['capExcluded']==0
    assert profile['samplingCompleteForSelectedCalls'] and profile['exactResourcePath'] is None
    assert all(x['failed']==0 for x in profile['origins'])
    assert sum(x['completed'] for x in profile['origins'] if x['name'] in ['Close','DirtyTick'])>=2
    audits=rows(log,'GAIA_SAVE_STOPPED_AUDIT ');assert len(audits)==1
    assert audits[0]['hashesStable'] and audits[0]['openOwned']==audits[0]['dirtyOwned']==0
    shard_rows=rows(log,'GAIA_SAVE_SHARD ');assert len(shard_rows)==2
    assert {x['shard'] for x in shard_rows}=={'1.sav','2.sav'}
    for row in shard_rows:
        path=root/'map_saves'/row['shard']
        assert path.stat().st_size==row['bytes']>0 and sha(path)==row['sha256'],'late or missing shard after process stop'
    assert sha(root/'gaia-save-profile.json')==pins['profile_file_sha256']
    assert not (root/'new_process_probe_failure.txt').exists()
    assert (root/'new_process_SAVE_result.txt').read_text()=='PASS: SAVE explicit production persistence probe'
    assert (root/'map_saves'/'save_complete.txt').is_file()
    scalar=rows(log,'GAIA_SAVE_SCALARS ')
    assert {'before','logical-completion','after-before-seal','stopped-audit'} <= {x['label'] for x in scalar}
    assert len({x['engineThread'] for x in scalar})==1
    return dict(stopped_host_evidence_accepted=True,engine_head=HEAD,game_manifest_sha256=GAME,
        both_shards_unchanged_through_owned_process_exit=True,
        independently_attributed_per_path_flush=False,generation_format_and_fresh_recovery='mandatory-not-established-here',
        retention_acceptance=False,original_hashes={str(p):sha(p) for p in [log_path,trx_path,guard_path,pins_path]})
def main():
    p=argparse.ArgumentParser();p.add_argument('--owned-root',required=True)
    for x in ['log','trx','guard','pins','receipt']:p.add_argument('--'+x,required=True)
    a=p.parse_args()
    try: receipt=verify(a.owned_root,a.log,a.trx,a.guard,a.pins)
    except Exception as error:
        receipt=dict(stopped_host_evidence_accepted=False,error_type=type(error).__name__,reason=str(error),
            partial_originals_preserved=True,full_gaia_acceptance=False)
    # Write only the explicitly caller-owned detached receipt; preserve originals.
    with Path(a.receipt).open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2);f.write('\n')
    return 0 if receipt.get('stopped_host_evidence_accepted') else 1
if __name__=='__main__':raise SystemExit(main())
