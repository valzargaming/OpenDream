"""Synthetic adversarial verifier checks. These do NOT run the engine or prove runtime behavior."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("construction_verifier", HERE / "verify.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
TAG = lambda name: "{" + V.NS["t"] + "}" + name
FRAME = "at Content.IntegrationTests.AssocListConstructionTests.<>c__DisplayClass3_0.<RejectedConstructionReleasesOwners>b__1() in /repo/Content.IntegrationTests/AssocListConstructionTests.cs:line 51"


def observation_lines(mode):
    rows = []
    for case in V.SPEC:
        alias = case["id"].endswith("_alias")
        held_lists = (1 if alias else 3) if "_list_" in case["id"] else 0
        expected_lists, expected_datums = 10 + held_lists, 20 + (1 if alias else 4)
        actual_lists = expected_lists + (1000 if mode == "baseline" else 0)
        owners = case["expected_owners" if mode == "positive" else "frozen_original_owners"]
        rows.append(f'{case["id"]}: owners=[{",".join(map(str, owners))}]; lists={actual_lists} expected={expected_lists}; datums={expected_datums} expected={expected_datums}')
    if mode == "positive":
        rows.append(V.MARKER)
    return rows


def aggregate(mode="baseline", embedded=False):
    blocks = []
    for index, (case, line) in enumerate(zip(V.SPEC, observation_lines(mode))):
        match = V.ROW.fullmatch(line)
        count = len(case["expected_owners"])
        changed = next(i for i, value in enumerate(case["frozen_original_owners"]) if value != 1)
        actual = case["frozen_original_owners"][changed]
        blocks.append(f'{2*index+1}) {case["id"]}_OWNERS_1000\nAssert.That(counts, Is.EqualTo(expectedOwners))\nExpected and actual are both <System.Int32[{count}]>\nValues differ at index [{changed}]\nExpected: 1\nBut was: {actual}\n' + (FRAME + "\n" if embedded else ""))
        blocks.append(f'{2*index+2}) {case["id"]}_LIVE_BUCKET_DreamObjectList\nAssert.That(refs.GetCountOf(type), Is.EqualTo(expected[type].Count))\nExpected: {match.group(4)}\nBut was: {match.group(3)}\n' + (FRAME + "\n" if embedded else ""))
    return "Multiple failures or warnings in test:\n" + "\n".join(blocks)


def evidence(mode="positive", embedded=False):
    root = ET.Element(TAG("TestRun"))
    results = ET.SubElement(root, TAG("Results"))
    outcome = "Passed" if mode == "positive" else "Failed"
    row = ET.SubElement(results, TAG("UnitTestResult"), testId="only", testName=V.TEST, outcome=outcome)
    output = ET.SubElement(row, TAG("Output"))
    stdout = "\n".join(observation_lines(mode))
    ET.SubElement(output, TAG("StdOut")).text = stdout
    if mode == "baseline":
        error = ET.SubElement(output, TAG("ErrorInfo"))
        ET.SubElement(error, TAG("Message")).text = aggregate(embedded=embedded)
        ET.SubElement(error, TAG("StackTrace")).text = FRAME
    definitions = ET.SubElement(root, TAG("TestDefinitions"))
    definition = ET.SubElement(definitions, TAG("UnitTest"), id="only")
    ET.SubElement(definition, TAG("TestMethod"), className=V.CLASS, name=V.TEST)
    summary = ET.SubElement(root, TAG("ResultSummary"))
    ET.SubElement(summary, TAG("Counters"), total="1", executed="1", passed="1" if mode == "positive" else "0", failed="0" if mode == "positive" else "1")
    log = stdout + f"\n{outcome} {V.TEST} [1 s]\nTest Run {'Successful' if mode == 'positive' else 'Failed'}."
    return ET.ElementTree(root), log


class Controls(unittest.TestCase):
    def check(self, tree, log, mode="positive", code=None):
        with tempfile.TemporaryDirectory(prefix="construction-verifier-pure-") as directory:
            path = Path(directory) / "synthetic.trx"
            tree.write(path, encoding="utf-8")
            return V.verify(path, mode, (0 if mode == "positive" else 1) if code is None else code, log)

    def test_exact_synthetic_modes(self):
        for mode in ("positive", "baseline"):
            for embedded in (False, True):
                with self.subTest(mode=mode, embedded=embedded):
                    self.assertTrue(self.check(*evidence(mode, embedded), mode))

    def test_wrong_mode_and_exit(self):
        for mode in ("positive", "baseline"):
            tree, log = evidence(mode)
            for code in (-1, 2, 127, 1 if mode == "positive" else 0):
                with self.subTest(mode=mode, code=code), self.assertRaises(AssertionError):
                    self.check(tree, log, mode, code)
        with self.assertRaises(AssertionError):
            self.check(*evidence(), "omitted-release")

    def test_missing_extra_or_wrong_test_identity(self):
        for mode in ("positive", "baseline"):
            for change in ("zero", "two", "class", "method", "testName", "testId", "definition", "skip"):
                tree, log = evidence(mode)
                root = tree.getroot()
                row = root.find("t:Results/t:UnitTestResult", V.NS)
                if change == "zero": root.find("t:Results", V.NS).remove(row)
                elif change == "two": root.find("t:Results", V.NS).append(copy.deepcopy(row))
                elif change in ("class", "method"):
                    root.find("t:TestDefinitions/t:UnitTest/t:TestMethod", V.NS).set("className" if change == "class" else "name", "Foreign")
                elif change in ("testName", "testId"): row.set(change, "Foreign")
                elif change == "definition": root.find("t:TestDefinitions", V.NS).append(copy.deepcopy(root.find("t:TestDefinitions/t:UnitTest", V.NS)))
                else: row.set("outcome", "NotExecuted")
                with self.subTest(mode=mode, change=change), self.assertRaises(AssertionError): self.check(tree, log, mode)

    def test_runner_counters_errors_and_stderr(self):
        for mode in ("positive", "baseline"):
            for key in ("executed", "total", "notExecuted", "error", "timeout", "warning", "unknown"):
                tree, log = evidence(mode)
                tree.find(".//t:Counters", V.NS).set(key, "0" if key in ("executed", "total") else "1")
                with self.subTest(mode=mode, key=key), self.assertRaises(AssertionError): self.check(tree, log, mode)
            for error in ("[ERRO] runtime", "Unhandled exception", "Runtime occurred", "runtime error", "test run aborted", "testhost crash", "Isolated DM fixture compilation failed", "error CS0001", "Build FAILED"):
                tree, log = evidence(mode)
                with self.subTest(mode=mode, error=error), self.assertRaises(AssertionError): self.check(tree, log + "\n" + error, mode)
            tree, log = evidence(mode)
            ET.SubElement(tree.find(".//t:Output", V.NS), TAG("StdErr")).text = "unexpected failure"
            with self.assertRaises(AssertionError): self.check(tree, log, mode)
            tree, log = evidence(mode)
            ET.SubElement(tree.find(".//t:ResultSummary", V.NS), TAG("RunInfo"), outcome="Error")
            with self.assertRaises(AssertionError): self.check(tree, log, mode)

    def test_observation_rows_exact_and_ordered(self):
        for mode in ("positive", "baseline"):
            for change in ("missing", "duplicate", "order", "id", "owner", "bucket", "datum", "baseline", "malformed", "foreign", "completion"):
                tree, log = evidence(mode)
                node = tree.find(".//t:StdOut", V.NS)
                rows = node.text.splitlines()
                if change == "missing": rows.pop(0)
                elif change == "duplicate": rows.insert(1, rows[0])
                elif change == "order": rows[0], rows[1] = rows[1], rows[0]
                elif change == "id": rows[0] = rows[0].replace("_caught_", "_foreign_", 1)
                elif change == "owner": rows[0] = rows[0].replace("owners=[", "owners=[999,", 1)
                elif change == "bucket": rows[0] = rows[0].replace("lists=10 ", "lists=11 ").replace("lists=1010 ", "lists=1009 ")
                elif change == "datum": rows[0] = rows[0].replace("datums=24", "datums=25")
                elif change == "baseline": rows[1] = rows[1].replace("expected=10", "expected=11").replace("lists=10 ", "lists=11 ").replace("lists=1010 ", "lists=1011 ")
                elif change == "malformed": rows[0] = rows[0].replace("; lists=", "; lists=-")
                elif change == "foreign": rows.append("ASSOC_CONSTRUCT_FOREIGN")
                else: rows.append(V.MARKER)
                node.text = "\n".join(rows)
                with self.subTest(mode=mode, change=change), self.assertRaises(AssertionError): self.check(tree, log, mode)

    def test_original_log_must_match(self):
        for mode in ("positive", "baseline"):
            tree, log = evidence(mode)
            for changed in ("", log.replace(V.TEST, "Foreign"), log + "\nPassed Foreign [1 s]", log.replace("owners=[", "owners=[999,", 1), log + "\nTest Run Successful.", "\n".join(log.splitlines()[1:])):
                with self.subTest(mode=mode), self.assertRaises(AssertionError): self.check(tree, changed, mode)

    def test_exact_96_failure_blocks(self):
        for change in ("missing", "extra", "duplicate", "order", "array", "index", "actual", "bucket", "expression", "foreign-marker"):
            tree, log = evidence("baseline")
            node = tree.find(".//t:Message", V.NS)
            if change == "missing": node.text = node.text.split("\n96)")[0]
            elif change == "extra": node.text += "\n97) unrelated failure"
            elif change == "duplicate": node.text = node.text.replace("2) ", "1) ", 1)
            elif change == "order": node.text = node.text.replace(V.SPEC[0]["id"] + "_OWNERS", V.SPEC[1]["id"] + "_OWNERS", 1)
            elif change == "array": node.text = node.text.replace("System.Int32[4]", "System.Int32[3]", 1)
            elif change == "index": node.text = node.text.replace("index [0]", "index [1]", 1)
            elif change == "actual": node.text = node.text.replace("But was: 1001", "But was: 1000", 1)
            elif change == "bucket": node.text = node.text.replace("But was: 1010", "But was: 1009", 1)
            elif change == "expression": node.text = node.text.replace("Assert.That(counts,", "Assert.That(other,", 1)
            else: node.text = node.text.replace("_OWNERS_1000", "_FOREIGN_1000", 1)
            with self.subTest(change=change), self.assertRaises(AssertionError): self.check(tree, log, "baseline")

    def test_strict_source_stack(self):
        for change in ("missing", "file", "foreign", "extra", "embedded"):
            tree, log = evidence("baseline", embedded=True)
            node = tree.find(".//t:StackTrace", V.NS)
            if change == "missing": node.text = ""
            elif change == "file": node.text = node.text.replace("AssocListConstructionTests.cs", "Foreign.cs")
            elif change == "foreign": node.text = "at ForeignFixture.Bad() in /repo/Foreign.cs:line 1"
            elif change == "extra": node.text += "\nat ForeignFixture.Bad() in /repo/Foreign.cs:line 1"
            else:
                node = tree.find(".//t:Message", V.NS)
                node.text = node.text.replace(FRAME, "at ForeignFixture.Bad()", 1)
            with self.subTest(change=change), self.assertRaises(AssertionError): self.check(tree, log, "baseline")

    def test_original_log_foreign_frame_and_assertion_marker(self):
        for mode in ("positive", "baseline"):
            tree, log = evidence(mode)
            for extra in ("at ForeignFixture.Bad()", "ASSOC_CONSTRUCT_SUCCESS_mixed_datum_distinct_LENGTH", "ASSOC_CONSTRUCT_UNKNOWN_OWNER"):
                with self.subTest(mode=mode, extra=extra), self.assertRaises(AssertionError):
                    self.check(tree, log + "\n" + extra, mode)

    def test_failure_structure_and_positive_failure_rejected(self):
        tree, log = evidence()
        ET.SubElement(tree.find(".//t:Output", V.NS), TAG("ErrorInfo"))
        with self.assertRaises(AssertionError): self.check(tree, log)
        for tag in ("Message", "StackTrace", "ErrorInfo"):
            tree, log = evidence("baseline")
            if tag == "ErrorInfo":
                parent = tree.find(".//t:Output", V.NS)
                parent.append(copy.deepcopy(parent.find("t:ErrorInfo", V.NS)))
            else:
                parent = tree.find(".//t:ErrorInfo", V.NS)
                parent.append(copy.deepcopy(parent.find("t:" + tag, V.NS)))
            with self.subTest(tag=tag), self.assertRaises(AssertionError): self.check(tree, log, "baseline")


if __name__ == "__main__":
    unittest.main(verbosity=2)