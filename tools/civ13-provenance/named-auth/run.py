"""Actual auth/connection source bodies with inert SQL/console/network adapters."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--dotnet',required=True)
parser.add_argument('--robust',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
robust=args.robust.resolve()
output=args.output.resolve()
output.mkdir(parents=True,exist_ok=False)
paths={name:robust/path for name,path in {
    'controller':'Robust.Client/GameController/GameController.cs',
    'launcher':'Robust.Client/Console/Commands/LauncherAuthCommand.cs',
    'manager':'Robust.Shared/Network/AuthManager.cs',
    'cli':'Robust.Client/CommandLineArgs.cs',
    'console':'Robust.Shared/Utility/CommandParsing.cs',
    'exec':'Robust.Shared/ProgramShared.cs'}.items()}
texts={name:path.read_text(encoding='utf-8-sig') for name,path in paths.items()}
def method(text,signature):
    start=text.index(signature)
    begin=text.index('{',start)
    depth=0
    for end in range(begin,len(text)):
        if text[end]=='{':depth+=1
        elif text[end]=='}':depth-=1
        if depth==0:return text[start:end+1]
    raise AssertionError('Complete production method required')
clear=method(texts['controller'],'private void ClearLauncherAuthState()')
startup=method(texts['controller'],'private bool TryRunStartupCommands()')
execute=method(texts['launcher'],'public override void Execute(')
exec_commands=method(texts['exec'],'public static void RunExecCommands(')
begin=texts['controller'].index('if (!TryRunStartupCommands())')
end=texts['controller'].index('return true;',begin)+len('return true;')
connection=texts['controller'][begin:end]
for name in ('manager','cli','console'):shutil.copyfile(paths[name],output/paths[name].name)
(output/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
adapters='''using System.Buffers;
namespace Robust.Shared { public sealed class MountOptions {public List<string> ZipMounts {get;}=new();public List<string> DirMounts {get;}=new();} public static class ProgramShared { EXEC } }
namespace Robust.Shared.Utility {public static class DebugTools {public static void AssertNotNull(object? value){if(value==null)throw new Exception();}} public static class ProbeExtensions {public static bool ContainsAny(this string value,SearchValues<char> chars)=>value.AsSpan().ContainsAny(chars);}}
namespace Robust.Shared.Collections {public struct ValueList<T> {public void Add(T value){}}}
namespace Robust.Shared.Network {public readonly record struct NetUserId(Guid Value);}
namespace Robust.Shared.Console {public interface IConsoleShell {void WriteLine(string message);}public interface IConsoleHost {void ExecuteCommand(string command);}}
sealed class Shell:Robust.Shared.Console.IConsoleShell {public void WriteLine(string message){}}
sealed class Log {public void Error(string message){}}
sealed class Manifest {public bool AutoConnect=true;}
static class LaunchState {public static object? ConnectEndpoint=new();}
sealed class Counter {public int Connections;public void ConnectToServer(object? endpoint){Connections++;}}
sealed class Row {public string Name="INERT Expected";public string Token="INERT TOKEN";public bool Found=true;public bool Throw;public int Queries;}
sealed class Parameters {public object? Value;public void AddWithValue(string name,object value){if(name!="@userName")throw new Exception("Wrong SQL selector");Value=value;}}
sealed class Db:IDisposable {readonly Row row;public Db(Row value){row=value;}public Command CreateCommand()=>new(row);public void Dispose(){}}
sealed class Command:IDisposable {readonly Row row;public Command(Row value){row=value;}public string CommandText="";public Parameters Parameters=new();public Reader ExecuteReader(){row.Queries++;if(!CommandText.Contains("Expires > datetime('NOW')")||!CommandText.Contains("AND UserName = @userName")||Parameters.Value is not string)throw new Exception("Saved lookup must use expiry and a bound named selector");if(row.Throw)throw new Exception("INERT query failure");return new(row);}public void Dispose(){}}
sealed class Reader:IDisposable {readonly Row row;public Reader(Row value){row=value;}public bool Read()=>row.Found;public string GetString(int index)=>index==0?"11111111-1111-1111-1111-111111111111":index==1?row.Name:row.Token;public void Dispose(){}}
abstract class CommandBase {public abstract void Execute(Robust.Shared.Console.IConsoleShell shell,string argStr,string[] args);}
sealed class Host:Robust.Shared.Console.IConsoleHost {readonly Action<string> action;public Host(Action<string> value){action=value;}public void ExecuteCommand(string command){try{action(command);}catch{ /* inert adapter mirrors console error isolation */ }}}
'''.replace('EXEC',exec_commands)
# Production RunExecCommands needs its actual imported console interface.
adapters='using Robust.Shared.Console;\n'+adapters
(output/'Adapters.cs').write_text(adapters)
template='''using Robust.Client;
using Robust.Shared;
using Robust.Shared.Console;
using Robust.Shared.Network;
using Robust.Shared.Utility;
sealed class Launcher:CommandBase {
 readonly IAuthManager _auth;readonly Row row;
 public Launcher(IAuthManager auth,Row value){_auth=auth;row=value;}
 Db GetDb()=>new(row);
 EXECUTE
}
sealed class Controller {
 readonly IAuthManager _authManager;readonly Log _logger=new();readonly IConsoleHost _console;
 readonly CommandLineArgs? _commandLineArgs;readonly Manifest? _resourceManifest=new();readonly Counter _client=new();
 public Controller(IAuthManager auth,Row row,string[] arguments){
  _authManager=auth;if(!CommandLineArgs.TryParse(arguments,out _commandLineArgs))throw new Exception("CLI parse failed");
  var launcher=new Launcher(auth,row);
  _console=new Host(command=>{var tokens=new List<string>();CommandParsing.ParseArguments(command,tokens);if(tokens.Count>0&&tokens[0]=="launchauth")launcher.Execute(new Shell(),command,tokens.Skip(1).ToArray());});
 }
 public int Connections=>_client.Connections;
 public bool Start(){ CONNECTION }
 CLEAR
 STARTUP
}
'''
program='''using Robust.Shared.Network;
static class Program {
 static void Require(bool value,string message){if(!value)throw new Exception(message);}
 static AuthManager Inherited()=>new(){Token="INERT INHERITED",UserId=new NetUserId(Guid.Parse("22222222-2222-2222-2222-222222222222")),LauncherAuthUserName="INERT Expected"};
 static string Auth(string value)=>"+launchauth \\\""+value.Replace("\\\\","\\\\\\\\").Replace("\\\"","\\\\\\\"")+"\\\"";
 static void Main(){
  Environment.SetEnvironmentVariable("ROBUST_AUTH_USERID","22222222-2222-2222-2222-222222222222");
  Environment.SetEnvironmentVariable("ROBUST_AUTH_TOKEN","INERT ENV TOKEN");
  Environment.SetEnvironmentVariable("ROBUST_AUTH_SERVER",null);Environment.SetEnvironmentVariable("ROBUST_AUTH_PUBKEY",null);Environment.SetEnvironmentVariable("ROBUST_AUTH_ALLOW_HWID",null);
  var fromEnv=new AuthManager{LauncherAuthUserName="INERT Stale"};fromEnv.LoadFromEnv();
  Require(fromEnv.Token=="INERT ENV TOKEN"&&fromEnv.UserId!=null&&fromEnv.LauncherAuthUserName==null,"Inherited environment must not prove a named lookup");
  var envController=new Controller(fromEnv,new Row{Found=false},new[]{"--connect",Auth("INERT Expected")});
  Require(!envController.Start()&&envController.Connections==0&&fromEnv.Token==null&&fromEnv.UserId==null,"Inherited environment cannot substitute for missing named login");
  Environment.SetEnvironmentVariable("ROBUST_AUTH_USERID",null);Environment.SetEnvironmentVariable("ROBUST_AUTH_TOKEN",null);
  foreach(var name in new[]{"INERT Expected","INERT Space \\\"Quote\\\"","INERT\\\\Backslash"}){
   var auth=Inherited();var row=new Row{Name=name};var controller=new Controller(auth,row,new[]{"--connect",Auth(name)});
   Require(controller.Start()&&controller.Connections==1&&auth.LauncherAuthUserName==name,"Matching named lookup must connect exactly once");
  }
  foreach(var row in new[]{new Row{Found=false},new Row{Throw=true},new Row{Name="INERT Other"},new Row{Token=""}}){
   var auth=Inherited();var controller=new Controller(auth,row,new[]{"--connect",Auth("INERT Expected")});
   Require(!controller.Start()&&controller.Connections==0,"Failed lookup must not auto-connect");
   Require(auth.Token==null&&auth.UserId==null&&auth.LauncherAuthUserName==null,"Failed named launch must clear inherited auth");
  }
  foreach(var commands in new[]{new[]{"--connect","+launchauth"},new[]{"--connect",Auth(" ")},new[]{"--connect",Auth("INERT Expected"),Auth("INERT Other")}}){
   var auth=Inherited();var row=new Row();var controller=new Controller(auth,row,commands);
   Require(!controller.Start()&&controller.Connections==0&&row.Queries==0,"Malformed or duplicate named launch must stop before lookup/connection");
  }
  var missing=Inherited();new Launcher(missing,new Row{Found=false}).Execute(new Shell(),"",new[]{"INERT Expected"});
  Require(missing.Token==null&&missing.UserId==null&&missing.LauncherAuthUserName==null,"Missing lookup must clear inherited command state");
  var mismatch=Inherited();new Launcher(mismatch,new Row{Name="INERT Other"}).Execute(new Shell(),"",new[]{"INERT Expected"});
  Require(mismatch.Token==null&&mismatch.UserId==null&&mismatch.LauncherAuthUserName==null,"Wrong returned identity must never populate auth state");
  var ordinary=new Controller(Inherited(),new Row(),new[]{"--connect"});Require(ordinary.Start()&&ordinary.Connections==1,"Non-named startup behavior must remain unchanged");
  Console.WriteLine("PASS named launcher fail-closed source cases");
 }
}
'''
(output/'Program.cs').write_text(program)
def generated(execute_body=execute,connection_body=connection):
    return template.replace('EXECUTE',execute_body).replace('CONNECTION',connection_body).replace('CLEAR',clear).replace('STARTUP',startup)
(output/'Production.cs').write_text(generated())
checks=[]
def run(command,label,failure=None):
    result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    (output/(label+'.log')).write_text(result.stdout)
    checks.append({'name':label,'exit':result.returncode})
    if failure:assert result.returncode!=0 and failure in result.stdout,(label,result.stdout)
    else:assert result.returncode==0,(label,result.stdout)
run([args.dotnet,'restore',str(output/'Probe.csproj'),'--disable-parallel'],'restore')
def probe(label,failure=None):
    run([args.dotnet,'run','--project',str(output/'Probe.csproj'),'-c','Release','--no-restore',
         '-p:UseSharedCompilation=false','-p:BuildInParallel=false'],label,failure)
probe('positive')
try:
    omitted=connection.replace('if (!TryRunStartupCommands())\n                return false;',
                               'ProgramShared.RunExecCommands(_console, _commandLineArgs?.ExecCommands);')
    assert omitted!=connection
    (output/'Production.cs').write_text(generated(connection_body=omitted))
    probe('autoconnect-gate-omission','Inherited environment cannot substitute for missing named login')
finally:(output/'Production.cs').write_text(generated())
try:
    omitted=execute.replace('_auth.Token = null;','').replace('_auth.UserId = null;','').replace('_auth.LauncherAuthUserName = null;','')
    (output/'Production.cs').write_text(generated(execute_body=omitted))
    probe('inherited-state-omission','Missing lookup must clear inherited command state')
finally:(output/'Production.cs').write_text(generated())
try:
    omitted=execute.replace('!string.Equals(userName, wantName, StringComparison.Ordinal) || ','')
    assert omitted!=execute
    (output/'Production.cs').write_text(generated(execute_body=omitted))
    probe('returned-identity-omission','Wrong returned identity must never populate auth state')
finally:(output/'Production.cs').write_text(generated())
receipt={'checks':checks,'source_inventory':{str(path.relative_to(robust)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()},
         'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'generated_inputs_and_logs':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()},
         'accounts_or_database_accessed':False,'client_or_network_target_executed':False,
         'adapters':'Inert SQL rows/parameter assertions, console dispatch/error isolation, connection counter, mount/range utility adapters',
         'positive_and_three_omission_controls':'passed'}
(output/'receipt.json').write_text(json.dumps(receipt,indent=2))
print('PASS fail-closed named launcher contract and three omission controls')
