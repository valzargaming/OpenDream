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
check("restored frozen inputs")
