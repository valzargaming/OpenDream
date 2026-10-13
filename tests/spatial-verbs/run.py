import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "tests/spatial-verbs/SpatialVerbProbe.csproj"
parser = argparse.ArgumentParser()
parser.add_argument("--dotnet", default="dotnet")
args = parser.parse_args()
def generate(*control):
    subprocess.run([sys.executable, "tests/spatial-verbs/generate.py", *control], cwd=ROOT, check=True, timeout=60)
def probe():
    return subprocess.run([args.dotnet, "run", "--project", PROJECT, "-c", "Release", "--no-restore",
                           "-p:UseSharedCompilation=false", "-p:BuildInParallel=false"], cwd=ROOT,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
generate()
subprocess.run([args.dotnet, "restore", PROJECT, "--disable-parallel"], cwd=ROOT, check=True, timeout=120)
positive = probe()
print(positive.stdout)
assert positive.returncode == 0 and "PASS 83 production spatial-verb assertions" in positive.stdout
try:
    for control, expected in (("--historical-client", "connected nearby spatial verb must be offered"),
                              ("--historical-server", "opaque obstruction must deny view while preserving range")):
        generate(control)
        result = probe()
        print(result.stdout)
        assert result.returncode != 0 and expected in result.stdout, "Control failed to detect its intended regression"
finally:
    generate()
print("PASS both historical spatial-verb controls")
