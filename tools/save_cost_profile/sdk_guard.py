"""Retain SDK selection evidence before enforcing the existing exact SDK guard."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

EXPECTED = b"10.0.401"
ENVIRONMENT = (
    "PATH", "DOTNET_ROOT", "DOTNET_ROOT_X64", "DOTNET_ROOT_X86",
    "DOTNET_HOST_PATH", "DOTNET_MULTILEVEL_LOOKUP", "DOTNET_ROLL_FORWARD",
    "DOTNET_ROLL_FORWARD_TO_PRERELEASE", "DOTNET_CLI_HOME", "DOTNET_NOLOGO",
    "DOTNET_SKIP_FIRST_TIME_EXPERIENCE", "MSBuildSDKsPath",
    "DOTNET_MSBUILD_SDK_RESOLVER_SDKS_DIR", "DOTNET_MSBUILD_SDK_RESOLVER_SDKS_VER",
)


def check_sdk(root, results, comparison, *, runner=subprocess.run,
              which=shutil.which, environment=None):
    """Run the version query once; lists/info cannot substitute for its result."""
    environment = dict(os.environ if environment is None else environment)
    root, results = Path(root).resolve(), Path(results).resolve()
    results.mkdir(parents=True, exist_ok=True)
    executable = which("dotnet", path=environment.get("PATH", ""))
    global_path = root / "global.json"
    global_raw = global_path.read_bytes() if global_path.is_file() else None
    if global_raw is not None:
        (results / "sdk-global.json").write_bytes(global_raw)
    data = {
        "schema": 1, "cwd": str(root), "expected": EXPECTED.decode(),
        "comparison": comparison, "executable": executable,
        "resolved_executable": str(Path(executable).resolve()) if executable else None,
        "environment": {key: environment[key] for key in ENVIRONMENT if key in environment},
        "global_json_sha256": hashlib.sha256(global_raw).hexdigest() if global_raw is not None else None,
        "commands": [], "accepted": False,
    }
    receipt = results / "sdk-selection.json"

    def save():
        receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    save()
    version = None
    for name, argument in (("version", "--version"), ("list-sdks", "--list-sdks"), ("info", "--info")):
        record = {"command": ["dotnet", argument], "exit_code": None}
        stdout, stderr = b"", b""
        try:
            process = runner(["dotnet", argument], cwd=root, env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            stdout, stderr = process.stdout, process.stderr
            record["exit_code"] = process.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr = error.stdout or b"", error.stderr or b""
            record["error"] = "TimeoutExpired"
        except OSError as error:
            record["error"] = type(error).__name__ + ": " + str(error)
        for channel, raw in (("stdout", stdout), ("stderr", stderr)):
            path = results / ("sdk-" + name + "." + channel)
            path.write_bytes(raw)
            record[channel] = {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        data["commands"].append(record)
        if name == "version":
            # Match the prior Bash command substitution or Python decode().strip().
            # Extra stdout (including a first-run banner) remains a hard failure.
            try:
                normalized = stdout.rstrip(b"\n") if comparison == "shell" else stdout.decode().strip().encode()
            except UnicodeDecodeError:
                normalized = None
            version = record["exit_code"] == 0 and normalized == EXPECTED
            data["accepted"] = version
        save()
        print(json.dumps({"command": record["command"], "exit_code": record["exit_code"],
                          "error": record.get("error"), "stdout": stdout.decode(errors="backslashreplace"),
                          "stderr": stderr.decode(errors="backslashreplace")}), flush=True)
    print("SDK guard: " + ("accepted" if version else "REJECTED") + "; receipt: " + str(receipt), flush=True)
    return 0 if version else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--comparison", choices=("shell", "strip"), required=True)
    args = parser.parse_args()
    raise SystemExit(check_sdk(Path(__file__).resolve().parents[2], args.results, args.comparison))
