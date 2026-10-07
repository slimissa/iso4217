#!/usr/bin/env python3
"""
tools/check_readme_drift.py

Verify that README.md's structural claims match the repository.

Checks:
  1. links    — every relative link resolves to a tracked file or a directory
  2. tree     — every name in the Project Structure block exists in the tree
  3. counts   — every count claim matches its source of truth
  4. adrs     — ADR numbers are unique and README references resolve

Exit codes:
  0  no drift
  1  drift detected (each instance printed to stdout)
  2  usage error
  3  README or repo layout unexpected
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK, EXIT_DRIFT, EXIT_USAGE, EXIT_FATAL = 0, 1, 2, 3


def _find_repo() -> Path:
    """Walk up from this file until a directory containing .git is found."""
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / ".git").exists():
            return cand
    return Path.cwd()


REPO = Path(os.environ.get("README_CHECK_REPO") or _find_repo()).resolve()
README = REPO / "README.md"


def _tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return set(out.splitlines())


def _acceptable_names(tracked: set[str]) -> set[str]:
    """
    Every name that may appear as a leaf in the README tree block.

    For a tracked path 'wrappers/python/iso4217.py', both the full
    path and each basename along the way are acceptable:
        wrappers, python, iso4217.py, wrappers/python, wrappers/python/iso4217.py
    A README tree that shows a nested directory by its bare name
    ('python/') therefore passes.
    """
    names: set[str] = set()
    for t in tracked:
        parts = t.split("/")
        for i in range(len(parts)):
            names.add(parts[i])
            names.add("/".join(parts[: i + 1]))
    return names


# --------------------------------------------------------------------------
# 1. links
# --------------------------------------------------------------------------
_LINK_RE = re.compile(r"\]\((?!https?://|mailto:|#)([^)#\s]+)(#[^)]*)?")


def check_links(text: str, tracked: set[str]) -> list[str]:
    errors: list[str] = []
    for m in _LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith("./"):
            target = target[2:]
        p = REPO / target
        try:
            rel = p.resolve().relative_to(REPO).as_posix()
        except ValueError:
            errors.append(f"link escapes repo: {target}")
            continue
        if rel in tracked or (REPO / rel).is_dir():
            continue
        errors.append(f"dangling link: {target}")
    return errors


# --------------------------------------------------------------------------
# 2. tree
# --------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```text\n(.*?)```", re.DOTALL)
_TREE_LINE_RE = re.compile(r"^[│ ]*[├└]── ([^\s#]+)")


def check_tree(text: str, tracked: set[str]) -> list[str]:
    errors: list[str] = []
    acceptable = _acceptable_names(tracked)
    for block_m in _FENCE_RE.finditer(text):
        block = block_m.group(1)
        if "├──" not in block and "└──" not in block:
            continue
        for line in block.splitlines():
            m = _TREE_LINE_RE.match(line)
            if not m:
                continue
            name = m.group(1).rstrip("/")
            # Skip template placeholders (<version>, <X.Y.Z>, ellipses).
            if "<" in name or "…" in name or "..." in name:
                continue
            if name in acceptable:
                continue
            errors.append(f"tree names a file or dir not in the tree: {name}")
    return errors


# --------------------------------------------------------------------------
# 3. counts
# --------------------------------------------------------------------------
_NUM_WORDS = {
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def _json_registry() -> dict:
    return json.loads((REPO / "iso4217.json").read_text(encoding="utf-8"))


def _count_active() -> int:
    return len(_json_registry()["currencies"]["active"])


def _count_withdrawn() -> int:
    return len(_json_registry()["currencies"]["withdrawn"])


def _count_non_iso() -> int:
    return sum(len(v) for v in _json_registry()["non_iso"].values())


def _count_gate_steps() -> int:
    sh = (REPO / "scripts" / "release.sh").read_text(encoding="utf-8")
    return sum(
        1 for line in sh.splitlines()
        if re.match(r"^\s+run_gate_step\s", line)
    )


_COUNT_RULES = [
    (re.compile(r"\b(\d+)\s+active currencies\b"), _count_active, "active currencies"),
    (re.compile(r"\b(\d+)\s+withdrawn currencies\b"), _count_withdrawn, "withdrawn currencies"),
    (re.compile(r"\b(\d+)\s+commonly used non-ISO\b"), _count_non_iso, "non-ISO instruments"),
]


def check_counts(text: str, _tracked: set[str]) -> list[str]:
    errors: list[str] = []
    for pat, fn, label in _COUNT_RULES:
        actual = fn()
        for m in pat.finditer(text):
            claimed = int(m.group(1))
            if claimed != actual:
                errors.append(f"{label}: readme={claimed} actual={actual}")

    actual_gate = _count_gate_steps()
    for m in re.finditer(r"\b([a-z]+|\d+)-check gate\b", text):
        tok = m.group(1).lower()
        claimed = _NUM_WORDS.get(tok, int(tok) if tok.isdigit() else None)
        if claimed is None:
            continue
        if claimed != actual_gate:
            errors.append(
                f"gate step count: readme says '{tok}' ({claimed}) "
                f"actual={actual_gate}"
            )
    return errors


# --------------------------------------------------------------------------
# 4. ADRs
# --------------------------------------------------------------------------
_ADR_HEADING_RE = re.compile(r"^#\s+ADR\s+(\d{4})\b", re.MULTILINE)


def check_adrs(text: str, _tracked: set[str]) -> list[str]:
    decisions = REPO / "docs" / "decisions"
    if not decisions.is_dir():
        return [f"decisions directory missing: {decisions}"]
    errors: list[str] = []
    seen: dict[str, str] = {}
    for f in sorted(decisions.glob("*.md")):
        for m in _ADR_HEADING_RE.finditer(f.read_text(encoding="utf-8")):
            num = m.group(1)
            if num in seen:
                errors.append(f"ADR {num} declared twice: {seen[num]} and {f.name}")
            else:
                seen[num] = f.name
    for m in re.finditer(r"\bADR\s+(\d{4})\b", text):
        num = m.group(1)
        if num not in seen:
            errors.append(f"README cites ADR {num}, which no file declares")
    return errors


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
_CHECKS = {
    "links":  check_links,
    "tree":   check_tree,
    "counts": check_counts,
    "adrs":   check_adrs,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="README drift check")
    p.add_argument("--only", choices=list(_CHECKS))
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if not README.is_file():
        print(f"FATAL: {README} not found", file=sys.stderr)
        return EXIT_FATAL
    text = README.read_text(encoding="utf-8")
    try:
        tracked = _tracked()
    except subprocess.CalledProcessError as e:
        print(f"FATAL: git ls-files failed: {e}", file=sys.stderr)
        return EXIT_FATAL

    names = [args.only] if args.only else list(_CHECKS)
    errors: list[str] = []
    for name in names:
        for e in _CHECKS[name](text, tracked):
            errors.append(f"[{name}] {e}")

    if errors:
        for e in errors:
            print(f"DRIFT: {e}")
        print(f"\n{len(errors)} drift(s) detected.", file=sys.stderr)
        return EXIT_DRIFT

    if not args.quiet:
        print(f"OK: README matches the tree ({len(names)} check(s) run)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
