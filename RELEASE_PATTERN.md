# Release pattern

**Status:** Adopted — reviewed by ISO 3166 and Exchange Calendar.

The `release.sh` script exists in four registries. Each was written
independently, then reconciled through a series of exchange messages
between the maintainers. They share eight invariants and diverge on
one step. This document captures both, plus the operator hygiene
rules that emerged from the specific failures each repo hit.

Implementations:

- ISO 4217 (`scripts/release.sh`, two axes, eleven version sites)
- ISO 3166 (`scripts/release.sh`, one axis, eight version sites)
- Exchange Calendar (`scripts/release.sh`, three sites, two workflows)
- ISO 10383 (`scripts/release.sh`, planned for v1.1.0)

---

## The essential eight

Every `release.sh` refuses on the same eight conditions, in this
order. The order matters: cheap checks first.

### 1. Refuse on unclean state

The working tree is clean, the current branch is `main`, and `HEAD`
matches `origin/main`. All three, or the release does not start.

The `HEAD` comparison must be against a freshly-fetched
`origin/main`. Without the fetch, a stale remote-tracking ref lets
the check pass locally while the remote has moved ahead.

Why: a release built from an uncommitted state is a release whose
contents can't be reproduced. A release from a non-`main` branch is
a release nobody else has. A release from a stale `main` is a
release that will conflict with the next push.

### 2. Refuse on version collision or missing CHANGELOG

`VERSION` differs from the target, and `CHANGELOG.md` has a
`## [<target>]` section. Both.

Why: the version collision check is a no-op guard against re-running
a release that already completed. The CHANGELOG check ensures the
release has a description before it has a tag.

### 3. Bump all version sites, then verify

Every site that carries the version is bumped. After the bumps, all
sites are re-read and compared. Any mismatch stops the release.

Why: a partial bump is worse than no bump. It ships a registry whose
own metadata disagrees with itself.

The site list is repo-specific. See `axes.json` for the ISO 4217
and ISO 3166 shapes.

### 4. Post-rebuild verify

Two shapes. Pick the one that matches your generator count.

**Single generator.** `build → re-read → compare`. Three lines,
immediate, points at the build script if it fails.

**Multiple generators.** `regenerate all → gate → consistency
check`. The gate centralizes the comparison. The failure message
names the stale artifact.

Rule: state which shape your repo uses, and why.

### 5. Gate before commit

Every check that CI runs also runs locally, before the release
commit is created. Any non-zero exit stops the release before
anything is committed or pushed.

Why: a release that fails CI is a release that needs a revert
commit. A release that fails the gate locally is a release that
was never created.

**The gate must include every check that runs in CI's fast
workflow.** A check that runs in CI but not in the gate is a
check that a release can bypass: the release commit lands on
`main` with a red CI before the tag is created. The v1.7.5
incident is the reference case. Pytest was not in the gate; a
stale test passed locally and failed in CI. Fixed by adding
`pytest tests/` as the fourteenth gate step in `release.sh`.

**The same rule covers the commands that produce what the release commits.**
A command that fails and isn't checked leaves stale output. The v1.6.9 snapshot
generator ran without its required `--source` argument; the shell continued; the
release carried the stale snapshot. Applies to artifact generators, exporters,
sync scripts, and any command whose output the release commit includes.
Sourced from ISO 3166 v1.6.9.

### 6. Poll every workflow

After the release commit is pushed, poll every workflow that runs
on push to the release branch. Wait for all of them to complete.
`in_progress`, `queued`, and `pending` are not green. Only
`completed success` is.

Schedule-driven workflows (`monitor`, `fetch`, `refresh`, `update`)
are deliberately excluded. The exclusion list is enumerated by hand
and verified against the workflows directory before every release.

Why: a tag that lands on a green commit whose second workflow is
still running is a tag that hides a failure. v1.3.0 in ISO 3166 is
the historical example.

**Reference implementation.** ISO 4217 `scripts/release.sh`, function
`poll_ci`, as of commit `1f38fb4`. It reads every run for the release
SHA via `gh run list --json databaseId,headSha,status,conclusion,
workflowName`, then iterates each run and asserts both `completed`
and `success` before returning. The failure message names which
workflow failed and its run ID.

The workflow-coverage check (`check_workflows_covered`) enumerates
`.github/workflows/*.yml`, filters schedule-driven workflows by name
prefix, and fails if any remaining workflow is not in the declared
poll list. This catches a new per-push workflow added without being
added to `POLLED_WORKFLOWS`.

### 7. Tag only on green

The tag is created only after all polled workflows report
`completed success`. No manual override, no force. The tag message
is written to a file, passed to `git tag -a -F <file> --cleanup=whitespace`,
then read back from the tag object and compared with the file; a
mismatch deletes the local tag and stops before the push, so a tag
that differs from what was meant never leaves the machine.
`--cleanup=whitespace` is deliberate: git's default cleanup removes
every line that begins with `#`, which drops the Markdown section
headings (`### Fixed`) from a CHANGELOG-derived message.

Why: this is the rule that the release process exists to enforce.
`CONTRIBUTING.md` says "don't tag on red"; the script says "you
cannot tag on red."

### 8. Immutable tags

Once a tag is pushed, the code it points at is what shipped,
whether or not the CHANGELOG reflects it accurately.

Reconciliation of a tag that shipped with a known issue is a future
CHANGELOG entry acknowledging the divergence, not a force-push, not
a moved tag, not a rewritten release.

The tag is a claim about what shipped. The CHANGELOG is a claim
about what was known when. When they disagree, the CHANGELOG is
corrected and the tag is left alone.

---

## Two shapes of step 4

### Single generator

```
build
re-read the version from the artifact
compare to VERSION
```

Three lines. Immediate. The failure message names the file.

Exchange Calendar uses this shape: `tools/build.py` writes
`calendar.json`, then the script re-reads `meta.version` and
compares.

### Multiple generators

```
regenerate every artifact
run the gate (which includes a version-consistency check)
the check compares every artifact's version to VERSION
```

The gate centralizes the comparison. The failure message names
which artifact is stale, but the failure point is the gate, not the
rebuild step.

ISO 4217 and ISO 3166 use this shape: every artifact regenerates,
then `check_version_consistency.py` compares all of them.

### How to pick

If the repo has one generator, use the single-generator shape. It
catches the failure at the point of the failure.

If the repo has multiple generators, use the multi-generator
shape. An explicit re-read of each artifact is N blocks of
duplicated code; a centralized check is one.

State your choice in the release script's header comment.

---

## Registry freshness vs. snapshot freshness

Two questions that look similar and aren't:

- **Registry freshness** — is my own source of truth current?
  Answered by comparing the registry's `meta.updated` against a
  threshold (typically 180 days).

- **Snapshot freshness** — are my vendored copies of other repos'
  sources current? Answered by checking each snapshot's
  `meta.review_by` against the current date.

Both share an exit-code contract (0 fresh, 1 stale, 2 fatal). Their
state designs differ: registry freshness is one date against one
threshold; snapshot freshness has three states (ISO date, `closed`,
`null`) because vendored sources can be static.

**Naming.** A tool named `check_snapshot_freshness.py` answers the
second question. If it is used to answer the first, the naming
collides with the purpose and a maintainer will look for the
registry's freshness check and not find it. The two questions want
two names.

**Reference implementation.** ISO 4217 has both as of v1.6.3:

- `tools/check_registry_freshness.py` — reads
  `iso4217.json → meta.updated`, 180-day threshold.
- `tools/check_snapshot_freshness.py` — adopted from ISO 3166
  v1.6.1. Globs `tools/*_snapshot.json`; reads `meta.review_by`
  from a sibling `<stem>.meta.json` when present, from the
  snapshot's own `meta` block when not.

Both run in CI, both run in the release gate. Neither supersedes
the other.

**When to add the registry check.** Any repo whose source of truth
is updated on a human cadence needs it. A repo whose source of
truth is updated by an automated pipeline that runs on every push
does not — the pipeline is the freshness guarantee. ISO 3166 is in
the second category today; ISO 4217 is in the first.

### Cadence variations

The threshold and the field name are repo-specific. Two reference
shapes as of 2026-09-28:

| Registry | Field read | Threshold | Cadence |
|----------|-----------|-----------|---------|
| ISO 4217 | `iso4217.json → meta.updated` | 180 days | irregular (ISO amendments) |
| ISO 10383 | `iso10383.json → meta.source_snapshot` | 60 days | monthly (SWIFT, second Monday) |

**`meta.updated` vs. `meta.source_snapshot`.** Two different questions.
`meta.updated` is when the file last changed. `meta.source_snapshot` is
which upstream release the file reflects. A file can be edited without
its upstream snapshot changing (formatting, bug fix), and the reverse
(a new snapshot lands without a human edit). A registry whose upstream
publishes on a calendar should track the second; a registry whose
upstream publishes irregularly tracks the first.

**Threshold rule.** The threshold is two publication cycles, not one.
A single missed cycle is late; two is stalled. 180 days for an
irregular quarterly-ish cadence; 60 days for a monthly cadence.

The pattern is shared; the field and the number are not. A port
between registries copies the pattern, not the parameters.

---

## The wrapper-copy test question

When a wrapper bundles a copy of the registry file (Python wheel
ships `iso3166.json`, Go module vendors it, Rust crate includes
it), the release script must verify the bundled copy matches the
root. But whether that check is *primary* or *defense-in-depth*
depends on one thing:

**Do the wrapper tests read from the bundled copy or from the root
file?**

- If tests read the bundled copy, pytest is the primary guard. The
  release-step check is redundant but cheap; keep it as
  defense-in-depth.
- If tests read the root file, the release-step check is the sole
  local guard. CI's wrapper-sync check is the backstop.

Before adding the check, `grep` the test suite for the path it
loads. Case in Exchange Calendar: tests load the repo-root file,
so the release-step check is primary. Case in ISO 3166: tests load
the bundled copy, so the check is defense-in-depth.

The rule: verify which path the tests exercise before deciding the
check's role.

---

## Tagged releases are immutable

Three rules, all consequences of the same principle.

**1. Never move a pushed tag.** A moved tag breaks anyone who has
already fetched. If v2.3.0 pointed at a commit whose polling fix
hadn't landed, the tag stays where it is. The fix is in the next
release.

**2. Never force-push over a tag.** Deleting and re-creating is the
same problem with an extra step. If the tag is wrong, the next
release corrects the record.

**3. The CHANGELOG acknowledges divergence.** When a tag shipped
with an issue that was discovered later, the next CHANGELOG's
`[Unreleased]` or the next release's section names the divergence
and points at the fix's commit. This is the reconciliation. It is
not a rewrite.

---

## The `[Unreleased]` rule

`CHANGELOG.md` may carry an `[Unreleased]` section at the top at release time. Nothing in the release
path reads the first line of the file, and nothing requires the target version's heading to be the
first heading. Presence, not position. Four consumers, each in ISO 4217:

- `release.sh` refuses unless a line beginning `## [<version>]` exists anywhere in the file.
- The staged heading `## [<version>] — Unreleased` is found anywhere in the file and rewritten to the
  release date. A literal `## [Unreleased]` heading is not touched.
- The tag message is the body of the `## [<version>]` section, from that heading to the next `## [`
  heading, wherever it sits.
- `tools/check_version_consistency.py` skips every heading that is not a dated version number, which
  covers both `## [Unreleased]` and `## [<version>] — Unreleased`.

One position still counts: among dated version headings, the first must equal `VERSION` before the
release script bumps it. An `[Unreleased]` section above it changes nothing.

A check that finds the target heading by reading the top of the file passes until the first release
that stages notes above it, and fails then. ISO 4217 conforms; each registry checks its own four
sites against this list.

## Version-pinned byte outputs

Any build tool that produces a byte-comparable artifact must be pinned to an exact version, not a range. A different
version can write different bytes for the same logical content.

ISO 3166 v1.6.8 hit this: `pyarrow>=15.0` let CI install a different pyarrow from the one that wrote the committed
`iso3166.parquet`, and CI's regeneration differed byte for byte. The fix was `pyarrow==25.0.1` (`aa784da`; the rule is `8902ba6`). ISO 4217
met the same class in v1.8.1: the committed Parquet footers named pyarrow 25.0.1 while `requirements-ci.txt` allowed
`>=26,<27`. Regenerating under 26.0.0 rewrote two bytes in each of the five files, the writer version in the footer.
ISO 4217's exporters' `--check` modes compare content, not bytes, so they passed throughout; the verdict there was
a sha256 comparison of regenerated against committed files. A `--check` that compares bytes would have failed.

CSV and JSON are usually stable across versions. Anything binary or with a structured footer (Parquet, Arrow, Avro,
HDF5) is not. Pin those.

**Corollary: pin the settings, not only the version.** Any tool that produces a byte-comparable artifact must have
all settings that affect those bytes pinned in the tool itself. Serialization order, encoding, and locale are
settings, not incidental choices. If a setting can differ between two runs of the same tool version, `--check`
will fail on a machine that made the other choice. Sourced from ISO 3166 `4b272e5`. ISO 4217's
`tools/vendor_iso3166.py` (v1.8.2) takes the question away for the snapshot by never re-serialising it, and takes
every setting for the one file it does serialise from a single function.

**Corollary: pin the render, not only the settings.** Any generator whose output is a committed artifact must not
read the clock, the OS, or an unpinned dependency. A value from `date.today()`, `os.getpid()`, or an unpinned
library version can pass `--check` only on the day (or machine) that generated the committed file. Pin the render,
or omit the varying field.

ISO 4217's instance: `tools/vendor_iso3166.py` copies the source bytes and takes the date it records from
`--vendored-at`; it never reads the clock. Absence claims in the manifest's `doc-facts` list, which
`tools/check_release_claims.py` checks on every run and so for every release, assert that `date.today(`,
`datetime.now(`, `time.time(`, `random.` and `uuid.uuid4(` do not appear in it. The tokens end at the open
parenthesis on purpose: the claim `datetime.now()` is not a substring of `datetime.now(timezone.utc)`, which is
what the tool called until v1.8.3, so it would have passed while the clock was read. A test,
`tests/test_check_release_claims.py`, evaluates the same claims against the tree on every pytest run and parses
the tool's syntax tree for calls an alias could hide. Sourced from ISO 10383 `268cbd8`; the unpinned instance is
ISO 3166's `gen_iso4217_snapshot.py`, which wrote `date.today()` into the bytes its `--check` compares (`4b272e5`).

## Operator hygiene

Four rules that emerged from specific failure modes across the
four implementations.

### 1. No heredocs for multi-line scripts

Inline Python or shell with quotes, braces, or shell
metacharacters will corrupt. Write the script to `/tmp/`, run it
standalone, check its exit code. Then proceed.

The failure mode: a heredoc silently absorbs the next shell
command into the file body. Happened in every release before the
rule.

### 2. `git diff` before every `git add`

If `git diff` is empty after an edit, the edit didn't land. The
commit will do nothing. The message describing the change will be
a lie.

The failure mode: a patch script that aborted at an anchor
mismatch, but the shell continued to the next command. The commit
message described a change that wasn't made.

### 3. Read every CI status before the next step

`in_progress`, `queued`, and `pending` are not green. Only
`completed success` is. Do not proceed past a CI check on any
other value.

The failure mode: a tag created while the second workflow was
still running. The tag landed on a commit that failed.

### 4. Every multi-line construct goes into a file

Heredocs, loops with function calls, `bash -c "..."`, Python via
stdin — all of them. If it needs quoting across more than one
level, it goes into a file. Run the file. Check the exit code.
Then proceed.

The failure mode: a `for` loop pasted into an interactive shell
that referenced functions defined inside a script. Twice.

### 5. The exit code of a pipeline is the last command's exit

`python3 tool.py | tail -3; echo $?` prints `tail`'s exit code, not
`tool.py`'s. `tail` always succeeds. The failure is invisible.

Redirect to a file, capture the exit code, then read the file:

```
python3 tool.py > /tmp/out 2>&1
echo "exit: $?"
tail -3 /tmp/out
```

The failure mode: a validator ran with a broken import, exited 1,
and the piped `tail -3` printed `0`. The release proceeded with the
validator broken.

Most checks that run in the gate also run in CI, so the gate is a
faster, local copy of the same signal. Some checks are gate-only by
design: their inputs are version-scoped in a way CI cannot reproduce.
`check_release_claims.py` is the reference case — the manifest has
claims about a version that does not exist until the release commit
lands. Gate-only checks are permitted; the tool's docstring names the
reason.

**Gate block shape.** The gate block must be a per-check capture
(each check's exit read individually) or a subshell with `set -e`.
Never a bare brace group on the left of `||`.

A brace group's exit status is the last command's status. With `||`
on the right, `set -e` is disabled inside the group — every check
runs, and only the last gates. ISO 3166 v1.6.6 shipped a release
where the claims check failed but the gate reported pass, because
`pytest` ran last and succeeded.

Two valid shapes:

    # Per-check capture
    GATE_FAILED=0
    run_check() {
        if output=$("$@" 2>&1); then
            echo "✓ $1"
        else
            echo "✗ $1"; GATE_FAILED=1
        fi
    }
    run_check validate.py python3 tools/validate.py
    ...
    [ "$GATE_FAILED" -eq 0 ] || fail "gate failed"

    # Subshell with set -e
    (
        set -e
        python3 tools/check_version_consistency.py
        python3 tools/check_release_claims.py "$VERSION"
        ...
    ) > "$GATE_LOG" 2>&1 \
        || { tail -20 "$GATE_LOG"; fail "gate failed"; }

ISO 4217 uses the first; the ISO 3166 fix uses the second. Both
work. The brace group does not.

### 6. Every artifact that quotes an implementation detail is coupled to that implementation

When a script's expression changes, every test that asserts on it
and every doc line or claim that quotes it change in the same commit.
The failure mode is silent: the script works, the doc lies.

The 10383 case: `\(.conclusion)` became
`\(.conclusion // \"pending\")` in a jq expression. The release-claims
manifest still asserted the old shape, and a test still checked for it.
Neither failed until the claim was verified against the tree.

Applies to:

- CHANGELOG entries that quote command output
- Verification docs that paste captured results
- README sections that show example invocations
- Release-claims manifests that assert on script internals

The rule: if an artifact reproduces text from a running program,
that artifact is a copy, not a reference. Copies drift.

### 6b. The commit is not the working tree

`git diff --cached --stat` before every commit. The message is a
claim about what the commit contains, not about what's on disk. If
the diff doesn't match the message, the message is wrong.

Three instances:
- ISO 4217 `82668a0` — the commit's title was "Run stores-200 demo
  test in CI"; the diff carried only a trailing-whitespace change.
- ISO 4217 `3687bc2` — the commit's message described the orphan
  check landing; the diff only carried the call site. The function
  body followed two commits later.
- ISO 3166 v1.6.4 — the CHANGELOG section named the ISO 10383
  reviewer entry and the orphan-preflight convention. Neither
  landed; a one-character anchor mismatch dropped both edits.

Both patches reported success. Neither diff matched its message.
The verification is `git diff --cached --stat` before every commit,
read against the intended change.

A `--stat` confirms *which files* changed, not
*what* changed. When the change is a specific line in a file — a
step added, a claim updated, a version bumped — read
`git diff --cached` in full, not just the stat. The stat catches a
missing edit; the full diff catches the wrong edit. The ISO 4217
v1.7.11 attempt is the reference case: the patch that installed
`duckdb` substituted a line inside a step rather than replacing
the step, producing an orphan `name:` in the YAML. The stat
named the workflow file; the diff would have named the orphan.

### 6c. Manifest claims describe state, not intent.

A claim in `release_claims.json` that asserts `file contains X`
must be verified against the file before the manifest is committed.
If X isn't there, the fix hasn't landed — not the claim.

Two failure classes:

- A claim describing a change that was intended but did not land.
- A claim whose string was edited to match the file, when the file
  was wrong.

Both turn the manifest into a check that always passes. The manifest
is a contract; a claim that describes intent instead of state is a
contract with nothing to enforce.

The `--audit` mode in `check_release_claims.py` runs every claim
against the current tree. Verify new claims before committing them.

### 6d. A check is only meaningful against the artifact it was designed for

The v1.7.11 release had three checks return a clean result against
the wrong file, and the release was cut three times before the
placeholder in its verification doc was caught.

Three concrete instances, all in one session:

- `grep -c TODO` on the verification doc returned 0, because the
  doc contained a placeholder (`<the real line>`) that is not the
  string `TODO`.
- `grep -c "986 passed\|test_stores_200"` on the same doc returned
  2, because the doc's own placeholder text contains both strings.
- `grep -c pytest` on a captured CI log returned 0, because the log
  was from the `Version and Hygiene` workflow, which does not run
  pytest. The `Validate Registry` workflow does.

A zero from a check pointed at the wrong file looks identical to a
zero from a check that correctly found nothing. The failure mode is
silent and it is the operator's responsibility to notice.

The rule:

- **Record which artifact each check reads, in the check's own
  output.** When a check produces a summary line, print the path or
  the run ID it was run against. `OK: 1 verification doc(s) clean`
  is weaker than `OK: 1 verification doc(s) clean under /repo/docs`.
  The second cannot be true if the check was pointed at the wrong
  place.
- **When a check returns zero unexpectedly, first confirm the
  artifact is the one intended.** Re-read the path or the command
  that produced it. A correct check against a wrong artifact is
  indistinguishable from a wrong check against the right artifact
  until you look.
- **Never write a check whose passing state is supplied by the
  artifact's own template.** A check on a doc that asks "does this
  contain X?" is a check that cannot fail if the doc's placeholder
  text contains X. Substituting a specific known-bad string for a
  general pattern is not a fix; it moves the failure to the next
  string.

This rule was added after v1.7.11. The check that closes the class is
`tools/check_verification_doc.py`: it holds the list of known
placeholder patterns in code, and its output names the file it
checked. Sourced from ISO 4217 v1.7.11.

### 7. A check that cannot run must fail, not pass

A built-in check that cannot execute — a missing toolchain, an absent
dependency, a network failure, a skipped test — is not a pass. It is an
unverified state, and the check must say so and exit non-zero.

Four consequences:

- A missing prerequisite is a failure, reported by name. The prerequisite
  is checked before anything is changed, and also under `--dry-run`.
- An exception must be explicit and visible: a flag on the command line
  that appears in the output. Not a silent default, not an environment
  variable, not a `skipped` line that still exits 0.
- "Nothing ran" is never success, even when every part of the check was
  excused.
- A check that wraps other checks reports how many ran, not only how many
  passed.

Sourced from ISO 4217 v1.7.12 (`poll_ci` returned success when it could
not poll), v1.7.13 (`check_cross_language.sh` reported a skipped suite as
OK), v1.7.14 (skipped tests counted as passes in the gate), and v1.7.15
(`check_amendments.py` exited 0 when it could not read the SIX page, so
the weekly monitor reported success while detecting nothing).

---

### 8. Every tool proves its own reachability

A tool with no `--check` or smoke invocation in CI may have unreachable code paths. The generator did: its
preservation block crashed on every invocation and only appeared to work because the snapshot's `review_by` was
set manually.

Every tool that produces a committed artifact runs in CI, even on unchanged inputs: a `--check` or smoke
invocation in the fast workflow and, under invariant 5, the same command in the release gate. The check does not
have to verify output; it has to make the tool's code path execute. A `--check` that rebuilds with the same
function the write path calls, and compares, satisfies both: it runs every branch and fails on an unreachable one.

Reference case: ISO 3166 `tools/gen_iso4217_snapshot.py` at `07e103f`, the commit before `b9c0807`. Given a valid
`--source` it raised `NameError` (`output_path` was undefined), in write mode and `--check` mode alike, and
exited 1, the code `--check` uses for "snapshot stale". The defects arrived in `da186b2`; `b9c0807` fixed three:
the undefined variable, a value assigned to a dict that was discarded before the return value was built, and a
stray import.

ISO 4217 had the same gap in v1.8.1: `tools/enrich_field.py --check` ran in neither CI nor the gate, and the vendored
ISO 3166 snapshot had no tool at all, so it was edited by hand and drifted from every tag. v1.8.2 adds the four
`enrich_field.py --check` steps and `tools/vendor_iso3166.py --check`.

Applies to: every tool with an output path in the repo, every generator, every exporter.
Sourced from ISO 3166 v1.6.9 (`94350d6`, `b9c0807`).

## The mojibake self-trigger rule

Any pattern-based check will find its own explanation. The mojibake
scanner matches corrupted bytes; a docstring that shows the
corruption by example contains those bytes. `check_version_
consistency.py` would trip on a doc that embedded a mismatch
example. A future freshness check would trip on an expired date
shown as an example.

Two escapes, both valid:

1. Describe the corruption in prose. "The circumflexed o becomes
   four bytes when a file is decoded as Latin-1 and re-encoded as
   UTF-8" rather than embedding the corrupted string.
2. Mark the file with the check's skip marker. Reserved for test
   fixtures that deliberately contain the pattern.

The general rule: state what the pattern matches, not the pattern
itself.

### Implementation note

`tools/check_mojibake.py` scans the first 200 bytes of every file
for the literal string `# mojibake-scan: skip`. If present, the file
is not scanned. This is the second escape, implemented.

The first escape — prose description — is a documentation
discipline, not a mechanical rule. It applies to any pattern-based
check, not just mojibake.

---

## What this document does not cover

- Specific `release.sh` implementations. See each repo's
  `scripts/release.sh`.
- The version sites each repo tracks. See `axes.json` in each repo.
- The versioning policy (semver, what counts as major / minor /
  patch). See `CONTRIBUTING.md` in each repo.
- The snapshot-vendoring pattern for cross-registry checks. See
  the "Consumed by" section in each registry's README and the
  registry-vs-snapshot subsection above.

---

## Reviewers

Reviewed by:

- ISO 4217 (`slimissa/iso4217`) — 2026-09-27
- ISO 3166 (`slimissa/iso3166`) — 2026-09-27
- Exchange Calendar (`slimissa/exchange-calendar`) — review pending

## Review history format

Every entry in a document's review history names the source repo,
not just the date and what changed.

Format:

    - YYYY-MM-DD — reviewed by <repo>. <what changed>.
      <attribution if the addition came from a specific exchange>.

`sourced from ISO 10383 v1.0.4` is a source. `co-authored` is not.
A reader tracing a rule's origin wants a specific commit to look up.

The convention was requested by the ISO 10383 builder, adopted by
ISO 4217 and ISO 3166, and applies to any document produced by more
than one registry.

## Review history

- 2026-09-27 — initial draft reviewed by ISO 4217 and ISO 3166.
  Two corrections incorporated: the wrapper-copy test question's
  framing, and the tag-immutability section's three-rule structure.
- 2026-09-27 — post-review addition: "Registry freshness vs.
  snapshot freshness" section, co-authored by ISO 4217 and ISO 3166.
  Names the two reference implementations in ISO 4217 v1.6.3.
- 2026-09-27 — post-review addition: "Operator hygiene" rule 5,
  on pipeline exit codes.
- 2026-09-28 — post-review addition: "Cadence variations" subsection,
  sourced from ISO 10383 v1.0.4. Names the `meta.updated` vs.
  `meta.source_snapshot` distinction and the two-cycle threshold rule.
- 2026-09-28 — post-review addition: operator-hygiene rule 6
  ("Every artifact that quotes an implementation detail is coupled to
  that implementation"), sourced from ISO 10383 v1.0.4. Generalizes
  the release-claims-manifest coupling failure to every artifact that
  reproduces program output.
- 2026-09-29 — post-review addition: operator-hygiene rule 6c
  ("Manifest claims describe state, not intent"), sourced from
  ISO 3166 v1.6.7.
- 2026-09-29 — post-review addition: gate-block shape rule under
  invariant 5. Names per-check capture and subshell-with-set-e as
  valid; the brace group as invalid. Sourced from ISO 3166 v1.6.6
  and confirmed against ISO 4217's per-check capture shape.
- 2026-10-07 — post-review addition: operator-hygiene rule 6d
  ("A check is only meaningful against the artifact it was
  designed for"). Sourced from ISO 4217 v1.7.11, where three
  checks returned clean against the wrong file in one session.
  Names `tools/check_verification_doc.py` as the check that
  closes the class for verification docs.
- 2026-10-16 — post-review addition: "The `[Unreleased]` rule" section. Sourced from
  ISO 3166 v1.6.8. The four consumers are those of ISO 4217's `release.sh` and
  `tools/check_version_consistency.py`.
- 2026-10-17 — post-review addition: invariant 5 amendment (commands that produce what the
  release commits). Sourced from ISO 3166 94350d6 (v1.6.9).
- 2026-10-17 — post-review addition: operator-hygiene rule 8 ("Every tool proves its own
  reachability"). Sourced from ISO 3166 94350d6 and b9c0807 (v1.6.9); reference case
  `tools/gen_iso4217_snapshot.py` at 07e103f.
- 2026-10-17 — post-review addition: "Version-pinned byte outputs" section and its settings
  corollary. Sourced from ISO 3166 8902ba6 (v1.6.8, the rule; the pin is aa784da) and 4b272e5 (the corollary);
  ISO 4217's instance is v1.8.1.
- 2026-10-19 — post-review addition: corollary "pin the render, not only the settings" (the
  clock rule). Sourced from ISO 10383 268cbd8; absence claims live in doc-facts.
