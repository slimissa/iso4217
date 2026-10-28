"""
The mutation sweep for the release harness (v1.9.4, ADR 0014, docs/decisions/release-harness.md, "The mutation sweep").

A mutant is a copy of scripts/release.sh (or scripts/bump_version.py) with one defect put back. It is killed when the
harness (tests/test_release_harness.py) passes on the unmutated script and fails on the mutant. A harness that cannot be
made to fail is a harness that tests nothing (RELEASE_PATTERN.md, rule 10): every mutant here must be killed.

How a mutant is judged:

  1. The control: the named killer tests run against the UNMUTATED script and must pass. If they do not, the mutant cannot
     be judged and its test fails with "control is red". Before the v1.9.4 refactor this is the honest state for every
     mutant whose killer is a red-first test.
  2. The mutation: the anchor must match exactly once (zero or two matches fail the test: a refactor must never turn a mutant
     into a silent no-op), and the mutated file must still parse (a mutant that does not parse is "killed" by everything).
  3. The kill: the same killer tests run against the mutant, with RH_RELEASE_SH / RH_BUMP_PY pointing at the mutated copy
     in a temp directory. Exit 1 from pytest is a kill; 0 is a SURVIVOR; anything else is an error in the sweep itself.

Anchors are written against the v1.9.3 script (ADR 0014: mutants are defined before the refactor so a mutant tests the
script, not the refactor). Each mutant has one anchor set per generation of the script ("v1.9.3", "refactored"); the
generation is "refactored" once scripts/bump_version.py exists. A generation with no anchor set fails with "anchor not
bound": that is the to-do list for the refactor, not a skip.

This file does not edit scripts/. Mutated copies live in tmp_path.
"""

from __future__ import annotations

import functools
import os
import py_compile
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from test_release_harness import E_COULD_NOT, NEW, build_fixture, fx, no_gh_path  # noqa: F401  (fixtures)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(sys.platform == "win32" or not BASH, reason="bash and POSIX git paths")

GEN = "refactored" if (PROJECT_ROOT / "scripts" / "bump_version.py").exists() else "v1.9.3"
REL, BUMP = "scripts/release.sh", "scripts/bump_version.py"
H = "tests/test_release_harness.py"


@dataclass
class Mutant:
    id: str
    defect: str
    killers: str                      # a pytest -k expression over tests/test_release_harness.py
    v193: list | None = None          # [(target, old, new)] against the v1.9.3 text, literal match, exactly once
    refactored: list | None = None    # bound at refactor time
    note: str = ""
    anchors: dict = field(init=False)

    def __post_init__(self):
        self.anchors = {"v1.9.3": self.v193, "refactored": self.refactored}


def flip(old: str, new_cond: str) -> list:
    """Replace the whole `if ...; then` line, keeping its indentation."""
    indent = old[: len(old) - len(old.lstrip())]
    return [(REL, old, f"{indent}{new_cond}")]


MUTANTS: list[Mutant] = [
    # -- the ten preconditions, each "always passes" -------------------------------------------------------------------
    Mutant("M01-clean-tree-always-passes", "a dirty tree is accepted", "test_check_clean_tree",
           flip('    if [[ -n "$(git status --porcelain)" ]]; then', "if false; then")),
    Mutant("M02-clean-tree-always-fails", "a clean tree is refused", "test_release_pushes_the_commit_and_the_annotated_tag",
           flip('    if [[ -n "$(git status --porcelain)" ]]; then', "if true; then")),
    Mutant("M03-head-at-origin-always-passes", "a stale HEAD is accepted", "test_check_head_at_origin_when_origin_has_moved",
           flip('    if [ "$local_head" != "$remote_head" ]; then', "if false; then")),
    Mutant("M04-on-main-always-passes", "a side branch is accepted", "test_check_on_main",
           flip('    if [[ "$branch" != "main" ]]; then', "if false; then")),
    Mutant("M05-tag-free-ignores-the-tag", "an existing local tag is accepted", "test_check_tag_free_refuses_a_local_tag",
           flip('    if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then', "if false; then")),
    Mutant("M06-changelog-section-always-passes", "a missing CHANGELOG section is accepted", "test_check_changelog_section",
           flip('    if ! grep -q "^## \\[$VERSION\\]" "$CHANGELOG"; then', "if false; then")),
    Mutant("M07-manifest-always-passes", "a version absent from release_claims.json is accepted", "test_check_manifest_has_version",
           [(REL, "sys.exit(0 if '$VERSION' in manifest else 1)", "sys.exit(0)")]),
    Mutant("M08-workflows-covered-never-fails", "an unpolled push workflow is accepted", "test_check_workflows_covered_refuses",
           flip('        if [ "$found" -eq 0 ]; then', "if false; then")),
    Mutant("M09-gh-ready-skips-the-probe", "an unauthenticated gh is accepted", "test_check_gh_ready_gh_unauthenticated",
           flip("    if ! gh run list --limit 1 --json databaseId >/dev/null 2>&1; then", "if false; then")),
    Mutant("M10-version-consistency-always-passes", "a drifted site is accepted", "test_check_version_consistency",
           flip("    if ! python3 tools/check_version_consistency.py >/dev/null 2>&1; then", "if false; then")),
    Mutant("M11-orphan-variables-always-passes", "an undefined variable is accepted", "test_check_no_orphan_variables",
           flip('    if [ -n "$orphans" ]; then', "if false; then")),
    # -- the bumps -----------------------------------------------------------------------------------------------------
    Mutant("M12-version-file-not-written", "VERSION keeps the old value", "test_every_site_holds_the_new_version",
           [(REL, "    printf '%s\\n' \"$VERSION\" > \"$VERSION_FILE\"", "    true")]),
    Mutant("M13-changelog-not-written", "the CHANGELOG heading stays Unreleased", "test_every_site_holds_the_new_version",
           [(REL, "if n > 0:\n    p.write_text(new_text", "if False:\n    p.write_text(new_text")]),
    Mutant("M14-iso-updated-not-written", "meta.updated keeps the old date", "test_every_site_holds_the_new_version",
           [(REL, "r'(\"updated\":\\s*)\"[0-9]{4}", "r'(\"updatedX\":\\s*)\"[0-9]{4}")]),
    Mutant("M15-readme-bump-hits-the-schema-badge", "the wrong badge is rewritten",
           "test_the_schema_badge_is_not_a_registry_site or test_every_site_holds_the_new_version",
           [(REL, "badge/registry-[0-9]\\+\\.[0-9]\\+\\.[0-9]\\+-orange|badge/registry-$VERSION-orange",
             "badge/schema-[0-9]\\+\\.[0-9]\\+\\.[0-9]\\+-blue|badge/schema-$VERSION-blue")]),
    Mutant("M16-package-json-wrong-key", "package.json gets a misspelled key", "test_every_site_holds_the_new_version",
           [(REL, 'data["version"] = version', 'data["verison"] = version')]),
    Mutant("M17-cargo-rewrites-every-version-line", "a version outside [package] is rewritten",
           "test_every_site_holds_the_new_version",
           [(REL, '        in_pkg = (s == "[package]")', '        in_pkg = s.startswith("[package")')]),
    Mutant("M18-iso-version-regex-ignores-meta", "meta.version is not addressed specifically",
           "test_iso_json_never_rewrites_a_version_outside_meta",
           note="v1.9.3 already has this defect; the mutant exists only for the refactored bump_version.py"),
    # -- --force and the tag -------------------------------------------------------------------------------------------
    Mutant("M19-force-moves-a-published-tag", "--force overwrites a tag on origin", "test_force_never_moves_a_tag_that_is_on_origin",
           [(REL, '    git tag -a "$TAG" --cleanup=verbatim -F "$msgfile"', '    git tag -f -a "$TAG" --cleanup=verbatim -F "$msgfile"'),
            (REL, '    git push origin "$TAG"', '    git push -f origin "$TAG"')]),
    Mutant("M20-force-always-fails", "--force is a no-op", "test_force_with_a_local_only_tag",
           flip("        if $FORCE; then", "if false; then")),
    Mutant("M21-tag-push-does-not-push", "the tag is created and never published",
           "test_release_pushes_the_commit_and_the_annotated_tag",
           [(REL, '    git push origin "$TAG"', "    true")]),
    # -- the gate, the commit, CI --------------------------------------------------------------------------------------
    Mutant("M22-gate-abort-does-not-abort", "a red gate still commits and tags", "test_a_failing_gate_step_aborts",
           flip('    if [[ "$GATE_FAILED" -ne 0 ]]; then', "if false; then")),
    Mutant("M23-poll-always-green", "a red run is accepted", "test_a_red_run_is_exit_6",
           flip('                if [ "$conclusion" != "success" ]; then', "if false; then")),
    Mutant("M24-poll-never-runs", "CI is not asked about", "test_both_polled_workflows_are_asked_about",
           [(REL, "\npoll_ci\ntag_release", "\ntrue\ntag_release")]),
    Mutant("M25-commit-is-not-pushed", "the release commit stays local", "test_release_pushes_the_commit_and_the_annotated_tag",
           [(REL, '    git push origin main\n    info "pushed to origin/main"', '    true\n    info "pushed to origin/main"')]),
    Mutant("M26-untracked-guard-removed", "a generator's stray file is committed", "test_a_file_left_behind_by_a_generator",
           flip('    if [ -n "$untracked" ]; then', "if false; then")),
    # -- the verification doc ------------------------------------------------------------------------------------------
    Mutant("M27-doc-is-a-stub", "the doc is written with TODO markers", "test_the_second_commit_is_one_complete_doc",
           note="the v1.9.3 script IS this mutant; its kill is the red-first result, judged against the refactored script"),
    Mutant("M28-doc-written-without-being-checked", "an invalid doc is committed", "test_a_doc_that_would_fail_the_checker",
           note="refactored script only: the check_verification_doc.py call before the doc commit"),
    # -- dry run -------------------------------------------------------------------------------------------------------
    Mutant("M29-dry-run-falls-through", "--dry-run goes on to release", "test_a_dry_run_leaves_the_tree_clean_enough",
           [(REL, '    print_plan\n    exit "$EXIT_OK"', "    print_plan")]),
    Mutant("M30-temp-copy-not-removed", "the dry-run copy is left behind", "test_the_temporary_copy_is_removed",
           note="refactored script only: the trap that removes the copy"),
    Mutant("M31-ls-remote-check-removed", "a tag only on origin is not seen",
           "test_check_tag_free_sees_a_tag_that_exists_only_on_origin",
           note="refactored script only: the git ls-remote read in check_tag_free"),
]


# ---------------------------------------------------------------------------
# Anchors for the refactored script (v1.9.4). "same" means the v1.9.3 anchor is still the right one.
# The refactor moved the bumps into scripts/bump_version.py and gave every failure its own exit code, so the
# mutants for those two things now edit bump_version.py or the re-assigned lines.
# ---------------------------------------------------------------------------

# Guards inside bump_version.run(); a "writes nothing" mutant must also remove them, or the script's own
# fail-loud checks would stop the release and the harness would never be asked.
G_NOCHANGE = (BUMP, '        if new_text == text:\n            raise SiteError("the write changed nothing")\n', "")
G_READBACK = (BUMP, '        if reader(path.read_bytes().decode("utf-8")) != new:\n'
                    '            raise SiteError(f"read-back: the site does not hold {new} after the write")\n', "")
G_ONLYFIELD = (BUMP, "        _check_only_that_value_changed(site, text, new_text)\n", "")

SAME = "same"
REFACTORED = {
    "M01": SAME, "M02": SAME, "M03": SAME, "M04": SAME,
    "M05": SAME,   # the line is unique: tag_release's own test begins `if $RECREATE_TAG &&`
    "M06": SAME, "M07": SAME, "M08": SAME, "M09": SAME, "M10": SAME, "M11": SAME,
    "M12": [(BUMP, '    return new + "\\n"', "    return text"), G_NOCHANGE, G_READBACK],
    "M13": [(BUMP, '        return re.sub(r"^" + re.escape(old) + r"$", lambda _m: new, text, count=1, flags=re.MULTILINE), "changed"',
             '        return text, "changed"'),
            (BUMP, '                if bump_changelog(path.read_bytes().decode("utf-8"), old, new)[1] != "already":\n'
                   '                    raise SiteError("read-back: the heading was not written")\n', "                pass\n")],
    "M14": [(BUMP, '    return _json_replace(text, "meta", "updated", current, new)', "    return text"), G_NOCHANGE, G_READBACK],
    "M15": [(BUMP, '    return _BADGE.sub(f"badge/registry-{new}-orange", text, count=1)',
             '    return re.sub(rf"badge/schema-{SEMVER}-blue", f"badge/schema-{new}-blue", text, count=1)'), G_READBACK],
    "M16": [(BUMP, '    return _json_replace(text, None, "version", current, new)',
             "    return text.replace('\"version\"', '\"verison\"', 1)"), G_ONLYFIELD, G_READBACK],
    "M17": [(BUMP, "        if in_pkg and _CARGO_VER.match(line.strip()):", "        if _CARGO_VER.match(line.strip()):"),
            (BUMP, '            break\n    return "".join(lines)', '            pass\n    return "".join(lines)')],
    "M18": [(BUMP, '    return _json_value(text, ("meta", "version"))',
             "    m = re.search(r'\"version\"\\s*:\\s*\"(\\d+\\.\\d+\\.\\d+)\"', text)\n"
             '    if not m:\n        raise SiteError("no version found")\n    return m.group(1)'),
            (BUMP, '    return _json_replace(text, "meta", "version", current, new)',
             "    return re.sub(r'(\"version\"\\s*:\\s*)\"\\d+\\.\\d+\\.\\d+\"', lambda m: m.group(1) + '\"' + new + '\"', text, count=1)"),
            G_ONLYFIELD],
    "M19": [(REL, '    if [ -n "$remote_tags" ]; then', "    if false; then"),
            (REL, '    git push origin "$TAG" || fail_code', '    git push -f origin "$TAG" || fail_code')],
    "M20": SAME,
    "M21": [(REL, '    git push origin "$TAG" || fail_code', "    true || fail_code")],
    "M22": SAME, "M23": SAME, "M24": SAME,
    "M25": [(REL, '    git push origin main || fail_code "$EXIT_PUSH"', '    true || fail_code "$EXIT_PUSH"')],
    "M26": SAME,
    "M27": [(REL, "        printf '## Known limits\\n\\n'", "        printf 'TODO: fill in\\n'\n        printf '## Known limits\\n\\n'"),
            (REL, "    if ! python3 tools/check_verification_doc.py >&2; then", "    if false; then")],
    "M28": [(REL, "    if ! python3 tools/check_verification_doc.py >&2; then", "    if false; then")],
    "M29": [(REL, '    dry_run\n    exit "$EXIT_OK"', "    dry_run")],
    "M30": [(REL, '        rm -rf "$DRY_COPY"', "        true")],
    "M31": [(REL, '    if ! remote_tags="$(git ls-remote --tags origin "refs/tags/$TAG" 2>&1)"; then',
             '    remote_tags=""\n    if false; then')],
}
for _m in MUTANTS:
    _bound = REFACTORED[_m.id[:3]]
    _m.refactored = _m.v193 if _bound == SAME else _bound
    _m.anchors["refactored"] = _m.refactored


def _inner(killers: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("RH_RELEASE_SH", "RH_BUMP_PY")}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "pytest", H, "-q", "-p", "no:cacheprovider", "-x", "-k", killers],
        cwd=PROJECT_ROOT, capture_output=True, text=True, env=env, timeout=900,
    )


@functools.lru_cache(maxsize=None)
def _control(killers: str) -> tuple[int, str]:
    r = _inner(killers)
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def _apply(m: Mutant, workdir: Path) -> dict:
    anchors = m.anchors[GEN]
    texts = {REL: (PROJECT_ROOT / REL).read_text(encoding="utf-8")}
    if (PROJECT_ROOT / BUMP).exists():
        texts[BUMP] = (PROJECT_ROOT / BUMP).read_text(encoding="utf-8")
    for target, old, new in anchors:
        n = texts[target].count(old)
        assert n == 1, f"{m.id}: anchor matches {n} times in {target} (must be exactly 1): {old[:70]!r}"
        assert old != new, f"{m.id}: the mutation changes nothing"
        texts[target] = texts[target].replace(old, new)
    out = {}
    for target, text in texts.items():
        dest = workdir / Path(target).name
        dest.write_text(text, encoding="utf-8")
        out[target] = dest
    return out


@pytest.mark.parametrize("m", MUTANTS, ids=lambda m: m.id)
def test_every_mutant_is_killed(m: Mutant, tmp_path):
    if m.anchors[GEN] is None:
        pytest.fail(f"{m.id}: anchor not bound for the {GEN} script. {m.note or 'Bind it when the script it targets exists.'}")

    code, tail = _control(m.killers)
    if code != 0:
        pytest.fail(f"{m.id}: control is red (exit {code}) against the unmutated {GEN} script, so the mutant cannot be "
                    f"judged yet. Killers: {m.killers!r}")

    files = _apply(m, tmp_path)
    assert subprocess.run([BASH, "-n", str(files[REL])]).returncode == 0, f"{m.id}: the mutated release.sh does not parse"
    if BUMP in files:
        py_compile.compile(str(files[BUMP]), doraise=True, cfile=str(tmp_path / "x.pyc"))

    env = {"RH_RELEASE_SH": str(files[REL])}
    if BUMP in files:
        env["RH_BUMP_PY"] = str(files[BUMP])
    r = _inner(m.killers, env)
    assert r.returncode != 0, f"{m.id}: SURVIVED. The harness passes with this defect put back: {m.defect}"
    assert r.returncode == 1, f"{m.id}: the sweep itself errored (pytest exit {r.returncode}):\n{(r.stdout + r.stderr)[-1200:]}"


def test_no_mutant_id_is_duplicated_and_every_killer_names_a_real_test():
    ids = [m.id for m in MUTANTS]
    assert len(ids) == len(set(ids))
    names = set(re.findall(r"def (test_\w+)", (PROJECT_ROOT / H).read_text(encoding="utf-8")))
    for m in MUTANTS:
        for token in re.findall(r"test_\w+", m.killers):
            assert any(n.startswith(token) for n in names), f"{m.id}: killer {token} matches no test in {H}"


# ---------------------------------------------------------------------------
# D3: a tag read from origin that cannot be read (ADR 0014, D2 "Shims")
# ---------------------------------------------------------------------------

class TestLsRemoteShim:
    def test_an_unreadable_origin_tag_list_is_exit_3_and_changes_nothing(self, fx):  # noqa: F811
        real_git = shutil.which("git")
        log = fx.base / "git-shim.log"
        shim = fx.bin / "git"                       # fx.bin is per-test and first on PATH
        shim.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = "ls-remote" ]; then echo "$*" >> "{log}"; echo "shim: ls-remote refused" >&2; exit 128; fi\n'
            f'exec "{real_git}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        before = fx.snapshot()
        r = fx.run(NEW)
        assert log.exists(), "the release never asked origin for its tags (git ls-remote was not called)"
        assert r.returncode == E_COULD_NOT, r.out
        assert "ls-remote" in r.out or "tags on origin" in r.out, "the failure must say what could not be read"
        assert fx.snapshot() == before, "nothing is mutated when the tag state cannot be read"

    def test_the_shim_is_transparent_for_every_other_subcommand(self, fx):  # noqa: F811
        # Guards the shim itself: a shim that broke git would make the test above pass for the wrong reason.
        real_git = shutil.which("git")
        shim = fx.bin / "git"
        shim.write_text(f'#!/bin/sh\nexec "{real_git}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        assert fx.run(NEW, "--dry-run").returncode == 0, "a pass-through shim must not change the outcome"
