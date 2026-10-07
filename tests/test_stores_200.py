"""
End-to-end test for examples/stores-200.

The demo reads its registry inputs (iso4217.parquet and the four
derived Parquet files) from two directories above its own cwd. The
test reproduces that layout in tmp_path: root/examples/stores-200/
for the demo, and the five parquets symlinked at root/. The demo is
run unchanged.

The demo depends on duckdb and pyarrow, which are not dependencies
of the main suite. The module skips cleanly when either is missing.

Assertions are specific substrings from the demo's actual output.
They are pinned in the docstrings so a future reader knows what each
one is checking, not just that a string matched.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "stores-200"

# The five Parquet artifacts the demo reads, at the tmp root.
REGISTRY_FILES = (
    "iso4217.parquet",
    "iso4217.countries.parquet",
    "currencies_by_region.parquet",
    "pegs_summary.parquet",
    "coverage_timeline.parquet",
)

# The demo also reads tools/iso3166_snapshot.json. Symlink the whole
# tools/ directory rather than enumerating its files: the demo treats
# it as read-only, and any future addition to what it reads is covered.
REGISTRY_DIRS = (
    "tools",
)

pytestmark = pytest.mark.skipif(
    not DEMO.is_dir(),
    reason="examples/stores-200 not present",
)

# Skip the whole module unless the demo's dependencies are available.
duckdb = pytest.importorskip("duckdb", reason="duckdb not installed")
pytest.importorskip("pyarrow", reason="pyarrow not installed")


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory) -> str:
    """
    Reproduce the repo layout in a tmp dir, run generate_facts.py and
    analyze.py, return analyze.py's stdout.

    Layout the demo expects:
        root/
          iso4217.parquet                  <- two levels up from cwd
          ...four more parquets...
          examples/
            stores-200/
              generate_facts.py            <- cwd
              analyze.py
              ...
    """
    root = tmp_path_factory.mktemp("demo")
    work = root / "examples" / "stores-200"
    work.mkdir(parents=True)

    for item in DEMO.iterdir():
        if item.name in {".gitignore", "__pycache__"}:
            continue
        if item.is_file():
            shutil.copy2(item, work / item.name)
        elif item.is_dir():
            shutil.copytree(item, work / item.name)

    for name in REGISTRY_FILES:
        src = REPO / name
        assert src.is_file(), f"missing registry artifact: {src}"
        (root / name).symlink_to(src)

    for name in REGISTRY_DIRS:
        src = REPO / name
        assert src.is_dir(), f"missing registry directory: {src}"
        (root / name).symlink_to(src, target_is_directory=True)

    gen = subprocess.run(
        [sys.executable, "generate_facts.py"],
        cwd=work, capture_output=True, text=True, timeout=180,
    )
    assert gen.returncode == 0, (
        f"generate_facts.py failed\n"
        f"stdout:\n{gen.stdout}\n"
        f"stderr:\n{gen.stderr}"
    )
    assert (work / "facts.parquet").is_file(), "generate_facts.py did not write facts.parquet"

    ana = subprocess.run(
        [sys.executable, "analyze.py"],
        cwd=work, capture_output=True, text=True, timeout=180,
    )
    assert ana.returncode == 0, (
        f"analyze.py failed\n"
        f"stdout:\n{ana.stdout}\n"
        f"stderr:\n{ana.stderr}"
    )
    assert ana.stderr.strip() == "", f"analyze.py wrote to stderr:\n{ana.stderr}"
    return ana.stdout


def test_demo_produces_six_query_sections(demo_run: str):
    for n in range(1, 7):
        assert f"Q{n}" in demo_run, f"missing Q{n} section"


def test_q1_total_revenue(demo_run: str):
    """Q1 total is fixed given deterministic facts."""
    assert "Total: 1,022,853,095 USD equivalents across 200 stores." in demo_run


def test_q1_join_double_counts(demo_run: str):
    """
    Joining stores to currencies_by_region on currency alone produces
    508 rows for 200 stores — the load-bearing demonstration that a
    currency is not a row key. If this number changes, either the demo
    or the registry changed shape; both deserve attention.
    """
    assert "508 rows for 200 stores" in demo_run
    assert "2,589,336,423 USD equivalents" in demo_run


def test_q1_check_passes(demo_run: str):
    assert "Check: 200 of 200 stores have their (region, currency) pair in currencies_by_region." in demo_run


def test_q4_reports_stores_without_region(demo_run: str):
    """
    XK and TW are valid country codes with no region in the ISO 3166
    snapshot. Seven stores, 36,531,068 USD equivalents.
    """
    assert "7 stores, 36,531,068 USD equivalents (3.6% of the chain)." in demo_run


def test_q4_naive_join_drops_stores(demo_run: str):
    """
    The demonstration that '=' on NULL is not true: 193 of 200 stores
    match on a plain (region, currency) join. The 7 that vanish are
    the whole point of Q4.
    """
    assert "Joining on (region, currency) with '=' matches 193 of 200 stores" in demo_run
    assert "IS NOT DISTINCT FROM matches 200" in demo_run


def test_q5_negative_result(demo_run: str):
    """
    Q5 asks a question coverage_timeline.parquet cannot answer: the
    timeline counts currencies per release, not per currency. The
    demo says so rather than guessing.
    """
    assert "stores with a registry release in force when they opened" in demo_run
    assert "0 of 200" in demo_run


def test_q6_pegged_share(demo_run: str):
    assert "6 of 22 currencies are pegged; they carry 13.2% of revenue." in demo_run
