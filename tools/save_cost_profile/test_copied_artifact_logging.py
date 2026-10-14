"""Replay authenticated actual CI logging regression; no engine/process execution."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from verify import NS, logs_clean, verify
PACKAGE = Path(__file__).resolve().parent
FIXTURE = PACKAGE / "fixtures/copied_artifact_logging"
METHOD = "DisabledFlushAndLifecycle"

class CopiedArtifactLoggingRegression(unittest.TestCase):
    def setUp(self):
        receipt = json.loads((FIXTURE / "receipt.json").read_text())
        self.assertEqual(receipt["head"], "2332bf58600fc77c8822051d3fb01aba8cc4a810")
        self.assertEqual(receipt["run"], 38536659930)
        self.assertEqual(receipt["artifact_id"], 11880971512)
        for name, digest in receipt["files"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), digest)
    def test_actual_copied_trx_retains_expected_output_but_minimal_console_rejected(self):
        path = FIXTURE / "copied-artifact.trx"
        tree = ET.parse(path)
        stdout = tree.findtext(".//t:UnitTestResult/t:Output/t:StdOut", "", NS)
        logs_clean(stdout, METHOD)
        self.assertEqual(stdout.count("SAVE_COST_DISABLED_LIFECYCLE_COMPLETE"), 1)
        log = (FIXTURE / "copied-artifact.log").read_text()
        self.assertIn("Passed!  - Failed:     0, Passed:     1", log)
        with self.assertRaisesRegex(ValueError, "unexpected/missing actual ERROR classification"):
            verify(path, METHOD, "original", 0, log)
    def test_actual_existing_normal_verbosity_host_pair_passes_strict_parser(self):
        trx = FIXTURE / "DisabledFlushAndLifecycle-original-0.trx"
        log = (FIXTURE / "DisabledFlushAndLifecycle-original-0.log").read_text()
        self.assertEqual(verify(trx, METHOD, "original", 0, log), "positive-one-test-pass")
    def test_actual_output_mutations_reject_missing_error_duplicate_and_unrelated_noise(self):
        path = FIXTURE / "DisabledFlushAndLifecycle-original-0.trx"
        log = (FIXTURE / "DisabledFlushAndLifecycle-original-0.log").read_text()
        for mutation in ("missing", "duplicate", "noise"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix="copied-log-control-", dir=PACKAGE) as directory:
                tree = ET.parse(path)
                stdout = tree.find(".//t:UnitTestResult/t:Output/t:StdOut", NS)
                original = stdout.text
                if mutation == "missing": stdout.text = "\n".join(line for line in original.splitlines() if not line.startswith("SAVE_COST_ACTUAL_LOG [Error]"))
                if mutation == "duplicate": stdout.text = original + "\n" + original
                if mutation == "noise": stdout.text = original + "\n[ERRO] unexpected genuine runtime\n"
                control = Path(directory) / "generated-control.trx"
                tree.write(control, encoding="utf-8", xml_declaration=True)
                with self.assertRaises(ValueError): verify(control, METHOD, "original", 0, log)
    def test_both_copied_dll_commands_request_matching_normal_console_logger(self):
        for name in ("ci.py", "run_package.py"):
            tree = ast.parse((PACKAGE / name).read_text())
            commands = [node for node in ast.walk(tree) if isinstance(node, ast.List) and len(node.elts) >= 2 and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "dotnet" and isinstance(node.elts[1], ast.Constant) and node.elts[1].value == "vstest"]
            self.assertEqual(len(commands), 1, name)
            strings = [node.value for node in commands[0].elts if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            self.assertEqual(strings.count("/Logger:console;Verbosity=normal"), 1, name)
            self.assertIn("NUnit.ExplicitMode=Relaxed", strings)
            self.assertEqual(sum(isinstance(node, ast.BinOp) and isinstance(node.left, ast.Constant) and node.left.value == "/Logger:trx;LogFileName=" for node in commands[0].elts), 1, name)
