"""Serial builds in the CI-generated lane, never treating build failure as proof."""
import argparse
import json
from pathlib import Path
from control import PACKAGE, prepare, run_suite, restore, verify_receipt
from ci import ROOT, build

def batch(control, head, results):
    specs = json.loads((PACKAGE / "controls.json").read_text())
    assert control == "all" or control in specs
    assert results.is_relative_to(ROOT) and results != ROOT
    verify_receipt(ROOT, "positive", head, results / "positive/source-receipt.json")
    # A complete first-positive receipt (7 methods + six workload trials) is
    # mandatory; a source preparation or zero-test result cannot unlock controls.
    positive = json.loads((results / "positive/test-receipts.json").read_text())
    assert len(positive) == 13 and all(row["verdict"] == "positive-one-test-pass" and row["exit_code"] == 0 for row in positive)
    selected = list(specs) if control == "all" else [control]
    completed = []
    for mode in selected:
        receipt = results / mode / "source-receipt.json"
        prepare(ROOT, mode, head, receipt)
        build(mode, receipt.parent)
        run_suite(ROOT, mode, head, receipt)
        verdicts = json.loads((receipt.parent / "test-receipts.json").read_text())
        assert len(verdicts) == 1 and verdicts[0]["verdict"] == "expected-assertion-negative-pass" and verdicts[0]["exit_code"] == 1
        restore(ROOT, mode, head, receipt)
        completed.append(mode)
        (results / "control-batch-receipt.json").write_text(json.dumps(dict(head=head, requested=selected, completed=completed,
                                    complete=completed == selected, serial=True, build_failures_never_accepted=True), indent=2) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    batch(args.control, args.expected_head, args.results.resolve())
