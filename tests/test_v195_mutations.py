"""
The v1.9.5 mutation sweep (ADR 0015, 0016, 0017; hygiene rule 10: a check that cannot fail is not a check).

Every fix in v1.9.5 has a mutant here: a copy of the project with one defect put back (usually the v1.9.4 behavior), run
against the tests that are supposed to notice. A mutant is *killed* when those tests pass on the unmutated copy (the control)
and fail on the mutated one. A mutant that survives means the test that guards the fix is decoration, and the fix is fixed
in the tests or the code, never accepted.

The release script's own mutants (the dry-run's document stage, the re-run date, the fence sanitiser) are in
tests/test_release_harness_mutations.py, which has the machinery to run the harness against a mutated script.

How it runs: it uses the same project copy as tests/test_gate_mutations.py (tracked and untracked files, no virtualenvs), edits
files in the copy only, and runs the named tests as a subprocess inside the copy. Go and Rust cases need those toolchains;
a case that cannot run fails (hygiene rule 7) rather than being skipped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from test_gate_mutations import pristine, tree  # noqa: F401  (fixtures)

PY = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
_CARGO_TARGET = Path(tempfile.gettempdir()) / "iso4217-v195-mutation-cargo-target"


@dataclass(frozen=True)
class Mutant:
    id: str
    defect: str
    edits: tuple[tuple[str, str, str], ...]     # (relative path, text that must occur exactly once, replacement)
    kind: str                                    # "pytest", "go" or "cargo"
    target: str                                  # pytest file, or "" for go and cargo
    expr: str = ""                               # pytest -k expression


def M(id, defect, edits, target, expr="", kind="pytest"):
    return Mutant(id, defect, tuple(edits), kind, target, expr)


CHK = "tools/check_verification_doc.py"
DOC = "tools/check_doc_paths.py"
RUL = "tools/check_rules_refs.py"
T_VER = "tests/test_check_verification_doc.py"
T_DOC = "tests/test_check_doc_paths.py"
T_RUL = "tests/test_check_rules_refs.py"
T_LC = "tests/test_wrapper_lookup_contract.py"
T_GM = "tests/test_gate_mutations.py"

MUTANTS = [
    # -- P5-11: the verification-doc checker (ADR 0017) -------------------------------------------------------------------
    M("V01-placeholder-is-case-insensitive-again", "prose 'placeholder' is a marker",
      [(CHK, '(re.compile(r"\\bPLACEHOLDER\\b"), "PLACEHOLDER marker")', '(re.compile(r"\\bPLACEHOLDER\\b", re.IGNORECASE), "PLACEHOLDER marker")')],
      T_VER, "lower_case_placeholder"),
    M("V02-ok-line-names-no-path", "the OK line cannot say what it checked",
      [(CHK, 'print(f"OK: {rel} clean ({len(docs[0].read_text(encoding=\'utf-8\').splitlines())} lines)")', 'print("OK: 1 verification doc(s) clean")')],
      T_VER, "names_the_path"),
    M("V03-stale-grandfather-entry-is-not-reported", "a listed doc that became clean stays listed",
      [(CHK, 'errors.append(f"STALE: {rel} is grandfathered but clean; remove it from {GRANDFATHER_FILE}")', "pass")],
      T_VER, "became_clean"),
    M("V04-missing-grandfathered-path-is-not-reported", "a listed path that is gone stays listed",
      [(CHK, "        if not (root / rel).is_file():", "        if False:")],
      T_VER, "does_not_exist"),
    M("V05-unclosed-fence-hides-the-rest", "an unterminated fence is not an error",
      [(CHK, "    if unclosed is not None:", "    if False:")],
      T_VER, "unclosed_fence"),
    M("V06-a-tilde-line-closes-a-backtick-fence", "the fence character is not tracked",
      [(CHK, "closes = bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and line.strip() == m.group(1)",
        "closes = bool(m) and len(m.group(1)) >= fence[1] and line.strip() == m.group(1)")],
      T_VER, "tilde_line"),
    M("V07-a-shorter-fence-closes-a-longer-one", "the fence length is not tracked",
      [(CHK, "closes = bool(m) and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and line.strip() == m.group(1)",
        "closes = bool(m) and m.group(1)[0] == fence[0] and line.strip() == m.group(1)")],
      T_VER, "shorter_fence"),
    M("V08-the-latest-doc-can-be-grandfathered", "a stub can hide on the list",
      [(CHK, "        if rel in grandfathered and doc != latest:", "        if rel in grandfathered:")],
      T_VER, "latest_doc_can_never"),
    M("V09-a-grandfather-entry-needs-no-reason", "an exemption nobody explained",
      [(CHK, "            if not reason.strip():", "            if False:")],
      T_VER, "must_carry_a_reason"),
    # -- the rename and the doc-path check --------------------------------------------------------------------------------
    M("V10-history-may-cite-any-dead-path", "a dead link in the CHANGELOG is excused as history",
      [(DOC, "                if historical and cited in RENAMED:", "                if historical:")],
      T_GM, "history_may_cite"),
    M("V11-the-example-marker-is-ignored", "a deliberate example is flagged",
      [(DOC, "            if EXAMPLE_MARKER in line:\n                continue\n", "")],
      T_DOC, "example_marker"),
    M("V12-a-cited-path-is-never-checked", "a dead link passes",
      [(DOC, "                if (root / cited).is_file():\n                    continue", "                if True:\n                    continue")],
      T_DOC, "cited_path_that_does_not_exist"),
    M("V13-an-old-name-is-no-longer-known-as-renamed", "history cannot cite the old file name",
      [(DOC, '    "docs/audits/fifth-pass.md": "docs/audits/third-pass.md",  # doc-path: example\n', "")],
      T_DOC, "old_name_is_allowed"),
    # -- P5-10 and EC: the rules checker (ADR 0016) ------------------------------------------------------------------------
    M("V14-duplicate-ids-are-allowed", "two rows for one rule",
      [(RUL, "        if rid in seen:", "        if False:")],
      T_RUL, "duplicate_id"),
    M("V15-a-row-need-not-match-a-heading", "the table drifts from the document",
      [(RUL, "        if r[\"section\"] != title or r[\"heading\"] not in doc_headings[title]:", "        if False:")],
      T_RUL, "heading_is_not_in_the_document or wrong_section"),
    M("V16-a-heading-with-no-row-is-not-reported", "a rule has no ID",
      [(RUL, "            if h not in indexed[title]:", "            if False:")],
      T_RUL, "no_row"),
    M("V17-qualified-citations-are-not-resolved", "a citation of a rule that does not exist passes",
      [(RUL, "                    if to_id(m.group(1)) not in ids:", "                    if False:")],
      T_RUL, "does_not_resolve"),
    M("V18-prefixed-4217-citations-are-not-resolved", "4217/H99 passes",
      [(RUL, '                if m.group(1) == "4217" and m.group(2) not in ids:', "                if False:")],
      T_RUL, "does_not_resolve"),
    M("V19-bare-citations-are-allowed-everywhere", "the ambiguity can grow",
      [(RUL, "                if rel not in legacy:", "                if False:")],
      T_RUL, "bare_rule_citation_in_an_unlisted_file"),
    M("V20-a-listed-file-may-grow-its-bare-citations", "the frozen count is not frozen",
      [(RUL, "        if rel in legacy and count > legacy[rel]:", "        if False:")],
      T_RUL, "held_to_its_recorded_count"),
    M("V21-a-stale-legacy-entry-is-not-reported", "the list never shrinks",
      [(RUL, "        if have < recorded:", "        if False:")],
      T_RUL, "held_to_its_recorded_count or legacy_entry_for_a_file_that_is_gone"),
    M("V22-history-is-scanned", "the CHANGELOG is held to today's numbering",
      [(RUL, "        if rel == SELF or HISTORICAL.match(rel):", "        if rel == SELF:")],
      T_RUL, "historical_records_are_not_scanned"),
    # -- P5-09: the wrappers (ADR 0015) -----------------------------------------------------------------------------------
    M("V23-python-last-section-wins-again", "currency() returns the non-ISO entry",
      [("wrappers/python/iso4217.py", "                self._all_codes.setdefault(code, entry)", "                self._all_codes[code] = entry")],
      T_LC, "TestPythonWrapper and vector"),
    M("V24-python-currency-takes-a-non-string", "currency(None) is an AttributeError again",
      [("wrappers/python/iso4217.py", "        return self._all_codes.get(_require_code(code))", "        return self._all_codes.get(code.upper())")],
      T_LC, "type_error and currency"),
    M("V25-python-none-slips-through-the-type-check", "None is not refused by name",
      [("wrappers/python/iso4217.py", "    if not isinstance(value, str):\n        raise TypeError(f\"{name}",
        "    if value is not None and not isinstance(value, str):\n        raise TypeError(f\"{name}")],
      T_LC, "type_error"),
    M("V26-python-membership-takes-a-non-string", "None in registry is an AttributeError again",
      [("wrappers/python/iso4217.py", "        return _require_code(code) in self._all_codes", "        return code.upper() in self._all_codes")],
      T_LC, "type_error and contains"),
    M("V27-javascript-last-section-wins-again", "currency() returns the non-ISO entry",
      [("wrappers/javascript/index.js", "        if (!this._all.has(code)) this._all.set(code, entry);", "        this._all.set(code, entry);")],
      T_LC, "JavaScriptWrapper"),
    M("V28-javascript-null-slips-through-the-type-check", "null is not refused by name",
      [("wrappers/javascript/index.js", "  if (typeof value !== 'string') {", "  if (value !== null && typeof value !== 'string') {")],
      T_LC, "JavaScriptWrapper"),
    M("V29-go-last-section-wins-again", "Currency() returns the non-ISO entry",
      [("wrappers/go/iso4217.go", "\t\t\tif _, taken := r.all[code]; !taken {", "\t\t\tif true {")],
      "", "", "go"),
    M("V30-rust-last-section-wins-again", "currency() returns the non-ISO entry",
      [("wrappers/rust/src/lib.rs", "all.entry(code.clone()).or_insert_with(|| currency.clone());", "all.insert(code.clone(), currency.clone());")],
      "", "", "cargo"),
    # -- the gate carries the new checks ----------------------------------------------------------------------------------
    M("V31-the-gate-drops-the-doc-paths-step", "CI runs a check the release gate does not",
      [("scripts/release.sh", '    run_gate_step "check_doc_paths.py"              python3 tools/check_doc_paths.py\n', "")],
      "tests/test_ci_parity.py", "every_tool_a_workflow_runs"),
    M("V32-the-gate-drops-the-rules-refs-step", "CI runs a check the release gate does not",
      [("scripts/release.sh", '    run_gate_step "check_rules_refs.py"             python3 tools/check_rules_refs.py\n', "")],
      "tests/test_ci_parity.py", "every_tool_a_workflow_runs"),
]


def _apply(tree_root: Path, m: Mutant) -> None:
    for rel, old, new in m.edits:
        path = tree_root / rel
        text = path.read_text(encoding="utf-8")
        n = text.count(old)
        assert n == 1, f"{m.id}: the anchor occurs {n} times in {rel} (must be exactly 1): {old[:80]!r}"
        assert old != new
        path.write_text(text.replace(old, new), encoding="utf-8")


def _command(m: Mutant, root: Path) -> tuple[list[str], Path, dict]:
    env = dict(os.environ)
    if m.kind == "pytest":
        cmd = PY + [m.target] + (["-k", m.expr] if m.expr else [])
        return cmd, root, env
    if m.kind == "go":
        env.update(GOFLAGS="-mod=mod")
        return ["go", "test", "-run", "TestLookupContract", "-count=1", "."], root / "wrappers" / "go", env
    env.update(CARGO_TARGET_DIR=str(_CARGO_TARGET))
    # A shared target directory plus mtimes preserved by the copy let cargo reuse a binary built from a different copy
    # (a mutated one, or the control's). Touch the crate's sources so it is always rebuilt; the dependencies stay cached.
    for src in (root / "wrappers" / "rust").rglob("*.rs"):
        os.utime(src, None)
    return ["cargo", "test", "--lib", "lookup_contract", "--quiet"], root / "wrappers" / "rust", env


def _run(m: Mutant, root: Path) -> subprocess.CompletedProcess:
    cmd, cwd, env = _command(m, root)
    if shutil.which(cmd[0]) is None:
        pytest.fail(f"{m.id}: {cmd[0]} is not installed; a mutant that cannot run is not a pass (hygiene rule 7)")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, timeout=1500)


_controls: dict[tuple, int] = {}


@pytest.mark.parametrize("m", MUTANTS, ids=lambda m: m.id)
def test_every_mutant_is_killed(m: Mutant, pristine, tree):  # noqa: F811
    key = (m.kind, m.target, m.expr)
    if key not in _controls:
        control = _run(m, pristine)
        assert control.returncode == 0, f"{m.id}: the control is red on the unmutated copy:\n{(control.stdout + control.stderr)[-1500:]}"
        _controls[key] = control.returncode
    _apply(tree, m)
    mutated = _run(m, tree)
    assert mutated.returncode != 0, f"{m.id}: SURVIVED. The tests pass with this defect put back: {m.defect}"
    if m.kind == "pytest":
        assert mutated.returncode == 1, (
            f"{m.id}: pytest exited {mutated.returncode} (not a test failure):\n{(mutated.stdout + mutated.stderr)[-1200:]}")


def test_mutant_ids_are_unique_and_every_target_file_exists():
    ids = [m.id for m in MUTANTS]
    assert len(ids) == len(set(ids))
    root = Path(__file__).resolve().parent.parent
    for m in MUTANTS:
        for rel, _old, _new in m.edits:
            assert (root / rel).is_file(), f"{m.id}: {rel} does not exist"
        if m.kind == "pytest":
            assert (root / m.target).is_file(), f"{m.id}: {m.target} does not exist"
