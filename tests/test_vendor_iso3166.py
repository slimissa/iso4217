"""
Tests for tools/vendor_iso3166.py (v1.8.2).

The snapshot is vendored byte for byte, and --check calls the same builder the write
path calls. These tests pin: the copy is verbatim, --check fails on either mismatch,
every preservation branch runs on every invocation, exit codes mean what the docstring
says, and each known source schema has a fixture.

No test touches the network: the fetch is exercised with a stand-in for urlopen.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import vendor_iso3166 as v  # noqa: E402

TOOL = PROJECT_ROOT / "tools" / "vendor_iso3166.py"


def _fixture_v167_plus(version: str = "9.9.9") -> bytes:
    """A small source in the ISO 3166 v1.6.7+ shape, deliberately not json.dumps-stable:
    inline arrays, tabs and odd spacing, so a re-serialising tool cannot reproduce it."""
    text = (
        "{\n"
        '\t"meta" : {"version":"' + version + '", "schema_version": "1.0.0", "updated": "2026-01-01"},\n'
        '\t"countries": {\n'
        '\t\t"active": [ {"alpha_2": "AD", "currency_codes": ["EUR"]},\n'
        '\t\t\t{"alpha_2":"BG","currency_codes":["EUR"],"note": "caf\u00e9 \u20ac"} ],\n'
        '\t\t"withdrawn": [ ]\n'
        "\t}\n"
        "}\n"
    )
    return text.encode("utf-8")


FIXTURES = {"iso3166-1.6.7+": _fixture_v167_plus}

META_WITH_REVIEW = {
    "$comment": "kept comment",
    "source": "iso3166",
    "source_version": "9.9.8",
    "vendored_at": "2026-01-01",
    "vendored_from": "https://github.com/slimissa/iso3166/blob/v9.9.8/iso3166.json",
    "meta": {"review_by": "2099-12-31", "refresh_cadence": "rare"},
    "notes": ["a note that must survive"],
}


def _repo(tmp_path: Path, snapshot: bytes, meta: dict | None) -> Path:
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "iso3166_snapshot.json").write_bytes(snapshot)
    if meta is not None:
        # --check verifies snapshot_sha256 first; a fixture meta gets the hash of the snapshot it sits beside.
        meta = {**meta, "snapshot_sha256": meta.get("snapshot_sha256", v.snapshot_sha256(snapshot))}
        (tmp_path / "tools" / "iso3166_snapshot.meta.json").write_bytes(v.serialize_meta(meta))
    return tmp_path


def _source(tmp_path: Path, data: bytes) -> Path:
    p = tmp_path / "source.json"
    p.write_bytes(data)
    return p


def _run(root: Path, *args: str):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), *args],
                          capture_output=True, text=True, timeout=60)


# ---------------------------------------------------------------------------
# One test case per source schema
# ---------------------------------------------------------------------------

def test_every_known_schema_has_a_fixture_and_every_fixture_a_schema():
    assert set(v.SCHEMAS) == set(FIXTURES), "add a fixture (or a SCHEMAS entry) so both sides exist"


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_each_schema_fixture_is_recognised_and_vendored_verbatim(name):
    data = FIXTURES[name]()
    assert v.detect_schema(json.loads(data)) == name
    snapshot, meta = v.build_vendored(data, "9.9.9", None, "2026-02-02")
    assert snapshot == data
    assert meta["source_version"] == "9.9.9"
    assert meta["vendored_from"] == "https://github.com/slimissa/iso3166/blob/v9.9.9/iso3166.json"


@pytest.mark.parametrize("doc", [[], {}, {"meta": {"version": "1"}}, {"meta": {"version": "1", "schema_version": "2.0.0"},
                                                                        "countries": {"active": [], "withdrawn": []}}])
def test_an_unknown_schema_is_fatal(doc):
    with pytest.raises(v.Fatal):
        v.detect_schema(doc)


# ---------------------------------------------------------------------------
# Verbatim copy, and the write/check round trip
# ---------------------------------------------------------------------------

def test_the_copy_is_verbatim_even_when_json_dumps_could_not_reproduce_it():
    data = _fixture_v167_plus()
    assert (json.dumps(json.loads(data), indent=2, ensure_ascii=False) + "\n").encode() != data
    assert v.build_vendored(data, "9.9.9", None, "2026-02-02")[0] == data


def test_write_then_check_passes(tmp_path):
    root = _repo(tmp_path, b"{}", dict(META_WITH_REVIEW))
    src = _source(tmp_path, _fixture_v167_plus())
    assert _run(root, "--version", "9.9.9", "--vendored-at", "2026-02-02", "--source", str(src)).returncode == 0
    r = _run(root, "--check", "--source", str(src))
    assert r.returncode == 0, r.stderr
    assert "byte-identical" in r.stdout


def test_check_fails_on_a_one_byte_difference(tmp_path):
    data = _fixture_v167_plus()
    root = _repo(tmp_path, data.replace(b"AD", b"AE", 1), {**META_WITH_REVIEW, "source_version": "9.9.9"})
    r = _run(root, "--check", "--source", str(_source(tmp_path, data)))
    assert r.returncode == 1
    assert "not byte-identical" in r.stderr and "active/AD" in r.stderr


def test_check_fails_when_only_whitespace_differs(tmp_path):
    data = _fixture_v167_plus()
    reformatted = (json.dumps(json.loads(data), indent=2, ensure_ascii=False) + "\n").encode()
    root = _repo(tmp_path, reformatted, {**META_WITH_REVIEW, "source_version": "9.9.9"})
    r = _run(root, "--check", "--source", str(_source(tmp_path, data)))
    assert r.returncode == 1
    assert "only whitespace or formatting differs" in r.stderr


def test_check_fails_when_source_version_disagrees_with_the_sources_own_version(tmp_path):
    data = _fixture_v167_plus("9.9.9")
    root = _repo(tmp_path, data, {**META_WITH_REVIEW, "source_version": "9.9.8"})
    r = _run(root, "--check", "--source", str(_source(tmp_path, data)))
    assert r.returncode == 1
    assert "source_version is 9.9.8" in r.stderr and "9.9.9" in r.stderr


# ---------------------------------------------------------------------------
# The preservation branches, exercised on purpose
# ---------------------------------------------------------------------------

def test_a_re_vendor_preserves_hand_set_metadata():
    data = _fixture_v167_plus()
    snapshot, meta = v.build_vendored(data, "9.9.9", dict(META_WITH_REVIEW), "2026-02-02")
    assert meta["meta"] == {"review_by": "2099-12-31", "refresh_cadence": "rare"}
    assert meta["notes"] == ["a note that must survive"]
    assert meta["$comment"] == "kept comment"
    assert meta["source_version"] == "9.9.9" and meta["vendored_at"] == "2026-02-02"


def test_existing_meta_without_review_by_gets_the_default():
    existing = {k: val for k, val in META_WITH_REVIEW.items() if k != "meta"}
    meta = v.build_vendored(_fixture_v167_plus(), "9.9.9", existing, "2026-02-02")[1]
    assert meta["meta"] == {"review_by": None, "refresh_cadence": "rare"}
    assert meta["notes"] == ["a note that must survive"]


def test_no_existing_meta_builds_the_defaults():
    meta = v.build_vendored(_fixture_v167_plus(), "9.9.9", None, "2026-02-02")[1]
    assert meta["meta"]["review_by"] is None and meta["notes"] == [] and meta["source"] == "iso3166"
    assert list(meta) == ["$comment", "source", "source_version", "vendored_at", "vendored_from", "snapshot_sha256",
                          "meta", "notes"]


@pytest.mark.parametrize("mode", ["write", "check"])
def test_every_invocation_runs_the_same_builder_and_the_preservation_branch(tmp_path, monkeypatch, mode):
    data = _fixture_v167_plus()
    root = _repo(tmp_path, data, {**META_WITH_REVIEW, "source_version": "9.9.9"})
    src = _source(tmp_path, data)
    calls = {"build": 0, "merge": 0}
    real_build, real_merge = v.build_vendored, v.merge_existing_meta

    def build(*a, **k):
        calls["build"] += 1
        return real_build(*a, **k)

    def merge(*a, **k):
        calls["merge"] += 1
        return real_merge(*a, **k)

    monkeypatch.setattr(v, "build_vendored", build)
    monkeypatch.setattr(v, "merge_existing_meta", merge)
    argv = ["--check"] if mode == "check" else ["--version", "9.9.9", "--vendored-at", "2026-02-02"]
    assert v.main(argv + ["--source", str(src)], root=root) == 0
    assert calls == {"build": 1, "merge": 1}


def test_the_meta_file_round_trips_through_its_single_serializer(tmp_path):
    root = _repo(tmp_path, b"{}", dict(META_WITH_REVIEW))
    src = _source(tmp_path, _fixture_v167_plus())
    assert _run(root, "--version", "9.9.9", "--vendored-at", "2026-02-02", "--source", str(src)).returncode == 0
    written = (root / "tools" / "iso3166_snapshot.meta.json").read_bytes()
    assert written == v.serialize_meta(json.loads(written))
    assert written.endswith(b"\n")


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

def test_check_without_a_meta_file_is_fatal(tmp_path):
    root = _repo(tmp_path, _fixture_v167_plus(), None)
    assert _run(root, "--check", "--source", str(_source(tmp_path, _fixture_v167_plus()))).returncode == 2


def test_invalid_json_in_the_source_is_fatal(tmp_path):
    root = _repo(tmp_path, b"{}", {**META_WITH_REVIEW, "source_version": "9.9.9"})
    assert _run(root, "--check", "--source", str(_source(tmp_path, b"{ not json"))).returncode == 2


def test_write_with_a_version_the_source_does_not_carry_is_fatal(tmp_path):
    root = _repo(tmp_path, b"{}", None)
    r = _run(root, "--version", "1.0.0", "--vendored-at", "2026-02-02",
             "--source", str(_source(tmp_path, _fixture_v167_plus("9.9.9"))))
    assert r.returncode == 2 and "expected '1.0.0'" in r.stderr


def test_write_mode_needs_a_date_because_the_tool_never_reads_the_clock(tmp_path):
    root = _repo(tmp_path, b"{}", dict(META_WITH_REVIEW))
    src = _source(tmp_path, _fixture_v167_plus())
    r = _run(root, "--version", "9.9.9", "--source", str(src))
    assert r.returncode == 2 and "never reads the clock" in r.stderr


def test_write_mode_needs_a_version_and_check_refuses_write_flags(tmp_path):
    root = _repo(tmp_path, b"{}", dict(META_WITH_REVIEW))
    assert _run(root).returncode == 2
    assert _run(root, "--check", "--version", "1.0.0").returncode == 2


# ---------------------------------------------------------------------------
# Fetching: three attempts, 404 is fatal, exhaustion is "could not run"
# ---------------------------------------------------------------------------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_fetch_url_is_the_immutable_tag():
    assert v.raw_url("1.6.9") == "https://raw.githubusercontent.com/slimissa/iso3166/v1.6.9/iso3166.json"


def test_the_fetch_retries_transient_failures_up_to_three_attempts(monkeypatch):
    attempts = []

    def urlopen(req, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.URLError("boom")
        return _Resp(b"payload")

    monkeypatch.setattr(v.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(v, "_sleep", lambda s: None)
    assert v.fetch_source("1.6.9") == b"payload"
    assert len(attempts) == 3


def test_the_fetch_gives_up_after_three_attempts_and_the_cli_exits_three(tmp_path, monkeypatch):
    attempts = []

    def urlopen(req, timeout=None):
        attempts.append(1)
        raise urllib.error.URLError("down")

    monkeypatch.setattr(v.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(v, "_sleep", lambda s: None)
    root = _repo(tmp_path, _fixture_v167_plus(), {**META_WITH_REVIEW, "source_version": "9.9.9"})
    assert v.main(["--check"], root=root) == 3
    assert len(attempts) == 3


def test_a_missing_tag_is_fatal_not_retried(monkeypatch):
    attempts = []

    def urlopen(req, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(v.urllib.request, "urlopen", urlopen)
    with pytest.raises(v.Fatal):
        v.fetch_source("0.0.0")
    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# The committed files (offline half of the check; CI runs the tag half)
# ---------------------------------------------------------------------------

def test_the_committed_meta_names_the_version_the_committed_snapshot_carries():
    snap = json.loads((PROJECT_ROOT / "tools" / "iso3166_snapshot.json").read_text(encoding="utf-8"))
    meta = json.loads((PROJECT_ROOT / "tools" / "iso3166_snapshot.meta.json").read_text(encoding="utf-8"))
    assert meta["source_version"] == snap["meta"]["version"]
    assert meta["vendored_from"] == v.blob_url(meta["source_version"])
    assert v.detect_schema(snap) in v.SCHEMAS


# ---------------------------------------------------------------------------
# snapshot_sha256 (v1.8.5, F21)
# ---------------------------------------------------------------------------

def _vendored(tmp_path: Path):
    data = _fixture_v167_plus()
    root = _repo(tmp_path, b"{}", dict(META_WITH_REVIEW))
    src = _source(tmp_path, data)
    assert _run(root, "--version", "9.9.9", "--vendored-at", "2026-02-02", "--source", str(src)).returncode == 0
    return root, src, data


def test_write_records_the_sha256_of_the_snapshot_it_wrote(tmp_path):
    root, _src, data = _vendored(tmp_path)
    meta = json.loads((root / "tools" / "iso3166_snapshot.meta.json").read_text(encoding="utf-8"))
    assert meta["snapshot_sha256"] == hashlib.sha256(data).hexdigest()
    assert list(meta).index("snapshot_sha256") == list(meta).index("vendored_from") + 1


def test_check_passes_and_reports_the_hash_when_nothing_changed(tmp_path):
    root, src, _data = _vendored(tmp_path)
    r = _run(root, "--check", "--source", str(src))
    assert r.returncode == 0, r.stderr
    assert "snapshot_sha256 matches" in r.stdout


def test_a_mutated_snapshot_fails_the_hash_check_before_any_fetch(tmp_path, monkeypatch, capsys):
    root, _src, data = _vendored(tmp_path)
    (root / "tools" / "iso3166_snapshot.json").write_bytes(data.replace(b"AD", b"AE", 1))

    def no_network(*a, **k):
        raise AssertionError("the hash check must run before the tag is fetched")

    monkeypatch.setattr(v, "fetch_source", no_network)
    assert v.main(["--check"], root=root) == 1
    err = capsys.readouterr().err
    assert "snapshot_sha256" in err and "MISMATCH" in err


def test_a_one_byte_mutation_of_the_committed_meta_hash_fails_the_check(tmp_path):
    root, src, _data = _vendored(tmp_path)
    meta_path = root / "tools" / "iso3166_snapshot.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["snapshot_sha256"] = ("0" if meta["snapshot_sha256"][0] != "0" else "1") + meta["snapshot_sha256"][1:]
    meta_path.write_bytes(v.serialize_meta(meta))
    r = _run(root, "--check", "--source", str(src))
    assert r.returncode == 1 and "snapshot_sha256" in r.stderr


@pytest.mark.parametrize("bad", [None, "", "abc", "Z" * 64, "A" * 64])
def test_a_missing_or_malformed_hash_is_fatal_not_a_pass(tmp_path, bad):
    root, src, _data = _vendored(tmp_path)
    meta_path = root / "tools" / "iso3166_snapshot.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if bad is None:
        del meta["snapshot_sha256"]
    else:
        meta["snapshot_sha256"] = bad
    meta_path.write_bytes(v.serialize_meta(meta))
    r = _run(root, "--check", "--source", str(src))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "snapshot_sha256" in r.stderr


def test_the_committed_snapshot_matches_its_recorded_sha256():
    snap = (PROJECT_ROOT / "tools" / "iso3166_snapshot.json").read_bytes()
    meta = json.loads((PROJECT_ROOT / "tools" / "iso3166_snapshot.meta.json").read_text(encoding="utf-8"))
    assert meta["snapshot_sha256"] == hashlib.sha256(snap).hexdigest()
