"""
Tests for tools/check_audit_table.py (v1.9.1): docs/AUDIT.md is derived from the tree and compared.

Every case builds a small synthetic project, so a failure names the one thing that was wrong. The
last test runs the tool on the real tree: the table has to be true for the commit being tested.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_audit_table.py"

TABLE = """\
| Tool | `--check` | CI | Gate |
|------|-----------|----|------|
| `alpha.py` | `--check` | ci.yml | yes |
| `beta.py` | \u2014 | ci.yml, other.yml | yes (2 steps) |
| `gamma.sh` | \u2014 | \u2014 | yes |
| `delta.py` | \u2014 | \u2014 | \u2014 |
"""

ALPHA = 'import argparse\np = argparse.ArgumentParser()\np.add_argument("--check", action="store_true")\n'
BETA = "print('beta')\n"

CI = """\
name: CI
on: push
jobs:
  a:
    steps:
      # python3 tools/delta.py is only mentioned in a comment
      - run: python3 tools/alpha.py --check
      - run: python3 tools/beta.py
  b:
    steps:
      - run: echo "tools/delta.py"
"""

OTHER = "name: Other\njobs:\n  c:\n    steps:\n      - run: python3 tools/beta.py\n"

RELEASE = """\
#!/usr/bin/env bash
run_gate() {
    run_gate_step "alpha" python3 tools/alpha.py --check
    run_gate_step "beta one" python3 tools/beta.py
    run_gate_step "beta two" python3 tools/beta.py --again
    run_gate_step "gamma" bash tools/gamma.sh
}

other() {
    :
}
"""


def build(tmp_path: Path, table: str = TABLE) -> Path:
    root = tmp_path / "proj"
    (root / "tools").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "scripts").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tools" / "alpha.py").write_text(ALPHA, encoding="utf-8")
    (root / "tools" / "beta.py").write_text(BETA, encoding="utf-8")
    (root / "tools" / "gamma.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (root / "tools" / "delta.py").write_text("# add_argument('--check') in a comment\n", encoding="utf-8")
    (root / "tools" / "data.json").write_text("{}", encoding="utf-8")
    (root / "docs" / "AUDIT.md").write_text("# Audit\n\n" + table, encoding="utf-8")
    (root / "scripts" / "release.sh").write_text(RELEASE, encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text(CI, encoding="utf-8")
    (root / ".github" / "workflows" / "other.yml").write_text(OTHER, encoding="utf-8")
    return root


def run(root: Path) -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(TOOL), "--root", str(root)], capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


def test_a_table_that_matches_the_tree_exits_0(tmp_path):
    code, out = run(build(tmp_path))
    assert code == 0, out
    assert "OK: docs/AUDIT.md matches the tree for all 4 tools" in out
    assert "checked under" in out and "docs" in out  # the OK line names what was checked (rule 6d)


def test_a_tool_with_no_row_exits_1(tmp_path):
    table = "\n".join(line for line in TABLE.splitlines() if "delta.py" not in line) + "\n"
    code, out = run(build(tmp_path, table))
    assert code == 1 and "delta.py: in tools/ but has no row" in out


def test_a_row_for_a_tool_that_does_not_exist_exits_1(tmp_path):
    code, out = run(build(tmp_path, TABLE + "| `ghost.py` | \u2014 | \u2014 | \u2014 |\n"))
    assert code == 1 and "ghost.py: has a row in docs/AUDIT.md but no file" in out


@pytest.mark.parametrize(
    "old,new,expect",
    [
        ("| `alpha.py` | `--check` | ci.yml | yes |", "| `alpha.py` | \u2014 | ci.yml | yes |", "--check column"),
        ("| `delta.py` | \u2014 | \u2014 | \u2014 |", "| `delta.py` | `--check` | \u2014 | \u2014 |", "--check column"),
        ("ci.yml, other.yml", "ci.yml", "CI column says ['ci.yml']"),
        ("| `delta.py` | \u2014 | \u2014 | \u2014 |", "| `delta.py` | \u2014 | ci.yml | \u2014 |", "CI column says ['ci.yml'], the workflows say none"),
        ("yes (2 steps)", "yes", "Gate column says 1 step(s), release.sh run_gate() has 2"),
        ("| `gamma.sh` | \u2014 | \u2014 | yes |", "| `gamma.sh` | \u2014 | \u2014 | \u2014 |", "Gate column says 0 step(s)"),
        ("| `alpha.py` | `--check` | ci.yml | yes |", "| `alpha.py` | `--check` | ci.yml | maybe |", "Gate column is 'maybe'"),
    ],
)
def test_a_cell_that_disagrees_with_the_tree_exits_1(tmp_path, old, new, expect):
    assert old in TABLE
    code, out = run(build(tmp_path, TABLE.replace(old, new)))
    assert code == 1 and expect in out, out


def test_a_tool_mentioned_only_in_a_comment_or_an_echo_is_not_invoked_by_ci(tmp_path):
    # delta.py appears in ci.yml in a comment and inside an echo; the table says no workflow runs it.
    code, out = run(build(tmp_path))
    assert code == 0, out


def test_a_duplicate_row_exits_1(tmp_path):
    code, out = run(build(tmp_path, TABLE + "| `alpha.py` | `--check` | ci.yml | yes |\n"))
    assert code == 1 and "appears in the table more than once" in out


def test_a_missing_audit_file_exits_2(tmp_path):
    root = build(tmp_path)
    (root / "docs" / "AUDIT.md").unlink()
    code, out = run(root)
    assert code == 2 and "FATAL" in out


def test_a_table_with_no_rows_exits_2(tmp_path):
    code, out = run(build(tmp_path, "no table here\n"))
    assert code == 2 and "no table rows" in out


def test_a_release_script_without_run_gate_exits_2(tmp_path):
    root = build(tmp_path)
    (root / "scripts" / "release.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    code, out = run(root)
    assert code == 2 and "run_gate" in out


def test_no_workflows_exits_2(tmp_path):
    root = build(tmp_path)
    for path in (root / ".github" / "workflows").iterdir():
        path.unlink()
    code, _ = run(root)
    assert code == 2


def test_the_real_table_matches_the_real_tree():
    done = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
