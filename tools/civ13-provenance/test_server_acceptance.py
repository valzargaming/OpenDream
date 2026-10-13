import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('server_acceptance', Path(__file__).with_name('server_acceptance.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
HEAD = 'a' * 40


class FileDistribution(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix='server-acceptance-fixture-')
        self.addCleanup(self.storage.cleanup)
        self.root = Path(self.storage.name)/'source'
        self.output = self.root/'provenance-output'
        self.output.mkdir(parents=True)
        for name in server.REQUIRED:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith('.deps.json'):
                path.write_text(json.dumps({'runtimeTarget': {'name': 'net10.0'},
                    'targets': {'net10.0': {}}, 'libraries': {'fixture': {}}}))
            elif name.endswith('.runtimeconfig.json'):
                path.write_text(json.dumps({'runtimeOptions': {'tfm': 'net10.0'}}))
            else:
                path.write_bytes(('inert fixture ' + name).encode())
        for name in ('RobustToolbox/Resources/engine.yml',
                     'bin/Content.Server/runtimes/win-x64/native/byondcore.dll',
                     'bin/Content.Server/runtimes/linux-x64/native/libbyond.so',
                     'RobustToolbox/bin/Server/transitive-dependency.dll'):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'inert fixture - never loaded')
        client = self.root/'bin/Content.Client/OpenDreamShared.dll'
        client.parent.mkdir(parents=True)
        shared = (self.root/'bin/Content.Server/OpenDreamShared.dll').read_bytes()
        client.write_bytes(shared)
        (self.output/'OpenDreamShared.dll').write_bytes(shared)
        (self.output/'OpenDreamRuntime.dll').write_bytes((self.root/'bin/Content.Server/OpenDreamRuntime.dll').read_bytes())
        self.make_zip(shared)
        (self.output/'sdk.log').write_text('10.0.401\n')
        self.ident = {'engine_head': HEAD, 'engine_tree': 'b' * 40,
                      'robust_head': server.ROBUST, 'robust_auth_patch_sha256': 'c' * 64,
                      'engine_sources': {'Resources/manifest.yml': self.sha(self.root/'Resources/manifest.yml'),
                         'OpenDreamServer/server_config.toml': self.sha(self.root/'bin/Content.Server/server_config.toml')},
                      'robust_sources': {'Resources/engine.yml': self.sha(self.root/'RobustToolbox/Resources/engine.yml')},
                      'submodules': []}
        self.proof = {**copy.deepcopy(self.ident), 'sdk_required': '10.0.401', 'build': 'passed',
                      'standalone_startup': {'sandboxed_headless_startup': 'passed'},
                      'checks': [{'name': name, 'exit': 0} for name in ('sdk', 'build-0', 'build-1', 'build-2')]}
        self.refresh()

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def make_zip(self, shared):
        with zipfile.ZipFile(self.output/'Content.Client-provenance.zip', 'w') as archive:
            archive.writestr('manifest.yml', b'fixture manifest')
            for name in ('OpenDreamClient.dll', 'OpenDreamClient.pdb', 'OpenDreamShared.pdb'):
                archive.writestr('Assemblies/' + name, b'inert fixture')
            archive.writestr('Assemblies/OpenDreamShared.dll', shared)

    def refresh(self):
        self.proof['server_acceptance_inputs'] = server.capture_inputs(self.root, self.output)
        self.proof['artifacts'] = {path.relative_to(self.root).as_posix(): server.file_record(path, server.Budget())
            for path in (self.output/'Content.Client-provenance.zip', self.output/'OpenDreamRuntime.dll',
                         self.output/'OpenDreamShared.dll', self.root/'bin/Content.Server/OpenDreamShared.dll',
                         self.root/'bin/Content.Client/OpenDreamShared.dll')}
        self.save()

    def save(self):
        (self.output/'receipt.json').write_text(json.dumps(self.proof))

    def export(self, budget=None):
        return server.export(self.root, self.output, HEAD, self.sha(self.output/'receipt.json'), budget,
                             identity_reader=lambda root, budget: copy.deepcopy(self.ident))

    def test_positive_actual_copy_hashes_and_complete_native_inventory(self):
        result = self.export()
        self.assertEqual(result['entrypoint'], ['dotnet', 'bin/Content.Server/OpenDreamServer.dll'])
        self.assertEqual(result['runtime_acceptance'], 'not run')
        self.assertFalse(result['installed'])
        self.assertEqual(server.inventory(self.output/'server-acceptance', server.Budget()), result['files'])
        self.assertIn('RobustToolbox/bin/Server/transitive-dependency.dll', result['files'])
        self.assertEqual(len(result['native_files']), 2)
        self.assertEqual(result['files']['server_config.toml'],
                         result['files']['bin/Content.Server/server_config.toml'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.export()

    def test_missing_required_file_control(self):
        (self.root/'bin/Content.Server/OpenDreamServer.dll').unlink()
        self.refresh()  # Even a self-consistent inventory cannot waive required files.
        with self.assertRaisesRegex(ValueError, 'Required acceptance file missing'):
            self.export()
        self.assertFalse((self.output/'server-acceptance').exists())

    def test_provenance_drift_control(self):
        self.ident['engine_tree'] = 'd' * 40
        with self.assertRaisesRegex(ValueError, 'provenance drift: engine_tree'):
            self.export()
        self.assertFalse((self.output/'server-acceptance').exists())

    def test_receipt_tampering_after_successful_build_freeze(self):
        frozen = self.sha(self.output/'receipt.json')
        self.proof['engine_tree'] = 'd' * 40
        self.save()
        with self.assertRaisesRegex(ValueError, 'receipt hash mismatch'):
            server.export(self.root, self.output, HEAD, frozen,
                          identity_reader=lambda root, budget: copy.deepcopy(self.ident))

    def test_postbuild_tamper_and_unexpected_file(self):
        (self.root/'bin/Content.Server/OpenDreamServer.dll').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            self.export()
        (self.root/'bin/Content.Server/new-unexpected.dll').write_bytes(b'unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            self.export()

    def test_unversioned_resource_even_when_receipt_inventory_refreshed(self):
        (self.root/'Resources/user-account.json').write_bytes(b'not versioned')
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'Unversioned|Unexpected/unversioned'):
            self.export()

    def test_client_zip_shared_mismatch_even_when_archive_receipt_refreshed(self):
        self.make_zip(b'wrong shared')
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'client ZIP contract mismatch'):
            self.export()

    def test_native_requirement_cannot_be_waived_by_inventory(self):
        for path in (self.root/'bin/Content.Server/runtimes').rglob('*'):
            if path.is_file():
                path.unlink()
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'native inventory missing'):
            self.export()

    def test_limits_deadline_and_failed_build(self):
        with self.assertRaisesRegex(ValueError, 'bound exceeded'):
            self.export(server.Budget(files=1))
        with self.assertRaisesRegex(ValueError, 'bound exceeded'):
            self.export(server.Budget(bytes_limit=1))
        with self.assertRaisesRegex(ValueError, 'bound exceeded'):
            self.export(server.Budget(timeout=-1))
        self.proof['build'] = 'failed'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Passed exact-head'):
            self.export()

    def test_bad_runtime_metadata_even_when_inventory_refreshed(self):
        (self.root/'bin/Content.Server/OpenDreamServer.runtimeconfig.json').write_text('{}')
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'runtime metadata'):
            self.export()

    def test_symlink_rejected_without_following(self):
        target = self.root/'Resources/linked'
        try:
            target.symlink_to(self.root/'bin/Content.Server/OpenDreamServer.dll')
        except (OSError, NotImplementedError):
            self.skipTest('Host cannot create fixture symlinks')
        with self.assertRaisesRegex(ValueError, 'Symlink/reparse'):
            self.export()

    def test_output_overlap(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            server.export(self.root, self.root/'Resources', HEAD, self.sha(self.output/'receipt.json'),
                identity_reader=lambda root, budget: copy.deepcopy(self.ident))


if __name__ == '__main__':
    unittest.main()
