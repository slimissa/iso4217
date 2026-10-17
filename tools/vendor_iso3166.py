#!/usr/bin/env python3
"""
tools/vendor_iso3166.py

Vendor ISO 3166's iso3166.json into tools/iso3166_snapshot.json, and prove it
stayed vendored.

The snapshot is a byte-for-byte copy of iso3166.json at a tagged ISO 3166
release. Its vendoring metadata (source_version, vendored_at, vendored_from,
review_by, refresh_cadence, notes) lives in the sibling
tools/iso3166_snapshot.meta.json, so the copy itself is never edited.

Nothing here re-serialises the copy. No serialization setting (key order,
indentation, escaping, newline) can therefore differ between two runs, and no
clock, locale or machine detail enters the bytes that --check compares. The one
file this tool does serialise, the meta file, takes every setting from
serialize_meta() and nowhere else.

Modes:
    python3 tools/vendor_iso3166.py --version 1.6.9 [--vendored-at YYYY-MM-DD] [--source PATH]
    python3 tools/vendor_iso3166.py --check [--source PATH]

The source is the ISO 3166 tag vX.Y.Z (tags are immutable), fetched from GitHub
with three attempts. --source reads a local iso3166.json instead.

--check calls the same build_vendored() the write path calls. There is no
separate comparison logic: every branch the write path takes, including the one
that preserves hand-set metadata, runs on every invocation. It compares
  1. tools/iso3166_snapshot.json against the snapshot bytes build_vendored() produces
  2. meta.source_version against the source's own meta.version
and fails on either mismatch.

One source schema is known today (ISO 3166 v1.6.7 and later). A second schema
needs an entry in SCHEMAS and a fixture in tests/test_vendor_iso3166.py; a test
fails until both exist.

Exit codes:
    0  wrote the snapshot, or --check matched
    1  --check found a mismatch (snapshot bytes, or source_version)
    2  usage or fatal error (unreadable file, invalid JSON, unknown source schema,
       no such tag, version mismatch on write)
    3  could not run: the source could not be fetched after three attempts
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_REL = "tools/iso3166_snapshot.json"
META_REL = "tools/iso3166_snapshot.meta.json"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_FATAL = 2
EXIT_CANNOT_RUN = 3

_sleep = time.sleep

DEFAULT_COMMENT = (
    "Vendoring metadata for tools/iso3166_snapshot.json. The snapshot itself stays "
    "byte-for-byte identical to ISO 3166's iso3166.json. Read by "
    "tools/check_snapshot_freshness.py, which looks for `meta.review_by` in this "
    "sibling file. The snapshot itself carries no `meta.review_by`; the vendoring "
    "metadata lives here so the byte-for-byte property is preserved."
)


class Fatal(Exception):
    exit_code = EXIT_FATAL


class CannotRun(Exception):
    exit_code = EXIT_CANNOT_RUN


class VersionMismatch(Exception):
    def __init__(self, expected: str, found: str) -> None:
        super().__init__(f"source meta.version is {found!r}, expected {expected!r}")
        self.expected, self.found = expected, found


# ---------------------------------------------------------------------------
# Source schemas
# ---------------------------------------------------------------------------

def _is_iso3166_1_6_7_plus(doc: Any) -> bool:
    if not isinstance(doc, dict):
        return False
    meta, countries = doc.get("meta"), doc.get("countries")
    if not isinstance(meta, dict) or not isinstance(meta.get("version"), str):
        return False
    if meta.get("schema_version") != "1.0.0":
        return False
    if not isinstance(countries, dict):
        return False
    active, withdrawn = countries.get("active"), countries.get("withdrawn")
    if not isinstance(active, list) or not active or not isinstance(withdrawn, list):
        return False
    return all(isinstance(c, dict) and isinstance(c.get("alpha_2"), str) for c in active)


SCHEMAS: dict[str, Callable[[Any], bool]] = {
    "iso3166-1.6.7+": _is_iso3166_1_6_7_plus,
}


def detect_schema(doc: Any) -> str:
    for name, matches in SCHEMAS.items():
        if matches(doc):
            return name
    raise Fatal("the source matches no known ISO 3166 schema (known: " + ", ".join(SCHEMAS) + ")")


# ---------------------------------------------------------------------------
# URLs and fetching
# ---------------------------------------------------------------------------

def raw_url(version: str) -> str:
    return f"https://raw.githubusercontent.com/slimissa/iso3166/v{version}/iso3166.json"


def blob_url(version: str) -> str:
    return f"https://github.com/slimissa/iso3166/blob/v{version}/iso3166.json"


def fetch_source(version: str, attempts: int = 3, timeout: float = 20.0) -> bytes:
    url = raw_url(version)
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "iso4217-vendor-check"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise Fatal(f"no ISO 3166 tag v{version} ({url} returned 404)") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        if attempt < attempts:
            _sleep(attempt)
    raise CannotRun(f"could not fetch {url} after {attempts} attempts: {last}")


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def merge_existing_meta(existing: dict[str, Any] | None) -> dict[str, Any]:
    """The preservation branch: carry hand-set vendoring metadata across a re-vendor.

    Preserved verbatim: $comment, source, meta (review_by, refresh_cadence), notes.
    Without an existing meta file, or without one of those keys, the default applies.
    """
    preserved = copy.deepcopy(existing) if existing else {}
    meta = preserved.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("review_by", None)
    meta.setdefault("refresh_cadence", "rare")
    notes = preserved.get("notes")
    return {
        "$comment": preserved.get("$comment", DEFAULT_COMMENT),
        "source": preserved.get("source", "iso3166"),
        "meta": meta,
        "notes": notes if isinstance(notes, list) else [],
    }


def build_vendored(
    source_bytes: bytes,
    version: str,
    existing_meta: dict[str, Any] | None,
    vendored_at: str | None,
) -> tuple[bytes, dict[str, Any]]:
    """Return (snapshot bytes, meta dict) for the ISO 3166 release `version`.

    The write path and --check both call this and nothing else to decide what the
    vendored files should contain.
    """
    try:
        doc = json.loads(source_bytes)
    except ValueError as exc:
        raise Fatal(f"the source is not valid JSON: {exc}") from exc
    detect_schema(doc)
    if doc["meta"]["version"] != version:
        raise VersionMismatch(version, doc["meta"]["version"])
    snapshot_bytes = source_bytes
    kept = merge_existing_meta(existing_meta)
    final = {
        "$comment": kept["$comment"],
        "source": kept["source"],
        "source_version": version,
        "vendored_at": vendored_at,
        "vendored_from": blob_url(version),
        "meta": kept["meta"],
        "notes": kept["notes"],
    }
    return snapshot_bytes, final


def serialize_meta(meta: dict[str, Any]) -> bytes:
    """Every setting that affects the meta file's bytes is named here and nowhere else."""
    return (json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def summarize_diff(old: bytes, new: bytes) -> list[str]:
    lines = []
    if old == new:
        return ["no difference"]
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            lines.append(f"first differing byte at offset {i}")
            break
    else:
        lines.append(f"one file is a prefix of the other ({len(old)} vs {len(new)} bytes)")
    try:
        o, n = json.loads(old), json.loads(new)
    except ValueError:
        return lines
    if o == n:
        lines.append("the JSON content is equal; only whitespace or formatting differs")
        return lines
    changed: list[str] = []
    for kind in ("active", "withdrawn"):
        oa = {c.get("alpha_2"): c for c in o.get("countries", {}).get(kind, [])}
        na = {c.get("alpha_2"): c for c in n.get("countries", {}).get(kind, [])}
        for code in sorted(set(oa) | set(na)):
            if oa.get(code) != na.get(code):
                fields = sorted(f for f in set(oa.get(code, {})) | set(na.get(code, {}))
                                if oa.get(code, {}).get(f) != na.get(code, {}).get(f))
                changed.append(f"{kind}/{code}: {', '.join(fields) or 'entry added or removed'}")
    meta_fields = sorted(f for f in set(o.get("meta", {})) | set(n.get("meta", {}))
                         if o.get("meta", {}).get(f) != n.get("meta", {}).get(f))
    if changed:
        lines.append(f"{len(changed)} entr{'y' if len(changed) == 1 else 'ies'} differ: " + "; ".join(changed[:12]))
    if meta_fields:
        lines.append("snapshot meta fields differ: " + ", ".join(meta_fields))
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Fatal(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise Fatal(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise Fatal(f"{path} is not a JSON object")
    return data


def _source_bytes(args: argparse.Namespace, version: str) -> bytes:
    if args.source:
        try:
            return Path(args.source).read_bytes()
        except OSError as exc:
            raise Fatal(f"cannot read --source {args.source}: {exc}") from exc
    return fetch_source(version)


def _run_check(args: argparse.Namespace, root: Path) -> int:
    snapshot_path, meta_path = root / SNAPSHOT_REL, root / META_REL
    existing_meta = _read_json(meta_path)
    version = existing_meta.get("source_version")
    if not isinstance(version, str) or not version:
        raise Fatal(f"{META_REL} has no source_version")
    try:
        committed = snapshot_path.read_bytes()
    except OSError as exc:
        raise Fatal(f"cannot read {snapshot_path}: {exc}") from exc
    source_bytes = _source_bytes(args, version)
    try:
        snapshot_bytes, _meta = build_vendored(source_bytes, version, existing_meta, existing_meta.get("vendored_at"))
    except VersionMismatch as exc:
        print(f"  MISMATCH: {META_REL} source_version is {exc.expected}, "
              f"but the source's meta.version is {exc.found}", file=sys.stderr)
        return EXIT_MISMATCH
    print(f"  source_version {version} == source meta.version {version}")
    if committed != snapshot_bytes:
        print(f"  MISMATCH: {SNAPSHOT_REL} is not byte-identical to ISO 3166 v{version}", file=sys.stderr)
        for line in summarize_diff(committed, snapshot_bytes):
            print(f"    {line}", file=sys.stderr)
        print(f"  Re-vendor with: python3 tools/vendor_iso3166.py --version {version}", file=sys.stderr)
        return EXIT_MISMATCH
    print(f"  {SNAPSHOT_REL}: byte-identical to ISO 3166 v{version} ({len(committed)} bytes)")
    return EXIT_OK


def _run_write(args: argparse.Namespace, root: Path) -> int:
    snapshot_path, meta_path = root / SNAPSHOT_REL, root / META_REL
    version = args.version
    existing_meta = _read_json(meta_path) if meta_path.exists() else None
    old_snapshot = snapshot_path.read_bytes() if snapshot_path.exists() else None
    vendored_at = args.vendored_at or datetime.now(timezone.utc).date().isoformat()
    try:
        date.fromisoformat(vendored_at)
    except ValueError as exc:
        raise Fatal(f"--vendored-at {vendored_at!r} is not an ISO date") from exc
    source_bytes = _source_bytes(args, version)
    try:
        snapshot_bytes, meta = build_vendored(source_bytes, version, existing_meta, vendored_at)
    except VersionMismatch as exc:
        raise Fatal(str(exc)) from exc
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(snapshot_bytes)
    meta_path.write_bytes(serialize_meta(meta))
    print(f"  wrote {SNAPSHOT_REL} ({len(snapshot_bytes)} bytes, ISO 3166 v{version})")
    print(f"  wrote {META_REL}")
    if old_snapshot is not None:
        for line in summarize_diff(old_snapshot, snapshot_bytes):
            print(f"    {line}")
    if meta["meta"].get("review_by") is None:
        print("  note: meta.review_by is unset; set it by hand once, later runs preserve it", file=sys.stderr)
    else:
        print(f"  preserved meta.review_by {meta['meta']['review_by']}; move it by hand if this re-vendor is a re-verification")
    return EXIT_OK


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vendor and verify the ISO 3166 snapshot.")
    ap.add_argument("--check", action="store_true", help="verify the committed snapshot against its source")
    ap.add_argument("--version", help="ISO 3166 release to vendor, for example 1.6.9 (write mode)")
    ap.add_argument("--vendored-at", help="date to record, YYYY-MM-DD (write mode; default today, UTC)")
    ap.add_argument("--source", help="read iso3166.json from this path instead of fetching the tag")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    base = Path(args.root) if args.root else (root or PROJECT_ROOT)
    try:
        if args.check:
            if args.version or args.vendored_at:
                raise Fatal("--check reads the version from the meta file; --version and --vendored-at are write-mode flags")
            return _run_check(args, base)
        if not args.version:
            raise Fatal("write mode needs --version (or use --check)")
        return _run_write(args, base)
    except (Fatal, CannotRun) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
