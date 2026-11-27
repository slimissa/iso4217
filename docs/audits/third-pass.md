# Third-pass audit: ISO 4217 registry v1.9.0

> **Editorial note (v1.9.5).** This document, formerly `docs/audits/fifth-pass.md`, was delivered calling itself the fifth <!-- doc-path: example -->
> pass. That was a naming fault: this repository counts the audit that runs from v1.9.1 to v1.9.5 as its **third pass**, and the
> file was renamed in v1.9.5 (ADR 0017, D6). The finding IDs keep their `P5-` prefix: they are identifiers, cited on about 110
> lines in 23 files including verification records that are not rewritten, so renaming them would break every one of those
> citations. Read "P5" as a label, not a count.
>
> The report below is otherwise as delivered. It refers three times to "pass 3" as an *earlier* audit, in its own numbering,
> which this repository does not use. **Settled at v1.9.6: all three mean the v1.7.11 audit (F1 to F30, closed at v1.9.0).**
> [Likely] The report never names it; the evidence is that each "why missed" sentence describes what one of that audit's
> fixes did, as the CHANGELOG records it:
>
> - P5-04 ("made `to_minor` rounding consistent and assumed `format` followed"): F28, closed at v1.9.0. The 1.9.0 entry says
>   `to_minor()` and `format()` both accept a `Decimal` and round it half away from zero. [Confirmed by running the v1.9.0
>   tree, fc3c5b5] `to_minor(Decimal("0.125"))` was 13 and `format(Decimal("0.125"))` was `$0.12`: only `to_minor` did, which
>   is P5-04's own second bullet. The v1.1.0 change this note used to guess (af37d41, "standardize rounding to
>   half-away-from-zero across all four languages") also fits the words, but it was never called an audit, and one name for
>   two audits in one report is the less likely reading.
> - P5-05 ("audited the gate's completeness against the lists in the docs"): F5, closed at v1.8.3, made the generator list in
>   CONTRIBUTING.md equal to the release script's and added a test that keeps the two lists equal; no workflow file was read.
> - P5-07 ("verified the behaviours of the bugs it found, not the coverage of the whole script"): the functions P5-07 lists as
>   tested (`poll_ci`, the tag path, `commit_and_push`) are those F1 (v1.7.12) and F3, F17, F19 and F25 (v1.7.14) fixed.
>
> Checked and not found: no CHANGELOG entry, commit message, verification record or decision record numbers the audits
> before this one, so "pass 3" itself is matched to nothing in the history; the match is by content. ADR 0017 (D6) already
> treats "the earlier audit" as the v1.7.11 audit.

Date: 2026-10-23. Scope: the project archive `iso4217-main.zip` at v1.9.0 (the archive carried no `.git`, so HEAD
479f623 and the tag at fc3c5b5 were not verified). Method: read-only. The gate checks, `pytest --fail-on-skip`, the
four wrapper suites and about 25 mutations were run on a scratch copy.

Status: findings P5-01 through P5-11 accepted in full. Queued for v1.9.1 through v1.9.5. v1.9.1 (gate truthfulness)
takes P5-02, P5-05, P5-08, F31, rule 10 and the audit-table check.

The text below is the report as delivered, followed by the addendum on exit-code coverage.

---

The first uncomfortable truth: **many of the gate's 23 checks can be switched off without any of the 1,421 tests
noticing.** The gate's results depend on its own checks, and for the seam checks nothing tests that those checks can
fail.

I ran the real gate checks, `pytest --fail-on-skip` (1,421 passed), all four wrapper suites (Go 1.22 and cargo 1.75
from apt, not the CI versions), and about 25 mutations. Nothing was modified in the tree.

## Where the brief and the tree disagree

- The brief said every wrapper's toMinor/format accepts Decimal. Only the Python wrapper does. Go and Rust take
  `float64`/`f64`, and JS takes `number`. The 1.9.0 CHANGELOG says "The Python wrapper's API gains a Decimal".
  [Confirmed]
- The counts are 166 active, 136 withdrawn and 22 non-ISO, not 167/135/21. The README agrees with the data, so this
  is a stale premise, not a finding. [Confirmed]
- "Every artifact claims byte-identity" is not what the code enforces. Parquet `--check` compares logical content
  (disclosed in the 1.9.0 CHANGELOG). Regenerating all artifacts on Linux produced zero diff against the committed
  bytes, so identity holds in practice but nothing enforces it. [Confirmed]
- A Price<USD> + Price<EUR> contract does not exist in any wrapper. No Money or Price type is in the tree, so that
  question belongs to Tempus.

## Findings

Severity uses the same P0-P3 scale as the earlier audits. The P5-nn prefix avoids colliding with F1-F31.

**P5-01 [P1] The Python wheel ships a schema that rejects its own registry** [Confirmed]
- Repro: build the wheel in `wrappers/python`, then validate the shipped `iso4217.json` against the shipped
  `schema.json`. That gives 314 errors (`amendment`, `classification`, `source_url` rejected), and the schema `$id`
  is v1.3.0.
- Scope: nothing in `iso4217.py` reads the file, so it is inert in code but misleading to any consumer who validates
  with it. `sync_wrappers.py` copies four JSON files and not this one. The 1.9.0 CHANGELOG lists it only as
  "differs".
- Why missed: the audits treated "wrapper copies in sync" as meaning `iso4217.json`. The schema copy was out of
  scope, then recorded as a known limit without anyone measuring its effect.
- Prevention: add `schema.json` to `WRAPPER_COPIES`, or stop shipping it. Add a test that validates the built
  wheel's registry against the wheel's schema.

**P5-02 [P1] Gate checks whose failure no test detects** [Confirmed by mutation]
- Repro: each of these was forced to exit 0 (`return EXIT_OK` inside the logic), and all 1,421 tests still passed:
  `check_country_codes.py` (the only enforcement of the 4217-to-3166 edge), `check_version_consistency.py`,
  `sync_wrappers.py --check` (both the mismatch and missing branches), `enrich_field.py --check` (4 gate steps).
- Sampled mutants of `check_registry_freshness`, `check_snapshot_freshness` and `export_sql --check` were killed
  correctly.
- Forcing the `__main__` exit to 0 also survived in the Parquet and aggregated exporters. That only exercises
  entry-point glue, so it is weak evidence.
- Why missed: the rule "every fix is tested by a mutation" was applied to the fixes of each pass, not to the checks
  that existed before the audits began.
- Prevention: a `tests/test_gate_mutations.py` that runs each gate tool against a known-bad fixture and asserts the
  exit code. Better, a mutation sweep script that fails if any mutant survives.

**P5-03 [P1] Country-to-currency drift is undetected, and 25 live disagreements are unreviewed** [Confirmed]
- Repro: Germany moved from the EUR `countries[]` to USD. `check_country_codes.py` exited 0 and `validate.py`
  exited 0. The check only asks whether country codes resolve in the snapshot, not whether the currency matches.
- Comparing 4217 `countries[]` with the vendored 3166 `currency_codes` shows 25 disagreements. Many are legitimate
  (CH has CHE and CHW, US has USN and USS, UY has UYI and UYW). Some need a decision: AS and UM (USD in 3166, absent
  from 4217), AX and TF (EUR in 3166, absent from 4217), XK (EUR in 4217, empty in 3166), GS (FKP in 3166, GBP in
  4217).
- 3166-to-4217 direction: the repo's own JOINS.md says it is checked on the ISO 3166 side. That repo's code was not
  available. [Likely]
- Why missed: the earlier passes treated "the code resolves" as the whole seam.
- Prevention: a membership comparison with a reviewed allow-list, where every exception carries a reason, in
  `check_country_codes.py`.
- The `Snapshot version` field is verified. A falsified `source_version` is caught by exactly one pytest test, and
  online by `vendor --check`, but by none of the offline check tools. `iso4217_version` lives in the other repo and
  was not audited.

**P5-04 [P2] The four wrappers diverge numerically, and the fixture cannot see it** [Confirmed by a differential run]

| Input | Python | JS | Go | Rust |
|---|---|---|---|---|
| USD 1.005 `format` | $1.00 | $1.01 | $1.00 | $1.00 |
| USD 0.125 `format` | $0.12 | $0.13 | $0.12 | $0.12 |
| JPY 500.9 `format` | ¥500 | ¥501 | ¥501 | ¥501 |
| JPY -2.5 `format` | ¥-2 | ¥-2 | ¥-3 | ¥-3 |
| USD 1e17 `to_minor` | 10^19 (bigint) | 1e+19 (float) | INT64_MIN | INT64_MAX |

- `to_minor` rounds ties identically in all four, but `format` does not.
- Go returns a negative value for a large positive amount, silently. That is the one to fix first.
- Inside Python, `Decimal("0.125")` gives `to_minor` 13 but `format` "$0.12" (half-up versus half-even).
- The CLI is exact, so `iso4217 minor 1.005 USD` gives 101 while the API call `to_minor(1.005)` gives 100. 1.9.0
  disclosed this as an output change, but it still differs from the other three wrappers.
- `format(nan)` returns "$nan" while `to_minor(nan)` raises.
- Fixture: it has 16 formatting vectors, all exactly representable, with no negatives, no ties and no large values.
  Error messages for the malformed-registry fixture matched between Python and JS in the probe.
- Why missed: the earlier audit the report called "pass 3" made `to_minor` rounding consistent and assumed `format` followed.
- Prevention: add tie, negative, overflow and `format`-versus-`to_minor` vectors to the fixture. Decide and document
  overflow behaviour.

**P5-05 [P2] The gate does not contain everything CI runs** [Confirmed]
- The 277 tests in `wrappers/python/tests/test_cli.py` and the console-script smoke tests run only in CI
  (`check-cli`). RELEASE_PATTERN.md:82 says the gate must include every check in CI's fast set.
- `npm run lint` runs nowhere. It passes when run, so F27's purpose is unrealised only by omission.
- The two CI pytest lines for the Python wrapper (`validate-wrappers` and `check-cli`) lack `--fail-on-skip`, which
  is hygiene rule 7's own flag.
- `check-wrapper-sync` diffs three of the four copies. The fourth is covered by `sync_wrappers --check` elsewhere.
- Why missed: the earlier audit the report called "pass 3" audited the gate's completeness against the lists in the docs, not against the workflow files.
- Prevention: a test that parses `validate.yml` and `version-and-hygiene.yml` and asserts every `run:` command is in
  the gate or on a named exception list.

**P5-06 [P2] Windows and CRLF** [Confirmed by simulation]
- `.gitattributes` pins LF only for `*.csv`, `*.tsv` and `VERSION`.
- A CRLF copy of the tree failed `vendor_iso3166.py --check` (SHA-256 of the snapshot), and `release.sh` no longer
  parses in bash. The SQL, JSON and Parquet checks passed.
- `windows-verify-manifest.txt` still holds v1.5.1 hashes, and the current `iso4217.csv` hash differs from the
  manifest, so it is stale. Nothing checks it.
- Prevention: `eol=lf` for `*.sh`, `*.py`, `*.json`, `*.sql`, and a CI job on a Windows runner that runs
  `vendor --check`. Delete or regenerate the manifest.

**P5-07 [P2] Most of `release.sh` has no test** [Confirmed by grep]
- Tested: poll_ci, the tag path, commit_and_push, the orphan check, the regenerate-stops case and print_plan.
- Not tested: the preconditions (`check_head_at_origin`, `check_on_main`, `check_clean_tree`, `check_tag_free`,
  `check_changelog_section`, `check_manifest_has_version`, `check_workflows_covered`); every `bump_*` function (the
  inline Python heredocs are the same kind of construct rule 4 forbids for operators); `--force`,
  `write_verification_doc`, and the gate-failure abort.
- Design points worth deciding: the header says the gate stops at the first failure, but `run_gate_step`
  accumulates and then fails; a failed gate leaves a mutated tree with no rollback; `release.sh` pushes a stub
  verification doc that its own CI check will reject until it is filled; `check_workflows_covered` exempts names
  starting with monitor, fetch, refresh, update or schedule.
- Why missed: the earlier audit the report called "pass 3" verified the behaviours of the bugs it found, not the coverage of the whole script.
- Prevention: a fake-remote harness that runs `release.sh` end to end with a stub `gh`.

**P5-08 [P2] `check_release_claims.py --audit` crashes** [Confirmed]
- The v1.7.4 claims name `.parquet` files. `check_claim` calls `read_text` first, so it dies with
  `UnicodeDecodeError` and exits 1 (the same code as "finding"). This also happens with
  `check_release_claims.py 1.7.4`.
- Rule 6c names `--audit` as its enforcement mechanism, and no test covers it.
- Prevention: handle non-text files in `check_claim`, and add an `--audit` test.

**P5-09 [P3] Wrapper lookup docs contradict the code** [Confirmed in Python and JS, Likely in Go and Rust]
- The `currency()` docstring says it searches active, then withdrawn, then non-ISO. All the code lets later entries
  overwrite earlier ones, so non-ISO wins. `validate.py` rejects overlaps (`DUPLICATE_*`, `NON_ISO_OVERLAPS_ISO`), so
  no data trips this today.
- `currency(None)` raises `AttributeError` in Python and `TypeError` in JS. Duplicate codes silently shrink
  `all_active`.

**P5-10 [P3] "Same pattern across registries" is false at the rule level** [Confirmed from raw files on main on
2026-10-23]
- Rule numbers collide: hygiene 7 means "a check that cannot run must fail" in 4217 and 10383, but "grep after every
  symbol removal" in exchange-calendar.
- ISO 3166 has no 6c, 7 or 8 equivalents and instead uses 9-19 for dry-run rules. 10383 has a 7b that 4217 lacks.
- Cross-repo citations such as "rule 7" are therefore ambiguous.
- ISO 3166 v1.8.1 exists since 2026-10-22. The vendored v1.8.0 snapshot is stale but data-identical, with only
  `meta.version` and `updated` differing. That is harmless today, and F31 would catch it.

**P5-11 [P3] `check_verification_doc.py` breaks rule 6d's own example**
- Its OK line is `OK: 1 verification doc(s) clean`, which is the weak form rule 6d quotes as the thing to avoid (no
  path).
- By default it checks only the latest doc. `--all` gives 24 false positives on prose containing "placeholder", so
  full-history checking is unusable.

## What held up

- **E:** the docs/AUDIT.md table is true as of v1.9.0 for all 23 rows. It was derived from the workflows and
  `release.sh` with a 20-line script. Nothing keeps it true.
- **Rule 8:** there is no automated enforcement of it.
- **Rule 9:** it works and is polled. It runs on push only, and the JS audit passes by construction.
- **Offline checks:** all 16 ran green on a clean Linux checkout.
- **Byte-identity:** Linux regeneration is byte-identical across all generated artifacts.
- **Cross-language:** the existing fixture passes in all four languages.

## Patch list, ordered by risk removed per effort

1. Add known-bad-fixture tests for `check_country_codes`, `check_version_consistency`, `sync_wrappers --check` and
   `enrich_field --check` (P5-02). Small effort, and it makes the gate trustworthy.
2. Fix the Go `to_minor` overflow (return an error or panic like NaN) and document it for all four (P5-04).
3. Remove or sync the stale `wrappers/python/schema.json` (P5-01).
4. Add `eol=lf` for the scripts and the vendored snapshot; delete the stale Windows manifest (P5-06).
5. Fix the `check_release_claims.py` parquet crash and test `--audit` (P5-08).
6. Add `--fail-on-skip` to the two Python CI pytest commands and put `test_cli.py` in the gate (P5-05).
7. Add the country-currency membership check with a reviewed allow-list, and decide the 25 cases (P5-03).
8. Add tie, negative and overflow vectors, and fix `format` (JPY truncation, JS rounding, Decimal half-even) (P5-04).
9. Add a fake-remote `release.sh` harness (P5-07). Larger effort.
10. Add a `check_audit_table.py` that derives the AUDIT.md table; align sibling rule numbers (P5-10); fix the
    docstring and the verification-doc OK line (P5-09, P5-11).

## Meta: what this pass learned about the method

- The earlier passes checked each fix with a mutation, but nobody mutated the checks that predate the audits. P5-02
  is the hole: the audit method inherited "the gate guards the release" as an unexamined premise.
- "Resolves" and "in sync" were treated as properties of the data when they are properties of one field or file.
  P5-01 and P5-03 are the same class.
- Fixtures were treated as the contract. P5-04 is what the fixture does not contain.
- Docs and tables were verified once by hand (AUDIT.md was true, and still has no checker).

## Should a further pass happen?

Not a pass of this kind again. One narrow pass after these patches land, looking for what this one could not reach:
the Windows and PyPI paths, the ISO 3166 side of the seam, a CI-toolchain diff (Go 1.27 and stable Rust, against Go
1.22 and Rust 1.75), and a live SIX amendment check.

## Limits of this audit

- The archive has no `.git`, so HEAD 479f623, the tag at fc3c5b5 and every commit hash were not verified.
- The SIX page was unreachable from the sandbox (`check_amendments.py` reported UNDETERMINED), so "registry is at
  amendment 180 and no 181 exists" is untested.
- Exit codes 0/1/2/3 were not enumerated per tool in the report itself (see the addendum), `release.sh` was not run
  end to end, and the ISO 3166 and ISO 10383 code was not audited, only their pattern docs.
- Go 1.22, cargo 1.75 and Python 3.12 were sandbox versions, not the CI's.

---

## Addendum: exit-code coverage (question D)

A regex heuristic, trusted only where it agrees with the mutation results above.

Where the two measurements agree [Confirmed]:

- `check_version_consistency.py`: exits 0, 1 and 2 are all declared, and no test asserts any of them. Its mutation
  survived.
- `check_country_codes.py`: exits 0 and 2 have no test, and the 1-path mutation survived.
- `sync_wrappers.py`: exits 2 and 3 have no test, and both `--check` branches survived mutation.
- `enrich_field.py`: exits 0 and 2 have no test, and the pending-changes mutation survived.

Where the heuristic is probably wrong:

- `check_mojibake.py`: the regex finds no exit-code assertions, but the mutation was killed by a test. The test
  asserts on something other than the numeric code.
- The tools that declare no `EXIT_*` constants (`validate.py`, `check_provenance.py`, `check_readme_drift.py`,
  `check_release_claims.py`, `check_verification_doc.py`, `update_from_iso.py`) show nothing either way and were not
  measured.
- `parse_source.py` has no test file at all and declares no exit codes.

What this adds to the report:

- It strengthens P5-02: the four tools above have no exit-code test, not just a missing failing case.
- Exit 3 ("could not run") has a test in `check_amendments.py`, `check_cross_language.sh`, the exporters,
  `vendor_iso3166.py` and `refresh_market_caps.py`. It has none in `sync_wrappers.py`.
- Item D is still not fully closed. A per-tool, per-code table needs a real harness: run each tool in an environment
  that triggers each code, then assert.


---

## P5-07 — Closed at v1.9.4

**Finding:** *Most of `release.sh` has no test* (P2). **Status: closed.**

**Proof:**
- `tests/test_release_harness.py` — 113 tests, run from `main()` against a bare
  git remote and a stub `gh`.
- `tests/test_release_harness_mutations.py` — 31 mutants, 31 killed, 0 survivors.
- `tests/test_release_hygiene.py` — 16 tests (function extraction), including the
  negative test that M28 requires.
- `docs/v1.9.4-verification.md` — the release receipt (§8.1–§8.6).
- ADR 0014 (`docs/decisions/release-harness.md`) — **Accepted**.

**Action item 9** ("Add a fake-remote `release.sh` harness (P5-07). Larger
effort.") is **done**.

The remaining findings (P5-09, P5-10, P5-11, EC) are scheduled for v1.9.5.

## Closure (v1.9.5)

This pass closes at v1.9.5. What follows records what closed each finding and what holds it today. It starts no new work; the last
section is a list for the fourth audit and nothing on it was begun.

### The findings

| Finding | Subject | Closed at | Held by |
|---|---|---|---|
| P5-01 | The wheel shipped a schema that rejected its own registry | v1.9.2 | `tests/test_wheel_contents.py` |
| P5-02 | The gate's tools were never shown able to fail | v1.9.1 | `tests/test_gate_mutations.py` |
| P5-03 | Country-currency drift went undetected | v1.9.2 | `check_country_codes.py --membership`, ADR 0010 |
| P5-04 | The four wrappers disagreed on rounding and formatting | v1.9.3 | `tests/test_wrapper_numeric_contract.py`, ADR 0013 |
| P5-05 | CI and the release gate ran different checks | v1.9.1 | `tests/test_ci_parity.py` |
| P5-06 | The line-ending policy covered three file types | v1.9.2 | `tools/check_line_endings.py`, `.gitattributes` |
| P5-07 | Most of `release.sh` had no test | v1.9.4 | `tests/test_release_harness.py`, `tests/test_release_harness_mutations.py`, ADR 0014 |
| P5-08 | `check_release_claims.py --audit` crashed on Parquet files | v1.9.1 | `tests/test_check_release_claims.py` |
| P5-09 | The wrappers' lookup contradicted its own documentation | v1.9.5 | `tests/test_wrapper_lookup_contract.py` and the four wrappers' own suites, ADR 0015 |
| P5-10 | Rule numbers collide across registries | v1.9.5, this repository's side | `tools/check_rules_refs.py`, `docs/rules.md`, ADR 0016; the sibling columns are unverified by tooling |
| P5-11 | `check_verification_doc.py` had a weak OK line and an unusable `--all` | v1.9.5 | `tests/test_check_verification_doc.py`, `docs/verification-grandfathered.json`, ADR 0017 |
| R10 | Hygiene rule 10: a check that cannot fail is not a check | v1.9.1 | the self-enforcing coverage test in `tests/test_gate_mutations.py` |
| AD | `docs/AUDIT.md` was written by hand and checked by nothing | v1.9.1 | `tools/check_audit_table.py` |
| F31 | A stale vendored ISO 3166 snapshot could not be noticed | v1.9.1 | `vendor_iso3166.py --check-upstream`, `tests/test_vendor_upstream.py` |
| EC | "Docs and pattern alignment" with Exchange Calendar | v1.9.5, as part of P5-10 | the Exchange Calendar column of `docs/rules.md`, labelled unverified |

EC is never defined in this document or anywhere else in the repository; it appears only in lists of the open findings. [Guess] It is
the Exchange Calendar alignment of P5-10, and ADR 0016 treats it so. If the owner meant something else this row is the one to correct.

### What held up

- **ADR first.** ADRs 0013 to 0017 were each written before the code they govern, and each was amended by what the tests found, not
  the other way round (ADR 0014 twice, ADR 0017 for the fence handling and the grandfather list).
- **The gate refuses to tag on red, and the release script that enforces it is tested.** 118 tests run the real script against a bare
  git remote, and 35 mutants of it are killed.
- **Mutation sweeps found defects in the tests themselves.** In v1.9.4 three (a `gh` stub that reported a run for any commit; a fixture
  value too weak to observe; two overlapping guards). In v1.9.5 the first run killed all 36 new mutants (32 in `tests/test_v195_mutations.py`,
  4 in the release harness's file); that is a statement about those mutants, not a proof that nothing is missing.
- **A tool that indexes a document finds the document's defects.** `check_rules_refs.py` requires every rule heading to have a row; it
  found that the heading of hygiene rule 6b carried a non-breaking space after the hashes and so did not render as a heading.
  `check_doc_paths.py` found the two dead links in the CHANGELOG that had stood for two releases.

### What this pass learned about the method

- **Run what processes real output on the real tree (the v1.9.5 brief's rule D).** v1.9.4's first real release exited 8: the generated
  verification document quoted the gate's output, and that output contained the line the 1.9.4 manifest's own claim printed. The harness used
  stubs and could not have seen it; the dry-run did not reach the document stage. Both are fixed (ADR 0017, D7).
- **The harness can be wrong too (rule E).** A fixture is a claim about the repository; when a fixture needed the repository's history
  (a list of grandfathered documents, a list of frozen citations) the list moved into a data file in the root being checked, so no other
  root inherits it.
- **A number in a document comes from a command (rule F).** "Non-ISO: 21" was written in the v1.9.3 verification document and carried
  forward to v1.9.4; the registry has 22. The v1.9.4 document's test counts disagreed with each other. Corrections are appended to those
  documents, dated; the originals are untouched.

### The fourth audit's input list

A list, not work. Nothing here was started.

1. The Windows and PyPI paths.
2. The ISO 3166 seam.
3. The CI-toolchain difference: this release was built with Go 1.27.3, Rust 1.99.1 and Node 22 installed from conda-forge in a sandbox;
   the versions CI uses were not compared.
4. Live SIX data.
5. The rules matrix: read the Exchange Calendar and ISO 10383 pattern files (the former's `docs` directory was blocked to automated access
   on 2026-10-29), replace every "unknown" cell, verify the matrix by tooling, and decide the difference in gate semantics (ISO 3166 and
   ISO 10383 describe a fail-fast gate; this repository's accumulates every failure).
6. **Closed at v1.9.6 (patch 08).** Deferred from v1.9.5: `check_workflows_covered` exempts workflows by name prefix (`monitor`, `fetch`, `refresh`, `update`, `schedule`), so a
   push-triggered `update-*.yml` would be silently unpolled. Exempting by trigger needs a YAML read the script cannot do without a helper and
   its own tests.
7. **Closed at v1.9.6 (patches 01 to 07, 09 and 10).** New findings from this release, not fixed:
   - Rust's collection accessors (`all_active()` and siblings) return hash-map order; Python, JavaScript and Go return file order.
     *Closed by patches 01 and 02.* Go did not return file order either: its accessors ranged over Go maps, whose order is random on
     every call [Confirmed by running v1.9.5]. Both now return file order beside O(1) maps, and the `collection_order` group of
     `tests/cross_language_consistency.json` holds all four to the same lists.
   - `by_country(None)` and `pegged_to(None)` raise `AttributeError` in Python [Confirmed by running] and an incidental `TypeError` in
     JavaScript [by reading]: the same accident P5-09 fixed for the five currency-code lookups.
     *Closed by patches 03 and 04.* No `by_country` exists; the country lookups are `issued_by` and `used_in` (`issuedBy`, `usedIn`). All
     three, and Python's module-level `pegged_to`, raise P5-09's `TypeError` and are in the `lookup_contract` invalid-input set.
   - Go and Rust sources are not formatted by `gofmt` and `rustfmt` (`gofmt -l` lists two files; `rustfmt` reports 45 differences on the
     v1.9.4 tree) and no gate step checks formatting.
     *Closed by patches 05, 06 and 07:* both formatted, and `tools/check_formatting.sh` is a gate step and a step of CI's Go and Rust legs.
   - This document still says "pass 3" three times for an earlier audit without saying which; the editorial note at the top records a guess.
     *Closed by patch 10:* the note now names the v1.7.11 audit and gives the evidence.
   - Any manifest claim whose output line contains a word the verification-document checker bans can still make a generated document fail it
     when the word is outside a code fence; the fence handling removes the known case, not the class.
     *Closed by patch 09:* `check_verification_doc.py --quote` writes every quoted gate output in a fence its content cannot close.
8. For the owner to measure on the real tree: the size and time of the dry-run's throwaway copy, and whether the real tree's gate output
   passes the checker in the dry-run's document stage.
9. Not verified in this release: CI, the commit hashes and tags (the archive carries no history), and the clean-venv count on the
   maintainer's machine.
