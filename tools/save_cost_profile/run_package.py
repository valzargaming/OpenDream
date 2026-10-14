"""Authenticate extracted runnable tree and observe same-host fresh-process workloads.

No game SAVE is initiated. Root owns any subsequent actual Gaia SAVE/VERIFY seam.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from verify import verify

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def authenticate(root):
    manifest = json.loads((root / "runnable-manifest.json").read_text())
    assert manifest["schema"] == 1 and manifest["mode"] in ("positive", "original")
    assert manifest["base"] == "644a0eca75c7a5a5d74b16de04ec589cf0ac1faa"
    assert manifest["robust"] == "af2a7d0406b410c4d960f0f4b34513651c6dc742"
    assert len(manifest["files"]) <= 25000 and manifest["total_bytes"] <= 2 * 1024 ** 3
    expected = set()
    total = 0
    for row in manifest["files"]:
        relative = Path(row["path"])
        assert not relative.is_absolute() and ".." not in relative.parts and row["path"] not in expected
        expected.add(row["path"])
        path = root / relative
        assert path.resolve().is_relative_to(root) and not path.is_symlink()
        assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"]
        total += row["bytes"]
    assert total == manifest["total_bytes"]
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    assert actual == expected | {"runnable-manifest.json"}, "unlisted or missing runnable files"
    return manifest

def run(root, output, mode):
    manifest = authenticate(root)
    assert mode in (("original",) if manifest["mode"] == "original" else ("disabled", "enabled"))
    assert output.is_absolute() and not output.exists() and not output.is_relative_to(root), "fresh external task output required"
    output.mkdir(parents=True)
    assert subprocess.check_output(["dotnet", "--version"], cwd=root).decode().strip() == "10.0.401"
    records = []
    for trial in range(1, 4):
        name = f"same-host-{mode}-{trial}"
        log, trx = output / (name + ".log"), output / (name + ".trx")
        env = os.environ.copy(); env.update(OD_SAVE_COST_MODE=mode, COMPlus_gcServer="1")
        command = ["dotnet", "vstest", str(root / "bin/Content.IntegrationTests/Content.IntegrationTests.dll"),
                   "/TestCaseFilter:FullyQualifiedName=Content.IntegrationTests.SaveCostProfileHostTests.ModerateFlushWorkload",
                   "/Logger:trx;LogFileName=" + trx.name, "/ResultsDirectory:" + str(output), "--", "NUnit.ExplicitMode=Relaxed"]
        with log.open("wb") as stream:
            process = subprocess.Popen(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            try:
                code = process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                if os.name == "nt": subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=stream, stderr=subprocess.STDOUT)
                else: process.kill()
                process.wait(); code = 124
        (output / (name + ".exit.txt")).write_text(str(code) + "\n")
        verdict = verify(trx, "ModerateFlushWorkload", manifest["mode"], code, log.read_text(errors="replace"))
        authenticate(root)
        records.append(dict(trial=trial, mode=mode, head=manifest["head"], verdict=verdict, trx_sha256=digest(trx), log_sha256=digest(log)))
        (output / "same-host-receipts.json").write_text(json.dumps(records, indent=2) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["original", "disabled", "enabled"], required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output.resolve(), args.mode)
