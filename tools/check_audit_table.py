#!/usr/bin/env python3
"""
tools/check_audit_table.py

Derive the truth of the tables in docs/AUDIT.md from the tree and compare.

docs/AUDIT.md says, for every tool in tools/: whether it declares a `--check`
option, which workflow files invoke it, and how many `run_gate()` steps in
scripts/release.sh invoke it. v1.8.4 wrote that table by hand and the fifth-pass
audit (v1.9.0) re-derived it with a short script and found it true, with nothing
keeping it true. This tool is that script, wired into the gate and CI
(RELEASE_PATTERN.md rule 8 says the table is the mechanism; this makes it
self-enforcing).

What is derived, and how:

  tools        every tools/*.py and tools/*.sh except __init__.py
  --check      an argparse declaration of the --check option, in code
               (a comment does not count; .sh tools never declare one)
  CI           .github/workflows/*.yml with a line that invokes the tool as
               `python3 tools/<name>` or `bash tools/<name>`, after comment
               lines are removed (a mention in a comment does not count)
  Gate         run_gate_step lines inside run_gate() in scripts/release.sh that
               invoke the tool; the table writes `yes` for one step and
               `yes (N steps)` for more

Every row in the table must match, every tool in tools/ must have a row, and
every row must name a tool that exists.

Usage:
    python3 tools/check_audit_table.py
    python3 tools/check_audit_table.py --root /path/to/project

Exit codes:
    0  the table matches the tree
    1  the table and the tree disagree (each disagreement is printed)
    2  fatal: AUDIT.md, release.sh or the workflows are missing or unreadable,
       run_gate() is not found, or the table has no rows
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_FATAL = 2

ROW = re.compile(r"^\|\s*`([\w.]+\.(?:py|sh))`\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
GATE_CELL = re.compile(r"^yes(?: \((\d+) steps\))?$")
DASH = "\u2014"


class FatalError(Exception):
    """Raised for conditions that map to exit code 2."""


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FatalError(f"cannot read {path}: {exc}") from exc


def derive_tools(root: Path) -> list[str]:
    tools_dir = root / "tools"
    if not tools_dir.is_dir():
        raise FatalError(f"no tools directory at {tools_dir}")
    return sorted(
        p.name for p in tools_dir.iterdir()
        if p.is_file() and p.suffix in (".py", ".sh") and p.name != "__init__.py"
    )


def declares_check(root: Path, tool: str) -> bool:
    if not tool.endswith(".py"):
        return False
    source = strip_comments(read(root / "tools" / tool))
    return bool(re.search(r"""add_argument\(\s*["']--check["']""", source))


def strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def derive_ci(root: Path, tool: str, workflows: dict[str, str]) -> list[str]:
    pattern = re.compile(r"\b(?:python3?|bash)\s+tools/" + re.escape(tool) + r"(?![\w.])")
    return sorted(name for name, text in workflows.items() if pattern.search(text))


def load_workflows(root: Path) -> dict[str, str]:
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        raise FatalError(f"no workflows directory at {folder}")
    files = sorted(folder.glob("*.yml")) + sorted(folder.glob("*.yaml"))
    if not files:
        raise FatalError(f"no workflow files under {folder}")
    return {p.name: strip_comments(read(p)) for p in files}


def gate_body(root: Path) -> str:
    text = read(root / "scripts" / "release.sh")
    found = re.search(r"(?ms)^run_gate\(\)\s*\{\n(.*?)^\}", text)
    if not found:
        raise FatalError("scripts/release.sh has no run_gate() function")
    return found.group(1)


def derive_gate(body: str, tool: str) -> int:
    pattern = re.compile(
        r"(?m)^\s*run_gate_step\s+\"[^\"]+\"\s+(?:python3?|bash)\s+tools/" + re.escape(tool) + r"(?![\w.])"
    )
    return len(pattern.findall(body))


def parse_table(text: str) -> tuple[dict[str, tuple[str, str, str]], list[str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    problems: list[str] = []
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        tool = match.group(1)
        if tool in rows:
            problems.append(f"{tool}: appears in the table more than once")
        rows[tool] = (match.group(2), match.group(3), match.group(4))
    return rows, problems


def compare(root: Path) -> tuple[list[str], int]:
    audit = read(root / "docs" / "AUDIT.md")
    rows, problems = parse_table(audit)
    if not rows:
        raise FatalError("docs/AUDIT.md has no table rows (| `tool.py` | ... | ... | ... |)")

    tools = derive_tools(root)
    workflows = load_workflows(root)
    body = gate_body(root)

    for tool in tools:
        if tool not in rows:
            problems.append(f"{tool}: in tools/ but has no row in docs/AUDIT.md")
    for tool in sorted(rows):
        if tool not in tools:
            problems.append(f"{tool}: has a row in docs/AUDIT.md but no file in tools/")

    for tool in tools:
        if tool not in rows:
            continue
        check_cell, ci_cell, gate_cell = rows[tool]

        has_check = declares_check(root, tool)
        if check_cell == "`--check`":
            table_check = True
        elif check_cell == DASH:
            table_check = False
        else:
            problems.append(f"{tool}: --check column is {check_cell!r}; expected `--check` or a dash")
            table_check = has_check
        if table_check != has_check:
            problems.append(
                f"{tool}: --check column says {'declared' if table_check else 'none'}, "
                f"the source says {'declared' if has_check else 'none'}"
            )

        ci_actual = derive_ci(root, tool, workflows)
        ci_table = [] if ci_cell == DASH else sorted(part.strip() for part in ci_cell.split(","))
        if ci_table != ci_actual:
            problems.append(
                f"{tool}: CI column says {ci_table or 'none'}, the workflows say {ci_actual or 'none'}"
            )

        gate_actual = derive_gate(body, tool)
        gate_match = GATE_CELL.match(gate_cell)
        if gate_cell == DASH:
            gate_table = 0
        elif gate_match:
            gate_table = int(gate_match.group(1)) if gate_match.group(1) else 1
        else:
            problems.append(f"{tool}: Gate column is {gate_cell!r}; expected a dash, `yes` or `yes (N steps)`")
            gate_table = gate_actual
        if gate_table != gate_actual:
            problems.append(f"{tool}: Gate column says {gate_table} step(s), release.sh run_gate() has {gate_actual}")

    return problems, len(tools)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_audit_table",
        description="Compare the tables in docs/AUDIT.md with the workflows, release.sh and tools/.",
    )
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help=f"project root (default: {PROJECT_ROOT})")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        problems, count = compare(root)
    except FatalError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return EXIT_FATAL

    if problems:
        print(f"docs/AUDIT.md does not match the tree ({len(problems)} disagreement(s)); the tree is right:")
        for problem in problems:
            print(f"  \u2717 {problem}")
        return EXIT_MISMATCH

    print(f"OK: docs/AUDIT.md matches the tree for all {count} tools (checked under {root / 'docs'})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
