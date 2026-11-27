"""
Tests for scripts/workflow_triggers.py (v1.9.6, the third audit pass's open item 6).

release.sh polls a workflow if and only if a push runs it. The helper reads the `on:` key of each workflow with the standard
library only, in every form GitHub accepts, and fails closed on anything it cannot read for certain. The end-to-end behaviour
(release.sh refusing or exempting a workflow) is in tests/test_release_harness.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HELPER = PROJECT_ROOT / "scripts" / "workflow_triggers.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import workflow_triggers as wt  # noqa: E402

JOBS = "\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo on: push\n"


class TestTheFormsGitHubAccepts:
    @pytest.mark.parametrize("on, expected", [
        ("on: push", ["push"]),
        ("on: [push, pull_request]", ["push", "pull_request"]),
        ("on: [ pull_request , 'push' ]", ["pull_request", "push"]),
        ("on: {push: {branches: [main]}, pull_request: {}}", ["push", "pull_request"]),
        ("on: {\"push\": {branches: [main, 'rel:*']}, workflow_dispatch: }", ["push", "workflow_dispatch"]),
        ("on:\n  push:\n    branches: [main]\n    tags: ['v*']\n  pull_request:\n", ["push", "pull_request"]),
        ("on:\n  - push\n  - workflow_dispatch\n", ["push", "workflow_dispatch"]),
        ("on:\n  schedule:\n    - cron: '0 8 * * 1'\n", ["schedule"]),
        ("on:\n  workflow_dispatch:\n    inputs:\n      push:\n        type: string\n", ["workflow_dispatch"]),
        ("on: workflow_dispatch", ["workflow_dispatch"]),
        ("on:   push   # every push to any branch", ["push"]),
        ("on:\n  # comment line\n  push:   # trailing\n\n  schedule:\n    - cron: '1 1 * * *'\n", ["push", "schedule"]),
        ("on: [push,\n     pull_request]", ["push", "pull_request"]),
        ("on:\n  \"push\":\n    branches: [main]\n", ["push"]),
    ], ids=lambda v: v if isinstance(v, str) else None)
    def test_the_trigger_names_are_read(self, on, expected):
        assert wt.triggers("name: x\n" + on + "\n" + JOBS) == expected

    @pytest.mark.parametrize("key", ["on", '"on"', "'on'"])
    def test_the_key_may_be_quoted(self, key):
        assert wt.triggers(f"name: x\n{key}: push\n" + JOBS) == ["push"]

    def test_the_yaml_1_1_on_true_trap(self):
        # A YAML 1.1 loader (PyYAML's safe_load) turns an unquoted `on` key into the boolean True, so a lookup of "on" finds
        # nothing and the workflow looks trigger-less: exempt from polling by accident. Here the unquoted key is the key.
        text = "name: x\non:\n  push:\n    branches: [main]\n" + JOBS
        assert wt.triggers(text) == ["push"]
        # And what a 1.1 loader would have produced is not mistaken for a trigger key: there is no on: key in it.
        with pytest.raises(wt.Unreadable, match="no top-level on: key"):
            wt.triggers("name: x\ntrue:\n  push: {}\n" + JOBS)

    def test_an_indented_on_inside_a_job_is_not_the_trigger_key(self):
        text = "name: x\non: workflow_dispatch\njobs:\n  a:\n    with:\n      on: push\n"
        assert wt.triggers(text) == ["workflow_dispatch"]

    def test_a_push_mentioned_only_in_a_setting_is_not_a_trigger(self):
        text = "name: x\non:\n  pull_request:\n    types: [push]\n" + JOBS
        assert wt.triggers(text) == ["pull_request"]


class TestItFailsClosed:
    @pytest.mark.parametrize("text, reason", [
        ("name: x\n" + JOBS, "no top-level on: key"),
        ("name: x\non: push\non: schedule\n" + JOBS, "2 top-level on: keys"),
        ("name: x\non: *triggers\n" + JOBS, "unsupported YAML"),
        ("name: x\non: &t [push]\n" + JOBS, "unsupported YAML"),
        ("name: x\non: !!seq [push]\n" + JOBS, "unsupported YAML"),
        ("name: x\non: [push, pull_request\n" + JOBS, "does not end with"),
        ("name: x\non: {push: [main}\n" + JOBS, "unbalanced"),
        ("name: x\non:\njobs:\n  a: {}\n", "an empty on: key"),
        ("name: x\non:\n  push and more\n" + JOBS, "neither"),
    ])
    def test_what_it_cannot_read_is_an_error_not_a_guess(self, text, reason):
        with pytest.raises(wt.Unreadable, match=reason):
            wt.triggers(text)


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, timeout=60)


class TestTheCommandLine:
    def _dir(self, tmp_path: Path, files: dict[str, str]) -> Path:
        d = tmp_path / "workflows"
        d.mkdir()
        for name, on in files.items():
            (d / name).write_text("name: x\n" + on + "\n" + JOBS, encoding="utf-8")
        return d

    def test_polled_lists_exactly_the_push_triggered_files_whatever_their_names(self, tmp_path):
        d = self._dir(tmp_path, {
            "update-docs.yml": "on: push",                        # the audit's case: was exempt by name
            "monitor-x.yaml": "on: [push]",
            "refresh-nightly.yml": "on:\n  schedule:\n    - cron: '0 0 * * *'",
            "ci.yml": "on: {pull_request: {}, push: {}}",
            "manual.yml": "on: workflow_dispatch",
        })
        done = _cli("--polled", str(d))
        assert done.returncode == 0, done.stderr
        assert done.stdout.split() == ["ci.yml", "monitor-x.yaml", "update-docs.yml"]

    def test_explain_gives_every_file_a_verdict_and_a_reason(self, tmp_path):
        d = self._dir(tmp_path, {"a.yml": "on: push", "b.yml": "on: workflow_dispatch"})
        done = _cli("--explain", str(d))
        assert done.returncode == 0, done.stderr
        assert done.stdout.splitlines() == [
            "a.yml: polled (has a push trigger (on: push))",
            "b.yml: exempt (no push trigger (on: workflow_dispatch))",
        ]

    def test_one_unreadable_file_fails_the_whole_run_and_is_named(self, tmp_path):
        d = self._dir(tmp_path, {"good.yml": "on: push", "bad.yml": "on: *alias"})
        done = _cli("--polled", str(d))
        assert done.returncode == 2 and done.stdout == ""
        assert "bad.yml" in done.stderr and "good.yml" not in done.stderr

    def test_a_missing_directory_exits_2(self, tmp_path):
        assert _cli("--polled", str(tmp_path / "nope")).returncode == 2

    def test_a_mode_is_required(self, tmp_path):
        assert _cli(str(tmp_path)).returncode == 2


class TestThisRepository:
    def test_the_verdicts_for_the_real_workflows(self):
        verdicts = {p.name: wt.verdict(p)[0] for p in wt.workflow_files(PROJECT_ROOT / ".github" / "workflows")}
        assert verdicts == {"monitor-amendments.yml": False, "validate.yml": True, "version-and-hygiene.yml": True}

    def test_the_poll_list_in_release_sh_is_exactly_the_push_triggered_set(self):
        text = (PROJECT_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
        block = text.split("POLLED_WORKFLOWS=(", 1)[1].split(")", 1)[0]
        declared = sorted(w.strip().strip('"') for w in block.split() if w.strip())
        polled = sorted(p.name for p in wt.workflow_files(PROJECT_ROOT / ".github" / "workflows") if wt.verdict(p)[0])
        assert declared == polled

    def test_release_sh_has_no_name_based_exemption(self):
        text = (PROJECT_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
        body = text.split("check_workflows_covered() {", 1)[1].split("\n}\n", 1)[0]
        assert "scripts/workflow_triggers.py --polled" in body
        for prefix in ("monitor", "fetch", "refresh", "update", "schedule"):
            assert prefix not in body, prefix

    def test_it_needs_nothing_outside_the_standard_library(self):
        imports = [line.split()[1] for line in HELPER.read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from ")) and not line.startswith("from __future__")]
        assert set(imports) <= {"argparse", "re", "sys", "pathlib"}, imports
