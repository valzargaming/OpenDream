import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import subprocess
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('standalone', Path(__file__).with_name('standalone.py'))
standalone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(standalone)


class StandalonePackageTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix='standalone-contract-')
        self.addCleanup(self.storage.cleanup)
        self.root = Path(self.storage.name)
        self.package, self.source = self.root/'package', self.root/'source'
        for directory in ['auth-loader', 'auth-webview']:
            (self.package/directory).mkdir(parents=True)
        (self.package/'auth-loader/Robust.Client.dll').write_bytes(b'fixture loader')
        (self.package/'auth-webview/module.dll').write_bytes(b'fixture webview')
        resources = self.source/'RobustToolbox/Resources'
        resources.mkdir(parents=True)
        (resources/'engine-resource.yml').write_text('fixture', encoding='utf-8')
        with zipfile.ZipFile(self.package/'Content.Client-provenance.zip', 'w') as archive:
            for name in ['OpenDreamClient.dll', 'OpenDreamClient.pdb', 'OpenDreamShared.dll', 'OpenDreamShared.pdb']:
                archive.writestr('Assemblies/'+name, b'fixture assembly')
            archive.writestr('manifest.yml', 'autoConnect: false')

    def test_default_mount_layout_and_independent_completeness(self):
        receipt = standalone.package_layout(self.package, self.source)
        layout = self.package/'standalone'
        standalone.verify_layout(layout, receipt)
        self.assertTrue((layout/'RobustToolbox/Resources/engine-resource.yml').is_file())
        self.assertTrue((layout/'Resources/manifest.yml').is_file())
        self.assertTrue((layout/'bin/Content.Client/OpenDreamShared.dll').is_file())
        target = layout/'bin/Content.Client/OpenDreamShared.dll'
        target.write_bytes(b'different assembly')
        with self.assertRaisesRegex(ValueError, 'complete build inventory'):
            standalone.verify_layout(layout, receipt)

    def test_missing_engine_resources_is_rejected(self):
        receipt = standalone.package_layout(self.package, self.source)
        (self.package/'standalone/RobustToolbox/Resources/engine-resource.yml').unlink()
        with self.assertRaisesRegex(ValueError, 'complete build inventory'):
            standalone.verify_layout(self.package/'standalone', receipt)

    def test_unexpected_staged_user_data_is_rejected(self):
        receipt = standalone.package_layout(self.package, self.source)
        (self.package/'standalone/user_data').write_text('unexpected', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'complete build inventory'):
            standalone.verify_layout(self.package/'standalone', receipt)

    def test_archive_traversal_never_writes_outside_resources(self):
        with zipfile.ZipFile(self.package/'Content.Client-provenance.zip', 'a') as archive:
            archive.writestr('../../outside.dll', b'unsafe')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            standalone.package_layout(self.package, self.source)
        self.assertFalse((self.root/'outside.dll').exists())

    def test_smoke_uses_pinned_cli_quit_syntax(self):
        receipt = standalone.package_layout(self.package, self.source)
        response = subprocess.CompletedProcess([], 0, 'PASS native identity content sandbox type checks', '')
        with patch.object(standalone.subprocess, 'run', return_value=response) as launch:
            result = standalone.smoke(self.package, 'fake-dotnet', receipt)
        self.assertEqual(launch.call_args.args[0][-3:], ['--self-contained', '--headless', '+quit'])
        self.assertEqual(result['sandboxed_headless_startup'], 'passed')
        self.assertEqual(result['authenticated_join'], 'not run')

    def test_timeout_retains_both_outputs(self):
        receipt = standalone.package_layout(self.package, self.source)
        error = subprocess.TimeoutExpired(['fake-dotnet'], 60, output=b'partial stdout', stderr=b'partial stderr')
        with patch.object(standalone.subprocess, 'run', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'within 60 seconds'):
                standalone.smoke(self.package, 'fake-dotnet', receipt)
        self.assertEqual((self.package/'standalone-startup.log').read_text(encoding='utf-8'),
                         'partial stdoutpartial stderr')


if __name__ == '__main__':
    unittest.main()
