"""Pure adversaries using explicitly synthetic TRX; no engine execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from control import frozen_inputs, target_sources, HELPER, PACKAGE
from verify import CLASS, NS, verify

def synthetic(method="CappedFlushStopsCounters", failed=False, message="", stack="", stdout=""):
    uri = NS["t"]
    root = ET.Element("{" + uri + "}TestRun")
    def node(parent, tag, attrs=None, text=None):
        result = ET.SubElement(parent, "{" + uri + "}" + tag, attrs or {})
        result.text = text
        return result
    row = node(node(root, "Results"), "UnitTestResult", dict(testName=method, testId="synthetic-id", outcome="Failed" if failed else "Passed"))
    output = node(row, "Output"); node(output, "StdOut", text=stdout)
    if failed:
        error = node(output, "ErrorInfo"); node(error, "Message", text=message); node(error, "StackTrace", text=stack)
    definition = node(node(root, "TestDefinitions"), "UnitTest", dict(id="synthetic-id"))
    node(definition, "TestMethod", dict(className=CLASS, name=method))
    counters = node(node(root, "ResultSummary"), "Counters", dict(total="1", executed="1", passed="0" if failed else "1", failed="1" if failed else "0"))
    return root, row, counters

class VerifierAdversaries(unittest.TestCase):
    def classify(self, root, method="CappedFlushStopsCounters", mode="positive", code=0, log=None):
        if log is None:
            log = ("Passed " + method + "\nTest Run Successful.\n")
        with tempfile.TemporaryDirectory(prefix="save-cost-synthetic-", dir=PACKAGE) as directory:
            path = Path(directory) / "synthetic.trx"
            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
            return verify(path, method, mode, code, log)

    def test_exact_one_positive_and_no_missing_counters(self):
        root, _, _ = synthetic()
        self.assertEqual(self.classify(root), "positive-one-test-pass")

    def test_rejects_zero_extra_wrong_skipped_timeout_and_exit(self):
        for change in ("zero", "extra", "wrong", "skip", "timeout", "exit", "infrastructure"):
            with self.subTest(change=change):
                root, row, counters = synthetic()
                code, log = 0, None
                if change == "zero": counters.set("executed", "0")
                if change == "extra": root.find("t:Results", NS).append(copy.deepcopy(row))
                if change == "wrong": row.set("testName", "Other")
                if change == "skip": row.set("outcome", "NotExecuted")
                if change == "timeout": counters.set("timeout", "1")
                if change == "exit": code = 1
                if change == "infrastructure": log = "Passed CappedFlushStopsCounters\nTest Run Successful.\nUnhandled exception"
                with self.assertRaises((ValueError, ET.ParseError)): self.classify(root, code=code, log=log)

    def test_exact_negative_and_wrong_assertion_rejected(self):
        method = "ActualFlushCountsBytesAndClocks"
        stack = "SaveCostDetachedSmoke.Smoke.Require\nSaveCostDetachedSmoke.Smoke.Run\n" + CLASS + "." + method + "\nRobustIntegrationTest"
        root, row, _ = synthetic(method, True, "System.Exception : actual monotonic clock wall bound", stack)
        log = "Failed " + method + "\nTest Run Failed.\n"
        self.assertEqual(self.classify(root, method, "zero-wall", 1, log), "expected-assertion-negative-pass")
        for change in ("message", "stack", "runtime", "teardown", "exit"):
            altered = copy.deepcopy(root)
            error = altered.find(".//t:ErrorInfo", NS)
            code = 1
            if change == "message": error.find("t:Message", NS).text = "System.Exception : unrelated"
            if change == "stack": error.find("t:StackTrace", NS).text = "SomeOtherTest"
            if change == "runtime": error.find("t:StackTrace", NS).text += "\nRuntime occurred"
            if change == "teardown": error.find("t:StackTrace", NS).text += "\nOneTimeTearDown"
            if change == "exit": code = 124
            with self.subTest(change=change), self.assertRaises(ValueError): self.classify(altered, method, "zero-wall", code, log)

    def test_numeric_control_is_not_any_expected_failure(self):
        method = "CappedFlushStopsCounters"
        spec = json.loads((PACKAGE / "controls.json").read_text())["omit-cap-coverage"]
        stack = CLASS + ".<CappedFlushStopsCounters>b__0 in /synthetic/SaveCostProfileHostTests.cs:line " + str(spec["source_line"]) + "\n" + CLASS + "." + method + "\nRobustIntegrationTest"
        root, _, _ = synthetic(method, True, "Expected: 2\nBut was:  0", stack)
        log = "Failed " + method + "\nTest Run Failed.\n"
        self.assertEqual(self.classify(root, method, "omit-cap-coverage", 1, log), "expected-assertion-negative-pass")
        altered = copy.deepcopy(root)
        altered.find(".//t:StackTrace", NS).text = stack.replace(":line " + str(spec["source_line"]), ":line 999")
        with self.assertRaises(ValueError): self.classify(altered, method, "omit-cap-coverage", 1, log)

    def test_rejects_unclassified_duplicate_and_wrong_error_path(self):
        method = "DisabledFlushAndLifecycle"
        path = "/tmp/opendream-save-cost-host-" + "a" * 32 + "/data/dirty.json"
        text = "SAVE_COST_ACTUAL_LOG [Error] opendream.res: Error flushing savefile " + path + ": System.Text.Json.JsonException: cycle\nDreamObjectSavefile.Flush\nSAVE_COST_EXPECTED_DIRTY_JSON_ERROR_CLASSIFIED " + path + "\nSAVE_COST_DISABLED_LIFECYCLE_COMPLETE\n"
        root, row, _ = synthetic(method, stdout=text)
        log = text + "Passed " + method + "\nTest Run Successful.\n"
        self.assertEqual(self.classify(root, method, "original", 0, log), "positive-one-test-pass")
        for bad in (text + text, text.replace("dirty.json", "production.json"), text + "SAVE_COST_ACTUAL_LOG [Fatal] other: fatal\n", text + "[ERRO] random\n"):
            altered = copy.deepcopy(root)
            altered.find(".//t:StdOut", NS).text = bad
            with self.assertRaises(ValueError): self.classify(altered, method, "original", 0, log)

class FrozenSourceControls(unittest.TestCase):
    def test_immutable_manifest_and_exact_v3_mutations(self):
        frozen_inputs()
        controls = json.loads((PACKAGE / "controls.json").read_text())
        self.assertEqual(len(controls), 9)
        positive = target_sources("positive")
        for control, spec in controls.items():
            changed = target_sources(control)
            self.assertEqual([path for path in changed if changed[path] != positive[path]], [spec["path"]])
        self.assertIsNone(target_sources("original")[HELPER])

class RunnableAdversaries(unittest.TestCase):
    def test_authenticated_tree_rejects_byte_path_and_inventory_drift(self):
        from run_package import authenticate, digest
        from control import BASE, ROBUST
        for mutation in (None, "bytes", "extra", "traversal", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix="save-cost-tree-", dir=PACKAGE) as directory:
                root = Path(directory).resolve()
                payload = root / "fixture.bin"
                payload.write_bytes(b"synthetic-only")
                row = dict(path=payload.name, bytes=payload.stat().st_size, sha256=digest(payload))
                manifest = dict(schema=1, mode="positive", base=BASE, robust=ROBUST, files=[row], total_bytes=row["bytes"])
                if mutation == "bytes": payload.write_bytes(b"incorrect")
                if mutation == "extra": (root / "unlisted.bin").write_bytes(b"extra")
                if mutation == "traversal": row["path"] = "../fixture.bin"
                if mutation == "duplicate": manifest["files"].append(dict(row))
                (root / "runnable-manifest.json").write_text(json.dumps(manifest))
                if mutation is None:
                    self.assertEqual(authenticate(root)["mode"], "positive")
                else:
                    with self.assertRaises(AssertionError): authenticate(root)
