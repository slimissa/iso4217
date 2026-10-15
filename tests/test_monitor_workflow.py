"""
Tests for .github/workflows/monitor-amendments.yml (v1.7.15, findings F8 and F9).

The workflow is read as text, step by step, so these tests need no YAML
parser. They pin the three properties the release exists for:

  - the job holds exactly the permissions it uses (F8);
  - no failure is excused with continue-on-error, and the exit code of the
    check is captured and acted on (F9);
  - exit 1 opens the amendment issue, exit 3 opens the "cannot read" issue
    and turns the job red.

The behaviour of the steps themselves can only be seen on GitHub: run the
workflow with workflow_dispatch and simulate = undetermined, then
new-amendment (docs/v1.7.15-verification.md records both runs).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "monitor-amendments.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")


def _steps() -> list[str]:
    parts = re.split(r"(?m)^      - name: ", TEXT)
    return parts[1:]


def _step(prefix: str) -> str:
    found = [s for s in _steps() if s.startswith(prefix)]
    assert len(found) == 1, f"expected exactly one step starting {prefix!r}, found {len(found)}"
    return found[0]


class TestPermissions:
    def test_the_job_declares_exactly_read_contents_and_write_issues(self):
        assert re.search(r"(?m)^    permissions:\n      contents: read\n      issues: write\n", TEXT)

    def test_issues_is_the_only_write_permission(self):
        assert re.findall(r"(?m)^\s+(\w[\w-]*): write\s*$", TEXT) == ["issues"]
        assert "write-all" not in TEXT


class TestFailsClosed:
    def test_no_step_excuses_its_own_failure(self):
        assert "continue-on-error" not in TEXT

    def test_nothing_reads_a_failed_step_as_a_new_amendment(self):
        assert "outcome ==" not in TEXT and "outcome==" not in TEXT

    def test_the_check_step_captures_its_exit_code(self):
        step = _step("Check for amendments")
        assert "id: amendment_check" in step
        assert "rc=$?" in step
        assert 'echo "exit_code=${rc}" >> "$GITHUB_OUTPUT"' in step

    def test_the_amendment_issue_runs_on_exit_1_only_and_checks_the_json(self):
        step = _step("Create issue if new amendment detected")
        assert "if: steps.amendment_check.outputs.exit_code == '1'" in step
        assert "new_amendment_detected !== true" in step
        assert "core.setFailed" in step

    def test_the_cannot_read_issue_runs_on_exit_3_only(self):
        step = _step('Open or update the "cannot read the SIX page" issue')
        assert "if: steps.amendment_check.outputs.exit_code == '3'" in step
        assert "createComment" in step  # a repeat updates the open issue, it does not duplicate

    def test_the_job_goes_red_on_anything_but_0_or_1(self):
        step = _step("Fail unless the check read the SIX page")
        assert "always()" in step
        assert "exit_code != '0'" in step and "exit_code != '1'" in step
        assert re.search(r"(?m)^\s+exit 1\s*$", step)
        assert "::error" in step

    def test_the_red_step_comes_after_both_issue_steps(self):
        names = [s.splitlines()[0] for s in _steps()]
        red = names.index("Fail unless the check read the SIX page")
        assert red > names.index("Create issue if new amendment detected")
        assert red > names.index('Open or update the "cannot read the SIX page" issue')


class TestTwoIssues:
    def test_the_blind_issue_is_found_and_labelled_monitor_blind(self):
        step = _step('Open or update the "cannot read the SIX page" issue')
        assert "labels: 'monitor-blind'" in step
        assert "labels: ['maintenance', 'monitor-blind']" in step

    def test_the_two_alerts_have_different_titles_so_neither_buries_the_other(self):
        amendment = _step("Create issue if new amendment detected")
        blind = _step('Open or update the "cannot read the SIX page" issue')
        assert "'ISO 4217 amendment '" in amendment and "monitor-blind" not in amendment
        assert "'Amendment monitor cannot read the SIX page'" in blind


class TestDispatchTest:
    def test_workflow_dispatch_offers_the_simulation_choices(self):
        block = TEXT[TEXT.index("workflow_dispatch:"):TEXT.index("permissions:")]
        assert "simulate:" in block and "type: choice" in block
        assert "options: [none, undetermined, new-amendment]" in block

    def test_the_check_step_passes_the_choice_through_an_env_var(self):
        step = _step("Check for amendments")
        assert "SIMULATE: ${{ inputs.simulate }}" in step
        assert '--simulate "${SIMULATE}"' in step

    @pytest.mark.parametrize("fragment", ["ISO 4217 amendment ", "Amendment monitor cannot read the SIX page"])
    def test_simulated_issues_are_marked_so_they_cannot_pass_for_real_ones(self, fragment):
        assert re.search(r"prefix \+ '" + re.escape(fragment), TEXT)
        assert "'[dispatch test] '" in TEXT
