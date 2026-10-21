"""Synthetic stopped-evidence parser controls, never native host evidence."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gaia_verify',HERE/'verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class VerifyTests(unittest.TestCase):
    def run_case(self,mutation=None):
        with tempfile.TemporaryDirectory(prefix='gaia-evidence-parser-') as name:
            p=Path(name);(p/'map_saves').mkdir()
            shards=[]
            for shard in ['1.sav','2.sav']:
                path=p/'map_saves'/shard;path.write_text(shard)
                shards.append(dict(shard=shard,bytes=path.stat().st_size,sha256=v.sha(path)))
            profile=dict(captureEnd='Completed',captureActive=False,capExcluded=0,samplingCompleteForSelectedCalls=True,
                         exactResourcePath=None,origins=[dict(name='Close',completed=2,failed=0)])
            (p/'gaia-save-profile.json').write_text(json.dumps(profile))
            (p/'new_process_SAVE_result.txt').write_text('PASS: SAVE explicit production persistence probe')
            (p/'map_saves/save_complete.txt').write_text('fixture')
            guard=dict(success=True,failures=[],cleanup_errors=[],owned_exits=[dict(pid=1,exit_code=0)],commands=[dict(exit_code=0)])
            files=[]
            for role in ['test_binary','runtime_binary','sdk_executable','full_game_json','host_source','compiler_binary']:
                path=p/role;path.write_text('synthetic '+role);files.append(dict(role=role,path=str(path),sha256=v.sha(path)))
                if role=='host_source':
                    path.write_bytes((HERE.parents[1]/'Content.IntegrationTests/GaiaSaveCostHostTests.cs').read_bytes())
                    files[-1]['sha256']=v.sha(path)
            pins=dict(engine_head=v.HEAD,game_manifest_sha256=v.GAME,host_test_name=v.TEST,sdk_version='10.0.401',
                      start_gate='explicit-root-start',source_and_binary_build_binding_verified=True,files=files,
                      profile_file_sha256=v.sha(p/'gaia-save-profile.json'))
            log=['GAIA_SAVE_PROFILE '+json.dumps(profile),'GAIA_SAVE_STOPPED_AUDIT '+json.dumps(dict(hashesStable=True,openOwned=0,dirtyOwned=0,postSealNaturalTicks=10,postSealElapsedDeciseconds=10))]
            log+=['GAIA_SAVE_SHARD '+json.dumps(x) for x in shards]
            log+=['GAIA_SAVE_SCALARS '+json.dumps(dict(label=x,engineThread=1)) for x in ['before','logical-completion','after-before-seal','stopped-audit']]
            if mutation:mutation(p,profile,guard,pins,log)
            (p/'host.log').write_text('\n'.join(log))
            cls,method=v.TEST.rsplit('.',1)
            (p/'test.trx').write_text('<TestRun><UnitTestResult testId="fixture-id" testName="'+method+'" outcome="Passed"/>'
                '<UnitTest id="fixture-id"><TestMethod className="'+cls+'" name="'+method+'" adapterTypeName="executor://nunit3testexecutor/"/></UnitTest></TestRun>')
            (p/'guard.json').write_text(json.dumps(guard));(p/'pins.json').write_text(json.dumps(pins))
            return v.verify(p,p/'host.log',p/'test.trx',p/'guard.json',p/'pins.json')
    def test_positive(self):self.assertTrue(self.run_case()['both_shards_unchanged_through_owned_process_exit'])
    def test_late_write(self):
        with self.assertRaises(AssertionError):self.run_case(lambda p,*_: (p/'map_saves/2.sav').write_text('late'))
    def test_missing_shard(self):
        with self.assertRaises(FileNotFoundError):self.run_case(lambda p,*_: (p/'map_saves/2.sav').unlink())
    def test_guard_failure(self):
        with self.assertRaises(AssertionError):self.run_case(lambda p,pr,g,*_:g.update(success=False))
    def test_caps(self):
        def mutant(p,profile,g,pins,log):profile['capExcluded']=1;log[0]='GAIA_SAVE_PROFILE '+json.dumps(profile)
        with self.assertRaises(AssertionError):self.run_case(mutant)
    def test_short_postseal_observation_rejected(self):
        def mutant(p,profile,g,pins,log):
            log[1]='GAIA_SAVE_STOPPED_AUDIT '+json.dumps(dict(hashesStable=True,openOwned=0,dirtyOwned=0,postSealNaturalTicks=2,postSealElapsedDeciseconds=2))
        with self.assertRaises(AssertionError):self.run_case(mutant)
    def test_runtime_failures(self):
        def mutant(p,profile,g,pins,log):profile['origins'][0]['failed']=1;log[0]='GAIA_SAVE_PROFILE '+json.dumps(profile)
        with self.assertRaises(AssertionError):self.run_case(mutant)
    def test_wrong_source(self):
        with self.assertRaises(AssertionError):self.run_case(lambda p,pr,g,pins,*_:pins.update(engine_head='other'))
    def test_failure_oracle(self):
        with self.assertRaises(AssertionError):self.run_case(lambda p,*_: (p/'new_process_probe_failure.txt').write_text('FAIL'))
if __name__=='__main__':unittest.main()
