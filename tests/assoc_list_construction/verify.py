"""Fail-closed classification of actual connected associative-construction evidence.
Pure adversarial controls are parser tests, never engine/runtime evidence.
"""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
CLASS = "Content.IntegrationTests.AssocListConstructionTests"
TEST = "RejectedConstructionReleasesOwners"
MARKER = "ASSOC_CONSTRUCT_COMPLETE: 48 rejection cases x 1000 real compiled constructions, 20 success controls, caller owners and reference buckets"
SPEC = json.loads(Path(__file__).with_name("expected-rejection-observations.json").read_text())
LIMIT = 8 * 1024 * 1024
ERROR = re.compile(r"\[ERRO\]|Unhandled exception|Runtime occurred|runtime error|test run aborted|testhost[^\n]*(?:crash|exit)|Isolated DM fixture compilation failed|(?:error|warning) (?:CS|DM)\d+|Build FAILED|Failed to (?:compile|start|launch)|NUnit.*(?:adapter error|discovery failed)", re.I)
ROW = re.compile(r"^(ASSOC_CONSTRUCT_REJECT_[a-z0-9_]+): owners=\[([0-9,]+)\]; lists=(\d+) expected=(\d+); datums=(\d+) expected=(\d+)$")

# This fixture is deliberately standalone. No GameTests/engine/foreign assertion frames are accepted.
FIXTURE_FILE = r"(?:[^\r\n]+/)?Content\.IntegrationTests/AssocListConstructionTests\.cs:line [1-9]\d*"
INTEGRATION_FILE = r"(?:[^\r\n]+/)?RobustToolbox/Robust\.UnitTesting/RobustIntegrationTest\.cs:line [1-9]\d*"
FIXTURE_METHODS = [
    r"RejectedConstructionReleasesOwners\(\)",
    r"Reject\(DreamManager manager, DreamObjectTree tree, DreamRefManager refs, DreamProc proc, DreamProc reuse, String route, Int32 bad, String position, Boolean list, Boolean alias\)",
    r"AssertBuckets\(DreamRefManager refs, Dictionary`2 expected, String id\)",
    r"<>c__DisplayClass\d+_\d+\.<RejectedConstructionReleasesOwners>b__\d+\(\)",
]
FRAME_PATTERNS = [r"at " + re.escape(CLASS) + r"\." + method + r" in " + FIXTURE_FILE for method in FIXTURE_METHODS] + [
    r"at NUnit\.Framework\.Assert\.Multiple\(TestDelegate testDelegate\)",
    r"at Robust\.UnitTesting\.RobustIntegrationTest\.IntegrationGameLoop\.(?:SingleThreadRunUntilEmpty|Run)\(\) in " + INTEGRATION_FILE,
    r"at Robust\.UnitTesting\.RobustIntegrationTest\.ServerIntegrationInstance\._serverMain\(\) in " + INTEGRATION_FILE,
    r"at System\.Threading\.Thread\.StartHelper\.Callback\(Object state\)",
]
FRAMES = [re.compile(pattern) for pattern in FRAME_PATTERNS]


def require(value, message):
    if not value:
        raise AssertionError(message)


def check_spec():
    expected = []
    for kind in ("datum", "list"):
        for alias in ("distinct", "alias"):
            for route in ("caught", "uncaught"):
                for bad in (0, 99):
                    for position in ("first", "middle", "last"):
                        expected.append(f"ASSOC_CONSTRUCT_REJECT_{route}_{bad}_{position}_{kind}_{alias}")
    require(len(SPEC) == 48 and [case["id"] for case in SPEC] == expected, "case specification order/identity drift")
    for case in SPEC:
        require(case["iterations"] == 1000 and case["expected_extra_lists"] == 0 and case["frozen_original_extra_lists"] == 1000 and case["expected_extra_datums"] == 0, "case expectation drift")
        alias = case["id"].endswith("_alias")
        fixed = [1] if alias else [1, 1, 1, 1]
        position = case["id"].split("_")[5]
        # Components: ASSOC CONSTRUCT REJECT route bad position kind identity.
        original = [3001] if alias else {"first": [1001, 1, 1001, 1001], "middle": [1001, 1001, 1, 1001], "last": [1001, 1001, 1001, 1]}[position]
        require(case["expected_owners"] == fixed and case["frozen_original_owners"] == original, "owner specification drift")


def check_stack(text, require_fixture=True):
    text = text.replace("\\", "/")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    require(lines, "missing assertion stack")
    for line in lines:
        require(any(pattern.fullmatch(line) for pattern in FRAMES), "foreign/unknown assertion stack frame: " + line)
    if require_fixture:
        require(any(CLASS + "." in line and "Content.IntegrationTests/AssocListConstructionTests.cs:line " in line for line in lines), "missing fixture/source frame")


def stdout_rows(text, mode):
    parsed = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ASSOC_CONSTRUCT_REJECT_") and ": owners=" in line:
            match = ROW.fullmatch(line)
            require(match is not None, "malformed ownership observation")
            identifier, owners, lists, expected_lists, datums, expected_datums = match.groups()
            parsed.append((identifier, [int(value) for value in owners.split(",")], int(lists), int(expected_lists), int(datums), int(expected_datums)))
        elif line.startswith("ASSOC_CONSTRUCT_") and not line == MARKER and not re.fullmatch(r"ASSOC_CONSTRUCT_REJECT_[a-z0-9_]+_(?:OWNERS_1000|LIVE_BUCKET_DreamObjectList)", line):
            require(False, "unknown fixture stdout observation")
    require(len(parsed) == 48, "missing/extra/duplicate ownership observations")
    for case, row in zip(SPEC, parsed):
        identifier, owners, lists, expected_lists, datums, expected_datums = row
        require(identifier == case["id"], "observation order/identity mismatch")
        require(owners == case["expected_owners" if mode == "positive" else "frozen_original_owners"], "wrong observed ownership counts")
        require(lists == expected_lists + (0 if mode == "positive" else 1000), "wrong observed list bucket count")
        require(datums == expected_datums, "wrong observed datum bucket count")
        # Exact held-bucket deltas must fit one constant pristine base for every case.
        alias, list_payload = identifier.endswith("_alias"), "_list_" in identifier
        held_lists = (1 if alias else 3) if list_payload else 0
        held_datums = 1 if alias else 4
        require(expected_lists >= held_lists and expected_datums >= held_datums, "negative pristine bucket baseline")
        row_base = (expected_lists - held_lists, expected_datums - held_datums)
        if identifier == SPEC[0]["id"]:
            pristine = row_base
        else:
            require(row_base == pristine, "pristine buckets drifted between cases")
    require(text.count(MARKER) == (1 if mode == "positive" else 0), "wrong completion marker count")
    return parsed


def message_blocks(message):
    require(message.startswith("Multiple failures or warnings in test:"), "not a NUnit aggregate failure")
    remainder = message[len("Multiple failures or warnings in test:"):]
    matches = list(re.finditer(r"(?m)^\s*(\d+)\)\s*", remainder))
    require(len(matches) == 96, "not exactly 96 assertion failures")
    require(not remainder[:matches[0].start()].strip(), "unknown aggregate preamble")
    blocks = []
    for index, match in enumerate(matches):
        require(int(match.group(1)) == index + 1, "wrong assertion numbering/order")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(remainder)
        blocks.append(remainder[match.end():end].strip())
    return blocks


def check_failure(block, marker, expression, body):
    lines = block.splitlines()
    require(lines and lines[0].strip() == marker, "unknown/missing/duplicate assertion ID")
    frame_start = next((index for index, line in enumerate(lines) if line.strip().startswith("at ")), len(lines))
    content = "\n".join(lines[1:frame_start]).strip()
    pattern = re.escape(expression) + r"\s+" + body
    require(re.fullmatch(pattern, content) is not None, "unexpected NUnit assertion message: " + marker)
    # Embedded assertion stacks may be omitted by NUnit; present frames are strictly checked.
    if frame_start < len(lines):
        check_stack("\n".join(lines[frame_start:]))


def verify(path, mode, exit_code, log):
    check_spec()
    require(mode in ("positive", "baseline"), "unknown verification mode")
    require(isinstance(log, str) and 0 < len(log.encode()) <= LIMIT, "missing/oversized original runner log")
    path = Path(path)
    require(0 < path.stat().st_size <= LIMIT, "empty/oversized TRX")
    tree = ET.parse(path)
    require(not ERROR.search(log + "\n" + "\n".join(tree.getroot().itertext())), "runtime/compile/runner error")
    rows = tree.findall(".//t:UnitTestResult", NS)
    counters_nodes = tree.findall(".//t:ResultSummary/t:Counters", NS)
    require(len(rows) == 1 and len(counters_nodes) == 1, "missing/extra result or counters")
    row, counters = rows[0], counters_nodes[0]
    allowed_counters = {"total", "executed", "passed", "failed", "error", "timeout", "aborted", "inconclusive", "notRunnable", "notExecuted", "disconnected", "warning", "passedButRunAborted", "inProgress", "pending", "completed"}
    require(set(counters.attrib).issubset(allowed_counters) and all(re.fullmatch(r"\d+", value) for value in counters.attrib.values()), "unknown/non-numeric runner counter")
    require(counters.get("completed", "1") == "1", "wrong completed counter")
    require(row.get("testName") == TEST, "wrong test result identity")
    definitions = tree.findall(".//t:TestDefinitions/t:UnitTest", NS)
    require(len(definitions) == 1 and definitions[0].get("id") == row.get("testId"), "wrong/missing/extra definition")
    methods = definitions[0].findall("t:TestMethod", NS)
    require(len(methods) == 1 and methods[0].get("className") == CLASS and methods[0].get("name") == TEST, "wrong fixture/method")
    require(counters.get("total") == counters.get("executed") == "1", "not exactly one executed test")
    for key in ("error", "timeout", "aborted", "inconclusive", "notRunnable", "notExecuted", "disconnected", "warning", "passedButRunAborted", "inProgress", "pending"):
        require(int(counters.get(key, "0")) == 0, "runner/skipped counter: " + key)
    require(not tree.findall(".//t:RunInfo[@outcome='Error']", NS) and not tree.findall(".//t:RunInfo[@outcome='Warning']", NS), "runner error/warning record")
    require(not any((node.text or "").strip() for node in tree.findall(".//t:StdErr", NS)), "unexpected stderr")
    outcome = "Passed" if mode == "positive" else "Failed"
    require(exit_code == (0 if mode == "positive" else 1) and row.get("outcome") == outcome, "wrong exit/outcome")
    require(counters.get("passed") == ("1" if mode == "positive" else "0") and counters.get("failed") == ("0" if mode == "positive" else "1"), "wrong pass/fail counters")
    result_lines = re.findall(r"(?m)^\s*(Passed|Failed|Skipped|NotExecuted)\s+([^\r\n]+)$", log)
    require(len(result_lines) == 1 and result_lines[0][0] == outcome and re.fullmatch(re.escape(TEST) + r"(?:\s+\[[^\r\n]+\])?", result_lines[0][1].strip()), "missing/extra/foreign runner test result")
    summary = "Test Run Successful." if mode == "positive" else "Test Run Failed."
    require(log.count(summary) == 1 and log.count("Test Run Successful.") + log.count("Test Run Failed.") == 1, "wrong/duplicate runner summary")
    stdout_nodes = row.findall("t:Output/t:StdOut", NS)
    require(len(stdout_nodes) == 1, "missing/extra stdout")
    observations = stdout_rows(stdout_nodes[0].text or "", mode)
    require(stdout_rows(log, mode) == observations, "runner log differs from original TRX stdout observations")
    allowed_markers = {case["id"] for case in SPEC}
    if mode == "baseline":
        allowed_markers |= {case["id"] + suffix for case in SPEC for suffix in ("_OWNERS_1000", "_LIVE_BUCKET_DreamObjectList")}
    else:
        allowed_markers.add("ASSOC_CONSTRUCT_COMPLETE")
    for marker in re.findall(r"\bASSOC_CONSTRUCT_[A-Za-z0-9_]+", log):
        require(marker in allowed_markers, "unknown/foreign fixture marker in original log")
    for line in log.replace("\\", "/").splitlines():
        if line.strip().startswith("at "):
            check_stack(line.strip(), require_fixture=False)
    errors = tree.findall(".//t:ErrorInfo", NS)
    if mode == "positive":
        require(not errors, "positive run has assertion failures")
    else:
        require(len(errors) == 1 and errors[0] is row.find("t:Output/t:ErrorInfo", NS), "not exactly one dedicated failure aggregate")
        error = errors[0]
        require(len(error.findall("t:Message", NS)) == len(error.findall("t:StackTrace", NS)) == 1, "missing/extra failure message/stack")
        blocks = message_blocks(error.findtext("t:Message", "", NS))
        for index, (case, observation) in enumerate(zip(SPEC, observations)):
            changed = next(i for i, value in enumerate(case["frozen_original_owners"]) if value != 1)
            count = len(case["expected_owners"])
            owner_body = (r"Expected and actual are both <System\.Int32\[" + str(count) + r"\]>\s+Values differ at index \[" + str(changed) + r"\]\s+Expected:\s+1\s+But was:\s+" + str(case["frozen_original_owners"][changed]))
            check_failure(blocks[2 * index], case["id"] + "_OWNERS_1000", "Assert.That(counts, Is.EqualTo(expectedOwners))", owner_body)
            bucket_body = r"Expected:\s+" + str(observation[3]) + r"\s+But was:\s+" + str(observation[2])
            check_failure(blocks[2 * index + 1], case["id"] + "_LIVE_BUCKET_DreamObjectList", "Assert.That(refs.GetCountOf(type), Is.EqualTo(expected[type].Count))", bucket_body)
        check_stack(error.findtext("t:StackTrace", "", NS))
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("trx", type=Path)
    parser.add_argument("mode", choices=["positive", "baseline"])
    parser.add_argument("exit_code", type=int)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    verify(args.trx, args.mode, args.exit_code, args.log.read_text())
    print("Strict dedicated construction TRX and original log accepted; this classifier does not create runtime evidence")