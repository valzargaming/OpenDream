"""Pinned, isolated Civ13 client/Shared build. Never installs or launches a game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
# Provenance forbids untracked source inputs, including generated module caches.
sys.dont_write_bytecode = True
from standalone import package_layout, smoke
from server_acceptance import capture_inputs

ROOT = Path(__file__).resolve().parents[2]
ROBUST = "af2a7d0406b410c4d960f0f4b34513651c6dc742"

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, timeout=60).strip()

def dependency_inventory(directory):
    """Verify gitlinks directly, avoiding platform-specific git-submodule shell wrappers."""
    result = []
    for entry in git("ls-tree", "-r", "-z", "HEAD", cwd=directory).split("\0"):
        if not entry or not entry.startswith("160000 "):
            continue
        metadata, name = entry.split("\t", 1)
        expected = metadata.split()[2]
        child = directory/name
        actual = git("rev-parse", "HEAD", cwd=child)
        if actual != expected:
            raise RuntimeError("Dependency gitlink mismatch: " + str(child))
        if subprocess.run(["git", "diff", "--quiet", "--ignore-submodules=all", "HEAD", "--", "."],
                          cwd=child, timeout=60).returncode:
            raise RuntimeError("Tracked nested dependency inputs differ from pinned head: " + str(child))
        reject_untracked_inputs(child)
        result.append({"path": str(child.relative_to(ROOT)), "head": actual,
                       "sources": source_inventory(child)})
        result.extend(dependency_inventory(child))
    return result

def run(args, label, expected=None, failure=None):
    started = time.monotonic()
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=max(1, int(DEADLINE-time.monotonic())), env=ENV)
    (OUT / (label + ".log")).write_text(result.stdout, encoding="utf-8")
    checks.append({"name": label, "exit": result.returncode, "seconds": time.monotonic()-started})
    if failure:
        if result.returncode == 0 or failure not in result.stdout:
            raise RuntimeError(label + " did not reject its intended regression")
    elif result.returncode or (expected and expected not in result.stdout):
        raise RuntimeError(label + " failed; inspect retained log")

def source_inventory(directory):
    names = git("ls-files", "-z", cwd=directory).split("\0")
    return {n: digest(directory/n) for n in names if n and (directory/n).is_file()}

def reject_untracked_inputs(directory):
    for name in git("ls-files", "--others", "-z", cwd=directory).split("\0"):
        if not name:
            continue
        path = directory/name
        if path == OUT or OUT in path.parents:
            continue
        parts = Path(name).parts
        generated = False
        for index, part in enumerate(parts):
            if part not in ("bin", "obj"):
                continue
            parent = directory.joinpath(*parts[:index])
            if parent == directory or any(parent.glob("*.csproj")):
                generated = True
                break
        if not generated:
            raise RuntimeError("Unexpected untracked build input: " + name)

parser = argparse.ArgumentParser()
parser.add_argument("--dotnet", default="dotnet")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--timeout", type=int, default=1200)
parser.add_argument("--prepare-only", action="store_true")
args = parser.parse_args()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
DEADLINE = time.monotonic() + args.timeout
ENV = os.environ.copy()
ENV.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", MSBUILDDISABLENODEREUSE="1")
checks = []
receipt = {"engine_head": git("rev-parse", "HEAD"), "engine_tree": git("rev-parse", "HEAD^{tree}"),
           "robust_head": git("rev-parse", "HEAD", cwd=ROOT/"RobustToolbox"),
           "sdk_required": "10.0.401", "build": "not run", "installed": False,
           "graphical_acceptance": "not run", "runtime_acceptance": "not run"}
try:
    if OUT.is_relative_to(ROOT):
        relative = OUT.relative_to(ROOT)
        if len(relative.parts) != 1 or (ROOT/relative.parts[0]).exists() and any(
                path.startswith(relative.parts[0]+"/") for path in git("ls-files").splitlines()):
            raise RuntimeError("Output must be a separate top-level generated directory")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".", ":!RobustToolbox"], cwd=ROOT).returncode:
        raise RuntimeError("Tracked engine inputs differ from the declared head")
    reject_untracked_inputs(ROOT)
    if receipt["robust_head"] != ROBUST:
        raise RuntimeError("RobustToolbox revision differs from pinned gitlink")
    patch = ROOT/"tools/civ13-provenance/robust-auth.patch"
    receipt["robust_auth_patch_sha256"] = digest(patch)
    # Normalize patch line endings while preserving the exact declared effective diff.
    subprocess.run([sys.executable, str(ROOT/"tools/civ13-provenance/prepare-robust.py")],
                   cwd=ROOT, check=True, timeout=60)
    reject_untracked_inputs(ROOT/"RobustToolbox")
    receipt["engine_sources"] = source_inventory(ROOT)
    receipt["robust_sources"] = source_inventory(ROOT/"RobustToolbox")
    receipt["submodules"] = dependency_inventory(ROOT/"RobustToolbox")
    if not args.prepare_only:
        run([args.dotnet, "--version"], "sdk", expected="10.0.401")
        projects = ["tests/glide/GlideProbe.csproj", "tests/icon-direction/DirectionProbe.csproj",
                    "OpenDreamClient/OpenDreamClient.csproj", "OpenDreamServer/OpenDreamServer.csproj",
                    "RobustToolbox/Robust.Client/Robust.Client.csproj"]
        for index, project in enumerate(projects):
            run([args.dotnet, "restore", project, "--disable-parallel", "-p:Configuration=Release"], "restore-"+str(index))
        metadata_project = "tools/civ13-provenance/metadata/LoaderMetadataProbe.csproj"
        run([args.dotnet, "restore", metadata_project, "--disable-parallel"], "restore-loader-metadata")
        def probe(project, label, expected=None, failure=None):
            run([args.dotnet, "run", "--project", project, "-c", "Release", "--no-restore",
                 "-p:UseSharedCompilation=false", "-p:BuildInParallel=false"], label, expected, failure)
        probe(projects[0], "glide-positive", "PASS 211 production glide assertions")
        target = ROOT/"OpenDreamClient/Rendering/AtomGlideSystem.cs"
        original = target.read_bytes()
        try:
            target.write_bytes(subprocess.check_output(["git", "show", "b1a452e7fefa36f8919bff38067c602d0bb4e1a5:OpenDreamClient/Rendering/AtomGlideSystem.cs"], cwd=ROOT))
            probe(projects[0], "glide-historical-control", failure="consecutive update must never snap")
        finally:
            target.write_bytes(original)
        target = ROOT/"OpenDreamClient/Rendering/GlideTiming.cs"
        original = target.read_bytes()
        try:
            target.write_bytes(original.replace(b"Math.Max(baseline, remaining / interval)", b"baseline"))
            probe(projects[0], "glide-slow-control", failure="automatic speed catches up to held-key cadence")
        finally:
            target.write_bytes(original)
        probe(projects[1], "icon-positive", "directional frame assertions")
        target = ROOT/"OpenDreamShared/Resources/DMIParser.cs"
        original = target.read_bytes()
        try:
            target.write_bytes(subprocess.check_output(["git", "show", "b1a452e7fefa36f8919bff38067c602d0bb4e1a5:OpenDreamShared/Resources/DMIParser.cs"], cwd=ROOT))
            probe(projects[1], "icon-historical-control", failure="normalized SOUTH frame must insert")
        finally:
            target.write_bytes(original)
        run([sys.executable, "tests/spatial-verbs/run.py", "--dotnet", args.dotnet],
            "spatial-verbs", expected="PASS both historical spatial-verb controls")
        shutil.copy2(ROOT/"tests/spatial-verbs/obj/source-receipt.json", OUT/"spatial-source-receipt.json")
        for index, project in enumerate(projects[2:]):
            run([args.dotnet, "build", project, "-c", "Release", "-t:Rebuild",
                 "--no-restore", "--disable-build-servers", "-m:1", "-p:UseSharedCompilation=false",
                 "-p:BuildInParallel=false", "-p:ContinuousIntegrationBuild=true",
                 "-p:PathMap="+str(ROOT)+"=/src"], "build-"+str(index))
        client = ROOT/"bin/Content.Client"
        server = ROOT/"bin/Content.Server"
        if digest(client/"OpenDreamShared.dll") != digest(server/"OpenDreamShared.dll"):
            raise RuntimeError("Client/server Shared assemblies differ")
        archive = OUT/"Content.Client-provenance.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            excluded = {"Maps", "emotes.xml", "Groups", "engineCommandPerms.yml", "clientCommandPerms.yml", ".gitignore", ".directory", ".DS_Store"}
            for path in sorted((ROOT/"Resources").rglob("*")):
                relative = path.relative_to(ROOT/"Resources")
                if path.is_file() and not set(relative.parts).intersection(excluded):
                    z.write(path, relative.as_posix())
            for name in ("OpenDreamClient.dll", "OpenDreamClient.pdb", "OpenDreamShared.dll", "OpenDreamShared.pdb"):
                z.write(client/name, "Assemblies/"+name)
        candidate_shared = OUT/"OpenDreamShared.dll"
        candidate_loader = OUT/"Robust.Client.dll"
        candidate_runtime = OUT/"OpenDreamRuntime.dll"
        shutil.copy2(server/"OpenDreamShared.dll", candidate_shared)
        shutil.copy2(server/"OpenDreamRuntime.dll", candidate_runtime)
        loader = ROOT/"RobustToolbox/bin/Client/Robust.Client.dll"
        release_loader = OUT/"Robust.Client.Release-control.dll"
        shutil.copy2(loader, release_loader)
        def loader_metadata(path, label, failure=None):
            run([args.dotnet, "run", "--project", metadata_project, "-c", "Release", "--no-restore",
                 "-p:UseSharedCompilation=false", "-p:BuildInParallel=false", "--", str(path)], label,
                expected=None if failure else "PASS launchauth metadata contract", failure=failure)
        loader_metadata(release_loader, "loader-release-control", "Launcher authentication command is missing")
        auth_project = projects[4]
        webview_project = "RobustToolbox/Robust.Client.WebView/Robust.Client.WebView.csproj"
        for label, project in (("loader", auth_project), ("webview", webview_project)):
            run([args.dotnet, "restore", project, "--disable-parallel", "-p:Configuration=Tools",
                 "-p:RobustToolsBuild=true"], "restore-auth-"+label)
        # WebView references Client: build that dependency graph once, then publish both
        # without a second compilation or the Client-only ILLink publication rewrite.
        run([args.dotnet, "build", webview_project, "-c", "Tools", "-t:Rebuild", "--no-restore",
             "--disable-build-servers", "-m:1", "-p:UseSharedCompilation=false", "-p:BuildInParallel=false",
             "-p:RobustToolsBuild=true", "-p:ContinuousIntegrationBuild=true",
             "-p:PathMap="+str(ROOT)+"=/src"], "build-auth-graph")
        for label, project in (("loader", auth_project), ("webview", webview_project)):
            run([args.dotnet, "publish", project, "-c", "Tools", "--no-build", "--no-restore",
                 "-p:RobustToolsBuild=true", "-p:RobustILLink=false",
                 "-o", str(OUT/("auth-"+label))], "publish-auth-"+label)
        for name in ("Robust.Client.dll", "Robust.Shared.dll", "Robust.Shared.Maths.dll", "Robust.LoaderApi.dll"):
            if digest(OUT/"auth-loader"/name) != digest(OUT/"auth-webview"/name):
                raise RuntimeError("Authentication loader/WebView dependency mismatch: " + name)
        run([sys.executable, "tools/civ13-provenance/native-paths/run.py", "--dotnet", args.dotnet,
             "--robust", str(ROOT/"RobustToolbox"), "--bundle", str(OUT/"auth-webview"),
             "--output", str(OUT/"native-path-proof")], "native-module-paths",
            expected="PASS native module path controls")
        run([sys.executable, "tools/civ13-provenance/named-auth/run.py", "--dotnet", args.dotnet,
             "--robust", str(ROOT/"RobustToolbox"), "--output", str(OUT/"named-auth-proof")],
            "named-auth-contract", expected="PASS fail-closed named launcher contract")
        validation_source = ROOT/"tools/civ13-provenance/client-validation"
        run([sys.executable, str(validation_source/"verify.py"), "--dotnet", args.dotnet,
             "--robust", str(ROOT/"RobustToolbox"), "--output", str(OUT/"client-validation-proof")],
            "client-front-end", expected="PASS pinned parser identity binding")
        if os.name == "nt":
            run([sys.executable, str(validation_source/"test-client-job.py"), str(OUT/"client-job-proof")],
                "client-job-controls", expected='"controls": 6')
        shutil.copytree(validation_source, OUT/"client-validation-source", ignore=shutil.ignore_patterns("__pycache__"))
        receipt["client_validation_source_inventory"] = {p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
                                                         for p in sorted(validation_source.glob("*.py"))}
        loader = OUT/"auth-loader/Robust.Client.dll"
        loader_metadata(loader, "loader-tools-positive")
        shutil.copy2(loader, candidate_loader)
        receipt["authentication_loader"] = {"configuration": "Tools", "RobustToolsBuild": True,
                                             "command": "launchauth", "metadata_contract": "passed",
                                             "publication_trimming": False, "shared_dependency_hash_agreement": "passed",
                                             "native_path_contract": "passed; target native loading not run",
                                             "named_launch_contract": "passed; account/database target not accessed",
                                             "credentials_accessed": False, "authenticated_join": "not run"}
        receipt["authentication_bundle_files"] = {str(path.relative_to(OUT)):
                                                   {"sha256": digest(path), "bytes": path.stat().st_size}
                                                   for directory in (OUT/"auth-loader", OUT/"auth-webview")
                                                   for path in sorted(directory.rglob("*")) if path.is_file()}
        receipt["standalone_layout"] = package_layout(OUT, ROOT)
        receipt["standalone_startup"] = smoke(OUT, args.dotnet, receipt["standalone_layout"])
        receipt["artifacts"] = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
                                 {"sha256": digest(p), "bytes": p.stat().st_size}
                                 for p in [archive, candidate_shared, candidate_loader, candidate_runtime, client/"OpenDreamClient.dll", client/"OpenDreamShared.dll",
                                           server/"OpenDreamShared.dll", loader]}
        receipt["server_acceptance_inputs"] = capture_inputs(ROOT, OUT)
        receipt["build"] = "passed"
    receipt["checks"] = checks
except BaseException as error:
    receipt["error"] = str(error)
    raise
finally:
    receipt["checks"] = checks
    (OUT/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if receipt["build"] == "passed" and "error" not in receipt and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as step_output:
            step_output.write("server_acceptance_receipt_sha256=" + digest(OUT/"receipt.json") + "\n")
