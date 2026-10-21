"""Pure SDK guard tests: injected command outputs, temporary storage, no SDK run."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("sdk_guard", Path(__file__).with_name("sdk_guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class SdkGuardTests(unittest.TestCase):
    def run_guard(self, stdout=b"10.0.401\n", stderr=b"", code=0, comparison="shell", error=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_global = b'{"sdk":{"version":"10.0.100","rollForward":"latestFeature"}}\r\n'
            (root / "global.json").write_bytes(raw_global)
            results = root / "results"
            calls = []

            def run(command, **kwargs):
                calls.append((command, kwargs))
                if command[1] == "--version":
                    if error:
                        raise error
                    return subprocess.CompletedProcess(command, code, stdout, stderr)
                return subprocess.CompletedProcess(command, 0, b"10.0.401 [SDK path]\n", b"")

            environment = {"PATH": "injected-sdk-path", "DOTNET_ROOT": "sdk-root", "SECRET_TOKEN": "excluded"}
            with contextlib.redirect_stdout(io.StringIO()) as console:
                result = guard.check_sdk(root, results, comparison, runner=run,
                                         which=lambda *a, **k: str(root / "dotnet"), environment=environment)
            data = json.loads((results / "sdk-selection.json").read_text())
            files = {p.name: p.read_bytes() for p in results.iterdir()}
            self.assertEqual([c[0][1] for c in calls], ["--version", "--list-sdks", "--info"])
            self.assertTrue(all(c[1]["env"] == environment for c in calls))
            self.assertEqual(files["sdk-global.json"], raw_global)
            self.assertEqual(data["environment"], {"PATH": "injected-sdk-path", "DOTNET_ROOT": "sdk-root"})
            self.assertNotIn("SECRET_TOKEN", json.dumps(data))
            return result, data, files, console.getvalue()

    def test_exact_sdk_accepted_and_stdout_stderr_retained(self):
        result, data, files, console = self.run_guard(stderr=b"diagnostic\r\n")
        self.assertEqual(result, 0)
        self.assertTrue(data["accepted"])
        self.assertEqual(files["sdk-version.stdout"], b"10.0.401\n")
        self.assertEqual(files["sdk-version.stderr"], b"diagnostic\r\n")
        self.assertIn("10.0.401", console)

    def test_installed_expected_sdk_cannot_mask_wrong_selected_sdk(self):
        result, data, files, _ = self.run_guard(b"10.0.402\n")
        self.assertEqual(result, 1)
        self.assertFalse(data["accepted"])
        self.assertIn(b"10.0.401", files["sdk-list-sdks.stdout"])

    def test_banner_is_retained_and_rejected_without_second_version_query(self):
        banner = b"Welcome to .NET!\n10.0.401\n"
        result, data, files, _ = self.run_guard(banner)
        self.assertEqual(result, 1)
        self.assertEqual(files["sdk-version.stdout"], banner)
        self.assertFalse(data["accepted"])

    def test_shell_comparison_preserves_leading_and_trailing_spaces(self):
        self.assertEqual(self.run_guard(b" 10.0.401 \n")[0], 1)

    def test_python_comparison_preserves_previous_strip_behavior(self):
        self.assertEqual(self.run_guard(b" \r\n10.0.401 \r\n", comparison="strip")[0], 0)

    def test_shell_command_substitution_only_trims_lf(self):
        self.assertEqual(self.run_guard(b"10.0.401\n\n")[0], 0)
        self.assertEqual(self.run_guard(b"10.0.401\r\n")[0], 1)

    def test_nonzero_version_cannot_pass_with_expected_stdout(self):
        self.assertEqual(self.run_guard(code=1)[0], 1)

    def test_empty_output_rejected(self):
        self.assertEqual(self.run_guard(b"")[0], 1)

    def test_timeout_retains_partial_output_before_rejecting(self):
        result, data, files, _ = self.run_guard(error=subprocess.TimeoutExpired(["dotnet", "--version"], 60, output=b"partial", stderr=b"error"))
        self.assertEqual(result, 1)
        self.assertEqual(data["commands"][0]["error"], "TimeoutExpired")
        self.assertEqual(files["sdk-version.stdout"], b"partial")
        self.assertEqual(files["sdk-version.stderr"], b"error")

    def test_missing_executable_still_retains_failure_receipt(self):
        result, data, _, _ = self.run_guard(error=FileNotFoundError("missing SDK"))
        self.assertEqual(result, 1)
        self.assertIn("FileNotFoundError", data["commands"][0]["error"])

    def test_invalid_utf8_retained_and_rejected(self):
        result, _, files, _ = self.run_guard(b"\xff10.0.401\n", comparison="strip")
        self.assertEqual(result, 1)
        self.assertEqual(files["sdk-version.stdout"], b"\xff10.0.401\n")


if __name__ == "__main__":
    unittest.main()
