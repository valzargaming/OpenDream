"""Compile an immutable Gaia candidate without launching or installing anything."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ENGINE = Path(__file__).resolve().parents[2]
GAME_HEAD = "b8a61dd5d9afed3a5716f62b27c280db4064a427"
ROBUST_HEAD = "af2a7d0406b410c4d960f0f4b34513651c6dc742"
MAP = "maps/nomads/nomads_gaia.dmm"

def git(directory, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=directory, text=True, timeout=60).strip()

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--game", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--dotnet", default="dotnet")
parser.add_argument("--timeout", type=int, default=1200)
parser.add_argument("--stale-output-control", action="store_true")
args = parser.parse_args()
game = args.game.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
deadline = time.monotonic()+args.timeout
receipt = {"engine_head": git(ENGINE, "rev-parse", "HEAD"),
           "engine_tree": git(ENGINE, "rev-parse", "HEAD^{tree}"),
           "game_repository": "Civ13/Civ13", "game_head": git(game, "rev-parse", "HEAD"),
           "game_tree": git(game, "rev-parse", "HEAD^{tree}"),
           "robust_head": git(ENGINE/"RobustToolbox", "rev-parse", "HEAD"),
           "map": MAP, "profile_intent": "Nomads Gaia, Classic Stone Age Start",
           "compatibility_version": "516.1681", "define_overrides": [],
           "opendream_define": "compiler-provided", "commands": [],
           "installed": False, "server_launched": False, "runtime_acceptance": "not run"}

def run(command, label, cwd=ENGINE):
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=max(1, int(deadline-time.monotonic())))
    (out/(label+".log")).write_text(result.stdout, encoding="utf-8")
    receipt["commands"].append({"argv": command, "cwd": str(cwd), "exit": result.returncode,
                                "seconds": time.monotonic()-started})
    if result.returncode:
        raise RuntimeError(label+" failed; inspect retained log")
    return result.stdout

try:
    assert receipt["game_head"] == GAME_HEAD
    assert receipt["robust_head"] == ROBUST_HEAD
    subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=game, check=True)
    unexpected = git(game, "ls-files", "--others", "-z")
    if unexpected:
        raise RuntimeError("Unexpected game input, including ignored files: " + unexpected.split("\0")[0])
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", ".", ":!RobustToolbox"], cwd=ENGINE, check=True)
    version = run([args.dotnet, "--version"], "sdk").strip()
    assert version == "10.0.401"
    receipt["sdk"] = version
    run([sys.executable, str(ENGINE/"tools/civ13-provenance/build.py"), "--prepare-only",
         "--output", str(out/"engine-source-proof")], "engine-input-contract")
    run([args.dotnet, "restore", "DMCompiler/DMCompiler.csproj", "--disable-parallel", "-p:Configuration=Release"], "compiler-restore")
    marker = b"CIV13_INVALID_STALE_COMPILER_CONTROL"
    if args.stale_output_control:
        stale = ENGINE/"bin/DMCompiler/DMCompiler.dll"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(marker)
        receipt["stale_output_control"] = {"path": str(stale.relative_to(ENGINE)), "marker_sha256": sha(stale)}
    run([args.dotnet, "build", "DMCompiler/DMCompiler.csproj", "-c", "Release", "-t:Rebuild", "--no-restore",
         "--disable-build-servers", "-m:1", "-p:UseSharedCompilation=false", "-p:BuildInParallel=false",
         "-p:ContinuousIntegrationBuild=true", "-p:PathMap="+str(ENGINE)+"=/src"], "compiler-rebuild")
    compiler_dir = out/"compiler"
    run([args.dotnet, "publish", "DMCompiler/DMCompiler.csproj", "-c", "Release", "--no-build", "--no-restore",
         "--disable-build-servers", "-m:1", "-p:UseSharedCompilation=false", "-p:BuildInParallel=false",
         "-p:ContinuousIntegrationBuild=true", "-p:PathMap="+str(ENGINE)+"=/src",
         "-o", str(compiler_dir)], "compiler-publish")
    receipt["compiler_files"] = {str(p.relative_to(compiler_dir)): sha(p) for p in sorted(compiler_dir.rglob("*")) if p.is_file()}
    receipt["game_sources"] = {name: sha(game/name) for name in git(game, "ls-files", "-z").split("\0") if name and (game/name).is_file()}
    dme = game/"civ13.dme"
    text = dme.read_text(encoding="utf-8-sig")
    pattern = re.compile(r'^\s*#include\s+"([^"\r\n]+\.dmm)"\s*$', re.MULTILINE|re.IGNORECASE)
    includes = pattern.findall(text)
    assert len(includes) == 1, "Expected one map include before explicit profile override"
    staged = game/"civ13-gaia.dme"
    staged.write_text(pattern.sub('#include "'+MAP+'"', text), encoding="utf-8")
    receipt["dme_original_sha256"] = sha(dme)
    receipt["original_map_include"] = includes[0]
    receipt["staged_dme_sha256"] = sha(staged)
    receipt["map_sha256"] = sha(game/MAP)
    compiler = compiler_dir/"DMCompiler.dll"
    if args.stale_output_control:
        assert compiler.read_bytes() != marker, "Stale compiler survived rebuild/publish"
        receipt["stale_output_control"]["replacement_sha256"] = sha(compiler)
        receipt["stale_output_control"]["passed"] = True
    receipt["compiler_sha256"] = sha(compiler)
    log = run([args.dotnet, str(compiler), "--version=516.1681", str(staged)], "gaia-compile", game)
    generated = staged.with_suffix(".json")
    assert generated.is_file() and generated.stat().st_size > 0
    parsed = json.loads(generated.read_text(encoding="utf-8-sig"))
    assert isinstance(parsed, dict) and "Maps" in parsed
    candidate = out/"civ13-gaia.json"
    candidate.write_bytes(generated.read_bytes())
    receipt["game_json_sha256"] = sha(candidate)
    receipt["game_json_bytes"] = candidate.stat().st_size
    receipt["game_top_level_keys"] = sorted(parsed)
    receipt["warning_lines"] = sum(bool(re.search(r'\bwarning\b', line, re.IGNORECASE)) for line in log.splitlines())
    receipt["compile"] = "passed"
except BaseException as error:
    receipt["error"] = str(error)
    receipt["compile"] = "failed"
    raise
finally:
    (out/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
