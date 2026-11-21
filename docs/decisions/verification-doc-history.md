# ADR 0017 - The audit's documents are held to the same standard as its code

**Status:** Proposed. It becomes Accepted when every test and mutant named below passes and the owner commits it.
**Date:** 2026-10-29
**Context:** v1.9.5 - closing P5-11, the rename of the audit document, and the decisions carried from v1.9.4.

## Context

P5-11: `check_verification_doc.py` breaks hygiene rule 6d's own example (its OK line names no path, so it cannot tell which artifact it
checked), and `--all` is unusable. Measured on the v1.9.4 archive with the fence-skip of `fcc04cf` in place, before any change
(`python3 tools/check_verification_doc.py --all`, exit 1):

- **`docs/v1.7.4-verification.md` and `docs/v1.7.5-verification.md`:** 11 of the 24 findings (4 and 7) are the prose word "placeholder". The
  pattern `PLACEHOLDER` is compiled with `re.IGNORECASE`, so ordinary prose matches. [Confirmed] A precision bug, not a history
  problem.
- **`docs/v1.5.4-verification.md`:** a real, never-completed stub that shipped (12 findings; 39 lines, markers in its table). [Confirmed]
- **`docs/v1.5.0-verification.md`:** 79 lines against a minimum of 80. A real document, one line short. [Confirmed] (1 finding)

The fence-skip added in `fcc04cf` masks fenced code **and** inline code spans. Reading it: [Confirmed] an unterminated fence
masks every line after it, so a stub that opens a fence and never closes it passes; and the fence tracking toggles on any
`~~~` or triple-backtick line, so a `~~~` line inside a backtick fence flips the state.

Why the first real release exited 8: the generated verification doc quotes the gate's output, and that output contained the
line `[OK  ] scripts/release.sh does not contain 'TODO'`, printed by `check_release_claims.py` for the 1.9.4 manifest entry
`{"file": "scripts/release.sh", "absent": "TODO"}`. [Confirmed: tests/test_check_verification_doc.py records the string.] That
claim was written by the v1.9.4 session, which had itself warned that real gate output could trip the checker. The checker
had no notion of "this is evidence". The release script was right to refuse to commit a
doc its own checker rejects; the checker was wrong about what is evidence. The fence-skip is the fix; it is recorded here and
in the amendment to ADR 0014 because it changes what D4's guard catches.

The audit document is `docs/audits/fifth-pass.md`, but the audit is the **third pass** (v1.9.1 to v1.9.5). The CHANGELOG <!-- doc-path: example -->
entries for 1.9.1 and 1.9.2 and `docs/v1.9.2-verification.md` already say "third pass" and link to `docs/audits/third-pass.md`,
which does not exist: two dead links today. [Confirmed] There are 17 references to `fifth-pass` in 9 files at the start of this
release, and the finding IDs (`P5-01` to `P5-11`) appear on about 110 lines in 23 files.

## Decisions

### D1. `PLACEHOLDER` is case-sensitive

**Decision:** only the upper-case word is a marker. **Reason:** it removes every prose false positive with no exemption. A
lower-case "placeholder" in prose is not an unfinished document; the real stub markers (`TODO`, `FIXME`, the `<paste ...>`
family) are unaffected. **Rejected:** a version cutoff (D2).

### D2. Grandfather by name, with a reason, and make the list self-checking

**Decision:** `docs/v1.5.0-verification.md` ("79 lines; one short of the minimum; a real record") and
`docs/v1.5.4-verification.md` ("the stub shipped uncompleted; the check did not exist until v1.7.11") are listed, with those
reasons, in `docs/verification-grandfathered.json` (a data file read from the root being checked; an absent file means an
empty list, so no other repository root, and no test fixture, is made to carry the repository's history). `--all` fails when a grandfathered doc becomes clean ("stale entry: remove it"), when a listed path does
not exist, and when an unlisted doc is dirty.
**Reason:** the doc is a historical record and is not edited. A version cutoff ("skip anything before v1.9.2") would exempt the
v1.5.4 stub as "old" and every future regression in an old document with it. A named list shrinks, each entry has a reason
a reader can disagree with, and the mechanism already exists in the repo (the country-currency allow-list's "every entry is
current").
**Rejected:** a version cutoff; editing the old docs (rewrites history).

### D3. The OK line names what it checked

**Decision:** default mode prints `OK: docs/v1.9.5-verification.md clean (<n> lines)`; `--all` prints <!-- doc-path: example -->
`OK: <n> verification doc(s) clean, <m> grandfathered: <paths>`. **Reason:** hygiene rule 6d. The line now says which artifact it checked
and what it set aside.

### D4. The fence handling is exact, and says what it does not catch

**Decision:** fence tracking follows the opening marker (character and length) and closes only on a matching marker; an
**unterminated fence is an error** (`unclosed code fence opened at line N`), so it can no longer hide the rest of a document.
The scanner skips fenced code and inline code spans and nothing else. It does **not** catch a marker inside code (by design:
quoted evidence), a marker written in another language, or a doc that is complete in form and wrong in substance; the doc's
own counts are still the author's responsibility (rule F of the v1.9.5 brief).
**Tests:** a `TODO` in a fence passes, the same `TODO` outside it fails, an unclosed fence fails, `~~~` inside a backtick fence
does not close it.

### D5. `--all` runs in the gate

**Decision:** the gate's `check_verification_doc.py` step runs with `--all`, locally and in CI, so a historical doc cannot be
damaged unnoticed. **Reason:** with D1 and D2 it is precise and green. **Rejected:** leaving `--all` CI-only (the check that
would have caught a damaged old record would then run nowhere that blocks a release).

### D6. The rename, and what keeps it true

**Decision:** `docs/audits/fifth-pass.md` becomes `docs/audits/third-pass.md` (`git mv`; the history follows). Its title and <!-- doc-path: example -->
self-descriptions say "third pass"; sentences that mean the earlier audit say "the v1.7.11 audit" (F1 to F30). **The `P5-`
prefix stays**: the IDs are identifiers, they are cited in verification records that must not be rewritten, and one paragraph
at the top of `third-pass.md` says so. The two dead CHANGELOG links already point at the new name and become true. Every other
`fifth-pass` reference is updated in current documents and tools; in historical records (the v1.9.1 verification doc, older
CHANGELOG entries) the sentence is left as written and a dated "Correction" note is appended.
**The old claim:** `tools/release_claims.json`'s 1.9.1 entry says `docs/audits/fifth-pass.md` exists. That was true of the <!-- doc-path: example -->
1.9.1 tree and is a statement about it. `--audit` is documented as a diagnostic that reports superseded claims (it already
reports version-string claims that way), so the entry is **not edited**. A 1.9.5 claim asserts that `third-pass.md` exists and
that `fifth-pass.md` is absent.
**The mechanism:** new tool `tools/check_doc_paths.py`: every `docs/...` path cited in a tracked text file must exist, with a
`<!-- doc-path: example -->` skip marker for deliberate examples. It is not scanned in historical records for *old* names
(they cite files as they were), but it is for the two dead links, which are corrections of a path. It would have caught them.

### D7. The v1.9.4 carry-overs

| Item | Decision |
|---|---|
| (a) the checker skips fenced code | Recorded here (Context) and in the amendment to ADR 0014. |
| (b) `--dry-run` does not reach the doc stage | **Fix.** The dry-run renders the verification doc in the throwaway copy and runs the checker on it. The v1.9.4 real release exited 8 at exactly the stage a dry-run did not exercise. |
| (c) a re-run on a later day rewrites `meta.updated` | **Fix.** On a re-run (`VERSION` already at the target) `iso_json_updated` is skipped: the release's date is the day the release commit was made. Safe because a partly bumped tree is restored with `git checkout -- .` before any re-run. |
| (d) `check_workflows_covered` exempts by name prefix | **Defer.** Exempting by trigger needs a YAML read the script cannot do without a helper script and its own tests; it goes on the fourth-audit input list with the reason. |
| (e) corrections to `docs/v1.9.4-verification.md` | Appended as a dated "Corrections" section, never edited in place (below). |

## Consequences

- The gate and CI grow by two steps (`check_doc_paths.py` here; `check_rules_refs.py` in ADR 0016) and the `--all` change
  touches the same step in `scripts/release.sh`, `.github/workflows/validate.yml` and the CI-parity test.
- **New findings, not fixed here:** none beyond D4's unterminated fence, which is within P5-11's subject (the check's
  fence handling), and ADR 0015's Rust ordering note.

## The corrections to the v1.9.4 document

Appended to `docs/v1.9.4-verification.md` as "Corrections (2026-10-29)": the test counts, the clean-venv count of the fix
commit, and the non-ISO total, each with the command that produced it. See that section; the numbers come from commands run
in a clean virtual environment, not from memory (rule F).

## Verification owed

- Re-run `check_verification_doc.py --all` on the maintainer's tree; the counts above are from the archive.
- Confirm in the release that the generated doc passes the checker, with the dry-run's doc stage as the prediction.
