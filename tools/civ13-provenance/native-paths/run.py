"""Resolve published native paths without loading target assemblies/libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--dotnet', required=True)
parser.add_argument('--robust', type=Path, required=True)
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
robust, bundle, output = args.robust.resolve(), args.bundle.resolve(), args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
module = bundle/'Robust.Client.WebView.dll'
cef_source = robust/'Robust.Client.WebView/Cef/WebViewManagerCef.cs'
module_source = robust/'Robust.Client/GameController/GameController.RobustModules.cs'

def body(source):
    text = source.decode('utf-8-sig')
    start = text.index('private static string? LocateCefResources()')
    begin = text.index('{',start)
    depth = 0
    for end in range(begin,len(text)):
        if text[end]=='{': depth+=1
        elif text[end]=='}': depth-=1
        if depth==0:
            return text[start:end+1]
    raise AssertionError('Complete production method required')

actual = body(cef_source.read_bytes())
historical = body(subprocess.check_output(['git','show','HEAD:Robust.Client.WebView/Cef/WebViewManagerCef.cs'],cwd=robust))
module_text = module_source.read_text(encoding='utf-8-sig')
assert 'alc.ResolvingUnmanagedDll +=' in module_text
assert 'nativeResolver.ResolveUnmanagedDllToPath(name)' in module_text
assert 'DllImportSearchPath.UseDllDirectoryForDependencies | DllImportSearchPath.SafeDirectories' in module_text
(output/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
template = '''using System.Runtime.Loader;
static class Assembly { public static Proxy GetExecutingAssembly()=>new(); public sealed class Proxy { public string Location=>Program.Module; } }
static class Program {
 public static string Module="";
 static string BasePath=>Path.GetDirectoryName(Module)!;
 static string[] NativeDllSearchDirectories()=>Array.Empty<string>();
 static void Require(bool condition,string message) { if(!condition)throw new Exception(message); }
 static void Main(string[] args) {
  Module=Path.GetFullPath(args[0]);
  var resolver=new AssemblyDependencyResolver(Module);
  var path=resolver.ResolveUnmanagedDllToPath("libcef");
  Require(path!=null && File.Exists(path),"CEF module native path must resolve");
  var expected=Path.Combine(Path.GetDirectoryName(path!)!,"cef_resources");
  Require(Directory.Exists(expected),"CEF native resources must exist");
  Require(LocateCefResources()==expected,"CEF resources must resolve through the module dependency file");
  Console.WriteLine("PASS module-native and production CEF resource paths; no native library loaded");
 }
 METHOD
}
'''
project = output/'Probe.csproj'
program = output/'Program.cs'
checks=[]
def run(command,name,expect=None,failure=None):
    result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    (output/(name+'.log')).write_text(result.stdout)
    checks.append({'name':name,'exit':result.returncode})
    if failure:
        assert result.returncode!=0 and failure in result.stdout,(name,result.stdout)
    else:
        assert result.returncode==0 and (expect is None or expect in result.stdout),(name,result.stdout)

program.write_text(template.replace('METHOD',actual))
run([args.dotnet,'restore',str(project),'--disable-parallel'],'restore')
def probe(name,failure=None):
    run([args.dotnet,'run','--project',str(project),'-c','Release','--no-restore',
         '-p:UseSharedCompilation=false','-p:BuildInParallel=false','--',str(module)],name,
        expect='PASS module-native and production CEF resource paths' if not failure else None,failure=failure)
probe('positive')
program.write_text(template.replace('METHOD',historical))
try:
    probe('historical-resource-control','CEF resources must resolve through the module dependency file')
finally:
    program.write_text(template.replace('METHOD',actual))
deps=bundle/'Robust.Client.WebView.deps.json'
original=deps.read_bytes()
try:
    deps.unlink()
    probe('missing-deps-control','CEF module native path must resolve')
finally:
    deps.write_bytes(original)
receipt={'checks':checks,'production_cef_source_sha256':hashlib.sha256(cef_source.read_bytes()).hexdigest(),
         'production_module_source_sha256':hashlib.sha256(module_source.read_bytes()).hexdigest(),
         'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'generated_source_inventory':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (program,project)},
         'module_dll_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),
         'module_deps_sha256':hashlib.sha256(deps.read_bytes()).hexdigest(),
         'log_inventory':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.log')},
         'target_assembly_loaded':False,'native_library_loaded':False,'accounts_accessed':False,
         'positive_paths':'passed','historical_and_missing_dependency_controls':'passed'}
(output/'receipt.json').write_text(json.dumps(receipt,indent=2))
print('PASS native module path controls; target loading and authenticated join not run')
