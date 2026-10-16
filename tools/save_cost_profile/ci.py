"""Root-owned CI execution; this detached agent has not run these commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from control import PACKAGE, verify_receipt
from verify import verify

ROOT = PACKAGE.parents[1]

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def run(command, cwd, log, timeout, env=None):
    with log.open("wb") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=stream, stderr=subprocess.STDOUT)
            else:
                process.kill()
            process.wait()
            code = 124
    log.with_suffix(".exit.txt").write_text(str(code) + "\n")
    print("\n".join(log.read_text(errors="replace").splitlines()[-50:]))
    return code

def build(mode, results):
    assert subprocess.check_output(["dotnet", "--version"], cwd=ROOT).decode().strip() == "10.0.401"
    assert run(["dotnet", "--info"], ROOT, results / "sdk-info.log", 60) == 0
    command = ["dotnet", "build", "OpenDream.slnx", "--configuration", "Release", "--property", "WarningLevel=4",
               "-m:1", "-p:UseSharedCompilation=false", "--disable-build-servers", "-p:SaveCostHostProfile=" + ("false" if mode == "original" else "true"),
               "-p:SaveCostHostOriginal=" + ("true" if mode == "original" else "false")]
    assert run(command, ROOT, results / "build.log", 1200) == 0, "full engine build failed; not a negative pass"
    paths = ["bin/Content.IntegrationTests/Content.IntegrationTests.dll", "bin/Content.IntegrationTests/Content.IntegrationTests.pdb",
             "OpenDreamRuntime/bin/Release/net10.0/OpenDreamRuntime.dll", "OpenDreamRuntime/bin/Release/net10.0/OpenDreamRuntime.pdb"]
    rows = []
    for path in paths:
        source = ROOT / path
        assert source.is_file(), "required runtime/test binary missing: " + path
        target = results / "binaries" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append(dict(path=path, sha256=digest(source), bytes=source.stat().st_size))
    (results / "binary-hashes.json").write_text(json.dumps(rows, indent=2) + "\n")

def no_runtimes(mode, results):
    trx = results / "ordinary-runtime.trx"
    log = results / "ordinary-runtime.log"
    command = ["dotnet", "test", "Content.IntegrationTests/Content.IntegrationTests.csproj", "--configuration", "Release", "--no-build",
               "--filter", "FullyQualifiedName=Content.IntegrationTests.GameTests.NoRuntimesTest", "--logger", "trx;LogFileName=" + trx.name,
               "--results-directory", str(results), "-v", "n"]
    env = os.environ.copy(); env["COMPlus_gcServer"] = "1"
    code = run(command, ROOT, log, 60, env)
    assert code != 124, "NoRuntimes timeout is not a test pass"
    verifier = ROOT / "tests/string_format_decoder/verify.py"
    assert subprocess.run([sys.executable, str(verifier), str(trx), "positive", str(code), "--log", str(log), "--runtime"], cwd=ROOT).returncode == 0
    (results / "ordinary-runtime-receipt.json").write_text(json.dumps(dict(exit_code=code, trx_sha256=digest(trx), log_sha256=digest(log)), indent=2) + "\n")

def package(mode, results):
    receipt = results / "source-receipt.json"
    source = json.loads(receipt.read_text())
    verify_receipt(ROOT, mode, source["head"], receipt)
    target = results / "runnable"
    assert not target.exists(), "fresh package directory required"
    target.mkdir()
    required = ["bin/Content.IntegrationTests", "bin/Content.Server", "bin/DMCompiler", "Resources", "RobustToolbox/Resources"]
    for path in required:
        directory = ROOT / path
        assert directory.is_dir(), "missing required runnable tree: " + path
        shutil.copytree(directory, target / path)
    shutil.copytree(results / "prepared-source", target / "prepared-source")
    shutil.copy2(receipt, target / "source-receipt.json")
    for name in ("control.py", "verify.py", "controls.json", "manifest.json", "run_package.py"):
        shutil.copy2(PACKAGE / name, target / name)
    for path in ("bin/Content.IntegrationTests/Content.IntegrationTests.dll", "bin/Content.IntegrationTests/Content.IntegrationTests.runtimeconfig.json",
                 "bin/Content.IntegrationTests/Content.IntegrationTests.deps.json", "bin/Content.IntegrationTests/DMStandard", "bin/Content.IntegrationTests/DMProject",
                 "bin/Content.Server/OpenDreamServer.dll", "bin/DMCompiler/DMCompiler.dll", "bin/DMCompiler/DMStandard"):
        assert (target / path).exists(), "runnable dependency/resource seam missing: " + path
    # Probe from COPIED root, selecting only one real method in a fresh host.
    # This establishes test-host runnable evidence, not Gaia SAVE/server acceptance.
    trx = results / "copied-artifact.trx"
    log = results / "copied-artifact.log"
    env = os.environ.copy(); env.update(OD_SAVE_COST_MODE="original" if mode == "original" else "disabled", COMPlus_gcServer="1")
    command = ["dotnet", "vstest", str(target / "bin/Content.IntegrationTests/Content.IntegrationTests.dll"),
               "/TestCaseFilter:FullyQualifiedName=Content.IntegrationTests.SaveCostProfileHostTests.DisabledFlushAndLifecycle",
               "/Logger:console;Verbosity=normal", "/Logger:trx;LogFileName=" + trx.name, "/ResultsDirectory:" + str(results), "--", "NUnit.ExplicitMode=Relaxed"]
    code = run(command, target, log, 60, env)
    verdict = verify(trx, "DisabledFlushAndLifecycle", mode, code, log.read_text(errors="replace"))
    rows, size = [], 0
    for path in sorted(target.rglob("*")):
        assert not path.is_symlink(), "symlinks excluded from runnable artifact"
        if not path.is_file():
            continue
        size += path.stat().st_size
        assert len(rows) < 25000 and size <= 2 * 1024 ** 3, "runnable artifact exceeds finite cap"
        rows.append(dict(path=path.relative_to(target).as_posix(), bytes=path.stat().st_size, sha256=digest(path)))
    manifest = dict(schema=1, head=source["head"], base=source["base"], robust=source["robust"], mode=mode,
                    max_files=25000, max_bytes=2 * 1024 ** 3, files=rows, total_bytes=size,
                    copied_test_host_verdict=verdict, server_and_gaia_runtime_acceptance=False)
    (target / "runnable-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive = results / "runnable.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(target).as_posix())
    (results / "runnable-archive-hash.json").write_text(json.dumps(dict(path=archive.name, bytes=archive.stat().st_size, sha256=digest(archive),
                       runnable_manifest_sha256=digest(target / "runnable-manifest.json")), indent=2) + "\n")
    # Archive is the complete retained runnable tree; avoid duplicate upload size.
    shutil.rmtree(target)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "no-runtimes", "package"])
    parser.add_argument("mode")
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    args.results = args.results.resolve()
    assert args.results.is_relative_to(ROOT) and args.results != ROOT, "results must remain inside this CI checkout"
    args.results.mkdir(parents=True, exist_ok=True)
    {"build": build, "no-runtimes": no_runtimes, "package": package}[args.action](args.mode, args.results)
