"""
CI and the release gate run the same checks (v1.9.1, audit finding P5-05; RELEASE_PATTERN.md section 5 and
hygiene rule 7).

The fifth-pass audit found a 277-test CLI suite that ran only in CI, an eslint script that ran nowhere, and two
CI pytest commands without `--fail-on-skip`. These tests read the workflows and release.sh and fail when
that happens again:

* every pytest command in a workflow passes `--fail-on-skip`
* every tool a workflow invokes is a gate step, unless it is named below with a reason
* every pytest target a workflow runs is covered by a pytest gate step
* the Python wrapper's test directory accepts the flag (the conftest shim)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
RELEASE_SH = PROJECT_ROOT / "scripts" / "release.sh"

# Tools a workflow runs that are deliberately not gate steps. Each needs a reason.
NOT_IN_GATE = {
    "check_amendments.py": "runs weekly in monitor-amendments.yml and needs the SIX site; it is a monitor, not a per-push check",
}


def _workflow_lines() -> list[tuple[str, str]]:
    lines = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("#"):
                lines.append((path.name, line))
    return lines


def _gate_body() -> str:
    found = re.search(r"(?ms)^run_gate\(\)\s*\{\n(.*?)^\}", RELEASE_SH.read_text(encoding="utf-8"))
    assert found, "release.sh has no run_gate()"
    return found.group(1)


def test_every_pytest_command_in_a_workflow_passes_fail_on_skip():
    offenders = [
        f"{name}: {line.strip()}"
        for name, line in _workflow_lines()
        if re.search(r"-m pytest\b", line) and "--fail-on-skip" not in line
    ]
    assert not offenders, "pytest without --fail-on-skip (a skipped test verified nothing):\n" + "\n".join(offenders)


def test_every_tool_a_workflow_runs_is_a_gate_step_or_exempt():
    gate = set(re.findall(r"run_gate_step\s+\"[^\"]+\"\s+(?:python3|bash)\s+tools/([\w.]+)", _gate_body()))
    assert len(gate) >= 15
    invoked = {
        match
        for _, line in _workflow_lines()
        for match in re.findall(r"\b(?:python3?|bash)\s+tools/([\w]+\.(?:py|sh))", line)
    }
    missing = sorted(invoked - gate - set(NOT_IN_GATE))
    assert not missing, f"CI runs these tools but the gate does not: {missing}"
    stale = sorted(set(NOT_IN_GATE) - invoked)
    assert not stale, f"NOT_IN_GATE names tools no workflow runs any more: {stale}"


def test_every_pytest_target_in_a_workflow_is_covered_by_a_gate_step():
    gate_targets = re.findall(r"run_gate_step\s+\"[^\"]+\"\s+python3 -m pytest (\S+)", _gate_body())
    assert gate_targets, "the gate has no pytest step"
    for name, line in _workflow_lines():
        match = re.search(r"-m pytest\s+(\S+)", line)
        if not match:
            continue
        target = match.group(1)
        assert any(target.startswith(g.rstrip("/")) for g in gate_targets), (
            f"{name} runs pytest on {target}, which no gate pytest step covers (gate: {gate_targets})"
        )


def test_the_plan_echoes_the_same_pytest_and_lint_steps():
    text = RELEASE_SH.read_text(encoding="utf-8")
    for needle in ("python3 -m pytest wrappers/python/tests/ -q --fail-on-skip", "bash tools/check_js_lint.sh"):
        assert re.search(r'(?m)^\s*echo "  ' + re.escape(needle) + '"$', text), f"print_plan does not list: {needle}"
        assert re.search(r'(?m)^\s*run_gate_step\s+"[^"]+"\s+' + re.escape(needle) + r"\s*$", text), f"gate does not run: {needle}"


def test_the_python_wrapper_test_directory_accepts_the_flag():
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "wrappers/python/tests", "--collect-only", "-q", "--fail-on-skip", "-p", "no:cacheprovider"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
