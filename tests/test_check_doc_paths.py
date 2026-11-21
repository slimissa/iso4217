"""
tools/check_doc_paths.py and the rename of the audit document (v1.9.5, ADR 0017, D6).

The CHANGELOG entries for 1.9.1 and 1.9.2 link to `docs/audits/third-pass.md`, a file that did not exist: two dead links that no
check noticed. This tool makes "every docs/ path a document cites exists" a gate step. The rename (fifth-pass.md to
third-pass.md) is held by the same tool plus the tests at the bottom.

Test classes (ADR 0014, D1): R = red-first, C = characterization. A mutation-killed test is one of these that a mutant in
tests/test_gate_mutations.py breaks.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_doc_paths.py"
AUDIT = PROJECT_ROOT / "docs" / "audits" / "third-pass.md"
OLD_AUDIT = PROJECT_ROOT / "docs" / "audits" / "fifth-pass.md"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    assert TOOL.exists(), "tools/check_doc_paths.py does not exist yet"
    return subprocess.run([sys.executable, str(TOOL), str(root), *args], capture_output=True, text=True, timeout=60)


def put(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    put(tmp_path, "docs/real.md", "# real\n")
    put(tmp_path, "docs/audits/third-pass.md", "# Third-pass audit\n")
    return tmp_path


class TestTheTool:
    def test_R_the_tool_exists(self):
        assert TOOL.exists()

    def test_R_a_cited_path_that_exists_passes(self, tree):
        put(tree, "README.md", "See [the audit](./docs/audits/third-pass.md) and docs/real.md.\n")
        r = run(tree)
        assert r.returncode == 0, r.stdout + r.stderr
        assert re.search(r"^OK: \d+ path\(s\) cited in \d+ file\(s\); all exist$", r.stdout, re.M), r.stdout

    def test_R_a_cited_path_that_does_not_exist_fails_with_file_and_line(self, tree):
        put(tree, "README.md", "intro\n\nSee docs/audits/missing-pass.md for more.\n")
        r = run(tree)
        assert r.returncode == 1
        assert "README.md:3" in r.stdout and "docs/audits/missing-pass.md" in r.stdout

    def test_R_the_two_dead_links_this_release_found_would_have_been_caught(self, tree):
        (tree / "docs/audits/third-pass.md").unlink()
        put(tree, "CHANGELOG.md", "see the third-pass audit (`docs/audits/third-pass.md`)\n")
        r = run(tree)
        assert r.returncode == 1 and "docs/audits/third-pass.md" in r.stdout

    def test_R_an_example_marker_skips_the_line(self, tree):
        put(tree, "README.md", "Write `docs/example-name.md` <!-- doc-path: example -->\n")
        assert run(tree).returncode == 0

    def test_R_wildcards_and_placeholders_are_not_paths(self, tree):
        put(tree, "README.md", "Every docs/v*-verification.md and docs/<name>.md and docs/ alone.\n")
        assert run(tree).returncode == 0

    def test_R_an_old_name_is_allowed_in_a_historical_record_but_not_in_a_current_document(self, tree):
        put(tree, "CHANGELOG.md", "the audit is docs/audits/fifth-pass.md\n")
        put(tree, "docs/v1.9.1-verification.md", "the audit is docs/audits/fifth-pass.md\n")
        assert run(tree).returncode == 0, "history cites files as they were"
        put(tree, "README.md", "the audit is docs/audits/fifth-pass.md\n")
        r = run(tree)
        assert r.returncode == 1 and "README.md" in r.stdout and "renamed to docs/audits/third-pass.md" in r.stdout

    def test_C_a_missing_root_is_a_usage_error(self, tmp_path):
        assert run(tmp_path / "nope").returncode == 2


class TestTheRename:
    def test_R_the_audit_document_is_named_third_pass(self):
        assert AUDIT.exists() and not OLD_AUDIT.exists()

    def test_R_it_says_third_pass_and_explains_why_the_ids_keep_their_prefix(self):
        text = AUDIT.read_text(encoding="utf-8")
        assert text.lstrip().startswith("# Third-pass audit")
        assert "P5-" in text and "identifier" in text.lower() and "fifth-pass" in text, "one paragraph explains the P5- prefix"

    def test_R_no_current_document_still_calls_it_fifth_pass(self):
        historical = re.compile(r"^(CHANGELOG\.md|docs/v[0-9.]+-verification\.md)$")
        offenders = []
        out = subprocess.run(["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        files = out.stdout.split() if out.returncode == 0 else [
            str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
        for rel in files:
            p = PROJECT_ROOT / rel
            if historical.match(rel) or p.suffix in {".json", ".parquet", ".sql", ".csv", ".tsv", ".zip", ".png"} \
                    or rel.startswith("docs/decisions/") or rel in {
                        "tests/test_check_doc_paths.py", "tools/check_doc_paths.py", "tests/test_v195_mutations.py"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if "fifth-pass" in line.lower().replace("fifth pass", "fifth-pass"):
                    if rel == "docs/audits/third-pass.md" and ("formerly" in line or "renamed" in line):
                        continue
                    offenders.append(f"{rel}:{i}")
        assert offenders == [], offenders

    def test_R_the_third_pass_claim_replaces_the_moved_file_claim(self):
        import json
        m = json.loads((PROJECT_ROOT / "tools" / "release_claims.json").read_text(encoding="utf-8"))
        claims = m.get("1.9.5", [])
        assert any(c.get("file") == "docs/audits/third-pass.md" for c in claims)
        assert any(c.get("file") == "docs/audits/fifth-pass.md" for c in m["1.9.1"]), \
            "the 1.9.1 claim is a statement about the 1.9.1 tree and is not edited (ADR 0017, D6)"

    def test_R_the_real_tree_has_no_dead_doc_path(self):
        r = run(PROJECT_ROOT)
        assert r.returncode == 0, r.stdout[-1500:]
