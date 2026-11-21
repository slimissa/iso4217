"""
tools/check_rules_refs.py and docs/rules.md (v1.9.5, ADR 0016; audit findings P5-10 and EC).

`docs/rules.md` is a numbering authority: one row per rule, an ID, a pointer to the heading in RELEASE_PATTERN.md it indexes. The
tool keeps this repository's side true: the table and the document index each other, qualified citations resolve, and a bare
"rule N" citation (ambiguous across registries, and inside this one: "rule 6" is both an essential and a hygiene rule) cannot
appear in a file that is not on a frozen list. Cross-repository verification is the fourth audit's work.

Test classes (ADR 0014, D1): R = red-first, C = characterization.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOL = PROJECT_ROOT / "tools" / "check_rules_refs.py"

PATTERN = """# Release pattern

## The essential eight

### 1. Refuse on unclean state

### 2. Refuse on version collision

## Operator hygiene

### 1. No heredocs

### 6b. The commit is not the working tree

### 7. A check that cannot run must fail

## Exit-code convention
"""

RULES_HEAD = "| ID | Meaning | Section | Heading in RELEASE_PATTERN.md | Aliases |\n|---|---|---|---|---|\n"
ROWS = {
    "E1": ("Refuse on unclean state", "The essential eight", "1. Refuse on unclean state", ""),
    "E2": ("Refuse on collision", "The essential eight", "2. Refuse on version collision", ""),
    "H1": ("No heredocs", "Operator hygiene", "1. No heredocs", ""),
    "H6b": ("Commit is not the tree", "Operator hygiene", "6b. The commit is not the working tree", ""),
    "H7": ("A check that cannot run must fail", "Operator hygiene", "7. A check that cannot run must fail", "R7"),
}


def rules_md(rows: dict | None = None) -> str:
    rows = ROWS if rows is None else rows
    body = "".join(f"| {k} | {m} | {s} | {h} | {a} |\n" for k, (m, s, h, a) in rows.items())
    return "# Rules\n\n" + RULES_HEAD + body


def put(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    put(tmp_path, "RELEASE_PATTERN.md", PATTERN)
    put(tmp_path, "docs/rules.md", rules_md())
    return tmp_path


def run(root: Path) -> subprocess.CompletedProcess:
    assert TOOL.exists(), "tools/check_rules_refs.py does not exist yet"
    return subprocess.run([sys.executable, str(TOOL), str(root)], capture_output=True, text=True, timeout=60)


def load_module():
    assert TOOL.exists(), "tools/check_rules_refs.py does not exist yet"
    spec = importlib.util.spec_from_file_location("check_rules_refs", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTheTable:
    def test_R_the_tool_exists(self):
        assert TOOL.exists()

    def test_R_a_table_that_indexes_the_document_passes_and_says_what_it_checked(self, tree):
        r = run(tree)
        assert r.returncode == 0, r.stdout + r.stderr
        assert re.search(r"^OK: 5 rule\(s\) in docs/rules\.md match RELEASE_PATTERN\.md; \d+ citation\(s\) checked", r.stdout, re.M), r.stdout

    def test_R_a_duplicate_id_fails(self, tree):
        text = rules_md() + "| H7 | again | Operator hygiene | 7. A check that cannot run must fail | |\n"
        put(tree, "docs/rules.md", text)
        r = run(tree)
        assert r.returncode == 1 and "duplicate ID H7" in r.stdout

    def test_R_a_malformed_id_fails(self, tree):
        put(tree, "docs/rules.md", rules_md({**ROWS, "X9": ("odd", "Operator hygiene", "1. No heredocs", "")}))
        r = run(tree)
        assert r.returncode == 1 and "malformed ID X9" in r.stdout

    def test_R_a_row_whose_heading_is_not_in_the_document_fails(self, tree):
        put(tree, "docs/rules.md", rules_md({**ROWS, "H1": ("No heredocs", "Operator hygiene", "1. Something renamed", "")}))
        r = run(tree)
        assert r.returncode == 1 and "H1" in r.stdout and "not found" in r.stdout

    def test_R_a_heading_under_the_wrong_section_fails(self, tree):
        put(tree, "docs/rules.md", rules_md({**ROWS, "H1": ("No heredocs", "The essential eight", "1. No heredocs", "")}))
        r = run(tree)
        assert r.returncode == 1 and "H1" in r.stdout

    def test_R_a_rule_heading_with_no_row_fails(self, tree):
        rows = {k: v for k, v in ROWS.items() if k != "H6b"}
        put(tree, "docs/rules.md", rules_md(rows))
        r = run(tree)
        assert r.returncode == 1 and "6b. The commit is not the working tree" in r.stdout and "has no row" in r.stdout

    def test_R_a_missing_rules_file_is_a_usage_error(self, tmp_path):
        put(tmp_path, "RELEASE_PATTERN.md", PATTERN)
        assert run(tmp_path).returncode == 2


class TestQualifiedCitations:
    @pytest.mark.parametrize("text", [
        "per invariant 2 of the pattern",
        "per hygiene rule 7",
        "per operator-hygiene rule 6b",
        "the rule R7 alias",
        "see 4217/H7 and 3166/H7 and 10383/H7b and ec/H1",
    ])
    def test_R_a_citation_that_resolves_passes(self, tree, text):
        put(tree, "docs/notes.md", text + "\n")
        assert run(tree).returncode == 0

    @pytest.mark.parametrize("text,needle", [
        ("per invariant 9", "invariant 9"),
        ("per hygiene rule 99", "hygiene rule 99"),
        ("per operator-hygiene rule 6d", "6d"),
        ("see 4217/H99", "4217/H99"),
    ])
    def test_R_a_citation_that_does_not_resolve_fails_with_file_and_line(self, tree, text, needle):
        put(tree, "docs/notes.md", "one\n" + text + "\n")
        r = run(tree)
        assert r.returncode == 1 and "docs/notes.md:2" in r.stdout and needle in r.stdout

    def test_R_an_unknown_R_token_and_a_foreign_prefix_are_not_citations(self, tree):
        put(tree, "docs/notes.md", "R99 is a label, and foo/H7 is a path.\n")
        assert run(tree).returncode == 0


class TestBareCitations:
    def test_R_a_bare_rule_citation_in_an_unlisted_file_fails(self, tree):
        put(tree, "docs/notes.md", "as rule 7 says\n")
        r = run(tree)
        assert r.returncode == 1 and "bare rule citation" in r.stdout and "docs/notes.md:1" in r.stdout

    def test_R_historical_records_are_not_scanned(self, tree):
        put(tree, "CHANGELOG.md", "rule 7 and invariant 99 and hygiene rule 99\n")
        put(tree, "docs/v1.0.0-verification.md", "rule 7 and invariant 99\n")
        assert run(tree).returncode == 0

    def test_R_code_files_are_not_scanned(self, tree):
        put(tree, "tools/x.py", "# rule 7, invariant 99\n")
        assert run(tree).returncode == 0

    def test_R_a_listed_file_is_held_to_its_recorded_count(self, tree):
        mod = load_module()
        put(tree, "docs/notes.md", "rule 7 and again rule 7\n")
        errors, _ = mod.run(tree, legacy={"docs/notes.md": 2})
        assert errors == []
        errors, _ = mod.run(tree, legacy={"docs/notes.md": 1})
        assert any("2 bare rule citation(s), 1 recorded" in e for e in errors)
        errors, _ = mod.run(tree, legacy={"docs/notes.md": 3})
        assert any("STALE" in e and "docs/notes.md" in e for e in errors)

    def test_R_a_legacy_entry_for_a_file_that_is_gone_is_stale(self, tree):
        mod = load_module()
        errors, _ = mod.run(tree, legacy={"docs/gone.md": 1})
        assert any("STALE" in e and "docs/gone.md" in e for e in errors)


class TestTheLegacyFile:
    def test_R_a_file_recorded_in_the_data_file_is_tolerated_at_its_count(self, tree):
        put(tree, "docs/notes.md", "as rule 7 says\n")
        put(tree, "docs/rules-legacy-bare.json", '{"docs/notes.md": 1}\n')
        assert run(tree).returncode == 0

    def test_R_a_malformed_data_file_is_a_usage_error(self, tree):
        put(tree, "docs/rules-legacy-bare.json", '{"docs/notes.md": "many"}\n')
        assert run(tree).returncode == 2


class TestTheRealTree:
    def test_R_the_real_tree_passes(self):
        r = run(PROJECT_ROOT)
        assert r.returncode == 0, r.stdout[-2000:]

    def test_R_rules_md_states_what_it_is_and_what_it_is_not(self):
        text = (PROJECT_ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
        assert "numbering authority" in text.lower()
        assert text.count("not verified by tooling") >= 3, "each of the three sibling columns carries the label"
        for registry in ("ISO 4217", "ISO 3166", "ISO 10383", "Exchange Calendar"):
            assert registry in text
        assert "4217/H7" in text, "the prefixed citation form is shown"

    def test_R_the_pattern_points_at_rules_md_and_its_stale_sentence_is_fixed(self):
        text = (PROJECT_ROOT / "RELEASE_PATTERN.md").read_text(encoding="utf-8")
        assert "docs/rules.md" in text
        assert "Four rules that emerged" not in text
        assert re.search(r"reviewed by .*ISO 4217", text, re.I | re.S)

    def test_R_every_current_rule_id_in_the_table_is_unique_and_covers_the_two_sections(self):
        text = (PROJECT_ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
        ids = re.findall(r"^\| ([EH][0-9]+[a-d]?) \|", text.split("## Adoption matrix")[0], re.M)
        assert len(ids) == len(set(ids))
        assert {"E1", "E8", "H1", "H6b", "H6c", "H6d", "H7", "H10"} <= set(ids)
