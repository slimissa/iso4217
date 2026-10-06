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
is written to a file first, read back, then passed to `git tag -F`.

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

ISO 4217 and ISO 3166 use this shape: nine artifacts regenerate,
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

Two instances:
- ISO 4217 `3687bc2` — the commit's message described the orphan
  check landing; the diff only carried the call site. The function
  body followed two commits later.
- ISO 3166 v1.6.4 — the CHANGELOG section named the ISO 10383
  reviewer entry and the orphan-preflight convention. Neither
  landed; a one-character anchor mismatch dropped both edits.

Both patches reported success. Neither diff matched its message.
The verification is `git diff --cached --stat` before every commit,
read against the intended change.

### 6c. Manifest claims describe state, not intent.**

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
---

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