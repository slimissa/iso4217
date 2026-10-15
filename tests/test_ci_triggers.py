"""
Tests for the triggers of .github/workflows/validate.yml (v1.7.15, F4).

validate.yml used to list the paths that trigger it. A file missing from the
list (examples/**, tools/export_aggregated.py, CHANGELOG.md, ...) changed
nothing in CI although tests/ guards it. These tests pin the opposite: no
allow-list. The only filter tolerated is a fail-open `paths-ignore` of docs/**.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
TEXT = (WORKFLOWS / "validate.yml").read_text(encoding="utf-8")
ON_BLOCK = TEXT.split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]


class TestNoAllowList:
    def test_no_paths_key_under_any_trigger(self):
        assert not re.search(r"(?m)^\s+paths:\s*$", ON_BLOCK)

    def test_the_only_tolerated_filter_is_a_docs_paths_ignore(self):
        found = re.findall(r"(?m)^\s+paths-ignore:\s*\n((?:\s+- .+\n)+)", ON_BLOCK)
        for block in found:
            assert re.findall(r"- (.+)", block) == ["'docs/**'"]

    def test_the_other_workflows_have_no_filter_either(self):
        for path in WORKFLOWS.glob("*.yml"):
            if path.name == "monitor-amendments.yml":
                continue  # schedule and dispatch only
            on_block = path.read_text(encoding="utf-8").split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
            assert not re.search(r"(?m)^\s+paths:\s*$", on_block), path.name


class TestTriggersStillExist:
    def test_push_to_main_pull_request_and_manual_dispatch(self):
        assert re.search(r"(?m)^  push:\n    branches: \[main\]", ON_BLOCK)
        assert re.search(r"(?m)^  pull_request:\n    branches: \[main\]", ON_BLOCK)
        assert re.search(r"(?m)^  workflow_dispatch:", ON_BLOCK)
