#!/usr/bin/env python3
"""
ISO 4217 Currency Registry — Wrapper Sync Tool

Go and Rust embed their own local copy of iso4217.json at compile time
(go:embed, include_str!). Python and JavaScript locate the root file at
runtime instead. That means the Go/Rust copies are physically separate
files that do NOT update automatically when the root iso4217.json changes.

This tool copies the root iso4217.json into every wrapper directory that
keeps its own local copy, so they can't silently drift out of sync.

Usage:
  python3 tools/sync_wrappers.py

Exit codes:
  0 — root file found, all copies synced successfully
  1 — root iso4217.json is missing
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_REGISTRY = PROJECT_ROOT / "iso4217.json"

# Wrapper directories that keep their own local copy of iso4217.json.
# Python and JavaScript locate the root file at runtime and do NOT need
# an entry here.
WRAPPER_COPIES = [
    PROJECT_ROOT / "wrappers" / "go" / "iso4217.json",
    PROJECT_ROOT / "wrappers" / "rust" / "iso4217.json",
]


def main() -> int:
    if not ROOT_REGISTRY.is_file():
        print(f"ERROR: root registry not found at {ROOT_REGISTRY}")
        return 1

    print(f"Root registry: {ROOT_REGISTRY}")

    for dest in WRAPPER_COPIES:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT_REGISTRY, dest)
        print(f"  copied -> {dest.relative_to(PROJECT_ROOT)}")

    print(f"Synced {len(WRAPPER_COPIES)} wrapper copy/copies from root iso4217.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
