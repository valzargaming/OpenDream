"""Pure front-end and pinned production-parser tests; no accounts/client/native load."""
import argparse
import ast
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--dotnet',required=True)
parser.add_argument('--robust',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
source=Path(__file__).resolve().parent
output=args.output.resolve()
output.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('frontend',source/'client-launch.py')
front=importlib.util.module_from_spec(spec)
spec.loader.exec_module(front)
helper=source/'client-job.py'
tree=ast.parse(helper.read_text())
redaction=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='redacted_arguments')
namespace={}
exec(compile(ast.Module(body=[redaction],type_ignores=[]),str(helper),'exec'),namespace)
redact=namespace['redacted_arguments']
names=['INERT Simple','INERT\\Backslash','INERT"Quote','INERT ; +quit']
cases=[]
for name in names:
    command=front.auth_command(name)
    assert redact([command],name)==['+launchauth <private-expected-username>']
    assert name not in json.dumps(redact([command],name))
    cases.append({'argv':[command],'expected':name,'bound':True})
cases.extend([{'argv':['+launchauth'],'expected':names[0],'bound':False},
              {'argv':['+launchauth',names[0]],'expected':names[0],'bound':False},
              {'argv':['+launchauth "INERT "Quote" Tail"'],'expected':'INERT "Quote" Tail','bound':False}])
for name in ('',' ','\n'):
    try: front.auth_command(name)
    except ValueError: pass
    else: raise AssertionError('Selector omission must fail')
fixture=output/'files'
fixture.mkdir()
sdk=fixture/'sdk.exe'
sdk.write_bytes(b'INERT_NOT_AN_EXECUTABLE')
front.SDK=sdk
head='a'*40
profile=fixture/'client-only-profile-aaaaaaaa'
profile.mkdir()
(profile/'loader').mkdir()
(profile/'webview').mkdir()
assembly=profile/'loader/Robust.Client.dll'
assembly.write_bytes(b'INERT_NOT_AN_ASSEMBLY')
(profile/'webview/Robust.Client.WebView.dll').write_bytes(b'INERT_WEBVIEW_BYTES')
(profile/'Content.Client.zip').write_bytes(b'INERT_MOUNT_BYTES')
shutil.copyfile(helper,fixture/'client-job.py')
stage={'source_head':head,'profile':str(profile),'process_launched':False,
       'files':{p.relative_to(profile).as_posix():{'sha256':front.file_hash(p),'bytes':p.stat().st_size} for p in profile.rglob('*') if p.is_file()}}
bundle={'engine_head':head,'build':'passed','authentication_loader':{'native_path_contract':'passed; target native loading not run'},
        'authentication_bundle_files':{'auth-loader/Robust.Client.dll':stage['files']['loader/Robust.Client.dll'],
                                       'auth-webview/Robust.Client.WebView.dll':stage['files']['webview/Robust.Client.WebView.dll']},
        'artifacts':{'Content.Client-provenance.zip':stage['files']['Content.Client.zip']}}
(fixture/'stage.json').write_text(json.dumps(stage))
(fixture/'package.json').write_text(json.dumps(bundle))
proposal={'source_head':head,'launch_specification_for_review_only':{'program':str(sdk)},
          'sdk_executable_sha256':front.file_hash(sdk)}
lease={'scope':'baseline-auth-observation-only','main_and_capture_grant_confirmed':True,
       'source_head':head,'native_paths_reviewed':True,'private_expected_identity_confirmed':True,
       'session_config_paths_reviewed':True,'absolute_end_utc':(datetime.now(timezone.utc)+timedelta(seconds=180)).isoformat(),
       'staged_receipt':'stage.json','guard_sha256':front.REVIEWED_GUARD_SHA256,'package_receipt':'package.json',
       'independently_reviewed_package_receipt_sha256':front.file_hash(fixture/'package.json')}
command,_,_=front.validate(proposal,lease,names[0],fixture)
assert command[-1]==front.auth_command(names[0]) and names[0] not in command
failures=[]
def refuse(label,change):
    p,l=copy.deepcopy(proposal),copy.deepcopy(lease)
    change(p,l)
    try: front.validate(p,l,names[0],fixture)
    except ValueError: failures.append(label)
    else: raise AssertionError('Front-end must reject '+label)
refuse('wrong-sdk-path',lambda p,l:p['launch_specification_for_review_only'].update(program=str(fixture/'other.exe')))
refuse('sdk-hash',lambda p,l:p.update(sdk_executable_sha256='0'*64))
refuse('helper-hash',lambda p,l:l.update(guard_sha256='0'*64))
refuse('package-allowlist-hash',lambda p,l:l.update(independently_reviewed_package_receipt_sha256='0'*64))
refuse('source-mismatch',lambda p,l:l.update(source_head='b'*40))
refuse('missing-native-review',lambda p,l:l.update(native_paths_reviewed=False))
refuse('missing-identity-review',lambda p,l:l.update(private_expected_identity_confirmed=False))
refuse('wrong-scope',lambda p,l:l.update(scope='save-or-gameplay'))
refuse('expired-deadline',lambda p,l:l.update(absolute_end_utc=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()))
refuse('excessive-deadline',lambda p,l:l.update(absolute_end_utc=(datetime.now(timezone.utc)+timedelta(seconds=300)).isoformat()))
refuse('escaping-review-path',lambda p,l:l.update(staged_receipt='../stage.json'))
original=assembly.read_bytes()
assembly.write_bytes(b'CORRUPTED_INERT_BYTES')
try: refuse('staged-file-hash',lambda p,l:None)
finally: assembly.write_bytes(original)
(profile/'unexpected-user-data').write_text('INERT')
try: refuse('unexpected-profile-file',lambda p,l:None)
finally: (profile/'unexpected-user-data').unlink()
project=output/'parser'
project.mkdir()
production=[args.robust/'Robust.Client/CommandLineArgs.cs',args.robust/'Robust.Shared/Utility/CommandParsing.cs']
for path in production: shutil.copyfile(path,project/path.name)
(project/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
(project/'Adapters.cs').write_text('''using System.Buffers;
namespace Robust.Shared { public sealed class MountOptions { public List<string> ZipMounts {get;}=new(); public List<string> DirMounts {get;}=new(); } }
namespace Robust.Shared.Utility { public static class DebugTools { public static void AssertNotNull(object? value) {if(value==null)throw new Exception();} } public static class ProbeExtensions {public static bool ContainsAny(this string value,SearchValues<char> chars)=>value.AsSpan().ContainsAny(chars);} }
namespace Robust.Shared.Collections { public struct ValueList<T> { public void Add(T value){} } }
''')
(project/'Program.cs').write_text('''using System.Text.Json;
using Robust.Client;
using Robust.Shared.Utility;
var cases=JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
int count=0;
foreach(var item in cases.EnumerateArray()) {
 var input=item.GetProperty("argv").EnumerateArray().Select(v=>v.GetString()!).ToArray();
 var expected=item.GetProperty("expected").GetString();
 var output=Console.Out; Console.SetOut(TextWriter.Null);
 bool accepted; CommandLineArgs? parsed;
 try {accepted=CommandLineArgs.TryParse(input,out parsed);} finally {Console.SetOut(output);}
 var tokens=new List<string>();
 if(accepted && parsed!.ExecCommands.Count==1)CommandParsing.ParseArguments(parsed.ExecCommands[0],tokens);
 var bound=tokens.Count==2 && tokens[0]=="launchauth" && tokens[1]==expected;
 if(bound!=item.GetProperty("bound").GetBoolean())throw new Exception("Production parser identity binding failed");
 count++;
}
Console.WriteLine($"PASS {count} pinned production-parser identity cases");
''')
(output/'parser-cases.json').write_text(json.dumps(cases))
logs=[]
for name,command in [('restore',[args.dotnet,'restore',str(project/'Probe.csproj'),'--disable-parallel']),
                     ('parser',[args.dotnet,'run','--project',str(project/'Probe.csproj'),'-c','Release','--no-restore',
                                '-p:UseSharedCompilation=false','-p:BuildInParallel=false','--',str(output/'parser-cases.json')])]:
    result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    (output/(name+'.log')).write_text(result.stdout)
    assert result.returncode==0,(name,result.stdout)
    logs.append({'name':name,'exit':result.returncode})
inventory={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')}
generated={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file() and ('bin' not in p.parts and 'obj' not in p.parts)}
receipt={'control_sources':inventory,'production_parser_sources':{str(p.relative_to(args.robust)):hashlib.sha256(p.read_bytes()).hexdigest() for p in production},
         'generated_inputs_and_logs':generated,'parser_cases':len(cases),'frontend_failures':failures,'checks':logs,
         'accounts_accessed':False,'client_or_native_target_loaded':False,
         'adapters':'MountOptions storage, null assertion, string span forwarding, discarded argument ranges; production tokenization/CLI files unmodified'}
(output/'receipt.json').write_text(json.dumps(receipt,indent=2))
print('PASS pinned parser identity binding, redaction and front-end refusal controls')
