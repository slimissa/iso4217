"""
Tests for tools/check_release_claims.py (claim shapes, doc-facts) and for the clock-free render rule.

The last two tests are the standing enforcement of RELEASE_PATTERN.md's "pin the render" corollary: they
run on every pytest run, so the rule holds in CI as well as in the release gate.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_release_claims as crc  # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    (tmp_path / "f.txt").write_text("alpha beta\n", encoding="utf-8")
    monkeypatch.setattr(crc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(crc, "MANIFEST", tmp_path / "tools" / "release_claims.json")
    return tmp_path


def _manifest(tree: Path, data: dict) -> None:
    (tree / "tools" / "release_claims.json").write_text(json.dumps(data), encoding="utf-8")


# -- claim shapes --------------------------------------------------------------------------------

def test_a_file_claim_needs_the_file(tree):
    assert crc.check_claim({"file": "f.txt"})[0] is True
    assert crc.check_claim({"file": "nope.txt"})[0] is False


def test_contains_passes_and_fails(tree):
    assert crc.check_claim({"file": "f.txt", "contains": "beta"})[0] is True
    assert crc.check_claim({"file": "f.txt", "contains": "gamma"})[0] is False


def test_absent_passes_when_the_text_is_not_there(tree):
    ok, detail = crc.check_claim({"file": "f.txt", "absent": "gamma"})
    assert ok and "does not contain 'gamma'" in detail


def test_absent_fails_when_the_text_is_there(tree):
    ok, detail = crc.check_claim({"file": "f.txt", "absent": "alpha"})
    assert not ok and "must be absent" in detail


def test_contains_and_absent_combine(tree):
    assert crc.check_claim({"file": "f.txt", "contains": "alpha", "absent": "gamma"})[0] is True
    assert crc.check_claim({"file": "f.txt", "contains": "alpha", "absent": "beta"})[0] is False


def test_an_unknown_key_fails_instead_of_weakening_the_claim(tree):
    ok, detail = crc.check_claim({"file": "f.txt", "abscent": "alpha"})
    assert not ok and "unknown claim key" in detail


def test_an_absent_claim_on_a_missing_file_fails(tree):
    ok, detail = crc.check_claim({"file": "renamed.txt", "absent": "alpha"})
    assert not ok and "missing file" in detail


def test_a_claim_without_a_file_key_fails(tree):
    assert crc.check_claim({"absent": "x"})[0] is False


# -- doc-facts -----------------------------------------------------------------------------------

def test_doc_facts_are_checked_for_every_version(tree, capsys):
    _manifest(tree, {"1.0.0": [{"file": "f.txt"}], "2.0.0": [{"file": "f.txt"}],
                     "doc-facts": [{"file": "f.txt", "absent": "alpha"}]})
    for version in ("1.0.0", "2.0.0"):
        assert crc.main([version]) == 1
        assert "[doc-facts]" in capsys.readouterr().out


def test_passing_doc_facts_do_not_block_a_release(tree):
    _manifest(tree, {"1.0.0": [{"file": "f.txt"}], "doc-facts": [{"file": "f.txt", "absent": "gamma"}]})
    assert crc.main(["1.0.0"]) == 0


def test_doc_facts_must_be_a_list(tree):
    _manifest(tree, {"1.0.0": [{"file": "f.txt"}], "doc-facts": {"file": "f.txt"}})
    with pytest.raises(SystemExit) as exc:
        crc.main(["1.0.0"])
    assert exc.value.code == 2


def test_a_version_without_an_entry_is_still_fatal(tree):
    _manifest(tree, {"doc-facts": []})
    with pytest.raises(SystemExit) as exc:
        crc.main(["9.9.9"])
    assert exc.value.code == 2


# -- the clock-free render rule, against the real tree -------------------------------------------

CLOCK_TOKENS = ["date.today(", "datetime.now(", "time.time(", "random.", "uuid.uuid4("]


def _real_manifest() -> dict:
    return json.loads((PROJECT_ROOT / "tools" / "release_claims.json").read_text(encoding="utf-8"))


def test_the_vendor_tool_absence_claims_are_in_doc_facts():
    facts = {(c.get("file"), c.get("absent")) for c in _real_manifest()["doc-facts"]}
    for token in CLOCK_TOKENS:
        assert ("tools/vendor_iso3166.py", token) in facts, token


def test_every_doc_fact_holds_on_this_tree():
    for claim in _real_manifest()["doc-facts"]:
        ok, detail = crc.check_claim(claim)
        assert ok, detail


FORBIDDEN_CALLS = {
    "date.today", "datetime.today", "datetime.now", "datetime.utcnow", "datetime.datetime.now",
    "datetime.datetime.today", "datetime.datetime.utcnow", "datetime.date.today", "time.time",
    "time.monotonic", "time.perf_counter", "time.time_ns", "uuid.uuid1", "uuid.uuid4",
    "os.getpid", "os.urandom", "secrets.token_hex", "secrets.token_bytes",
}


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_the_vendor_tool_never_calls_the_clock_or_a_random_source():
    tree = ast.parse((PROJECT_ROOT / "tools" / "vendor_iso3166.py").read_text(encoding="utf-8"))
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("datetime", "time", "uuid", "os", "random", "secrets"):
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            head, _, rest = name.partition(".")
            resolved = aliases.get(head, head) + ("." + rest if rest else "")
            if resolved in FORBIDDEN_CALLS or resolved.startswith("random."):
                found.append((node.lineno, name))
    assert not found, found
