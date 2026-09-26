#!/usr/bin/env python3
"""
ISO 4217 Currency Registry — Wrapper Sync Tool.

Three wrapper directories carry a local copy of iso4217.json:

  wrappers/python/iso4217.json   resolved at runtime by iso4217.py
  wrappers/go/iso4217.json       embedded at build time (go:embed)
  wrappers/rust/iso4217.json     embedded at build time (include_str!)

None of them update automatically when the root file changes. This tool
copies root into all three, and its --check mode fails the build when
any copy has drifted.

Usage:
  python3 tools/sync_wrappers.py            copy root to all three
  python3 tools/sync_wrappers.py --check    verify without writing

Exit codes:
  0 — all copies match root (or were successfully updated)
  1 — --check mode: at least one copy differs from root
  2 — fatal error (root registry missing, I/O failure)
  3 — --check mode: at least one destination is missing
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_REGISTRY = PROJECT_ROOT / "iso4217.json"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_FATAL = 2
EXIT_MISSING = 3

WRAPPER_COPIES = [
    PROJECT_ROOT / "wrappers" / "python" / "iso4217.json",
    PROJECT_ROOT / "wrappers" / "go" / "iso4217.json",
    PROJECT_ROOT / "wrappers" / "rust" / "iso4217.json",
]


def _read_bytes(path: Path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def check_all(verbose: bool) -> int:
    root_bytes = _read_bytes(ROOT_REGISTRY)
    if root_bytes is None:
        print(f"FATAL: root registry not found at {ROOT_REGISTRY}", file=sys.stderr)
        return EXIT_FATAL

    missing = []
    mismatched = []

    for dest in WRAPPER_COPIES:
        dest_bytes = _read_bytes(dest)
        if dest_bytes is None:
            missing.append(dest)
        elif dest_bytes != root_bytes:
            mismatched.append(dest)
        elif verbose:
            print(f"  ok  {dest.relative_to(PROJECT_ROOT)}")

    for path in mismatched:
        print(f"  ✗ mismatched: {path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
    for path in missing:
        print(f"  ✗ missing:    {path.relative_to(PROJECT_ROOT)}", file=sys.stderr)

    if missing:
        print("Run 'python3 tools/sync_wrappers.py' to fix.", file=sys.stderr)
        return EXIT_MISSING
    if mismatched:
        print("Run 'python3 tools/sync_wrappers.py' to fix.", file=sys.stderr)
        return EXIT_MISMATCH

    print(f"All {len(WRAPPER_COPIES)} wrapper copies match the root registry.")
    return EXIT_OK


def sync_all() -> int:
    if not ROOT_REGISTRY.is_file():
        print(f"FATAL: root registry not found at {ROOT_REGISTRY}", file=sys.stderr)
        return EXIT_FATAL

    print(f"Root registry: {ROOT_REGISTRY}")
    for dest in WRAPPER_COPIES:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT_REGISTRY, dest)
        print(f"  copied -> {dest.relative_to(PROJECT_ROOT)}")
    print(f"Synced {len(WRAPPER_COPIES)} wrapper copies.")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync root iso4217.json to wrapper-local copies.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verify without writing; exit 1 on mismatch, 3 on missing",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print each copy that matches",
    )
    args = parser.parse_args()

    if args.check:
        return check_all(args.verbose)
    return sync_all()


if __name__ == "__main__":
    sys.exit(main())