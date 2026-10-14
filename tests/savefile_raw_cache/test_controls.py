"""Pure source/provenance controls; these do not execute C# or DM."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('raw_control',HERE/'control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
ROOT=HERE.parents[1]

class SourceControls(unittest.TestCase):
    def resource(self): return (ROOT/control.RESOURCE).read_bytes().replace(b'\r\n',b'\n')
    def savefile(self): return (ROOT/control.SAVEFILE).read_bytes().replace(b'\r\n',b'\n')
    def test_all_manifest_pins(self):
        import json
        pins=json.loads((HERE/'source-manifest.json').read_text())['sources']
        for path,expected in pins.items():
            self.assertEqual(control.sha((ROOT/path).read_bytes().replace(b'\r\n',b'\n')),expected,path)
    def test_registered_fresh_native_processes_and_receipts(self):
        workflow=(ROOT/'.github/workflows/savefile-raw-cache.yml').read_text()
        self.assertIn('mode: [positive, baseline, omit-release, drop-inmemory]',workflow)
        self.assertIn('FullyQualifiedName=Content.IntegrationTests.SavefileRawCacheTests.DiskReadLifetimeAndIdentity',workflow)
        self.assertIn('FullyQualifiedName=Content.IntegrationTests.GameTests.NoRuntimesTest',workflow)
        self.assertEqual(workflow.count('dotnet test Content.IntegrationTests/Content.IntegrationTests.csproj'),2)
        self.assertIn('archive_logs.py raw-cache-results --verify',workflow)
        self.assertIn('capture.py raw-cache-results --binaries',workflow)
        self.assertIn('include-hidden-files: true',workflow)
    def test_exact_selected_base_production_delta(self):
        import json
        base=json.loads((HERE/'source-manifest.json').read_text())['base_commit']
        original_resource=control.git(ROOT,'show',base+':'+control.RESOURCE)
        original_savefile=control.git(ROOT,'show',base+':'+control.SAVEFILE)
        profile=(ROOT/'tools/save_cost_profile/control.py').read_text()
        import ast
        tree=ast.parse(profile)
        helper=next(ast.literal_eval(item.value) for item in tree.body if isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CACHE_HELPER' for t in item.targets))
        self.assertEqual(self.resource().count(helper),1)
        self.assertEqual(self.resource().replace(helper,b''),original_resource)
        self.assertEqual(control.mutate(self.savefile(),control.SAVEFILE,'baseline'),original_savefile)
        self.assertIn(b'if (text.Length <= 4096)',self.resource())
    def test_positive_byte_identity(self):
        for path,raw in [(control.RESOURCE,self.resource()),(control.SAVEFILE,self.savefile())]:
            self.assertEqual(control.mutate(raw,path,'positive'),raw)
    def test_baseline_only_restores_read(self):
        raw=self.savefile();changed=control.mutate(raw,control.SAVEFILE,'baseline')
        self.assertEqual(changed.replace(b'            var data = Resource.ReadAsString();',control.READ.encode()),raw)
        self.assertIn(b'CreateResourceFromSavefile',changed)
    def test_omission_keeps_finally(self):
        changed=control.mutate(self.savefile(),control.SAVEFILE,'omit-release')
        self.assertIn(b'} finally {\n                // Deliberate omitted disk-cache release.',changed)
        self.assertIn(b'CreateResourceFromSavefile',changed)
    def test_inmemory_guard_is_only_mutation(self):
        raw=self.resource();changed=control.mutate(raw,control.RESOURCE,'drop-inmemory')
        self.assertEqual(changed.replace(b'        ResourceData = null; // Deliberate loss of in-memory resource data.',control.GUARD.encode()),raw)
    def test_setter_tools_accounting_and_embedded_ctor(self):
        text=self.resource().decode();setter=text[text.index('        private set {'):text.index('    private byte[]? _resourceDataBacking;')]
        self.assertIn('_tracyMemoryId?.ReleaseMemory();',setter)
        self.assertIn('Profiler.BeginMemoryZone',setter)
        self.assertIn('this(id, null, null)',text)
        self.assertIn('public virtual string? ReadAsString()',text)
    def test_constructor_branch_and_flush_do_not_change(self):
        savefile=self.savefile();changed=control.mutate(savefile,control.SAVEFILE,'baseline')
        for marker in (b'    protected override void HandleDeletion()',b'    public void Close()',b'    private void Flush('):
            self.assertEqual(changed[changed.index(marker):],savefile[savefile.index(marker):])
    def test_tampered_read_rejected(self):
        with self.assertRaises(AssertionError):control.mutate(self.savefile().replace(b'Resource.ReleaseFileDataCache();',b'Resource.ReloadFromDisk();'),control.SAVEFILE,'positive')
    def test_tampered_guard_rejected(self):
        with self.assertRaises(AssertionError):control.mutate(self.resource().replace(b'string.IsNullOrEmpty(filePath)',b'filePath == null'),control.RESOURCE,'positive')

if __name__=='__main__': unittest.main()
