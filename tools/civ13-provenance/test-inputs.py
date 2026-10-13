"""Exercise recipe contamination rejection without compiling or launching anything."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT/"tools/civ13-provenance/build.py"

def check(label, expected=None):
    with tempfile.TemporaryDirectory(prefix="civ13-input-control-") as output:
        result = subprocess.run([sys.executable, str(BUILDER), "--prepare-only", "--output", output],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        text = result.stdout+result.stderr
        if expected is None:
            assert result.returncode == 0, text
        else:
            assert result.returncode != 0 and expected in text, label+": "+text
    print("PASS "+label)

check("clean frozen inputs")
for relative in ("OpenDreamClient/UnexpectedSource.cs", "Resources/UnexpectedResource.bin"):
    path = ROOT/relative
    assert not path.exists()
    try:
        path.write_text("unexpected input", encoding="utf-8")
        check(relative, "Unexpected untracked build input")
    finally:
        path.unlink(missing_ok=True)
ignored = ROOT/"OpenDreamClient/UnexpectedIgnored.cs"
exclude = Path(subprocess.check_output(["git", "rev-parse", "--git-path", "info/exclude"], cwd=ROOT, text=True).strip())
if not exclude.is_absolute():
    exclude = ROOT/exclude
original = exclude.read_bytes() if exclude.exists() else None
try:
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes((original or b"")+b"\n/OpenDreamClient/UnexpectedIgnored.cs\n")
    ignored.write_text("unexpected ignored input", encoding="utf-8")
    check("ignored source contamination", "Unexpected untracked build input")
finally:
    ignored.unlink(missing_ok=True)
    if original is None:
        exclude.unlink(missing_ok=True)
    else:
        exclude.write_bytes(original)
target = ROOT/"RobustToolbox/Robust.Client/GameController/GameController.cs"
original = target.read_bytes()
try:
    target.write_bytes(original+b"\n// Unrelated dependency modification\n")
    check("extra Robust edit", "Robust effective diff differs")
finally:
    target.write_bytes(original)
child = ROOT/"RobustToolbox/NetSerializer"
ignored = child/"UnexpectedIgnored.cs"
exclude = Path(subprocess.check_output(["git", "rev-parse", "--git-path", "info/exclude"], cwd=child, text=True).strip())
if not exclude.is_absolute():
    exclude = child/exclude
original = exclude.read_bytes() if exclude.exists() else None
assert not ignored.exists()
try:
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes((original or b"")+b"\n/UnexpectedIgnored.cs\n")
    ignored.write_text("unexpected nested ignored input", encoding="utf-8")
    check("nested ignored source contamination", "Unexpected untracked build input")
finally:
    ignored.unlink(missing_ok=True)
    if original is None:
        exclude.unlink(missing_ok=True)
    else:
        exclude.write_bytes(original)

# Ignore submodule dirt in the parent's diff deliberately: child guards must stand alone.
config = subprocess.run(["git", "config", "--local", "--get", "diff.ignoreSubmodules"], cwd=ROOT/"RobustToolbox", capture_output=True, text=True)
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=child, text=True).split("\0")
target = child/next(name for name in tracked if name.endswith(".cs"))
original = target.read_bytes()
try:
    subprocess.run(["git", "config", "--local", "diff.ignoreSubmodules", "all"], cwd=ROOT/"RobustToolbox", check=True)
    target.write_bytes(original+b"\n// Unexpected nested tracked edit\n")
    check("nested tracked modification with parent ignore", "Tracked nested dependency inputs differ")
finally:
    target.write_bytes(original)
    if config.returncode == 0:
        subprocess.run(["git", "config", "--local", "diff.ignoreSubmodules", config.stdout.strip()], cwd=ROOT/"RobustToolbox", check=True)
    else:
        subprocess.run(["git", "config", "--local", "--unset", "diff.ignoreSubmodules"], cwd=ROOT/"RobustToolbox", check=True)
check("restored frozen inputs")
