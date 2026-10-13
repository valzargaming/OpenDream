"""Compile unchanged production method bodies with inert transport/map adapters."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent/"obj"
OUT.mkdir(parents=True, exist_ok=True)
def extract(path, signature):
    text = (ROOT/path).read_text(encoding="utf-8-sig")
    start = text.index(signature)
    left = text.index("{", start)
    right, depth = left+1, 1
    while depth:
        depth += (text[right] == "{") - (text[right] == "}")
        right += 1
    return text[start:right]

client = extract("OpenDreamClient/ClientVerbSystem.cs", "public IEnumerable<(int Id, ClientObjectReference Src, VerbInfo VerbInfo)> GetExecutableVerbs(bool")
server = extract("OpenDreamRuntime/ServerVerbSystem.cs", "private bool CanExecute(DreamConnection connection")
helpers = "\n".join(extract("OpenDreamRuntime/Procs/Native/DreamProcNativeHelpers.cs", signature) for signature in (
    "private static IEnumerable<(int X, int Y)> DantomSpiral(",
    "public static IEnumerable<ViewAlgorithm.Tile?> MakeViewSpiral(",
    "public static ViewAlgorithm.Tile?[,] CollectViewData(",
    "public static DreamList HandleView("))
if "--historical-client" in sys.argv:
    client = client.replace("if(_playerManager.LocalEntity is null)", "if(_playerManager.LocalEntity is not null)")
if "--historical-server" in sys.argv:
    server = server.replace("DreamProcNativeHelpers.HandleView(_atomManager, _mapManager, connection.Mob,", "DreamProcNativeHelpers.HandleRange(connection.Mob,")
source = "using OpenDreamShared.Dream;\nnamespace SourceProbe;\n"
source += "public partial class ClientVerbSystem {\n"+client+"\n}\n"
source += "public partial class ServerVerbSystem {\n"+server+"\n}\n"
source += "public static partial class DreamProcNativeHelpers {\n"+helpers+"\n}\n"
(OUT/"GeneratedProduction.cs").write_text(source, encoding="utf-8")
(OUT/"source-receipt.json").write_text(json.dumps({"production_methods_sha256": hashlib.sha256((client+server+helpers).encode()).hexdigest(), "arguments": sys.argv[1:], "scope": "offline production bodies with inert adapters; not connected acceptance"}, indent=2), encoding="utf-8")
