# ADR 0014 - Release harness

**Status:** Proposed. It becomes Accepted when `tests/test_release_harness.py` and `tests/test_release_harness_mutations.py` pass with every mutant killed, and the owner commits it.
**Date:** 2026-10-28
**Context:** v1.9.4 - closing P5-07. Spine sentence: "The release script is tested the same way the registry is."

## Context

P5-07 says `release.sh` is mostly untested. Measured on the v1.9.3 tree (`scripts/release.sh`, 854 lines), the finding is
right in direction and the brief that scoped it is wrong in four counts. The ADR is written against the script, not the brief.

1. **There are ten preconditions, not seven.** Beyond the seven the finding names, the script runs `check_gh_ready`,
   `check_version_consistency` and `check_no_orphan_variables`. Three more guards run later and are also untested end to end:
   the untracked-file and non-modification aborts in `commit_and_push`, and the tag-message read-back in `tag_release`.
2. **There are seven `bump_*` functions covering eight sites**, not eight functions (`bump_iso_json` writes `meta.version`
   and `meta.updated`). Four are inline Python heredocs (changelog, iso_json, js_package, rust_cargo); two are GNU `sed -i`.
3. **Parts of the script are already tested** by function extraction: `poll_ci`, `tag_release`, `commit_and_push`,
   `check_no_orphan_variables`, `regenerate_artifacts`, `print_plan`, `check_gh_ready`, the `--poll-timeout` flag. None of
   those tests runs the script from `main()`, so none can see an ordering bug between stages. That is the gap.
4. **`--force` does not do what its usage text says.** `check_tag_free` only continues when the tag exists; `tag_release`
   then runs `git tag -a`, which refuses an existing tag, after the release commit has been pushed and CI polled. The flag
   defers the failure to the latest possible point. [Confirmed by reading; the harness cannot reproduce that exact point,
   because on a released version the stub verification doc already fails `check_verification_doc.py` in the gate on any
   re-run (measured: exit 1 at the gate), so `--force` dies earlier and for a second reason.] It is also only a local
   check: `git rev-parse refs/tags/$TAG` never asks origin, so a tag that exists on origin and not locally passes
   `check_tag_free` (measured: the release then pushes the commit before it fails, leaving origin changed).

Silent no-ops found in the bump functions: `bump_changelog` and `bump_iso_json` write nothing when their pattern does not
match, `sed -i` does nothing when its pattern does not match, and none reads the result back. `check_version_consistency.py`
in the gate catches a wrong version; it is not known to catch a wrong CHANGELOG date or `meta.updated`.

## Decisions

### D1. What the harness tests

**Decision:** the whole pipeline, run from `main()` of the real `scripts/release.sh` copied into a fixture repository, plus
one test per path. Function extraction stays for what it already covers; the harness adds what it cannot see.
**Reason:** a stage-by-stage test cannot catch "precondition passes, then bump, then push, then tag, then doc" being
mis-ordered or one stage swallowing another's failure.
**Rejected:** preconditions only (does not reach the bugs in items 3 and 4); a full fake with no git (cannot catch a tag
that is created but not pushed).

**Three classes of test (owner's rule; folded into D1 so D9 and D10 keep their numbers).** The red-first rule applies to the
class, not to the count of tests:

1. **Red-first:** fails on the v1.9.3 script, passes on the fixed one. Every defect this ADR fixes has one.
2. **Characterization:** passes today and must pass after. Every correct behavior this ADR preserves has one.
3. **Mutation-killed:** passes today, passes after, and fails on a mutant that reintroduces the defect. Every fix has one
   in addition to its red-first test. Where a red-first test cannot be judged against a green control until the refactor
   exists, the mutation sweep is where it is judged.

Measured on v1.9.3: 81 red-first, 29 passing (17 characterization, 11 positive-path characterization, 1 awaiting its
mutant: "the temporary copy is removed after a passing dry-run", which passes today only because no copy is made).

### D2. The fake remote

**Decision:** a bare git repo in a temp dir as `origin`; real `git` throughout, **not** a stubbed `git push`; a stub `gh`
on `PATH`, driven by a state file, because `gh` is the only thing that talks to GitHub. A push is made to fail with a
`pre-receive` hook in the bare repo.
**Reason:** a stubbed `git push` cannot fail the way a real push fails (rejected ref, hook, non-fast-forward) and cannot
prove a ref arrived. A hook gives the real failure mode.
**Departs from the brief:** the brief stubs `git push`. A stub would make "the tag-push does not push" mutant
unobservable, because the stub is the thing that would have to notice.
**Shims:** the git in the fake remote is the real git. Where a test must make one git subcommand fail (`git ls-remote`
for D3), it uses a test-only shim: one per test, in that test's own temp directory, prepended to `PATH`, failing only that
subcommand and `exec`-ing the real git for everything else.
**Harness environment (owner's amendments).** The fixture copy of `release.sh` shortens the poll timing (`POLL_GRACE=60` to 3,
`POLL_INTERVAL=10` to 1) and asserts each replaced text matches exactly once; the real script's constants are unchanged.
The harness runs the script under test from `RH_RELEASE_SH`, and `scripts/bump_version.py` from `RH_BUMP_PY`, when they are
set. Only the mutation sweep sets them; the default target is `scripts/release.sh`. The fixture's `gh` stub reports a run
only for a commit that origin holds, because GitHub has no run for a commit it never received.
**Isolation:** every test builds its own fixture: a fresh `git init --bare` origin in a new temp directory, a fresh
working clone, a fresh `gh` state file, discarded afterwards. No fixture is shared between tests, so a tag or a commit
pushed by one test cannot be seen by the next (a leaked tag would turn "tag free" tests into false passes).
**Fixture tools:** the fixture supplies stub `tools/*.py`, a trivial `tests/` and `wrappers/python/tests/`, and a minimal
`CHANGELOG.md`, `iso4217.json`, `README.md`, wrapper manifests and `release_claims.json`, so the gate runs without
pyarrow, Go or Rust. A stub tool fails when the environment variable `RH_FAIL` names it, which is how a test forces a gate step to fail
(an environment variable, not a file: an untracked file would trip `commit_and_push`'s own guard). The one real tool in the
fixture is a copy of `tools/check_version_consistency.py` and, for D4, `tools/check_verification_doc.py`, so the harness
exercises the checks the release actually depends on.

### D3. `--force` and an existing tag

**Decision:** the tag state is read from both places, **origin first** (`git ls-remote --tags origin`, then `git rev-parse`
locally), so a tag that exists only on origin is seen.

| Local tag | Tag on origin | No `--force` | `--force` |
|---|---|---|---|
| no | no | proceed | proceed; print that `--force` had nothing to do |
| yes | no | exit 1, name `--force` | delete the local tag and recreate it from the CHANGELOG, so the message is verified again |
| any | yes | exit 1 | exit 1; a published tag is never moved (RELEASE_PATTERN.md invariant 8) |
| - | `ls-remote` cannot be read | exit 3 | exit 3 |

**Implementation (owner's amendment):** `check_tag_free` calls `git ls-remote --tags origin` before the local check. The
`ls-remote` shim test (`TestLsRemoteShim`) is red on v1.9.3, which never calls `ls-remote`, and green on the refactored script;
the mutant that removes the call (M31) is killed.
**Reason:** a tag that was created and not pushed was never published, so recreating it breaks no one. Immutability
protects a tag someone may have fetched.
**Rejected:** moving the tag (violates invariant 8); refusing regardless of `--force` (strands the local-only case, which
is a real state after a failed `git push origin $TAG`).

### D4. The verification doc

**Decision:** the stub retires; the second commit does not. `write_verification_doc` writes a **complete** document, and
it still writes it after the tag.
**Departs from the brief, with the reason:** the brief wants a complete doc *before* the tag with no follow-up commit. Two
fields in the existing docs cannot satisfy that. The tag commit's hash cannot be written inside the commit it names. The CI
result for the release commit does not exist until that commit is pushed. A doc that omits both is not the doc
`check_verification_doc.py` and the v1.9.2 and v1.9.3 docs describe. So the follow-up commit is structural, not a workaround.
What was a defect is the stub: it is pushed to `main`, it fails the repo's own `check_verification_doc.py` (80-line
minimum, no `TODO`) in CI, and it stays red until a human edits it.
**CI coverage of the document (owner's amendment).** The D4 assertion covers every commit the release makes: the release
commit, the doc commit `release.sh` adds, and, if `write_v194_doc.py` then overwrites the doc, that third commit as well. The
verification doc records CI for each.
**What the doc contains:** the tag, the tag commit, the run ids and URLs `poll_ci` already holds, and the captured output of
every gate step. That clears the 80-line minimum with real content. It contains no hand-written prose; the human
completion script stays optional and overwrites a file that exists.
**Rule:** if the generated doc would fail `check_verification_doc.py`, the script does not commit it and exits 8. The
document is never pushed in a state the repo's own check rejects.
**Test obligation (added by the owner):** the second commit's CI must be green on the first try. If the doc is valid, CI on
the tag commit and on the follow-up both pass; a red second commit means the script should not have written the doc.
What the harness can prove and what it cannot: the harness has no GitHub, so it asserts the proxy that decides CI's
verdict, namely that the generated doc passes the real `check_verification_doc.py` *before* it is committed, that the
commit is not made when it does not, and that the follow-up commit contains only the doc. That CI is green on the real
second commit is observed in the release itself and recorded in the verification doc; it is not claimed as harness-proven.
**Rejected:** committing the doc inside the release commit (impossible for the hash and the CI result); keeping the stub
(red CI by design).

### D5. Dry-run

**Decision:** `--dry-run` runs the preconditions, then **bump, regenerate and the gate**, in a throwaway copy of the tree
(`cp -a` of the working directory including ignored files, to `mktemp -d`, removed on exit). It never commits, pushes,
polls, tags, or touches the operator's tree.
**Departs from the brief:** the brief runs the gate in place and uses a `dry_run` flag to skip the commit and tag. That
leaves the operator's tree dirty, which makes the next real `release.sh` fail `check_clean_tree`, and it contradicts the
flag's own contract ("no mutation"). The gate cannot run before the bump either: `check_release_claims.py $VERSION` and
`check_version_consistency.py` pass or fail on the post-bump tree.
**Reason:** a dry-run that cannot tell the operator whether the gate passes is a plan. The v1.9.3 dry-run was that.
**Cost to measure before accepting:** the copy size and the gate time, including `node_modules` and `target/`. If the copy
is impractical, the fallback is `git worktree` plus an explicit statement that the gate skips untracked toolchain state.
**Cleanup obligation (added by the owner):** the temporary directory is removed on success **and** on failure (a `trap`
on `EXIT`, which also runs under `fail`). Tests assert the directory is gone after a passing dry-run, after a dry-run whose gate fails, and after a dry-run whose
bump fails inside the copy (the copy exists, the failure comes later). The harness points
`TMPDIR` at a per-test directory so "gone" is checkable without guessing names.
**Rejected:** in-place run with a flag; plan-only (status quo).

### D6. Exit codes

**Decision:** keep the repo's meanings for 0 to 3 (RELEASE_PATTERN.md, "Exit-code convention") and extend upward by stage:

| Code | Meaning | State when it is returned |
|---|---|---|
| 0 | success, or a successful dry-run | |
| 1 | a precondition found a problem | nothing mutated |
| 2 | usage error | nothing mutated |
| 3 | could not run: `gh` missing or unauthenticated, origin unreadable, a required tool absent | nothing mutated |
| 4 | a generator or the gate failed | tree mutated, nothing committed |
| 5 | commit or push failed | local commit may exist |
| 6 | CI was not green, was unreadable, or timed out | release commit on origin, untagged |
| 7 | tag creation, verification or push failed | CI green, tag absent or local only |
| 8 | the verification doc failed | released and tagged; only the doc is missing |

**Departs from the brief:** the brief puts "gate failure" at 3. The repo's convention says 3 is "could not run", and tools
such as `check_cross_language.sh` already use it that way; a caller reading both would be told two things by one number.
**Reason:** the codes carry the operator's recovery action. 1 to 3 mean "fix and re-run". 4 means "the tree is dirty,
`git checkout -- .` then re-run". 6 means "the commit is public; re-run, do not bump". 7 and 8 mean the release is partly
done and says which part.
**Consequence (stated explicitly):** every exit in `scripts/release.sh` is re-audited and re-assigned in the same commit.
`fail()` keeps its one-argument form and its default of 1; a stage-aware `fail_code CODE MSG` is added. The four existing
function-extraction test files (`test_release_commit_and_push.py`, `test_release_hygiene.py`, `test_release_poll_ci.py`,
`test_release_tag.py`) define their own `fail()` and gain the new helper in the same commit. The audit of the v1.9.3 script
(every `fail` call, every explicit `exit`, and every bare `git` command that `set -e` turns into an exit) assigns:

| Site (v1.9.3 line) | Today | New |
|---|---|---|
| usage errors, `--poll-timeout` checks, unknown flag, missing or bad version (96-136) | 2 | 2 |
| `--help`, successful dry-run, success (117, 841) | 0 | 0 |
| `check_head_at_origin`: cannot fetch, cannot resolve `origin/main` (149, 155) | 1 | 3 |
| `check_head_at_origin`: HEAD differs from origin (158) | 1 | 1 |
| `check_workflows_covered`, orphan variables, manifest missing or without entry, dirty tree, not on main, tag exists, CHANGELOG section, version consistency (181, 222, 229, 236, 243, 251, 273, 287) | 1 | 1 |
| `check_gh_ready`: no `gh`, `gh` cannot list runs (261, 264) | 1 | 3 |
| `check_tag_free`: `ls-remote` unreadable (new) | n/a | 3 |
| `regenerate_artifacts`: a generator exits non-zero (407-417) | 1 | 4 |
| `run_gate`: any step failed (476) | 1 | 4 |
| `commit_and_push`: untracked file, non-modification (494, 503) | 1 | 4 (nothing committed yet) |
| `commit_and_push`: commit or `git push origin main` fails (set -e today: git's own 1 or 128) | 1 or 128 | 5 |
| `poll_ci`: `gh` error, run not green, no run, timeout (550-581) | 1 | 6 |
| `tag_release`: empty message, read-back mismatch, delete failed, `git tag` or `git push origin $TAG` fails (615-634, set -e) | 1 or 128 | 7 |
| `write_verification_doc`: doc fails the checker, commit or push fails (new) | 1 or 128 | 8 |

Where today's code relies on `set -e` and a bare `git` command, the exit is git's own (1 or 128); the re-assignment wraps
each such command so the code is the table's, not git's. A test per row is in the harness.

### D7. Preconditions

**Decision:** all ten run before anything is mutated, in the existing order, and each has a test that forces it and asserts
its exit code and its message. `check_tag_free` gains the origin read of D3. The three in-pipeline guards (untracked file,
non-modification, tag read-back) are tested through `main()` as well as by extraction.

### D8. The bump functions

**Decision:** the seven functions move out of `release.sh` into one `scripts/bump_version.py`, one callable per site. Each is
idempotent: a site already at the target is a no-op that says so; a site that does not match its pattern and is not already
at the target **fails**; each reads its result back. `bump_all_sites` calls the script. `scripts/` is used, not `tools/`,
so `check_audit_table.py` does not gain a row.
**Reason:** RELEASE_PATTERN.md operator-hygiene rule 4 (a multi-line construct goes in a file) and the four heredocs; the
two `sed -i` calls depend on GNU `sed`; a silent no-op is how a site stays at the old version without a failure.
**Interface (owner-specified, with the two choices the ADR makes):**

    usage: bump_version.py [--root ROOT] [--from OLD] [--to NEW] SITE
    SITE in version | changelog | iso_json_version | iso_json_updated
          | readme_badge | setup_py | package_json | cargo_toml

- **One SITE per call; `iso_json` is two sites.** `iso_json_version` and `iso_json_updated` are separate SITE values. Reason:
  one site per call keeps "exit 1 if OLD is not found where SITE expects it" unambiguous. A combined site could succeed on
  one field and fail on the other, and the exit would not say which.
- **What OLD and NEW mean per site.** `version`, `iso_json_version`, `readme_badge`, `setup_py`, `package_json`,
  `cargo_toml`: OLD and NEW are versions. `iso_json_updated`: OLD is the literal `DATE` (any `YYYY-MM-DD`; `release.sh`
  does not know yesterday's value) and NEW is a date. `changelog`: OLD and NEW are the **exact heading lines**
  (`## [1.0.1] — Unreleased` and `## [1.0.1] — 2026-10-28`), so no option beyond the owner's interface is needed.
- **The `DATE` convention (owner's refinement, amended).** The owner's wording was that a bump whose OLD value is today's
  date takes a literal `DATE` as OLD and the script substitutes the current date. I disagree with that wording for two
  reasons, and the ADR adopts the corrected form. First, the value `release.sh` does not know is *yesterday's* date (the
  one in the file), not today's; today's is the NEW value. Second, a script that reads the clock itself makes the
  CHANGELOG date and `meta.updated` able to differ across midnight and makes tests time-dependent. The convention is:
  OLD `DATE` means "any `YYYY-MM-DD` currently there"; NEW is always passed in, and `release.sh` computes it once (UTC) and
  passes the same string to both sites; `bump_version.py` never reads the clock. Only `iso_json_updated` uses `DATE`.
  `changelog` does not: its OLD is the exact heading line ending in `Unreleased`, which is known.
- **Idempotent:** a site already holding NEW exits 0 and says "already at NEW". Running twice is a no-op, byte for byte.
- **Fails loudly:** a site that holds neither OLD nor NEW, or does not contain its pattern at all, exits 1 and names the site
  and the file. (A missing site file is 2, the repo's "a local input is missing" code.)
- **Read-back:** after writing, the script re-reads the site and exits 1 if it does not hold NEW.
- **The clock (owner's addition).** `release.sh` reads the clock exactly once, at the start of the run (UTC, `TODAY`), and
  passes the computed date to `bump_version.py` as part of NEW. `bump_version.py` never reads the clock. A test passes a
  fixed NEW and gets deterministic output. Tested: `date -u` appears once in `release.sh`; `bump_version.py` imports no
  time or date module.
- **In `release.sh`:** any exit from it maps to 4. The `OLD` for the version sites is the `VERSION` file's content as read in
  the preconditions. On a re-run after the release commit exists (`OLD == NEW`) the version sites and the CHANGELOG heading
  are no-ops; `iso_json_updated` is still rewritten to the day of the run, as in v1.9.3 (reported for the v1.9.5 triage, not
  changed here).

**Rejected:** testing the heredocs where they are (works, but leaves the silent no-ops); leaving the `sed` calls (an
extraction that keeps one GNU dependency is half an extraction); a combined `iso_json` site (above).

### D9. The gate accumulates

**Decision:** the gate runs every step and fails at the end (the code does this today); the header comment that says "stops
at the first failure" is corrected. A test asserts that two forced failures are both reported and the exit is 4.

### D10. A failed gate does not roll back

**Decision:** no automatic rollback. The preconditions guarantee the tree was clean at the start, so the printed recovery
(`git checkout -- .`) is exact; an automatic rollback would delete the evidence of what failed. The test asserts nothing is
committed, tagged or pushed, and the message names the command.

## The mutation sweep

`tests/test_release_harness_mutations.py` defines every mutant against the **v1.9.3** script before the refactor, so a
mutant is not a test of the refactor. Three consequences are decided here:

1. **A mutant is judged only against a green control.** A mutant is "killed" when the harness passes on the unmutated script
   and fails on the mutated one. Before the refactor 81 harness tests are red, so a mutant whose killer is red-first cannot
   be judged yet; its test fails with "control is red", which is the honest state. Mutants whose killers are among the 29
   passing characterization tests are judged now. The rest are judged by the same file after the refactor.
2. **Anchors are bound per generation.** Each mutant has an anchor in the v1.9.3 text. After the refactor each anchor is
   re-bound (the exit codes, the extracted `bump_version.py`) in the same table, and the sweep refuses a mutant whose anchor
   matches zero or more than one place, so a refactor can never turn a mutant into a no-op that "survives" or is skipped.
3. **The count exceeds 20 on purpose.** Ten preconditions each need an "always passes" mutant; fewer would leave a
   precondition without proof. The mutants that exist only after the refactor (the doc is written without being checked, the
   temporary copy is not removed) are defined now and fail with "anchor not bound" until then.

The harness runs the script under test from `RH_RELEASE_SH` (and `scripts/bump_version.py` from `RH_BUMP_PY`) when set;
the sweep points them at a mutated copy in a temp directory and never edits `scripts/`.

## Consequences: the surface the harness must test

The harness is built from this list. A line here without a test is a harness that lies.

1. **Ten preconditions, not seven.** `check_head_at_origin`, `check_on_main`, `check_clean_tree`, `check_tag_free`,
   `check_changelog_section`, `check_manifest_has_version`, `check_workflows_covered`, `check_gh_ready`,
   `check_version_consistency`, `check_no_orphan_variables`. Each has a test that forces it from `main()` and asserts its code
   and message (D6, D7).
2. **Seven functions, eight sites.** `bump_iso_json` writes `meta.version` and `meta.updated`. D8 names both; there is one
   test per site (eight), against `scripts/bump_version.py` and through `release.sh`.
3. **Already-tested pieces never ran from `main()`.** `poll_ci`, `tag_release`, `commit_and_push`, the orphan check and
   `print_plan` have function-extraction tests. `tests/test_release_harness.py` runs `release.sh` from `main()`, so an
   ordering or swallowed-failure bug between stages is visible.
4. **`--force` is broken today.** It lets an existing tag through `check_tag_free` and fails at `git tag -a`, after the push
   and the CI poll. D3 replaces it; the three-state table is the test.
5. **`check_tag_free` is local-only.** D3 reads origin first. A tag that exists on origin and not locally must refuse.
6a. **Six of seven bump sites let the release finish with exit 0 and the site unbumped.** Measured on v1.9.3 with one
    site's pattern removed: iso_json version, iso_json updated, README badge, setup.py, package.json and Cargo.toml all
    exit 0; the seventh, the CHANGELOG heading, is caught only by the gate's consistency step, after the tree is mutated,
    with exit 1. The real `check_version_consistency.py` reports a site whose pattern is gone as `SKIP`, which does not
    fail. Fixed by D8 (fail loudly, read back). Tested by one "pattern removed" test per site.
6b. **The iso_json version regex rewrites the first `"version"` anywhere in the file when `meta.version` is missing.**
    Fixed by D8's script, which addresses `meta.version` specifically. Tested by
    `test_iso_json_never_rewrites_a_version_outside_meta`.
6c. **The first `gh` stub returned a green run for any commit, which hid a missing commit push (a latent bug in the test
    fixture, not in `release.sh`).** Found by the mutation sweep (M25, "the release commit is not pushed", survived: the later
    doc push sent the commit anyway). The fixed stub reports a run only for a commit origin holds, and a new test, "no run for
    the pushed commit is exit 6", fails on the missing-push mutant. `release.sh` exited 1 for this on v1.9.3 and exits 6 now;
    the fixture was the blind spot.
7. **`check_workflows_covered` exempts by name prefix** (`monitor`, `fetch`, `refresh`, `update`, `schedule`). The harness
   tests both sides; the exemption list is **unchanged** and is a v1.9.5 finding (a push-triggered `update-*.yml` would be
   silently unpolled).
8. **The `docs/audits/fifth-pass.md` to `third-pass.md` rename is v1.9.5.** It is not done here and is named under
   "Verification owed".

Also consequent: the gate accumulates (D9), a failed gate leaves a mutated tree and says how to restore it (D10), the
`--dry-run` path leaves no temp directory (D5), and the second commit's doc is checked before it is committed (D4).

## Verification owed

- **The mutation file has 31 mutants.** On v1.9.3, 20 were killed and 11 were unjudged: 6 had a red control (their killers are
  red-first tests: M09, M19, M20, M22, M23, M26) and 5 had no anchor (M18, M27, M28, M30, M31). A mutant is judged only
  against a green control, so those 11 were refactor-to-do items, not skips. After the refactor every mutant is bound and
  judged: 31 of 31 killed, no survivors. A mutant that remains "anchor not bound" is a bug in the mutation file, not a finding.
- **The sweep found three survivors in the harness itself, fixed in the tests, not accepted.** M17 (a `version` outside
  `[package]` rewritten) survived because the fixture's `version = "7"` is not semver-shaped; the fixture now has a
  `[dependencies.serde]` table with `version = "7.0.0"` and the assertion requires it untouched. M18 (meta.version not
  addressed specifically) survived because the foreign `version` differed from OLD and was refused for that reason; it now
  equals OLD, so only addressing `meta` specifically refuses it. M26 (untracked-file guard removed) survived because the
  second guard also fires; the test now asserts which guard fired. (The owner's fixture requirement named
  `[package.metadata.docs]` with `version = "7"`; the sweep showed that is not enough, and the form above replaces it.)
- **The harness found its own fixture bug.** The first fixture lacked `schema.json`, which the real
  `check_version_consistency.py` requires, so the `check_version_consistency` precondition failed in every fixture and many
  tests were red for the wrong reason (87 red instead of 81). Fixed in the fixture before the red-first numbers were taken.
  (It is unrelated to the wheel test.)
- **The uploaded v1.9.3 archive carries the stub verification doc.** `docs/v1.9.3-verification.md` in the archive is the
  39-line stub, so `check_verification_doc.py`, a gate step, fails on that tree. If the real HEAD has the completed doc this
  is only an artifact of the archive; confirm on the real tree before the release.
- **Measured here, to be confirmed on the real tree:** the D5 dry-run on a real copy of the tree, its size and gate time (owner:
  the `[Guess]` becomes `[Confirmed]`), and the `ls-remote` read with the maintainer's `gh` and git versions.
- **D4's CI assertion, recorded in the v1.9.4 verification doc:** "The second commit (Complete v1.9.4 verification report)
  passed CI on the first try. CI URL: <url>. This is the D4 assertion the harness cannot prove." The harness proves only that
  the generated doc passes `check_verification_doc.py` before it is committed. If any of the release's commits fails CI, that
  is a finding: record it under "Known limits" and fix it in v1.9.5.
- **The gate is still 28 steps.** The new tests run inside the existing `pytest tests/` step. `docs/AUDIT.md` needs no row:
  `check_audit_table.py` derives its table from `tools/`, and nothing was added there (`scripts/bump_version.py` is in
  `scripts/`).
- **For the v1.9.5 triage (new findings, not fixed here):** a re-run on a later day rewrites `meta.updated`; the
  `check_workflows_covered` name-prefix exemption; and the `fifth-pass.md` to `third-pass.md` rename.
- The harness depends on `bash`, `git` and POSIX paths; it is skipped on Windows like the existing release tests.
