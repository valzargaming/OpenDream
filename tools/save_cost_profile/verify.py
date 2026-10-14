"""Strict TRX classifier. Synthetic verifier tests are not runtime evidence."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
CLASS = "Content.IntegrationTests.SaveCostProfileHostTests"
INFRA = re.compile(r"Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost.*(?:crash|unexpected.*exit)|Isolated host compilation failed|LastDMException|\[ERRO\]|\[FATL\]", re.I)
MARKERS = {"ActualFlushCountsBytesAndClocks": "SAVE_COST_SMOKE ", "EnabledCloseAndDirtyFailure": "SAVE_COST_LIFECYCLE ",
           "ScopeAndResourceFilterCoverage": "SAVE_COST_COVERAGE ", "DisabledFlushAndLifecycle": "SAVE_COST_DISABLED_LIFECYCLE_COMPLETE",
           "ModerateFlushWorkload": "SAVE_COST_WORKLOAD ", "EmptyClockCalibration": "SAVE_COST_CLOCK_CALIBRATION "}

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def logs_clean(text, method):
    # A full original expected ERROR remains in stdout. Restrict permission to
    # exact task-created path and one matching classifier marker, never any ERROR.
    actual = re.findall(r"^SAVE_COST_ACTUAL_LOG \[(Error|Fatal)\] ([^:]+): ([^\r\n]+)", text, re.M)
    classified = re.findall(r"^SAVE_COST_EXPECTED_DIRTY_JSON_ERROR_CLASSIFIED ([^\r\n]+)", text, re.M)
    expects = method in ("EnabledCloseAndDirtyFailure", "DisabledFlushAndLifecycle")
    require(len(actual) == len(classified) == (1 if expects else 0), "unexpected/missing actual ERROR classification")
    if expects:
        level, sawmill, message = actual[0]
        path = classified[0]
        require(re.fullmatch(r"(?:[A-Za-z]:)?[^\r\n]*[/\\]opendream-save-cost-host-[0-9a-f]{32}[/\\]data[/\\]dirty\.json", path) is not None, "wrong expected-error task path")
        require(level == "Error" and sawmill == "opendream.res" and message.startswith("Error flushing savefile " + path + ": System.Text.Json.JsonException:"), "wrong expected ERROR")
        require("DreamObjectSavefile.Flush" in text, "expected error lacks real Flush stack")
    require(INFRA.search(text) is None, "infrastructure/runtime/compiler error evidence")
    # Any conventional runner ERROR/Fatal lines bypassing classifier are rejected.
    require(re.search(r"^.*\[(?:Error|Fatal)\].*$", text, re.M) is None or all(line.startswith("SAVE_COST_ACTUAL_LOG ") for line in text.splitlines() if re.search(r"\[(?:Error|Fatal)\]", line)), "unclassified error line")

def verify(path, method, mode, exit_code, log):
    controls = json.loads(Path(__file__).with_name("controls.json").read_text())
    negative = mode not in ("positive", "original")
    require(not negative or mode in controls and controls[mode]["method"] == method, "wrong negative method")
    tree = ET.parse(path)
    rows = tree.findall(".//t:UnitTestResult", NS)
    definitions = tree.findall(".//t:TestDefinitions/t:UnitTest", NS)
    counters = tree.find(".//t:ResultSummary/t:Counters", NS)
    require(len(rows) == len(definitions) == 1 and counters is not None, "missing/extra/zero test rows")
    row, definition = rows[0], definitions[0]
    test_method = definition.find("t:TestMethod", NS)
    require(row.get("testName") == method and row.get("testId") == definition.get("id"), "wrong test identity")
    require(test_method is not None and test_method.get("className") == CLASS and test_method.get("name") == method, "wrong exact FQN")
    require(counters.get("total") == counters.get("executed") == "1", "not exactly one executed test")
    for key in ("error", "timeout", "aborted", "inconclusive", "notRunnable", "disconnected", "warning", "notExecuted"):
        require(int(counters.get(key, "0")) == 0, "runner counter " + key)
    require(not tree.findall('.//t:RunInfo[@outcome="Error"]', NS), "runner RunInfo error")
    stdout = row.findtext("t:Output/t:StdOut", "", NS)
    # Inspect both channels independently so duplicate capture is not mistaken
    # for duplicate actual log events, and neither channel can hide other errors.
    logs_clean(stdout, method)
    logs_clean(log, method)
    outcome = "Failed" if negative else "Passed"
    summary = "Test Run Failed." if negative else "Test Run Successful."
    require(re.search(r"\b" + outcome + " " + re.escape(method) + r"(?:\s|\[)", log) is not None and summary in log, "original log lacks selected result")
    require(exit_code == (1 if negative else 0) and row.get("outcome") == outcome, "wrong exit or outcome")
    require(counters.get("failed") == ("1" if negative else "0") and counters.get("passed") == ("0" if negative else "1"), "wrong outcome counters")
    errors = row.findall("t:Output/t:ErrorInfo", NS)
    require(len(tree.findall(".//t:ErrorInfo", NS)) == len(errors) == (1 if negative else 0), "extra/hidden error evidence")
    if not negative:
        marker = MARKERS.get(method)
        if marker:
            require(stdout.count(marker) == 1, "missing/duplicate completion marker")
        return "positive-one-test-pass"
    spec = controls[mode]
    message = errors[0].findtext("t:Message", "", NS).strip()
    stack = errors[0].findtext("t:StackTrace", "", NS)
    require(INFRA.search(message + stack) is None, "negative has unrelated failure")
    if "exception_message" in spec:
        require(message == "System.Exception : " + spec["exception_message"], "wrong exact smoke assertion")
        require("SaveCostDetachedSmoke.Smoke.Require" in stack and "SaveCostDetachedSmoke.Smoke." + spec["frame"] in stack, "wrong smoke assertion chain")
    else:
        # NUnit versions may prefix the source expression. Only its exact
        # declared expression and Expected/But numeric pair are accepted.
        normalized = "\n".join(line.strip() for line in message.splitlines() if line.strip())
        pair = f"Expected: {spec['expected']}\nBut was:  {spec['actual']}"
        admitted = {pair, spec["expression"] + "\n" + pair}
        require(normalized in admitted, "wrong exact numeric assertion")
        require((spec["frame"] in stack and CLASS in stack) if spec["frame"].startswith("<") else CLASS + "." + spec["frame"] in stack, "wrong numeric assertion frame")
        require(re.search(r"SaveCostProfileHostTests\.cs:line " + str(spec["source_line"]) + r"\b", stack) is not None, "wrong frozen assertion source line")
    require(method in stack and "RobustIntegrationTest" in stack, "failure lacks actual integration fixture chain")
    require("OneTimeTearDown" not in stack and "TearDown" not in message and "SetUp" not in message, "setup/cleanup failure cannot pass negative")
    return "expected-assertion-negative-pass"
