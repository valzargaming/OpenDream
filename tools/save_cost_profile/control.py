"""Detached source preparation and receipts. Native commands run only in root-owned CI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parent
BASE = "644a0eca75c7a5a5d74b16de04ec589cf0ac1faa"
ROBUST = "af2a7d0406b410c4d960f0f4b34513651c6dc742"
SAVEFILE = "OpenDreamRuntime/Objects/Types/DreamObjectSavefile.cs"
RESOURCE = "OpenDreamRuntime/Resources/DreamResource.cs"
HELPER = "OpenDreamRuntime/Resources/SaveCostProfile.cs"
HOST = "Content.IntegrationTests/SaveCostProfileHostTests.cs"
SMOKE = "Content.IntegrationTests/Smoke.cs"
SEAM = "OpenDreamShared/Dream/StringFormatDecoder.cs"
RUNTIME = [SAVEFILE, RESOURCE, HELPER]
METHODS = ["ActualFlushCountsBytesAndClocks", "CappedFlushStopsCounters", "EnabledCloseAndDirtyFailure",
           "ScopeAndResourceFilterCoverage", "DisabledFlushAndLifecycle", "ModerateFlushWorkload", "EmptyClockCalibration"]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)

def lf(raw):
    return raw.replace(b"\r\n", b"\n")

def frozen_inputs():
    manifest_raw = (PACKAGE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest["base"] == BASE and manifest["robust"] == ROBUST
    for path, digest in manifest["files"].items():
        assert sha((PACKAGE / path).read_bytes()) == digest, "frozen source drift: " + path
    required = {
        "frozen/candidate/" + SAVEFILE: "703f8bdb950af75b0ac826d74488fbe863a6668207205b18b15833695b3c110f",
        "frozen/candidate/" + RESOURCE: "7eb6c235e91a88f18acc394d9d9a1599747da456a9177679222eeda415a0cc4d",
        "frozen/candidate/" + HELPER: "2ba2371a9104633d9e7e104dc56c48f5b640bbff953982fc1b65dbb116d3e7eb",
        "frozen/fixture/SaveCostProfileHostTests.cs": "c251e7803b0276999081e30b068b382c2daa7daab3da63674d8b57df0e6f087f",
        "frozen/fixture/Smoke.cs": "322d1cf6d3cbc115c2d60841e25ba2232e39b952ae7bf3b3750307f0ad60efb8",
    }
    assert all(manifest["files"].get(path) == digest for path, digest in required.items()), "reviewed source binding drift"
    return manifest, sha(manifest_raw)

def target_sources(mode):
    frozen_inputs()
    sources = {HOST: (PACKAGE / "frozen/fixture/SaveCostProfileHostTests.cs").read_bytes()}
    if mode == "original":
        sources.update({p: (PACKAGE / "frozen/original" / p).read_bytes() for p in (SAVEFILE, RESOURCE)})
        sources.update({HELPER: None, SMOKE: None})
    else:
        sources.update({p: (PACKAGE / "frozen/candidate" / p).read_bytes() for p in RUNTIME})
        sources[SMOKE] = (PACKAGE / "frozen/fixture/Smoke.cs").read_bytes()
        if mode != "positive":
            spec = json.loads((PACKAGE / "controls.json").read_text())[mode]
            path = spec["path"]
            needle, replacement = spec["needle"].encode(), spec["replacement"].encode()
            raw = lf(sources[path])
            assert raw.count(needle) == 1, "mutation must match exactly once"
            sources[path] = raw.replace(needle, replacement)
            if mode == "clear-after-json":
                anchor = b"            SaveCostProfile.Serialized(json);"
                assert sources[path].count(anchor) == 1
                sources[path] = sources[path].replace(anchor, needle + anchor)
            assert sha(sources[path]) == spec["frozen_v3_sha256"], "mutation differs from reviewed v3 bytes"
    return sources

def prepare(root, mode, head, receipt):
    manifest, manifest_sha = frozen_inputs()
    assert git(root, "rev-parse", "HEAD").decode().strip() == head, "wrong exact head"
    git(root, "merge-base", "--is-ancestor", BASE, head)
    assert git(root / "RobustToolbox", "rev-parse", "HEAD").decode().strip() == ROBUST, "wrong Robust pin"
    # Frozen manifest and fixtures must be committed at the tested head.
    prefix = PACKAGE.relative_to(root).as_posix()
    for path in [".gitattributes", "manifest.json", "controls.json", "control.py", "verify.py", "ci.py", "test_verify.py", "run_package.py", "control_batch.py", "test_copied_artifact_logging.py", *manifest["files"]]:
        assert (PACKAGE / path).read_bytes() == git(root, "show", head + ":" + prefix + "/" + path), "uncommitted package input"
    originals = {}
    for path in (SAVEFILE, RESOURCE, SEAM):
        committed = git(root, "show", BASE + ":" + path)
        assert lf(committed) == lf((PACKAGE / "frozen/original" / path).read_bytes()), "wrong immutable original"
        originals[path] = sha(committed)
    assert subprocess.run(["git", "-C", str(root), "cat-file", "-e", BASE + ":" + HELPER], capture_output=True).returncode != 0, "helper must be absent at baseline"
    before = {}
    for path, frozen in [(p, "frozen/candidate/" + p) for p in RUNTIME] + [(HOST, "frozen/fixture/SaveCostProfileHostTests.cs"), (SMOKE, "frozen/fixture/Smoke.cs")]:
        committed = git(root, "show", head + ":" + path)
        assert lf(committed) == lf((PACKAGE / frozen).read_bytes()), "head source differs from reviewed candidate: " + path
        assert lf((root / path).read_bytes()) == lf(committed), "dirty input: " + path
        before[path] = sha(committed)
    project = root / "Content.IntegrationTests/Content.IntegrationTests.csproj"
    assert lf(project.read_bytes()) == lf(git(root, "show", head + ":Content.IntegrationTests/Content.IntegrationTests.csproj"))
    assert b"SaveCostHostProfile" in project.read_bytes() and b"SAVECOST_PROFILE" in project.read_bytes()
    outputs = {}
    for path, raw in target_sources(mode).items():
        target = root / path
        if raw is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        outputs[path] = None if raw is None else sha(raw)
        artifact = receipt.parent / "prepared-source" / path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            artifact.write_bytes(raw)
    data = dict(schema=1, mode=mode, head=head, base=BASE, robust=ROBUST, manifest_sha256=manifest_sha,
                immutable_originals=originals, reviewed_head_sources=before, prepared_sources=outputs,
                project_sha256=sha(project.read_bytes()), absent_baseline_helper=True,
                package_code_sha256={name: sha((PACKAGE / name).read_bytes()) for name in ("controls.json", "control.py", "verify.py", "ci.py", "test_verify.py", "run_package.py", "control_batch.py", "test_copied_artifact_logging.py")})
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(data, indent=2) + "\n")

def verify_receipt(root, mode, head, receipt):
    _, manifest_sha = frozen_inputs()
    data = json.loads(receipt.read_text())
    assert data["schema"] == 1 and data["mode"] == mode and data["head"] == head
    assert data["base"] == BASE and data["robust"] == ROBUST and data["manifest_sha256"] == manifest_sha
    assert git(root, "rev-parse", "HEAD").decode().strip() == head
    assert git(root / "RobustToolbox", "rev-parse", "HEAD").decode().strip() == ROBUST
    assert data["absent_baseline_helper"] is True
    assert data["immutable_originals"] == {path: sha(git(root, "show", BASE + ":" + path)) for path in (SAVEFILE, RESOURCE, SEAM)}
    assert data["reviewed_head_sources"] == {path: sha(git(root, "show", head + ":" + path)) for path in (*RUNTIME, HOST, SMOKE)}
    assert data["package_code_sha256"] == {name: sha((PACKAGE / name).read_bytes()) for name in ("controls.json", "control.py", "verify.py", "ci.py", "test_verify.py", "run_package.py", "control_batch.py", "test_copied_artifact_logging.py")}
    expected = target_sources(mode)
    assert data["prepared_sources"] == {p: None if raw is None else sha(raw) for p, raw in expected.items()}
    for path, raw in expected.items():
        assert ((root / path).read_bytes() == raw) if raw is not None else not (root / path).exists()
        if raw is not None:
            assert (receipt.parent / "prepared-source" / path).read_bytes() == raw
    assert data["project_sha256"] == sha((root / "Content.IntegrationTests/Content.IntegrationTests.csproj").read_bytes())
    return data

def restore(root, mode, head, receipt):
    # Restore ONLY this verified generated variant's five known targets.
    # Never reset/stash the checkout or discard an unverified current mutation.
    verify_receipt(root, mode, head, receipt)
    for path, raw in target_sources("positive").items():
        assert raw is not None
        (root / path).write_bytes(raw)

def run_suite(root, mode, head, receipt):
    from verify import verify
    verify_receipt(root, mode, head, receipt)
    result_dir = receipt.parent.resolve()
    if mode == "original":
        plan = [("DisabledFlushAndLifecycle", "original", 0)] + [("ModerateFlushWorkload", "original", i) for i in range(1, 4)]
    elif mode == "positive":
        plan = [(method, "disabled", 0) for method in METHODS]
        plan += [("ModerateFlushWorkload", choice, i) for i in range(1, 4) for choice in ("disabled", "enabled")]
    else:
        method = json.loads((PACKAGE / "controls.json").read_text())[mode]["method"]
        plan = [(method, "enabled", 0)]
    import os
    records = []
    for method, host_mode, trial in plan:
        name = f"{method}-{host_mode}-{trial}"
        log_path = result_dir / (name + ".log")
        trx = result_dir / (name + ".trx")
        env = os.environ.copy()
        env.update(OD_SAVE_COST_MODE=host_mode, COMPlus_gcServer="1")
        command = ["dotnet", "test", "Content.IntegrationTests/Content.IntegrationTests.csproj", "--configuration", "Release", "--no-build",
                   "--filter", "FullyQualifiedName=Content.IntegrationTests.SaveCostProfileHostTests." + method,
                   "--logger", "trx;LogFileName=" + trx.name, "--results-directory", str(result_dir), "-v", "n", "--", "NUnit.ExplicitMode=Relaxed"]
        timed_out = False
        from ci import run
        exit_code = run(command, root, log_path, 60, env)
        timed_out = exit_code == 124
        (result_dir / (name + ".exit.txt")).write_text(str(exit_code) + "\n")
        assert not timed_out, "60-second method timeout is infrastructure failure"
        verdict = verify(trx, method, mode, exit_code, log_path.read_text(errors="replace"))
        verify_receipt(root, mode, head, receipt)
        records.append(dict(method=method, host_mode=host_mode, trial=trial, verdict=verdict,
                            log_sha256=sha(log_path.read_bytes()), trx_sha256=sha(trx.read_bytes()), exit_code=exit_code))
        (result_dir / "test-receipts.json").write_text(json.dumps(records, indent=2) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "verify-receipt", "run-suite", "restore"])
    parser.add_argument("mode")
    parser.add_argument("--root", type=Path, default=PACKAGE.parents[1])
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    controls = json.loads((PACKAGE / "controls.json").read_text())
    assert args.mode in ("positive", "original", *controls)
    assert len(args.expected_head) == 40 and all(c in "0123456789abcdef" for c in args.expected_head)
    {"prepare": prepare, "verify-receipt": verify_receipt, "run-suite": run_suite, "restore": restore}[args.action](args.root.resolve(), args.mode, args.expected_head, args.receipt.resolve())
