"""
Tests for the topology and caching of .github/workflows/validate.yml (v1.9.0, F30).

The workflow is read as text (no YAML parser: PyYAML is not a CI dependency). The failure class these tests exist for: a
`cache:` input with no dependency file to hash. setup-python and setup-node fail the whole step then, and this repo has no
requirements.txt, no package-lock.json and no root go.sum, so every cache must name its file.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (PROJECT_ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
_JOB = re.compile(r"^  ([a-z0-9-]+):[ ]*\n", re.M)


def _jobs() -> dict[str, str]:
    start = WORKFLOW.index("\njobs:")
    heads = [(m.group(1), m.start()) for m in _JOB.finditer(WORKFLOW) if m.start() > start]
    return {n: WORKFLOW[s:(heads[i + 1][1] if i + 1 < len(heads) else len(WORKFLOW))] for i, (n, s) in enumerate(heads)}


def _steps(block: str) -> list[str]:
    parts = re.split(r"^      - ", block, flags=re.M)[1:]
    return ["      - " + p for p in parts]


def _needs(block: str) -> list[str]:
    m = re.search(r"^    needs: \[(.*?)\]", block, re.M)
    return [n.strip() for n in m.group(1).split(",")] if m else []


def test_validate_wrappers_does_not_wait_for_validate_json():
    jobs = _jobs()
    assert "validate-json" in jobs and "validate-wrappers" in jobs
    assert "validate-json" not in _needs(jobs["validate-wrappers"])
    assert "validate-wrappers" not in _needs(jobs["validate-json"])


def test_validate_wrappers_still_waits_for_what_it_consumes():
    needs = _needs(_jobs()["validate-wrappers"])
    for job in ("check-wrapper-sync", "check-sql-export", "check-csv-export", "check-parquet-export", "check-cli"):
        assert job in needs, job


def test_every_job_named_in_needs_exists():
    jobs = _jobs()
    for name, block in jobs.items():
        for dep in _needs(block):
            assert dep in jobs, f"{name} needs {dep}, which does not exist"


def test_every_cache_dependency_path_exists():
    paths = re.findall(r"cache-dependency-path:\s*(\S+)", WORKFLOW)
    assert len(paths) >= 6, paths
    for p in paths:
        assert (PROJECT_ROOT / p).exists(), f"cache-dependency-path {p} does not exist"


def test_every_setup_step_with_a_cache_names_its_dependency_file():
    checked = 0
    for name, block in _jobs().items():
        for step in _steps(block):
            if re.search(r"uses: actions/setup-(python|node|go)@", step) and re.search(r"^\s+cache: ", step, re.M):
                assert "cache-dependency-path:" in step, f"{name}: a cache with no dependency file:\n{step}"
                checked += 1
    assert checked >= 6, checked


def test_jobs_that_pip_install_cache_pip():
    for name, block in _jobs().items():
        if "pip install" not in block:
            continue
        setup = [s for s in _steps(block) if "actions/setup-python@" in s]
        assert setup and all("cache: 'pip'" in s for s in setup), f"{name} pip-installs without a pip cache"


def test_the_node_and_go_legs_are_cached():
    block = _jobs()["validate-wrappers"]
    node = [s for s in _steps(block) if "actions/setup-node@" in s][0]
    go = [s for s in _steps(block) if "actions/setup-go@" in s][0]
    assert "cache: 'npm'" in node and "wrappers/javascript/package.json" in node
    assert "cache: true" in go and "wrappers/go/go.sum" in go


def test_rust_is_cached_with_rust_cache_not_a_nonexistent_toolchain_input():
    steps = _steps(_jobs()["validate-wrappers"])
    toolchain = [s for s in steps if "dtolnay/rust-toolchain@" in s][0]
    assert "cache:" not in toolchain                       # that action has no such input
    cache = [s for s in steps if "Swatinem/rust-cache@" in s]
    assert len(cache) == 1
    assert re.search(r"Swatinem/rust-cache@[0-9a-f]{40} # v\d+\.\d+\.\d+", cache[0])
    assert "workspaces: wrappers/rust" in cache[0]
    assert steps.index(cache[0]) > steps.index(toolchain)
