using System.Buffers.Binary;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;

if (args.Length != 1) throw new ArgumentException("Expected loader DLL path");
using var stream = File.OpenRead(args[0]);
using var pe = new PEReader(stream);
var reader = pe.GetMetadataReader();
var handles = reader.TypeDefinitions.Where(h => {
    var type = reader.GetTypeDefinition(h);
    return reader.GetString(type.Namespace) == "Robust.Client.Console.Commands"
        && reader.GetString(type.Name) == "LauncherAuthCommand";
}).ToArray();
if (handles.Length != 1) throw new InvalidOperationException("Launcher authentication command is missing");
var definition = reader.GetTypeDefinition(handles[0]);
bool command = false, execute = false;
foreach (var handle in definition.GetMethods()) {
    var method = reader.GetMethodDefinition(handle);
    var name = reader.GetString(method.Name);
    execute |= name == "Execute";
    if (name != "get_Command") continue;
    var il = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes()!;
    for (int i = 0; i+4 < il.Length; i++) {
        if (il[i] != 0x72) continue; // ldstr, inspected without executing the assembly
        var token = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(i+1, 4));
        if ((token & unchecked((int)0xff000000)) == 0x70000000)
            command |= reader.GetUserString(MetadataTokens.UserStringHandle(token & 0x00ffffff)) == "launchauth";
    }
}
bool sqlite = reader.AssemblyReferences.Any(h => reader.GetString(reader.GetAssemblyReference(h).Name) == "Microsoft.Data.Sqlite");
if (!command || !execute || !sqlite) throw new InvalidOperationException("Launcher authentication command contract is incomplete");
Console.WriteLine("PASS launchauth metadata contract (type, command getter, Execute, SQLite reference)");
