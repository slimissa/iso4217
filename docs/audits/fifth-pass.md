# Fifth-pass audit: ISO 4217 registry v1.9.0

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
- Why missed: pass 3 made `to_minor` rounding consistent and assumed `format` followed.
- Prevention: add tie, negative, overflow and `format`-versus-`to_minor` vectors to the fixture. Decide and document
  overflow behaviour.

**P5-05 [P2] The gate does not contain everything CI runs** [Confirmed]
- The 277 tests in `wrappers/python/tests/test_cli.py` and the console-script smoke tests run only in CI
  (`check-cli`). RELEASE_PATTERN.md:82 says the gate must include every check in CI's fast set.
- `npm run lint` runs nowhere. It passes when run, so F27's purpose is unrealised only by omission.
- The two CI pytest lines for the Python wrapper (`validate-wrappers` and `check-cli`) lack `--fail-on-skip`, which
  is hygiene rule 7's own flag.
- `check-wrapper-sync` diffs three of the four copies. The fourth is covered by `sync_wrappers --check` elsewhere.
- Why missed: pass 3 audited the gate's completeness against the lists in the docs, not against the workflow files.
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
- Why missed: pass 3 verified the behaviours of the bugs it found, not the coverage of the whole script.
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

## Meta: what the fifth pass learned about the method

- The earlier passes checked each fix with a mutation, but nobody mutated the checks that predate the audits. P5-02
  is the hole: the audit method inherited "the gate guards the release" as an unexamined premise.
- "Resolves" and "in sync" were treated as properties of the data when they are properties of one field or file.
  P5-01 and P5-03 are the same class.
- Fixtures were treated as the contract. P5-04 is what the fixture does not contain.
- Docs and tables were verified once by hand (AUDIT.md was true, and still has no checker).

## Should a sixth pass happen?

Not a fifth-style pass again. One narrow pass after these patches land, looking for what this one could not reach:
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
