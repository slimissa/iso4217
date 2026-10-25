# Changelog

All notable changes to the ISO 4217 Currency Registry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---
## [1.9.1] — Unreleased

The gate learns to fail. The fifth-pass audit (`docs/audits/fifth-pass.md`) forced four gate tools to exit 0 and all
1,421 tests stayed green. This release adds the tests that make every gate tool prove it can fail (P5-02), the rule that
requires them (R10), a check that keeps `docs/AUDIT.md` true (AD), CI and gate parity (P5-05), the fix for the
`check_release_claims.py --audit` crash (P5-08) and `vendor_iso3166.py --check-upstream` (F31). No registry data change;
no schema change. The other audit findings are queued for later releases.

### Added

- **Every gate tool is now tested in its failing state (P5-02).** `tests/test_gate_mutations.py` breaks one thing in
  a copy of the project per case, runs the real tool, and asserts its exit code, for `check_country_codes`,
  `check_version_consistency`, `sync_wrappers --check`, `enrich_field --check` (all four fields),
  `check_snapshot_freshness`, `check_registry_freshness` (the 180/181-day boundary), the five exporters' `--check`
  modes, `validate`, `check_mojibake` and `check_release_claims`. A meta-test fails when a tool joins the gate
  without a case or a written exemption. Before this, forcing `check_country_codes`, `check_version_consistency`,
  `sync_wrappers --check` or `enrich_field --check` to exit 0 left all 1,421 tests green.
- **Hygiene rule 10 (R10): a check that cannot fail is not a check.** `RELEASE_PATTERN.md` states it, cites P5-02, and
  names its enforcement (`tests/test_gate_mutations.py`). The numbering collides with ISO 3166's rules 10 to 19
  (P5-10); the rule is proposed to the siblings.
- **`tools/check_audit_table.py` derives `docs/AUDIT.md` from the tree (AD).** It reads `tools/`, the workflows and
  `run_gate()` and compares the `--check`, CI and Gate columns row by row; exit 0 match, 1 disagreement, 2 fatal. It is
  a gate step (the gate is now 24 checks) and a CI job. The table was true when the fifth-pass audit re-derived it;
  nothing kept it true.
- **`vendor_iso3166.py --check-upstream` (F31).** Lists the ISO 3166 tags with `git ls-remote --tags`, takes the highest
  stable `vX.Y.Z` and compares it with the vendored `source_version`: exit 0 current, 1 behind (or not an upstream tag),
  2 no stable tags or bad flags, 3 the tags could not be read. It is not a gate step (it needs the network, and a new
  upstream tag with no data change should not block a release). Against the vendored v1.8.0 it reports behind: ISO 3166
  v1.8.1 exists and changes no data.

### Notes

- **Fifth-pass audit complete.** 11 new findings (P5-01 through P5-11) and 2 meta-additions (R10, AD) identified; the
  report is `docs/audits/fifth-pass.md`. Queued for v1.9.1 through v1.9.5.

---
## [1.9.0] — 2026-10-22

The wrappers and the CLI: the npm package carries its data, the four wrappers fail the same way on malformed data, and
the CLI stops crashing, stops echoing terminal escapes, and stops losing digits. Audit findings F6, F13, F14, F15 and
F28, with F27 (cleanup) and F30 (CI topology) folded in and F29 recorded as accepted. No registry data change, no
schema change; the vendored ISO 3166 snapshot is re-vendored (see Changed). The Python wrapper's API gains a Decimal
overload.

### Fixed

- **The npm package shipped without its data (F6).** `package.json` listed `iso4217.json` under `files`, but the file
  was not in `wrappers/javascript/`, and `npm pack` omits a missing entry silently: the tarball held `index.js` and no
  registry, and an installed package could not find its data unless the caller's working directory held one.
  `tools/sync_wrappers.py` now keeps a fourth copy, `wrappers/javascript/iso4217.json`; a test packs the real package,
  reads the tarball, installs it into an empty project and loads it.
- **`iso4217 --registry <directory>` died with an `IsADirectoryError` traceback and exit 1 (F14).** It now exits 3 with
  a message, like every other unusable registry; so do unreadable paths and paths through a file.
- **The CLI echoed untrusted text into the terminal (F15).** `iso4217 lookup $'\x1b]0;PWNED\x07'` set the window title.
  Every error message that echoes input, argparse's own included, now escapes control, format, surrogate and
  line-separator characters (`\x1b`, `\u202e`); ordinary text, Windows paths and non-ASCII letters are untouched.
- **`iso4217 minor` and `format` lost digits through `float()` (F28).** `minor 99999999999999999999 USD` now prints
  `9999999999999999999900`. Amounts are parsed as `decimal.Decimal`; `NaN` and `Infinity` are still refused (exit 2);
  amounts of more than 100 integer digits are refused instead of computed. **Output changes** for decimal ties a binary
  float cannot hold: `minor 1.005 USD` is now `101` (it was `100`).

### Changed

- **One strict validation pass and one documented error type per wrapper (F13).** A malformed registry now fails at load,
  with the same message shape in all four languages, `malformed registry data: <JSON path>: <reason>`: Python
  `RegistryDataError` (a `ValueError`), JavaScript `RegistryDataError` (an `Error`), Go an error wrapping
  `ErrMalformedRegistry`, Rust `Err(String)` starting with that text. The contract is `docs/WRAPPER_VALIDATION.md`;
  `tests/cross_language_consistency.json` gains `malformed_registry_tests` (33 registries to reject with the path each
  must name, 6 to accept), so `tools/check_cross_language.sh` exercises all four. **Behaviour change:** Python no longer
  raises `json.JSONDecodeError` or `UnicodeDecodeError` for an unparsable file; both are `RegistryDataError` (still a
  `ValueError`). The CLI maps it to exit 3.
- `Currency.to_minor()` and `Currency.format()` in the Python wrapper accept a `Decimal` and convert it exactly (round
  half away from zero). `int` and `float` behave as before.

- **Cleanup (F27).** Unused imports removed: `hashlib` and `defaultdict` in `tools/update_from_iso.py`, the unused
  `jsonschema` import line in `tools/validate.py` (`SchemaError`, and `validate` with it), `overload` in the Python
  wrapper. `pyyaml` leaves the Python dev extra (nothing imports it) and `CONTRIBUTING.md` stops saying it is needed.
  `npm run lint` failed because `eslint` was not a dependency: it is now in `devDependencies`, exactly pinned, with an
  `eslint.config.js` (ESLint 9 and later will not run without one). `tools/check_mojibake.py` scanned by suffix and so
  skipped eight text files (`.gitattributes`, both `.gitignore`, `LICENSE`, `VERSION`, `MANIFEST.in`, `go.mod`,
  `go.sum`); it now scans them by name. The five `.parquet` outputs are binary and stay skipped.
- **CI topology (F30).** In `validate.yml`, `validate-wrappers` no longer waits for `validate-json`; both start once their
  export and sync checks have passed. Dependency caches: pip (four jobs), npm and Go (their legs of the wrapper matrix)
  and Rust through a SHA-pinned `Swatinem/rust-cache`, because `dtolnay/rust-toolchain` has no `cache` input. Each cache
  names its dependency file (`cache-dependency-path`) because this repo has none of the default ones and setup-python and
  setup-node fail the step without one. The JavaScript audit now runs `npm audit --omit=dev`: it audits what ships, as
  before, instead of the linter's dependency tree. The Go leg of the matrix runs on a newer Go than `wrappers/go/go.mod`
  declares (1.21), as it has since 1.8.5.
- `tools/iso3166_snapshot.json` re-vendored from ISO 3166 v1.8.0. Closes six releases of drift (v1.7.0 through v1.8.0),
  including the independent field correction in v1.7.3 and the note provenance fix in v1.7.4. `check_snapshot_freshness.py`
  did not catch this because it checks `review_by`, not source-version drift; that gap becomes F31 in v1.9.1.

### Added

- `docs/WRAPPER_VALIDATION.md`, `tests/test_js_package.py`, and tests for each item: the schema of the shared fixture in
  all four wrapper suites, directory and escape cases in `wrappers/python/tests/test_cli.py`, Decimal cases in both the
  wrapper and the CLI.
- Claims for all of the above in `tools/release_claims.json`; `doc-facts` asserts the CLI no longer parses amounts with
  `float()`.

### Notes

The duplicated code in `tools/` (e.g., `load_registry`, `_atomic_write_binary`) is accepted by design. Each tool is deliberately self-contained so it can be read, run, and reviewed alone.

Audit closure. All 30 findings from the v1.7.11 audit are either closed (F1–F28, F30) or explicitly accepted (F29). F31 (upstream-drift detection) is a new finding surfaced during the v1.9.0 release cycle and is scheduled for v1.9.1.

### Not in this release

- `iso4217 major` still prints its result through `float` (`from_minor()` returns a float), so a very large minor amount
  loses digits on output. Its input is already an exact `int`.
- JavaScript cannot tell `2.0` from `2`, so it accepts an integral float for `minor_units`; Python, Go and Rust reject it.
- The wrappers do not check for duplicate currency codes; the last one wins, as before.
- The release gate runs `pytest tests/` only. `wrappers/python/tests/` (the CLI suite) runs in CI, not in the gate.
- The `check-wrapper-sync` job's `git diff` list still omits `wrappers/python/iso4217.json` (`sync_wrappers.py --check`
  covers it in CI and the gate). `docs/LAYERS.md` and `CONTRIBUTING.md` still describe two or three wrapper copies, not four.
- `CONTRIBUTING.md` still says "As of v1.8.4". Nothing bumps that line.
- Other unused imports remain, outside the F27 list: `subprocess`, `Set` and `Tuple` in `tools/update_from_iso.py`,
  `from email import errors` in `tools/validate.py`, and ones in `enrich_field.py`, `export_aggregated.py` and
  `refresh_market_caps.py`. No check enforces it.
- `npm run lint` is not run in CI, and the Go leg of the CI matrix does not test the minimum `go 1.21` the module declares.

---
## [1.8.5] — 2026-10-20

Input hardening: `tools/validate.py` stops passing when it could not run, stops crashing on hostile input, and rejects
what `json.loads` silently accepts; the vendored ISO 3166 snapshot records its own hash. Audit findings F10, F11, F12,
F21 and F26. No data change, no schema change, no change to `RELEASE_PATTERN.md`.

### Fixed

- **`tools/validate.py` exited 0 when its schema layer did not run (F11).** A missing `schema.json` appended a warning
  and the run ended in "VALIDATION PASSED". The warning was never printed either: `validate()` rebuilds its warning list
  from the error list at the end, so the one it had appended was discarded. A missing schema file (default location or
  `--schema`) now exits 2, a missing `jsonschema` package exits 3, and `--no-schema` skips the layer on purpose and says
  so (`SCHEMA_SKIPPED`). An empty schema object `{}` was treated as "not found"; it is a schema.
- **Hostile input crashed `tools/validate.py` with a traceback and exit 1 (F10),** the code that means "a problem was
  found". Deep nesting (`RecursionError`), an integer of thousands of digits (`ValueError`), invalid UTF-8
  (`UnicodeDecodeError`) and a non-object root (`AttributeError`) now exit 2 with `FATAL: <file>: <reason>`. Integer
  literals are capped at 100 digits by the parser's own hook, so the result does not depend on the Python version. The
  schema file goes through the same loader.
- **The loader accepted duplicate keys and non-standard numbers (F12).** A file whose first `"version"` was wrong and
  whose second was right passed. Duplicate keys at any depth, `NaN`, `Infinity`, `-Infinity` and numbers that overflow
  to infinity (`1e999`, not named in the finding) now exit 2.

### Added

- `snapshot_sha256` in `tools/iso3166_snapshot.meta.json`, written by `tools/vendor_iso3166.py` and checked first by
  `--check`, before the tag is fetched; a missing or malformed value exits 2 (F21).
- `tests/test_validate_schema_guard.py`, `tests/test_validate_hostile_input.py`, `tests/test_validate_strict_json.py`:
  every case runs the tool as a subprocess and asserts the exit code and the absence of a traceback. New tests in
  `tests/test_vendor_iso3166.py` (a mutated snapshot fails the hash check before any fetch) and
  `tests/test_check_readme_drift.py`.
- `tools/check_readme_drift.py` documents that it needs a git work tree and reads the index, not the disk (F26).
- Claims for all of the above in `tools/release_claims.json`; `doc-facts` asserts `tools/validate.py` no longer carries
  the two warning codes it used to swallow.

### Not in this release

- A registry whose root is an object but whose shape is wrong below it (`"currencies": []`) still reaches the domain
  validators and ends in an `AttributeError` traceback with exit 1. Only the four input classes of F10 are caught.
- Only `tools/validate.py` is hardened. The other loaders of `iso4217.json` (the exporters, `update_from_iso.py`) are
  unchanged.
- `--check` on the snapshot already byte-compared it with the tag when the network was up. The hash adds a verdict
  before any network access, a value that shows in the meta diff, and a test that runs offline; it does not catch
  anything the byte comparison missed.
- F26 as written ("fails ungracefully without git") was fixed in 1.8.3 (exit 3, no traceback). 1.8.5 documents the
  requirement; it changes no behaviour.
- `CONTRIBUTING.md` still says "As of v1.8.4". Nothing bumps that line.

---
## [1.8.4] — 2026-10-20

Eleven items from the ISO 3166 and ISO 10383 review threads: a reachability table for every tool, the rule for which
layer compares bytes and which compares content, two `release.sh` tag fixes, the coordination-note rule, four stale
documentation lines, and dependency audits in CI. No data change. One description change in `schema.json`.

### Fixed

- **`release.sh` tag verification.** The message file is checked non-empty before the tag is created. The recorded
  message is compared with `$(...)` and `[[ ]]` before the push, as before; what is new is that `git tag -d` on a
  mismatch is checked. Under `set -e` a failing delete used to stop the script with git's own exit code before `fail`
  printed anything, leaving a local tag that nothing reported (A12).
- `release.sh` passes `--cleanup=verbatim` to `git tag`, so git records the message file exactly as written instead of
  running the whitespace cleanup over it (A13).
- `docs/LAYERS.md` named ISO 3166 v1.5.2 as the vendored snapshot; it is v1.6.9 (G1).
- `CONTRIBUTING.md` said "As of v1.5.0: registry is `1.5.0`, Python package is `1.1.0`"; it now says 1.8.4 for both (G2).
- The README tool tree omitted `tools/vendor_iso3166.py` (G3).
- `schema.json` described `meta.amendment_date` as an effective date; the field holds the date printed on the amendment
  PDF (G4). This closes the limitation recorded under "Not in this release" in 1.8.0.

### Added

- `docs/AUDIT.md`: every tool in `tools/`, its `--check`, its CI workflow and its gate status, in three categories, with
  the gaps listed. Operator-hygiene rule 8 links to it (A10).
- `RELEASE_PATTERN.md`: "CURATED vs AGGREGATED comparison" (A11), including the two CURATED Parquet files as the
  documented exception; "Coordination notes" (A14); operator-hygiene rule 9, "Every lockfile is audited on every
  push" (H9b).
- CI: `cargo audit`, `npm audit --audit-level=high`, `pip-audit` and `govulncheck ./...` run in the
  `validate-wrappers` job. The Rust and JavaScript jobs generate their lockfile first (both are gitignored);
  `pip-audit` reads `requirements-ci.txt`. `cargo-audit` is installed with a SHA-pinned `taiki-e/install-action`. The Go
  job's `setup-go` moves from 1.21 to a supported release so `govulncheck` is not scanning an end-of-life standard
  library; `wrappers/go/go.mod` still says `go 1.21`. They are polled by `release.sh`, not gate steps (H9a).
- `tests/test_release_tag.py`: a failing `git tag -d` aborts and says the tag still exists; source checks for the
  agreed forms.
- Claims for all of the above in `tools/release_claims.json`; `doc-facts` asserts `release.sh` contains neither
  `diff -q` nor the old cleanup flag.

### Not in this release

- `tools/export_parquet.py` and `export_countries_parquet.py` compare logical content, not bytes, against the A11 rule
  as worded. `pyarrow` is pinned, so a byte comparison is possible; it is a separate decision.
- `docs/AUDIT.md` is not checked by any tool. `parse_source.py` runs neither in CI nor in the gate and no decision
  records why. `update_from_iso.py` and `refresh_market_caps.py` are out of CI and the gate by design (manual,
  network-dependent); the table says so.
- The Go wrapper is no longer tested in CI on the minimum Go it declares (`go 1.21`).
- The JavaScript audit has no dependencies to audit. The audits run on push only, so an advisory published between
  pushes is seen at the next push.
- `wrappers/python/schema.json` is not synced by `sync_wrappers.py` and differs from the root `schema.json`.
- `docs/LAYERS.md` still names `check_country_codes.py --refresh-from` as the snapshot's refresh command;
  `vendor_iso3166.py` writes it. `CONTRIBUTING.md` still calls wrapper versions independent; they move together.

---
## [1.8.3] — 2026-10-19

Six audit findings (F5, F16, F18, F20, F22, F23), the amendment row in the versioning policy, and the lessons from the
ISO 10383 round-trip. Tooling, tests and documentation; no data change and no schema change.

### Fixed

- **`tools/check_release_claims.py` silently ignored every claim key except `file` and `contains`.** A claim
  `{"file": ..., "absent": ...}` passed as "file exists". It now supports `absent`, fails on any unknown key and on a
  missing file for every claim shape, and checks a top-level `"doc-facts"` list on every run, for every release.
- `tools/vendor_iso3166.py` read the clock: `--vendored-at` defaulted to `datetime.now`. It is now required in write mode.
- `CONTRIBUTING.md` step 3 listed four generators; `release.sh` runs six. A contributor following it got a red
  `export_aggregated.py --check`. The list is the release script's, and a test keeps the two equal (F5).
- `tools/validate.py` cited ADR 0006 for schema-version consistency (ADR 0009) and ADR 0005 for numeric-code reuse
  (ADR 0008). Nothing checked ADR citations in tools; a test now does (F16).
- `tools/check_registry_freshness.py` printed `check_snapshot_freshness.py` as its own name, in `--help`, its docstring
  and its report header; `docs/PROVENANCE.md` attributed the 180-day check to the snapshot tool (F18).
- Exit codes (F20): `check_verification_doc.py` and `check_readme_drift.py` exited 3 for a missing local input, the
  code the convention keeps for "could not run"; both now exit 2. `check_readme_drift.py` with git absent was an uncaught
  traceback, exit 1, which reads as drift; it now exits 3. `check_verification_doc.py` had no tests.
- `docs/JOINS.md` gave a hard-coded count at ISO 3166 v1.5.2; it now says what the check reports.

### Added

- Absence claims in `doc-facts`: `tools/vendor_iso3166.py` must not contain `date.today(`, `datetime.now(`, `time.time(`,
  `random.` or `uuid.uuid4(`, and `scripts/release.sh` must not contain `&& info `. The tokens end at the open parenthesis
  because `datetime.now()` is not a substring of `datetime.now(timezone.utc)`. `tests/test_check_release_claims.py`
  evaluates them on every pytest run and parses the tool's syntax tree for aliased calls.
- `docs/PROVENANCE.md` section 9: a per-field table, 46 rows (field, where, source, refresh trigger, checked by), and
  `tools/check_provenance.py`, which fails when a field of `iso4217.json` has no row, a row names a missing field, a cell
  is empty, or "Checked by" names a file that does not exist. CI job and gate step; the gate is now 23 steps (F22).
- `docs/JOINS.md`: the `region` and `subregion` edge from ISO 3166, consumed by `export_aggregated.py` (F23).
- Versioning policy: an ISO amendment that changes which currencies are active is Minor, not Patch (`CONTRIBUTING.md`,
  `README.md`).
- `RELEASE_PATTERN.md`: corollary "pin the render, not only the settings"; the exit-code convention (0 ok, 1 finding,
  2 fatal or usage, 3 could not run); "Asserting on prose"; the rule 6d paragraph on reading a structured file as stored.
- Tests: ADR citations, tool self-names, CONTRIBUTING against `release.sh`, the versioning policy, `check_verification_doc.py`.

---
## [1.8.2] — 2026-10-17

Closes the ISO 3166 v1.6.9 exchange: the vendored snapshot gets a tool and a CI check, the enrichment tool gets a CI
check, four rules are written down, and two docstring notes are corrected. One data change: the vendored snapshot.

### Fixed

- **`tools/iso3166_snapshot.json` was not a copy of any ISO 3166 release.** It was labelled v1.6.7, but BG `currency_codes`
  had been edited by hand to `["EUR"]` before ISO 3166 shipped that change (`docs/v1.8.0-verification.md` records it as vendored
  ahead of its source). It is now byte-identical to v1.6.9. Against the old file that changes BG `last_verified` and `note`,
  and the snapshot's own `meta.version` and `updated`; no currency code changes and `check_country_codes.py` is unaffected.
- `tools/check_mojibake.py` docstring: the entry attributed to a check mark is the Latin-1 corruption of the Mathematical
  Operators block, and the entry attributed to box drawing is the Latin-1 corruption of General Punctuation. Box drawing
  corrupts to a different prefix that no pattern covers; the docstring now says so, and tests compute the provenance.
- `tools/enrich_field.py` docstring: `--field` is required.
- `release.sh`: `regenerate_artifacts` wrote each generator as `cmd >/dev/null && info ...`, and a failure in a
  non-final position of an `&&` list does not trigger `set -e`. A failing generator now stops the release and is named.

### Added

- `tools/vendor_iso3166.py` with `--check`: the snapshot is vendored byte for byte, and `--check` calls the same builder the
  write path calls, compares the snapshot with the ISO 3166 tag named in `tools/iso3166_snapshot.meta.json`, and compares
  `source_version` with the source's own version. Exit 3 when the tag cannot be fetched. `tests/test_vendor_iso3166.py` is new.
- CI: job "ISO 3166 snapshot matches its source" runs `vendor_iso3166.py --check`; `enrich_field.py --check` runs for all four
  fields (four jobs). Both are also release-gate steps (invariant 5): the gate is now 22 steps.
- `RELEASE_PATTERN.md`: invariant 5 covers the commands that produce what the release commits (ISO 3166 v1.6.9); operator-hygiene
  rule 8, every tool proves its own reachability (ISO 3166 v1.6.9); a "Version-pinned byte outputs" section with its settings
  corollary (ISO 3166 v1.6.8 and `4b272e5`).

---
## [1.8.1] — 2026-10-16

Five tooling and documentation fixes from the ISO 3166 v1.6.8 review. No data changes; no schema changes.

### Fixed

- `release.sh`: the orphan-variable check never ignored comments. It filtered comment lines out of `grep -n`
  output, where every line starts with `N:`, so the filter matched nothing and a `$VAR` named in a comment
  aborted the release as an undefined variable. The filter now anchors after the prefix. A trailing comment
  on a code line is still scanned.
- `tools/check_mojibake.py`: two signatures added, the Windows-1252 reading of the prefix shared by dashes,
  curly quotes and ellipses, and the U+FFFD replacement character. The docstring described U+201A as a
  corrupted em dash; it is what a corrupted euro sign leaves behind. `tests/test_check_mojibake.py` is new;
  the checker had no tests.

### Changed

- `requirements-ci.txt`: `pyarrow>=26,<27` → `pyarrow==26.0.0`. Every Parquet footer records the pyarrow
  version that wrote it.
- `tools/check_snapshot_freshness.py` docstring: names the two freshness mechanisms, scheduled re-verification
  and the consumer's cross-reference check, and says not to merge them.
- `RELEASE_PATTERN.md`: new section "The `[Unreleased]` rule" (presence, not position).

---
## [1.8.0] — 2026-10-16

Amendment 180 applied: Bulgaria joins the euro on 2026-01-01 and BGN becomes a historic code.

### Changed

- **BGN moved from `currencies.active` to `currencies.withdrawn`** (withdrawn 2026-01-01, replaced by EUR at 1.95583), shaped like HRK. A consumer that looks BGN up in `active`, or lists the EUR-pegged currencies, no longer finds it. Active 167 → 166, withdrawn 135 → 136.
- Bulgaria (`BG`) added to the EUR `countries[]` as `issuing`.
- `meta.amendment` and `source.last_amendment_applied` 179 → 180. `meta.amendment_date` and `source.last_amendment_date` now hold the date printed on the amendment's PDF, 2025-09-22 (see `docs/PROVENANCE.md`). `source.last_verified` 2026-07-29 → 2026-10-15.
- `tools/iso3166_snapshot.json` re-vendored from ISO 3166 1.6.7, where BG's `currency_codes` is `["EUR"]`.
- `tools/check_amendments.py`: `KNOWN_LATEST_AMENDMENT` 179 → 180; the history entry for 179 is corrected (its date and "no currency additions" were wrong).

### Added

- **XAD**, Arab Accounting Dinar (numeric 396, minor unit 2, Arab Monetary Fund), in `non_iso.special_purpose` beside XDR, XUA and XSU. It is the whole content of amendment 179 (PDF 2025-05-02, effective 2025-05-12); earlier releases omitted it. Non-ISO 21 → 22.

### Fixed

- **The registry was created on 2026-07-29 at "amendment 179", ten months after amendment 180 was published (2025-09-22) and seven months after it took effect (2026-01-01). Every release from v1.0.0 to v1.7.15 listed BGN as active.** The amendment monitor that should have caught it reported success on a page it could not parse until v1.7.15.

### Not in this release

- `tools/update_from_iso.py --apply` is unchanged and still must not be used for an amendment.
- `schema.json` still describes `meta.amendment_date` as an "effective date"; the field holds the PDF date.

---
## [1.7.15] — 2026-10-15

The amendment monitor fails closed, CI is pinned, and three release-script
rough edges are gone. Findings F4, F7, F8, F9, and F24 of the v1.7.11 audit, and
the three release-script items from `docs/v1.7.14-verification.md`. No data
changes; no schema changes.

### Fixed

- The amendment monitor could go blind and stay green (F9). When it could not
  read the SIX page, `tools/check_amendments.py` exited 0 and reported the
  hard-coded 179; a page that parsed to no amendment number did the same
  (`parse_failed`, which is what the page does today). It now exits 3, retries
  transient failures three times first, and turns an uncaught exception into
  exit 2 instead of Python's 1 (which meant "new amendment"). The workflow no
  longer uses `continue-on-error`: exit 1 opens the "amendment N detected" issue,
  exit 3 opens or updates a separate "cannot read the SIX page" issue (label
  `monitor-blind`) and turns the run red.
  The page parser is repaired as well: the amendment number is also read from
  the download link's file name (`dl-currency-iso-amendment-180.pdf`; the
  redesigned page shows it nowhere else in its text), so the monitor reads
  amendment 180, which the registry does not yet apply.
- `monitor-amendments.yml` had no `permissions:` block and the repository's
  default token is read-only, so its `issues.create` call could not have
  worked (F8). The job now holds `contents: read` and `issues: write`.
- `validate.yml` ran only when a listed path changed, and the list omitted
  files whose tests live in the suite it runs (F4). It now runs on every push
  to main and every pull request, with no path filter.
- `version-and-hygiene.yml` ran two checks as steps of a job named "Country
  codes resolve" (F24). Each check now has its own job; "Country codes resolve"
  keeps its name. The header no longer states a count.
- `release.sh`: `commit_and_push` no longer opens a pager when run
  interactively; `check_no_orphan_variables` called an undefined `die` and
  now calls `fail`; `print_plan` lists all 17 gate steps, in gate order.

### Added

- Supply-chain pins (F7): all six workflow actions are pinned by commit SHA
  with a version comment; `requirements-ci.txt` pins the CI Python
  dependencies (duckdb exactly) and every pip install reads it;
  `--upgrade pip` and `npm install` are gone; `.github/dependabot.yml`
  covers `github-actions`, `pip`, `gomod`, and `cargo`.
- `check_amendments.py --simulate undetermined|new-amendment`, and a
  `simulate` input on `workflow_dispatch`, to exercise both alert paths
  without contacting SIX.
- Tests (1088 → 1177): `test_check_amendments.py`, `test_monitor_workflow.py`, `test_check_amendments_page.py`,
  `test_ci_supply_chain.py`, `test_ci_job_layout.py`, `test_ci_triggers.py`,
  `test_release_hygiene.py`.

### Changed

- `RELEASE_PATTERN.md` rule 7 cites v1.7.15 (F9) as its fourth instance.
- `docs/PROVENANCE.md` §2 says what the monitor does when it cannot read the
  page.

---
## [1.7.14] — 2026-10-11

Release-script and test-gate patch. Findings F3, F17, F19, and F25 of the
v1.7.11 audit, and operator-hygiene rule 7. No data changes; no schema changes.

### Fixed

- Skipped tests counted as passes. Without pandas, 8 tests were skipped and
  `pytest tests/` still exited 0, so CI and the release gate could be green
  without them (and without the demo test when duckdb was missing). CI now
  installs pandas, and both CI and the gate run `pytest tests/` with the new
  `--fail-on-skip` option; the allowed number of skips is 0.
- The release commit could contain files the release did not mean to change.
  `commit_and_push` ran `git add -A` and committed without showing what was
  staged. It now aborts on any untracked file, prints `git diff --cached --stat`,
  and aborts (unstaging first) if any staged path is not a plain modification.
- Dates were taken from the machine's local clock while CI runs in UTC. The
  release date, `meta.updated`, the CHANGELOG date, `last_verified`,
  `withdrawn_date`, and the freshness and validation comparisons now use UTC.
  The one-day tolerance in `check_registry_freshness.py` stays.
- `RELEASE_PATTERN.md` invariant 7 described a tag message written to a file and
  read back; `release.sh` used `git tag -a -m`. Both `-m` and `-F` also stripped
  every line beginning with `#`, so tag messages lost their `### Fixed` and
  `### Added` headings. The message is now written to a file, tagged with
  `-F <file> --cleanup=whitespace`, read back from the tag object and compared;
  a mismatch deletes the local tag and stops before the push. Tags before this
  release are immutable and unchanged. The stale "nine artifacts" count in
  `RELEASE_PATTERN.md` is removed.

### Added

- `tests/conftest.py` with `--fail-on-skip`.
- Operator-hygiene rule 7 in `RELEASE_PATTERN.md`: a check that cannot run must
  fail, not pass.
- Tests: `test_fail_on_skip.py`, `test_release_commit_and_push.py`,
  `test_utc_dates.py`, `test_release_tag.py`.

### Changed

- `RELEASE_PATTERN.md` — hygiene rule 6c now precedes 6d, and its heading has no
  stray `**`.
- `README.md` — the release-pipeline section describes the four behaviours above.

---
## [1.7.13] — 2026-10-10

Cross-language check fails closed. Finding F2 of the v1.7.11 audit. No data
changes; no schema changes.

### Fixed

- `tools/check_cross_language.sh` — a wrapper suite whose toolchain was
  missing was reported as `skipped` and the script still exited 0
  (`OK: 2 wrapper suite(s) passed, 2 skipped`), so the release gate could pass
  having run two of four suites. Every suite is now required: a suite that
  cannot run is `NOT RUN` and the script exits 3.
- `tools/check_cross_language.sh` — with no toolchain installed it printed
  `OK: 0 wrapper suite(s) passed, 4 skipped` and exited 0; the documented exit 2
  ("no suite could be run at all") was unreachable because skipped suites
  counted toward the total. That case now exits 2.
- `tools/check_cross_language.sh` — the header said CI runs the strict path.
  No workflow calls the script; CI's wrapper matrix runs each suite directly.
  The header is rewritten.
- `scripts/release.sh` — the gate and the dry-run plan wrapped the
  cross-language step in `if [[ -f tools/check_cross_language.sh ]]`, so a
  missing script dropped the step silently. Both guards are removed; a missing
  script now fails the gate step by name.

### Added

- `--allow-skip LANG` (repeatable; python, javascript, go, or rust, any case):
  the only way to excuse a suite. The exception is printed in the output.
- Exit code 3: no suite failed, but a required suite did not run.
- `tests/test_check_cross_language.py` — runs the real script against stub
  toolchains and covers every exit code, the skip path, and `--allow-skip`.

### Removed

- `--strict`. A suite that does not run is now a failure by default, so the flag
  has nothing left to do. Passing it is a usage error that says so.

### Changed

- `README.md` — states that all four toolchains are required and how to excuse
  one.

---
## [1.7.12] — 2026-10-09

Release-script patch. `poll_ci` no longer returns success on any path where
it did not see every polled workflow complete green. Finding F1 of the
v1.7.11 audit. No data changes; no schema changes.

### Fixed

- `scripts/release.sh` — `poll_ci` returned success on three paths where it
  had not polled: `gh` not installed, a run that never appeared (the loop ran
  to the timeout), and the 5-minute timeout itself. `tag_release` ran next, so
  a commit whose CI had not passed could be tagged, contradicting invariant 7
  (tag only on green). Every one of those paths now fails the release.
- `scripts/release.sh` — `gh run list ... 2>/dev/null || echo ""` made a `gh`
  authentication or API error indistinguishable from "no runs yet". A `gh`
  error now fails at once and prints `gh`'s own message.
- `scripts/release.sh` — `poll_ci` returned as soon as the runs it could see
  were green, so a workflow whose run had not been created yet (for example
  `validate.yml` while `version-and-hygiene.yml` had finished) was not waited
  for. It now requires a run for every workflow in `POLLED_WORKFLOWS`.

### Added

- `--poll-timeout N` (seconds, positive integer, default 300). Validated when
  parsed; a bad value is a usage error (exit 2) before anything runs.
- `check_gh_ready` in the preconditions: `gh` must be installed and able to
  list this repository's workflow runs. It runs under `--dry-run` too, so a
  dry-run on a machine that cannot poll CI fails instead of passing. There is
  deliberately no flag to skip polling.
- `tests/test_release_poll_ci.py` — runs `poll_ci` and `check_gh_ready` in a
  bash subshell with stub `gh`, `git`, and `sleep`; covers all of the above.

### Changed

- `README.md` — the release-pipeline section names the `gh` prerequisite and
  the `--poll-timeout` flag.

---
## [1.7.11] — 2026-10-07

CI-only patch. Wires the stores-200 demo test into the `validate-json`
CI job, and acknowledges a divergence recorded by v1.7.10's
verification doc.

### Fixed

- `.github/workflows/validate.yml` — the `validate-json` job did not
  install `duckdb`, so `tests/test_stores_200.py` skipped at
  collection in CI even though it ran in the release gate. The job
  now installs `duckdb` before the test step.
- `.github/workflows/validate.yml` — trailing whitespace left on the
  blank line after the pytest step by commit `82668a0` is removed.

### Note

v1.7.10's CHANGELOG stated that the demo test runs in CI. It did
not: commit `82668a0`, titled "Run stores-200 demo test in CI",
carried only a whitespace change to the workflow file. The tag is
immutable and stays where it is. This release makes the claim true.
`docs/v1.7.10-verification.md` records the divergence.

---

## [1.7.10] — 2026-10-07

Test-only patch. Adds an end-to-end test for `examples/stores-200`,
the companion demo. No data changes; no schema changes.

### Added

- `tests/test_stores_200.py` — reproduces the repository layout in a
  tmp directory, runs the demo unchanged, and asserts the specific
  numbers it prints: the 508-row join fan-out and the
  2,589,336,423 USD-equivalent overcount (Q1), the 7 stores whose
  countries have no region and the 193-of-200 naive join (Q4), the
  0-of-200 negative result (Q5), and the 13.2% pegged revenue share
  (Q6). The module skips cleanly when `duckdb` or `pyarrow` is
  unavailable.
- The test runs in CI alongside the main suite.

### Note

The fixture symlinks the registry's Parquet files and the whole
`tools/` directory into the tmp root, because the demo reads its
inputs from two directories above its own cwd. The fixture was
corrected twice during development, both times because a file the
demo reads was not enumerated. Symlinking `tools/` as a directory
covers any future read from there without a fixture change.

---

## [1.7.9] — 2026-10-07

Tooling-only patch. Adds a check that verifies README.md's structural
claims against the repository, wired into both CI's fast workflow and
the release gate. No data changes; no schema changes.

### Added

- `tools/check_readme_drift.py` — four checks against `README.md`:
  every relative link resolves, every file named in the Project
  Structure block exists, every count claim (`167 active currencies`,
  `sixteen-check gate`, ...) matches its source of truth, and every
  ADR number is unique with every README reference resolved.
- `tests/test_check_readme_drift.py` — eight tests, one per check
  plus the fatal path, each against a minimal fake repo in `tmp_path`.
- The check runs in CI's fast workflow (`version-and-hygiene.yml`)
  and as the fifteenth step of `release.sh`'s gate.

### Changed

- `README.md` — the release-pipeline section now says
  `sixteen-check gate`, matching the gate's sixteen steps. The check
  found this drift the moment it was added; it is the check's first
  catch.

---

## [1.7.8] — 2026-10-07

Three defects surfaced after the v1.7.7 verification; a fourth, in
`tools/export_aggregated.py`, was found while preparing this patch.
No data changes; no schema changes.

### Fixed

- `scripts/release.sh` — `tools/check_country_codes.py` was not in
  the gate. `docs/JOINS.md` claimed it ran "in the release gate and
  in CI"; only CI ran it. Added as the fifteenth gate step, after
  `check_registry_freshness.py` and before `check_cross_language.sh`.
  This restores the invariant 5 rule added in v1.7.6: the gate must
  include every check that runs in CI's fast workflow.
- `wrappers/python/iso4217_cli.py` — piping the CLI into a reader
  that closes early (`head`, `less`) raised an uncaught
  `BrokenPipeError` traceback. The CLI now exits 141 quietly and
  suppresses the final flush traceback. Subprocess tests cover
  the behavior.
- `tools/export_aggregated.py` — a `## [X.Y.Z] — Unreleased`
  CHANGELOG heading, which `release.sh` expects to find, was rejected
  as a malformed date and failed `--check` (exit 2). Such a heading
  is now skipped: an unreleased version has no row in
  `coverage_timeline.parquet` until the release script dates it.

### Changed

- `README.md` — rewritten against the v1.7.7 tree. The previous
  README pinned v1.7.3, described a nine-artifact eleven-check
  release, carried the wrong ADR numbers, claimed packages were
  published to PyPI/npm/crates.io, and said `axes.json` was read
  by the version check. None of that was true.

---
## [1.7.7] — 2026-10-07

Test-only patch. Adds coverage for the two freshness tools'
date-handling paths. No data changes; no schema changes.

### Added

- `tests/test_check_registry_freshness.py` — 18 tests covering the
  `--today` flag, the one-day timezone tolerance, the threshold
  flag, the fatal paths, the `--json` output, and one assertion
  against the committed registry.
- `tests/test_check_snapshot_freshness.py` — 8 tests covering the
  three-state design (`ISO date` / `"closed"` / `null`), the
  sibling-metadata preference, and the no-snapshots fatal case.

### Fixed

- `tools/check_registry_freshness.py` — an invalid `--today`
  value previously raised an uncaught `ValueError`. It now returns
  `EXIT_FATAL` with a diagnostic message. Found by the new test
  suite.

### Note

The `--today` flag on `check_registry_freshness.py` was added in
v1.7.6 with no test. The v1.7.6 verification report named this as
a follow-up. This release closes it.

---

## [1.7.6] — 2026-10-07

Two follow-ups from the v1.7.5 incidents. No data changes; no
schema changes.

### Added

- `--today YYYY-MM-DD` on `tools/check_registry_freshness.py`.
  Matches the shape already on `check_snapshot_freshness.py`. The
  timezone-tolerance fix from v1.7.5 is now testable without
  changing the system clock.
- `RELEASE_PATTERN.md` invariant 5 gains the rule: "the gate must
  include every check that runs in CI's fast workflow." Names the
  v1.7.5 pytest incident as the reference case.

### Note

The `--today` flag has no test yet. A synthetic test that exercises
the one-day tolerance and the two-day failure is a follow-up.

---

## [1.7.5] — 2026-10-07

Documentation-only patch. Fixes a CHANGELOG placeholder date and
resolves an ADR numbering collision. No data changes; no schema
changes.

### Fixed

- `CHANGELOG.md` — the v1.5.3 heading carried the placeholder
  `2026-09-XX` instead of the tag's actual date. Corrected to the
  date recorded on the `v1.5.3` tag. The
  `export_aggregated.py --check` note about the placeholder no
  longer fires.
- `docs/decisions/numeric-code-reuse.md` — renumbered from ADR 0005
  to ADR 0008. The number 0005 was already claimed by
  `note-source-split.md` (v1.6.0).
- `docs/decisions/schema-version-consistency.md` — renumbered from
  ADR 0006 to ADR 0009. The number 0006 was already claimed by
  `code-lifetime.md` (v1.6.0).
- Cross-references updated to name the new numbers.

### Note

The numbering is unique but not strictly chronological: 0007 was
assigned to `aggregated-layer-0007.md` at v1.7.4, and 0008/0009
renumber the two duplicates that followed in release order. A
future renumber to restore full chronological order is possible
but not necessary.

---

## [1.7.4] — 2026-10-06

Ships the AGGREGATED layer. Adds one CURATED projection, three
aggregated artifacts, and two new CI jobs. No data changes; no
schema changes.

### Added

#### CURATED

- `iso4217.countries.parquet` — one row per (currency, country,
  relationship). Five columns: `currency_code`, `country_code`,
  `country_name`, `relationship`, `status`. A sixth column,
  `classification`, is nullable and carries the currency's v1.6.0
  classification alongside the country join.
- `tools/export_countries_parquet.py` — the generator, in the shape
  of `tools/export_parquet.py` (`--check`, atomic writes, exit codes
  0/1/2/3, deterministic output).

#### AGGREGATED

- `currencies_by_region.parquet` — one row per (region, currency).
  Joins `iso4217.countries.parquet` with the vendored ISO 3166
  snapshot. `subregion` is populated only when every country in a
  group shares it, and is null otherwise. `XK` (Kosovo) and `TW`
  (Taiwan) have no region in the snapshot; those rows are retained
  with a null region, sorted last.
- `pegs_summary.parquet` — one row per anchor currency, aggregating
  the 44 single-peg currencies across 8 anchors.
- `coverage_timeline.parquet` — one row per released version,
  parsed from CHANGELOG headings. Counts are null for versions
  whose totals aren't in the CHANGELOG; no extrapolation.
- `tools/export_aggregated.py` — reads only from the CURATED layer
  and the vendored snapshot. It never opens `iso4217.json`.

#### Infrastructure

- CI jobs `check-countries-parquet` and `check-aggregated-export`
  in `version-and-hygiene.yml`.
- `docs/decisions/aggregated-layer-0007.md` — ADR 0007.
- `tests/test_export_countries_parquet.py` (37 tests) and
  `tests/test_export_aggregated.py` (68 tests).

### Changed

- `scripts/release.sh` — regenerates the four new artifacts; the
  gate runs thirteen checks (was eleven).
- `docs/LAYERS.md` — the AGGREGATED layer is now shipped, with the
  three artifacts and the rule that it reads CURATED only.
- `README.md` — new "Aggregated exports" subsection; Project
  Structure tree updated.
- `tools/check_version_consistency.py` — docstring notes why only
  the flat `iso4217.parquet` is a version site; the four new
  Parquet files' footers are checked by their own `--check` modes.

### Note

- The ISO 3166 snapshot contains `SK` and `AI` in both the active
  and withdrawn lists (Sikkim, Afars and Issas — historical codes
  reassigned to Slovakia and Anguilla). The country join resolves
  against `countries.active` only. Merging the lists would have
  misclassified both countries.

---

## [1.7.3] — 2026-09-29

Hardens the release-claims workflow and documents two release
patterns. No data changes; no schema changes.

### Added

- `check_manifest_has_version` precondition in `scripts/release.sh`.
  Fails before version bump when the manifest has no entry for the
  version being released. The v1.7.2 release caught the same
  condition at gate time, after artifact regeneration; the
  precondition moves the catch two seconds in.
- `--audit` mode in `tools/check_release_claims.py`. Iterates every
  manifest entry and reports per-entry pass counts. Diagnostic
  tool for verifying new claims before committing them.
- `RELEASE_PATTERN.md` operator-hygiene rule 6c — "Manifest claims
  describe state, not intent," sourced from ISO 3166 v1.6.7.
- `RELEASE_PATTERN.md` gate-block shape rule under invariant 5.
  Names per-check capture and subshell-with-set-e as valid; the
  bare brace group as invalid. Sourced from ISO 3166 v1.6.6 and
  confirmed against 4217's per-check capture.

### Changed

- `print_plan()` lists the new manifest precondition.

### Adopted from

- ISO 3166 v1.6.6 (gate-block shape)
- ISO 3166 v1.6.7 (rule 6c)

---

## [1.7.2] — 2026-09-29

Fixes the orphan check to fail on finding, records the gate-only
design for the release-claims check, and adds two conventions to
`RELEASE_PATTERN.md`. No data changes; no schema changes.

### Fixed

- `check_no_orphan_variables` now `die`s on finding. The warn-only
  behavior in v1.6.3 of the source was a bug: the check's name implies
  failing, and the failure class it catches is exactly what produced
  a partial release in an earlier registry. Reciprocal port from the
  source, matching the source's own v1.6.6 fix.

### Added

- `RELEASE_PATTERN.md` operator hygiene rule 6b — "the commit is not
  the working tree." Names two instances of the same failure class.
- `RELEASE_PATTERN.md` "Review history format" — the attribution
  convention from the ISO 10383 exchange. Every entry names its
  source repo.
- `tools/check_release_claims.py` docstring — the gate-only design
  rationale, plus a note in `RELEASE_PATTERN.md` invariant 5.

### Changed

- `RELEASE_PATTERN.md` invariant 5 — "gate before commit" softened to
  allow gate-only checks whose inputs are version-scoped.

---

## [1.7.1] — 2026-09-29

Ports two release checks from ISO 3166. No data changes; no schema
changes.

### Added

- `check_no_orphan_variables` in `scripts/release.sh` preflight,
  ported from ISO 3166 v1.6.3. Warns (does not fail) on names
  referenced in the script but defined nowhere.
- `tools/check_release_claims.py` and `tools/release_claims.json`,
  ported from ISO 3166 v1.6.5. The release gate runs the claims
  check after version consistency. Mechanically enforces
  operator-hygiene rule 6 (implementation-detail coupling). Claims
  are checked at release time, not in CI.

### Changed

- `scripts/release.sh` gate now runs eleven checks.
- `print_plan()` output aligned with the actual preconditions and
  gate steps.

---

## [1.7.0] — 2026-09-27

Closes the schema-version-consistency gap and (optionally) the
cross-wrapper is_independent default. No data changes; no schema
changes.

### Fixed

- `tools/validate.py` — removed the hardcoded schema-version check.
  It warned on every run since v1.6.0 because the constant drifted
  from the schema. Version agreement is owned by
  `tools/check_version_consistency.py`. Warning count returns to 26.
- Wrapper `is_independent` default aligned across Python, JavaScript,
  Go, and Rust. Absent field reads as `False` in all four, matching
  the CSV export. Previously JS/Go/Rust defaulted to `True`.

### Added

- `docs/decisions/schema-version-consistency.md` — ADR 0006.
- `RELEASE_PATTERN.md` — subsection on registry freshness vs.
  snapshot freshness, co-authored with ISO 3166.

---

## [1.6.3] — 2026-09-27

Adopts ISO 3166's multi-source snapshot freshness check and restores
the registry freshness check as a separate tool. No data changes; no
schema changes.

### Added

- `tools/check_registry_freshness.py` — the registry's own freshness
  check, restored under a name that describes its purpose. Reads
  `iso4217.json → meta.updated` and fails if older than 180 days.
- CI job `check-registry-freshness`.

### Changed

- `tools/check_snapshot_freshness.py` — adopted from ISO 3166 v1.6.1.
  Now reads a sibling `<stem>.meta.json` when present, falling back
  to the snapshot's own `meta` block. Scoped to vendored snapshots;
  the registry's own freshness is checked separately.
- `tools/iso3166_snapshot.meta.json` — `review_by` and
  `refresh_cadence` moved under a `meta` object to match the shape
  the adopted tool reads.
- CI job `check-snapshot-freshness` — replaces the previous
  `check-freshness`, which had been named for the wrong scope.
- `scripts/release.sh` — the release gate now runs both freshness
  checks.

### Adopted from

- ISO 3166 v1.6.1 (`check_snapshot_freshness.py` sibling-metadata
  support)

---

## [1.6.2] — 2026-09-27

Two release-script fixes and two validator-doc updates. No data
changes; no schema changes.

### Fixed

- `scripts/release.sh` now polls **every** workflow triggered by the
  release commit, not just the first. The previous `head -1` only
  checked one run per SHA; a second workflow still in progress could
  let a tag land on a partially-green commit. Verified against the
  release commit's `gh run list` output.
- `scripts/release.sh` now fetches `origin/main` and refuses to
  release when local `HEAD` differs from the remote. A local main one
  commit behind origin could previously proceed.
- `scripts/release.sh` now verifies that every per-push workflow in
  `.github/workflows/` is in the poll list. A newly-added workflow
  could previously be missed by the poll silently.

### Added

- `docs/decisions/numeric-code-reuse.md` — ADR 0005, documenting the
  26 permanent, expected warnings from the validator.
- `tools/iso3166_snapshot.meta.json` — vendoring metadata for the
  ISO 3166 snapshot, carrying `review_by` and `refresh_cadence`. The
  snapshot itself stays byte-for-byte.

### Changed

- `tools/validate.py` — `UNUSUAL_MINOR_UNITS_COUNT` now checks only
  circulating currencies. Fund and indexation units (CLF, UYW) carry
  their ISO 4217 precision without firing the warning. Warning count
  drops from 27 to 26.

---

## [1.6.1] — 2026-09-26

Convention extension and the first cross-registry snapshot. No data
changes; no schema changes.

### Added

- `axes.json` — declares the two version axes (registry, schema) and
  the 11 sites that carry them. Not yet read by the check script;
  exists as a stable contract for registries that will adopt it.
- `tools/iso3166_snapshot.json` — vendored byte-for-byte copy of
  ISO 3166 v1.5.2's `iso3166.json`.
- `tools/check_country_codes.py` — verifies every `countries[].code`
  in the registry resolves in the snapshot.
- CI job `check-country-codes`.

### Changed

- `tools/check_mojibake.py` — signature set extended from three
  literal byte sequences to four patterns. The fourth is a range
  check covering every Latin-1 accented-character round-trip:
  circumflexed, cedilla, tilde, and acute accents, and the
  Latin Extended-A range. Added `.sql` and `.html` to the scan
  suffixes. Added a `# mojibake-scan: skip` marker for test
  fixtures that deliberately contain corrupted bytes.
- `README.md` — ISO 3166 added to the "Consumed by" table with the
  vendored version.
- `docs/LAYERS.md` — vendored-snapshots subsection under CURATED.

### Verified

- `python3 tools/check_mojibake.py` exits 0 on the clean repo
- `python3 tools/check_country_codes.py` exits 0
- `python3 tools/validate.py` — 0 errors
- All eight gate checks pass

---

## [1.6.0] — 2026-09-26

Data model extension. Adds four fields to the registry, extends the
schema, and adds validation rules. No breaking changes — every new
field is optional at the schema level; the wrappers read absent fields
as null.

### Added

#### Registry data
- `classification` on every active entry (`circulating` | `fund` |
  `settlement` | `indexation`)
- `numeric_reused` on every active entry (boolean)
- `source_url` on every active and withdrawn entry (http(s) URI)
- `code_lifetime` on every withdrawn entry (`{from, to}` object)
- `meta.amendment` and `meta.amendment_date`

#### Schema
- Four new fields on `activeCurrency`, two on `withdrawnCurrency`
- Two new fields on `meta`
- `$id` bumped to `v1.4.0`

#### Tooling
- `tools/enrich_field.py` — one tool, four modes, formatting-preserving
- `tools/validate.py` — six new rules, `validate_v160_fields()`

#### Documentation
- Four ADRs under `docs/decisions/`
- `README.md` "Enums" section
- `README.md` per-field coverage table

#### Wrappers
- `classification`, `numeric_reused`, `source_url`, `code_lifetime`
  on `Currency` in Python, JavaScript, Go, and Rust
- `by_classification(cls)` / `byClassification(cls)` /
  `ByClassification(cls)` / `by_classification(cls)` on
  `CurrencyRegistry` in all four
- Extended `tests/cross_language_consistency.json` with
  `classification_tests`

### Changed

- `tools/parse_source.py` — removed stray `USS` from `ACTIVE_ISO_CODES`
- `schema.json` — `amendment` and `amendment_date` moved out of `version`
  up to `meta.properties`

### Verified

- `python3 tools/validate.py` — 0 errors
- All four `--check` commands exit 0
- All four wrapper suites pass
- `bash tools/check_cross_language.sh` exits 0

---

## [1.5.4] — 2026-09-26

Port the convention: add the VERSION file, the version consistency check
tool, and reconcile every version site. No data changes; no schema changes.

### Added

- `VERSION` at repo root
- `tools/check_version_consistency.py` — two-axis version check
- `.gitattributes` rule for `VERSION` (eol=lf)

### Changed

- All version sites reconciled to `1.5.4`
- `iso4217.json` → `meta.schema_version` set to `1.3.0`
- `wrappers/python/iso4217.json` added to `sync_wrappers.py`
- `tools/validate.py` schema version expectation updated to `1.3.0`

### Fixed

- `tools/parse_source.py`: removed stray `USS` from `ACTIVE_ISO_CODES`

### Verified

- `python3 tools/check_version_consistency.py` exits 0
- All six export and validation checks exit 0

---

## [1.5.3] — 2026-09-18

A patch release correcting five issues surfaced by an external audit of
v1.5.2: one code defect, one verification report with unverified
claims, one incorrect layering-discipline statement, one incorrect
provenance field, and one stale documentation reference. No schema
changes, no currency data changes. `iso4217.json` differs from v1.5.2
only in `source.crypto_source` and `source.stablecoin_source`
(`meta.version` and `meta.updated` are bumped at release, not here).

### Fixed

- **`tools/update_from_iso.py::save_registry`** required a `path`
  argument but was called with one argument from `--add-currency` and
  `--apply`, raising `TypeError: save_registry() missing 1 required
  positional argument: 'path'`. `path` now defaults to
  `REGISTRY_PATH`.

- **`docs/v1.5.2-verification.md`** section 8.4 claimed two DuckDB
  query results that did not match the actual Parquet file. Corrected
  `WHERE is_independent AND minor_units = 3` from `['JOD', 'OMR']` to
  `['IQD', 'LYD', 'TND']`, and the top-three-by-`peg_rate` result from
  `XAF`/`XOF`/`DJF` to `XAF`/`XOF`/`KMF`. The Parquet export was
  correct; the report was written from a template, not from command
  output.

- **`docs/LAYERS.md`** stated *"No tool writes to `iso4217.json`. It is
  edited by hand."* This is false — `tools/refresh_market_caps.py` and
  `tools/update_from_iso.py` both write to it directly. Corrected to
  *"No tool commits changes to `iso4217.json`. Every write must be
  reviewed and committed by a human,"* plus an explicit write-capable
  tools table naming both tools and their review gates.

- **`iso4217.json`** — `source.crypto_source` and
  `source.stablecoin_source` said CoinMarketCap. The actual fetch code
  (`tools/refresh_market_caps.py`, `COINGECKO_MARKETS_URL`) and
  `docs/PROVENANCE.md` both say CoinGecko. Corrected.

- **README** Project Structure tree named `.github/workflows/monitor.yml`;
  the actual file is `monitor-amendments.yml`.

### Added

#### Tests

- **`tests/test_update_from_iso.py`** — 89 tests. The only
  write-capable tool in the repository had no coverage before this
  release. Includes
  `TestSaveRegistry::test_save_registry_with_one_argument_no_longer_raises`,
  the regression guard for the `save_registry` fix above, plus
  coverage of the diff engine, change application, backup naming, and
  report formatting.

- Two tests in **`tests/test_export_parquet.py`** —
  `test_independent_three_decimal_currencies` and
  `test_top_three_by_peg_rate` — locking in the corrected values from
  section 8.4 of the v1.5.2 verification report.

- Full suite: **1,008 tests passing** (up from 917 at v1.5.2).

### Process

- Verification reports must be produced by running commands, not by
  filling in a template. The v1.5.2 report contained two claims that
  were never verified against the actual file. The correction and the
  two new lock-in tests prevent this class of error.

### Verified

- *To be filled in after release verification.*

---

## [1.5.2] — 2026-09-16

A patch release that adds a fourth consumption format and formalizes the
registry's data-layering discipline. No data changes — `iso4217.json` is
byte-identical to v1.5.1 except for `meta.version` and `meta.updated`.

### Added

#### Parquet export

- **`iso4217.parquet`** — a single typed, columnar, snappy-compressed
  Parquet file. 302 rows, 11 columns, ~15 KB. The eleven columns match
  the CSV export's names and order; the types differ where Parquet's
  type system allows it.

- **`tools/export_parquet.py`** — the generator. Same structure as
  `export_sql.py` and `export_csv.py`: `--check` mode, atomic writes,
  exit codes 0/1/2/3. One documented divergence: `--check` compares
  *logical content*, not bytes, because Parquet permits byte-different
  files with identical content.

- **`tests/test_export_parquet.py`** — 143 tests. Covers the schema,
  native types (`int8`, `bool`, `float64`), null semantics, metadata,
  determinism, sort order, the tampered-value / tampered-type /
  tampered-metadata failure modes of `--check`, and cross-checks
  against the CSV and SQL exports.

- **`docs/decisions/parquet-schema.md`** — ADR recording the schema
  decision, the three type differences from CSV, the null policy, the
  metadata contract, and the alternatives considered (Avro, Iceberg,
  no-export, CSV-compatible types).

#### Data layering

- **`docs/LAYERS.md`** — formal documentation of the three-layer model
  the registry follows: RAW (`iso4217.json`), CURATED (SQL, CSV, TSV,
  Parquet exports; wrapper copies; the CLI), and AGGREGATED (not yet
  implemented). States the rule — *a layer may only assume what the
  layer below guarantees* — and maps every artifact in the repository
  to its layer.

### Changed

- **README** gains a `Direct download (Parquet)` subsection documenting
  the three type differences from CSV and the footer metadata contract,
  plus a new "Why?" bullet for analytics teams and an updated Project
  Structure tree.

- **CONTRIBUTING**'s "after editing `iso4217.json`" step now regenerates
  the Parquet export alongside SQL, CSV, and the wrapper copies. The
  full regeneration sequence is four commands, not three.

### Fixed

- **`validate-json` CI job now installs pyarrow.** The parquet test file
  imports pyarrow at module level; `validate-json` runs the full test
  suite and did not have pyarrow in its install step, so collection
  failed. This was the sole cause of the failure on commits `bd54a16`
  through `3ba251a`.

### Tests

- Parquet export test suite: **143 tests** (new)
- Full repository: **917 tests passing** (up from 774 at v1.5.1)

### Verified

- `tools/export_parquet.py --check` exits 0 against the committed file.
- `pandas.read_parquet('iso4217.parquet')` returns a DataFrame of shape
  `(302, 11)` with native dtypes: `is_independent` is `bool`,
  `minor_units` is `int8`, `pegged_to` has 256 nulls, `peg_rate` has
  258 nulls (256 + MAD + KWD).
- DuckDB reads the file natively and evaluates
  `WHERE pegged_to IS NOT NULL` correctly — 46 pegged currencies.
- CI has a new `check-parquet-export` gate; the pipeline now has six
  top-level jobs plus the four-language wrapper matrix.

### Known limitations

The `agg` keyword in the pyarrow writer is not used; default row-group
and compression settings are taken as-is. At 302 rows this is correct —
multiple row groups are a scale optimization the file will never need.
If the registry grows past 100,000 rows, revisit.

---

## [1.5.1] — 2026-09-15

A patch release focused on documentation accuracy and verification
completeness. No data changes, no schema changes, no wrapper API
changes — the JSON, the SQL exports, and the CSV/TSV exports are
byte-identical to v1.5.0 except for the version string in headers.

Triggered by an external review of the v1.5.0 README that found nine
issues — five documentation gaps, three design questions, and one
cross-repo inconsistency. The five that were in scope for a patch are
addressed here; the rest are deferred to v1.6.0 and tracked in
`docs/decisions/v1.6.0-candidates.md`.

### Added

#### Documentation

- **`docs/PROVENANCE.md`** — sources by category, refresh cadence,
  what `tools/check_amendments.py` actually checks (detection only, not
  ingestion), how Wikipedia is used (secondary only, never sole source),
  a five-step audit procedure for any currency code, and five explicit
  known gaps. Answers the "where does this data come from?" question
  institutional readers ask before adopting.

- **`docs/decisions/withdrawn-codes.md`** — an ADR for the
  `<STEM>_<OLD>` synthetic identifier convention. The withdrawn Mexican
  peso entry `MXN_OLD` is 7 characters; ISO 4217 codes are 3 letters.
  The ADR records why the synthetic identifier exists, what alternatives
  were rejected, and the consequences for SQL column widths and wrapper
  length assumptions.

- **`docs/decisions/v1.6.0-candidates.md`** — deferred decisions that
  did not fit the v1.5.x line, starting with the `standard` field on
  every JSON entry and the potential consolidation of the three Mexican
  entries (`MXN`, `MXP`, `MXN_OLD`).

- **`docs/v1.5.1-verification.md`** — post-release verification of the
  three CLI checks that did not complete during v1.5.0's Phase 8, plus
  the results of the documentation-review follow-ups.

#### Tests

- **`TestV151Counts`** in `tests/test_iso_codes.py` — crypto count (7)
  and stablecoin count (6) guards. Tied to the README's new count
  descriptions; if either count changes, this fails until the README is
  updated to match.

- **`TestV151CodeLengths`** in `tests/test_iso_codes.py` — active codes
  are always exactly 3 characters; withdrawn codes are either 3 chars
  or match the `<STEM>_<SUFFIX>` convention documented in the ADR.

- **`test_numeric_maps_to_numeric_code`** in `tests/test_export_sql.py`
  — codifies the JSON field → SQL column mapping the README now
  documents. Every row's `numeric_code` appears in the rendered SQL.

- **`test_numeric_not_used_as_column_name`** in
  `tests/test_export_sql.py` — regression guard. The SQL column list
  must never use `numeric` as an identifier.

- Full suite: **768 → 774 tests passing.**

### Changed

#### Documentation

- **README** — five targeted edits:
  - Documents the `numeric` → `numeric_code` rename. The JSON field is
    `numeric`; the SQL and CSV column is `numeric_code`. The rename is
    deliberate (`numeric` is an ANSI SQL reserved word) but was only
    documented in a code comment. Now it is in the README.
  - Corrects the non-ISO count descriptions. The counts (7 crypto, 6
    stablecoin) are correct; the "excluding X" phrasing implied BTC,
    ETH, USDT, USDC, and DAI were excluded when they are included.
  - Shows the top-level JSON shape so readers can see where `status`
    comes from. It is derived by the exporters from which array an
    entry lives in; it is not a JSON field.
  - Reframes "Adopted By" as "Consumed By" with two subsections
    ("Within the QuantOS ecosystem" and "External adopters") plus a
    "How to adopt" section.
  - Adds the Tempus integration code example — the generated C array
    that the Tempus compiler links into every binary. Makes the
    ecosystem feel wired together instead of adjacent.

### Fixed

- **`wrappers/python/setup.py`** — the `build_py` override now copies
  `iso4217.json` and `schema.json` into the wheel. setuptools does not
  ship non-Python files in a wheel for a `py_modules` distribution,
  regardless of `MANIFEST.in` or `include_package_data`. The override
  was added in `d718d21` (post-v1.5.0 tag) and is included in v1.5.1.
  A wheel built from v1.5.1 resolves its data file at runtime; a wheel
  built from v1.5.0 does not.

- **CLI verification** — three checks that did not complete during
  v1.5.0's Phase 8 (8.4.4 CLI-vs-TSV byte comparison, 8.4.5 help
  output, 8.5 README-vs-CLI subcommand parity) now run and pass. The
  initial verification run reported FAIL for 8.4.5 and 8.5 due to a
  grep-pattern bug: argparse indents subcommands with 4 spaces, not 2.
  After fixing the pattern, all three checks pass.

### Deferred to v1.6.0

- **`standard` field on every JSON entry** — would make filtering
  "give me only ISO 4217 entries" a one-liner. Deferred because it is
  a schema addition, and v1.5.1 is a patch.

- **Consolidation of the three Mexican entries** (`MXN`, `MXP`,
  `MXN_OLD`) — all share numeric code 484. Two withdrawn entries for
  the same currency lineage is a data-quality wart. Consolidating
  requires deciding which form is canonical and updating the schema,
  wrappers, and tests accordingly. Deferred because it is a data
  change, not a documentation one.

- **Author name consolidation across the ecosystem** — Tempus uses
  "LASS," ISO 4217 uses "Le P'tit," LAS_Shell uses "slimissa."
  Deferred to a coordinated cross-repo update.

- **Publication to PyPI, npm, and crates.io** — the packages are
  installable from source and from locally built wheels but are not
  yet published to the public registries. Tracked as a v1.6.0
  milestone.

### Known limitations

The v1.5.0 tag ships a wheel that lacks `iso4217.json` and
`schema.json`. The `build_py` fix landed after the tag, in `d718d21`.
Users installing from a wheel built at the `v1.5.0` tag will get a CLI
that cannot resolve its data file. Users installing from the v1.5.1
tag or from `main` are unaffected. The v1.5.0 tag is not retroactively
modified — the fix is captured in v1.5.1.

Windows-specific CSV checks (Excel encoding, CR bytes, BOM policy) and
the LibreOffice European-locale check were not run on the verification
host (Ubuntu). They are documented as "not tested — deferred" in
`docs/v1.5.1-verification.md` and will be appended when a Windows
environment is available.

### Verified

- 774 tests passing (`pytest tests/ wrappers/python/tests/ -q`)
- `tools/validate.py`: 0 errors, 27 warnings
- `tools/export_sql.py --check`: exit 0
- `tools/export_csv.py --check`: exit 0
- All three wrapper copies byte-identical to `iso4217.json`
- CI green across all six top-level jobs plus the four-language matrix

---

## [1.5.0] — 2026-09-15

### Added

#### SQL export — four dialects
- **`iso4217.sql`** — ANSI SQL-92 portable export. Works on PostgreSQL, MySQL 8+, MariaDB 10.4+, SQLite 3.37+, SQL Server 2016+, Oracle 12c+, and IBM Db2.
- **`iso4217.postgresql.sql`** — PostgreSQL 12+ export, with a commented `INSERT ... ON CONFLICT (code) DO NOTHING` alternative for append-only imports.
- **`iso4217.mysql.sql`** — MySQL 8+ / MariaDB 10.4+ export using `ENGINE=InnoDB` and `utf8mb4`.
- **`iso4217.sqlite.sql`** — SQLite 3.37+ export using `STRICT` tables for real type enforcement.
- **`tools/export_sql.py`** — dialect-parameterized generator with `--dialect`, `--stdout`, and `--check` modes. Atomic writes; deterministic row ordering; exit codes 0/1/2/3 aligned with the rest of the toolchain.
- **`tests/test_export_sql.py`** — 154 tests covering row construction, escaping, per-dialect rendering, determinism, sort order, `--check` mode, CLI exit codes, and cross-checks against the committed SQL files.
- **Schema:** one `currencies` table with seven columns (`code`, `numeric_code`, `name`, `minor_units`, `symbol`, `entity`, `status`). `status` is `'active'` or `'withdrawn'`, CHECK-constrained. `code` is the primary key in every dialect.
- The SQL files intentionally **exclude** non-ISO instruments, peg information, and country relationships — they are a reference table for foreign keys, not a relational mirror of the JSON.

#### CSV / TSV export — four dialects
- **`iso4217.csv`** — RFC 4180 comma-separated, 11 columns.
- **`iso4217.excel.csv`** — Excel-compatible, UTF-8 BOM.
- **`iso4217.european.csv`** — semicolon-delimited for European Excel locales.
- **`iso4217.tsv`** — tab-separated for terminal, clipboard, and Google Sheets workflows.
- **`tools/export_csv.py`** — dialect-parameterized generator with the same `--check` / `--stdout` interface as `export_sql.py`. LF line endings in all four files; BOM only in the Excel dialect; quoting delegated to the Python standard library's `csv` module rather than hand-rolled.
- **`tests/test_export_csv.py`** — 266 tests covering quoting round-trip via `csv.reader`, per-dialect delimiters, BOM policy, LF enforcement, determinism, full-file data-integrity scans, and a cross-check that the seven shared columns match `iso4217.sqlite.sql` row for row.
- The CSV files intentionally **include** peg metadata (`is_independent`, `pegged_to`, `peg_type`, `peg_rate`) and intentionally **exclude** countries, central banks, and non-ISO instruments — they are for human analysis, not for FK constraints.

#### Command-line interface
- **`iso4217` console script** — eight subcommands: `lookup`, `list`, `minor`, `major`, `format`, `peg`, `info`, `validate`. Supports bare-argument shorthand (`iso4217 USD` ≡ `iso4217 lookup USD`) and reads codes from stdin via `-`.
- **Five output modes** — default human-readable; `--json` (single object or array); `--jsonl` (newline-delimited); `--tsv` / `--csv` (columns match the corresponding export byte for byte); and `--raw FIELD` for bare-value extraction. Machine modes are mutually exclusive with each other and with the human default; piped output never contains color.
- **`ISO4217_COLOR=never|auto|always`** — environment variable for color control. Precedence: environment variable wins over TTY detection. Colors are limited to three roles: bold code, status green/dim, peg type yellow/blue/magenta.
- **`--registry PATH`** — test-only escape hatch for running against an alternate registry file. Composes with `--raw` and the bare-argument shorthand.
- **`wrappers/python/tests/test_cli.py`** — 171 tests covering every subcommand, every output mode, every exit code, stdin via `-`, the `--registry` flag and its compositions, help output, and a cross-check that `list --active --tsv` matches the committed `iso4217.tsv` row for row.
- The CLI reuses the existing Python wrapper (`CurrencyRegistry`, `pegged_to`, `with_minor_units`, `issued_by`, `used_in`) for all lookups and filters — no duplicated query logic. A regression in the wrapper's basket-peg rule changes the CLI's behavior in the same commit; no drift is possible by construction.

### Changed

- **Python package version bumped from `1.0.0` to `1.1.0`.** The registry remains at `1.5.0`; the wrapper's version tracks its own API surface independently of the registry data version, so a wrapper-only release (e.g., a bug fix in `format()`) does not require a registry bump and vice versa.
- **CI now gates on three parallel export checks** — `check-sql-export`, `check-csv-export`, and `check-cli` run simultaneously and all three must pass before `validate-json` and `validate-wrappers` start. A stale flat-file artifact fails the build in under a minute rather than after the slower wrapper matrix completes.

### Schema

- **`is_independent` is now permitted on non-ISO entries.** The wrapper's `is_independent` default changed from `True` to `False` (see Fixed, below) to match the CSV export's conservative choice, and eleven non-ISO entries — BTC, ETH, XRP, SOL, BNB, ADA, DOGE, and the four metals XAU/XAG/XPT/XPD — now carry the field explicitly. The schema's `additionalProperties: false` on those definitions was not updated at the same time as the data, so the schema file is now extended to allow `is_independent` on every non-ISO category. Backward-compatible: an entry without the field is still valid, and consumers must treat absent as `False`.
- `schema.json`'s `$id` remains at its previous version. The schema version is independent of the registry version, and this change relaxes a constraint rather than adding or removing a required field.

### Fixed

- **`Currency.is_independent` in the Python wrapper now defaults to `False`** when the field is absent from the source JSON, matching the CSV export's conservative choice. Previously it defaulted to `True`, silently reporting currencies without an explicit `is_independent` field as "freely floating" — which contradicts the `pegged_to is not None` invariant that `tools/validate.py` enforces on the source data. The CLI's cross-check against `iso4217.tsv` surfaced this on its first full run.
- **`wrappers/python/setup.py` entry point corrected.** The previous declaration referenced a function (`iso4217:main_validate`) that was never written. The entry point now points at the real CLI entry (`iso4217_cli:main`).
- **Data-file packaging corrected.** `package_data` and `data_files` were both silently failing for this `py_modules`-based distribution: `package_data` only applies to directories that are Python packages, and `data_files` with an empty target installs to `sys.prefix` rather than to the module directory. Replaced with `include_package_data=True` plus a `MANIFEST.in` that ships `iso4217.json` and `schema.json` next to the installed modules.

### Tests

- SQL export test suite: **154 tests**
- CSV/TSV export test suite: **266 tests**
- CLI test suite: **171 tests**
- Full repository: **768 tests passing** (`pytest tests/ wrappers/python/tests/ -q`)

### Verified

- `tools/validate.py` runs clean: 0 errors, same warning count as v1.4.1.
- `tools/export_sql.py --check` and `tools/export_csv.py --check` both exit 0 against the committed artifacts.
- CI is green with **eight top-level jobs** plus the four-language wrapper matrix (`check-wrapper-sync`, `check-sql-export`, `check-csv-export`, `check-cli`, `validate-json`, `validate-wrappers` × 4 languages).
- The Python package installs cleanly in a fresh virtualenv; `iso4217 --version` prints the registry version (`1.5.0`), not the package version (`1.1.0`).
- The three deliverables — SQL, CSV/TSV, and CLI — derive from `iso4217.json` and regenerate from a single command sequence.

---

## [1.4.1] — 2026-09-14

### Fixed
- `tests/test_refresh_market_caps.py::TestParseArgs::test_defaults` hardcoded
  the developer's absolute path to `iso4217.json`. It now compares against the
  module's own `DEFAULT_REGISTRY_PATH` constant, so the test passes on any
  machine — developer laptop, CI runner, or container. This was the sole cause
  of the v1.4.0 CI failure.

### Data
- **USDP `market_cap_rank` corrected from 50 to 700.** CoinGecko's current
  rank for Pax Dollar is 700 (below the tool's default `--top-n 250` fetch
  window). The tool correctly warned that USDP wasn't in the response — it
  wasn't delisted or renamed, just ranked lower than expected. The v1.4.0
  CHANGELOG's "Top 10 stablecoins" phrasing was too strong for a coin that has
  since dropped out of the top 250 globally; the registry documents
  *significant* stablecoins, not exclusively top-10 ones.
- USDP's `note` field now records the rank and the tool's fetch-window
  limitation.

### Docs
- Documented the tool's `--top-n 250` default and its consequence: entries
  below that rank won't be refreshed automatically, and need manual
  reconciliation via CoinGecko's `/coins/{id}` endpoint. This was learned the
  hard way with USDP.
  
## [1.4.0] — 2026-09-14

### Added

#### Registry Data — Non-ISO Expansion
- **5 new cryptocurrencies**: XRP, SOL, BNB, ADA, DOGE (top 10 by market cap, excluding existing BTC and ETH)
- **3 new stablecoins**: USDP (Paxos), FRAX (Frax Finance, Hybrid peg), TUSD (TrueUSD)
- Cryptocurrency count: 2 → **7**
- Stablecoin count: 3 → **6**
- BUSD intentionally excluded (deprecated by Paxos Feb 2024)
- Market cap ranks reflect a snapshot on 2026-09-14
- BNB uses 18 minor units (BEP20 convention); BEP2 uses 8 — documented in the entry's note

### Tests
- Added 8 ground-truth tests to `tests/test_iso_codes.py::TestNonISO`
- Test suite: 91 → **99 Python tests**

### Verified
- `tools/validate.py` runs clean: 0 errors, 27 expected warnings
- All existing tests still pass
- Wrapper copies synced (Go, Rust)
- Schema unchanged (new entries fit existing schema)

---

## [1.3.0] — 2026-08-26

### Added

#### Registry Data — Complete Withdrawn Coverage
- **111 new withdrawn currencies**, bringing the total from 24 to **135 of 135** — every withdrawn or obsolete ISO 4217 alphabetic code now present
- Revaluation chains covered:
  - **Brazilian**: BRB → BRC → BRN → BRE → BRR (5 currencies)
  - **Yugoslav**: YUD → YUN → YUR → YUO → YUG → YUM → CSD (7 currencies)
  - **Angolan**: AOK → AON → AOR (3 currencies)
  - **Bulgarian**: BGJ → BGK → BGL (3 currencies)
  - **Argentine**: ARM → ARL → ARP → ARA (4 currencies)
  - **Czechoslovak**: CSK, CSJ (2 currencies)
  - **Zimbabwean**: RHD → ZWC → ZWD → ZWN → ZWR → ZWL (6 currencies)
  - **Zairean**: ZRZ → ZRN (2 currencies)
  - **Peruvian**: PEH → PEI (3 currencies)
  - **Asian**: BUK, DDM, LAJ, TJR, TMM, TPE, VNC, YDD (8 currencies)
  - **African**: 37 currencies (BOP, CHC, CSD, GEK, GHC, GHP, GQE, HRD, LTT, LUC, LUL, LVR, MGF, MKN, MLF, MTP, MVQ, MZE, MZM, MRO, PLZ, SDD, SDP, SLL, SRG, STD, UAK, UGS, UGW, UYN, UYP, VEB, VEF, ZAL, ZMK, plus others)
  - **Eurozone micro-states**: ADF, ADP, MCF, SML, VAL
  - **Special settlement**: XEU (ECU), XFO (Gold Franc), XFU (UIC Franc), XRE (RINET)
- Every withdrawn currency includes `withdrawn_date`, `replaced_by`, and `conversion_rate` with documented sources

#### Tools
- Added `tools/generate_v1_3_skeletons.py` — reads `tools/parse_source.py`'s curated withdrawn-code set, diffs against the registry, and generates skeleton JSON entries with `TODO` placeholders. Auto-fills Eurozone rates (locked by ECB).
- Archived skeleton generators to `tools/archive/` (v1.2 and v1.3) — historical tools, job complete

#### Validation
- **Added revaluation chain detection**: same-entity numeric reuse (e.g., Brazil's 076 shared by BRB/BRC/BRN/BRE) now emits a warning, not an error. Different-entity reuse still errors.
- **Fixed entity mismatches**: SUR/RUR unified as Russia; RHD/ZWD/ZWC unified as Zimbabwe; CSD/YUM unified as Yugoslavia; micro-states aligned to parent currencies
- **Numeric code collision detection** now handles shared codes across revaluation chains correctly

#### CI/CD
- **CI matrix testing**: `validate-wrappers` split into 4 parallel jobs (Python, JavaScript, Go, Rust) with `fail-fast: false` — per-language visibility, faster runs
- **Automated ISO amendment monitoring**: `tools/check_amendments.py` + `.github/workflows/monitor-amendments.yml` — weekly check for new SIX Group amendments, creates GitHub Issue when detected

### Tests
- `tests/test_iso_codes.py` unchanged (already covered withdrawn currencies)
- Test suite remains **91 Python tests + 29 JavaScript tests + 60 Go tests + 42 Rust tests**

### Verified
- **135/135 withdrawn ISO 4217 currencies** — complete coverage against `tools/parse_source.py::WITHDRAWN_ISO_CODES`
- All 111 new currencies validated: numeric codes, replacement codes, conversion rates all correct
- `tools/validate.py` runs clean: 0 errors, 27 expected warnings
- Wrapper copies synced

---

## [1.2.0] — 2026-08-17

### Added

#### Registry Data — Full ISO 4217 Coverage

- **106 new active currencies**, bringing the total from 61 to **167 of 167** — every currently-assigned ISO 4217 alphabetic code is now present
- New currencies grouped by region:

| Region | Currencies |
|--------|------------|
| CFA franc zones (EUR-pegged) | XOF, XAF, XPF |
| Southern Africa | BWP, LSL, NAD, SZL (all ZAR-pegged), ZMW, ZWG, MWK, MZN |
| East Africa | AOA, BIF, CDF, DJF (USD-pegged), ERN (USD-pegged), ETB, KMF (EUR-pegged), MGA, MRU, MUR, RWF, SCR, SDG, SLE, SOS, SSP, STN (EUR-pegged), TZS, UGX |
| West Africa | CVE (EUR-pegged), GMD, GNF, LRD |
| Caribbean | ANG, AWG, BBD (USD-pegged), BMD, BSD, BZD, CUC, CUP, DOP, GYD, HTG, JMD, KYD, SVC, TTD, XCD |
| Central Asia | AMD, AZN, KGS, TJS, TMT, UZS |
| Middle East | AFN, IRR, SYP, YER |
| Balkan/Eastern Europe | ALL, BAM (EUR-pegged), BYN, GEL, MDL, MKD (EUR-pegged), RSD |
| Latin America | BOB, GTQ, HNL, NIO, PAB (USD 1:1), PYG, SRD, UYU, VES |
| Asia-Pacific | BND (SGD 1:1), BTN (INR 1:1), FJD, KHR, KPW, LAK, MMK, MNT, MOP (HKD-pegged), MVR, NPR (INR-pegged), PGK, SBD, TOP, VUV, WST |
| Territories (GBP 1:1) | FKP, GIP, SHP |
| Fund codes / indexation units | BOV, CHE, CHW, CLF, COU, MXV, USN, USS, UYI, UYW, VED |

- Every new currency includes: numeric code, official name, minor units, symbol, entity, central bank, peg information (where applicable), and country relationships with issuing/adopting/territory classification
- Pegged currency count increased from 11 to **46** (of 167 active)
- Fund codes include explanatory `note` fields clarifying they are indexation or settlement units, not circulating currencies

#### Tools

- Added `tools/generate_v1_2_skeletons.py` — reads `tools/parse_source.py`'s curated 167-code ground-truth set, diffs against the current registry, and generates skeleton JSON entries with `TODO` placeholders for manual research. Recognizes fund codes and adds explanatory notes.

### Changed

#### Validation

- **Removed `--allow-partial` from CI** — the registry now exceeds the 150-currency minimum, so the flag is no longer needed. Coverage enforcement is now unconditional.
- **Removed the tripwire test** (`test_current_registry_active_count_is_below_min_active_currencies`) — it was designed to fail when full coverage shipped, and has served its purpose.
- `tools/validate.py` now runs without any suppression flags

#### Documentation

- Rewrote README's `## Coverage` section: "61 of ~180, here's what's missing" → "**167 of 167 — complete ISO 4217 active coverage**"
- Updated Registry Contents table: Active ISO 4217 currencies now reads **167 of 167**
- Updated Quick Start download URL to point at the v1.2.0 tag
- Updated Adopted By section: Tempus now consumes via `make update-registry`

### Verified

- **167/167 active ISO 4217 currencies** — complete coverage against `tools/parse_source.py::ACTIVE_ISO_CODES`
- All 106 new currencies validated: numeric codes are 3-digit strings, codes match `^[A-Z]{3}$`, minor units in range 0–18
- All peg targets validated: every `pegged_to` reference resolves to an existing active currency
- No duplicate active codes, no duplicate withdrawn codes, no active/withdrawn overlap except the documented MXN/MXN_OLD 484 case
- `tools/validate.py` runs clean **without** `--allow-partial`: 0 errors, 2 expected warnings (numeric code reuse, unusual minor units on fund codes)
- Full test suite: **91 tests passing** (92 minus the removed tripwire test)
- Wrapper copies (Go, Rust) synced and byte-identical to root

---

## [1.1.0] — 2026-08-16

### Schema

- Added `peg_type` field to active currencies (`"single"` / `"basket"` / `"undisclosed"` / `null`), so consumers can tell a parseable ISO code apart from a free-text peg description without guessing
- Added conditional validation: `peg_type` is required whenever `pegged_to` is set; `pegged_to` must match `^[A-Z]{3}$` when `peg_type` is `"single"`, and must *not* match that pattern when `peg_type` is `"basket"` or `"undisclosed"`
- Added `iso_status` field to `special_purpose` entries (`"iso_code"` / `"market_convention"` / `"obsolete_iso"`), required
- Added optional `numeric` field to `special_purpose` entries

### Data

- Tagged all 11 pegged active currencies with `peg_type`: AED, SAR, QAR, HKD, JOD, BHD, OMR, DKK, BGN → `"single"`; MAD → `"basket"`; KWD → `"undisclosed"`
- Fixed XDR being flagged as a false-positive non-ISO code — it's a genuine ISO 4217 code (numeric 960), now tagged `iso_status: "iso_code"`
- Added XUA (ADB Unit of Account, numeric 965) and XSU (SUCRE, numeric 994) — both genuine ISO 4217 fund/unit-of-account codes previously missing from `special_purpose`
- Tagged CNH with `iso_status: "market_convention"` (it is not an ISO 4217 code)
- Documented the MXN/MXN_OLD numeric code 484 reuse in MXN_OLD's note (Mexico reused the numeric code after the 1993 revaluation)

### Wrappers (Python, JavaScript, Go, Rust)

- Added `peg_type` property/field to `Currency` in all four wrappers
- **Fixed a real bug**: `pegged_to()` / `peggedTo()` / `PeggedTo()` used substring matching and incorrectly returned MAD for `pegged_to("USD")` queries, because `"USD"` is a substring of MAD's basket description `"EUR+USD basket"`. Fixed to exact-match gated on `peg_type == "single"` in all four wrappers
- Standardized `to_minor()` / `toMinor()` / `ToMinor()` rounding to half-away-from-zero in all four wrappers — fixed Python (was using banker's rounding via `round()`) and JavaScript (`Math.round()` rounds half toward `+Infinity`, not away from zero, so `Math.round(-2.5)` was `-2` instead of `-3`)
- Fixed Go and Rust `Format()` / `format()` to add thousands separators, matching Python/JS (`"$1,000.00"` instead of `"$1000.00"`)
- Added `market_cap_rank` and `peg_mechanism` properties to the Python wrapper's `Currency` class, closing a cross-language API gap (Go/Rust/JS already had them)

### Tools

- Added `tools/sync_wrappers.py` — copies root `iso4217.json` into `wrappers/go/iso4217.json` and `wrappers/rust/iso4217.json`, which are embedded at compile time (`go:embed`, `include_str!`) and don't update automatically when root changes
- Added active-currency-count plausibility check to `tools/validate.py`: `MIN_ACTIVE_CURRENCIES = 150` (error), `WARN_ACTIVE_CURRENCIES = 100` (warning), independent of each other — a registry with 5 active currencies previously passed validation with no complaint
- Added `--allow-partial` CLI flag to downgrade the count-below-minimum error to a warning, for intentional partial releases (e.g. v1.0.0's 61 currencies)
- Added numeric-code collision detection: uniqueness enforced within active-only and withdrawn-only; active/withdrawn overlap allowed but warned on, since it can be legitimate historical reuse (MXN/MXN_OLD)
- Fixed a validator false positive on XDR — it was flagged for missing a "not an ISO code" disclaimer despite being a genuine ISO 4217 code; the check now reads the `iso_status` field instead of guessing from note text
- Fixed a related pre-existing text-matching bug affecting CNH: the disclaimer check looked for the substring `"not an iso"`, which didn't match CNH's actual note text `"Not an official ISO 4217 code"`

### Tests

- Added `wrappers/javascript/test.js` — 29 zero-dependency tests. The JavaScript wrapper previously had no tests at all; CI only ran a 4-line inline smoke script that didn't assert anything beyond "didn't throw"
- Ported `tests/cross_language_consistency.json` to JavaScript, Go, and Rust — previously only the Python wrapper's test suite exercised these vectors, so a behavioral divergence between wrappers (including the two bugs above) could ship undetected
- Added rounding-boundary test vectors (USD `100.005 → 10001`, JPY `2.5 → 3` and `0.5 → 1`, plus negative-boundary cases) to catch banker's-rounding-vs-half-away-from-zero divergence specifically
- Added 8 tests for the active-count plausibility check to `tests/test_validate_schema.py`
- Added `peg_type` assertions across all 11 pegged currencies to `tests/test_iso_codes.py`, plus a cross-cutting regression test
- Test suite: 92 Python tests (up from 83 at v1.0.0), plus 29 new JavaScript tests

### CI/CD

- Added `check-wrapper-sync` job: runs `sync_wrappers.py`, then `git diff --exit-code` on the two wrapper JSON copies, fails the build if they've drifted from root
- Expanded CI path filters to include wrapper source files (`wrappers/**/*.py`, `.js`, `.go`, `.rs`, `Cargo.toml`, `go.mod`, `package.json`) — previously, editing wrapper source code alone did not trigger CI at all
- `validate-wrappers` job now depends on `check-wrapper-sync`, so wrapper tests never run against a known-stale JSON copy
- JavaScript CI step now runs `npm test` (the real 29-test suite) instead of the inline smoke script
- CI now runs `validate.py --allow-partial`, temporarily, until v1.2.0 ships full ISO 4217 coverage

### Docs

- Added a `## Coverage` section to README.md: honestly states 61/~180 active-currency scope, lists what's included in v1.0.0 and what's targeted for v1.1.0 (grouped by region), and removes prior "canonical"/"complete" claims that overstated coverage
- Documented the MXN/MXN_OLD numeric code reuse in README's schema section
- Updated CONTRIBUTING.md to document the `tools/sync_wrappers.py` step as required before committing changes to `iso4217.json`

---

## [1.0.0] — 2026-07-29

### Added

#### Registry Data

- 61 actively traded ISO 4217 currencies with full metadata
- 24 withdrawn currencies with replacement information and conversion rates
- 12 non-ISO currencies across four categories:
  - Cryptocurrencies: BTC, ETH
  - Stablecoins: USDT, USDC, DAI
  - Commodities: XAU, XAG, XPT, XPD
  - Special purpose: XDR, CNH
- Rich currency entries including: central bank names, peg information (anchor, rate, band, date), country relationships with classification (issuing, adopting, territory, parallel, local_issue), market convention notes for currencies where ISO and market practice diverge (e.g., IDR)
- Eurozone irrevocable conversion rates for all pre-EUR currencies
- ISO 4217 amendment tracking (amendment 179)

#### Schema

- JSON Schema (`schema.json`) for structural validation of the registry
- Support for active currencies, withdrawn currencies, and four non-ISO categories
- Strict validation: required fields, pattern constraints, type checking

#### Wrappers

- **Python** (`wrappers/python/`): `Currency` + `CurrencyRegistry` classes, full type hints, minor/major conversion, formatting, peg filtering, singleton convenience functions
- **JavaScript** (`wrappers/javascript/`): `Currency` + `CurrencyRegistry` classes, TypeScript declarations, Map-based O(1) lookups
- **Rust** (`wrappers/rust/`): `Currency` + `CurrencyRegistry` structs, compile-time embedded via `include_str!()`, zero runtime I/O
- **Go** (`wrappers/go/`): `Currency` + `CurrencyRegistry` structs, compile-time embedded via `//go:embed`, singleton via `sync.Once`

#### Tools

- `tools/validate.py` — 6-layer validation: schema, meta, source, integrity, cross-reference, statistical anomaly detection
- `tools/update_from_iso.py` — semi-automated fetch/diff/apply workflow against SWIFT, Wikipedia, and SIX Group
- `tools/parse_source.py` — Wikipedia table classifier with active/withdrawn/non-ISO classification

#### Tests

- `tests/cross_language_consistency.json` — shared test vectors
- `tests/test_iso_codes.py` — 52 ground-truth assertions in 7 test classes
- `tests/test_validate_schema.py` — 17 schema and integrity tests
- `tests/test_wrappers.py` — 14 cross-wrapper consistency tests

#### Documentation & CI/CD

- Root README, wrapper READMEs, CONTRIBUTING, LICENSE
- GitHub Actions workflow for validation

### Verified

- All active currency codes against ISO 4217 amendment 179
- Schema validation: 0 errors, 0 warnings
- Test suite: 83/83 passing
- Rust crate: `cargo test` passing, `cargo clippy` clean
- Go module: `go test ./...` passing, `go vet ./...` clean

---

### Planned for v1.6.0

The v1.5.0 roadmap's three deliverables — SQL dump export, CSV export, and CLI tool for registry queries — all shipped in v1.5.0. Remaining planned work:

- Additional language wrappers (C#, Java, Swift, Kotlin, Ruby)
- ISO 3166 country registry — a companion registry that makes the 200+ country codes already referenced in `currencies[].countries[]` resolvable without a second lookup table

---

## Version History

| Version | Date | Active | Withdrawn | Non-ISO | Wrappers | Exports |
|---------|------|--------|-----------|---------|----------|---------|
| **1.5.0** | **2026-09-15** | **167** | **135** | **21** | Python, JS, Rust, Go | **SQL, CSV/TSV, CLI** |
| 1.4.1 | 2026-09-14 | 167 | 135 | 21 | Python, JS, Rust, Go | — |
| 1.4.0 | 2026-09-14 | 167 | 135 | 21 | Python, JS, Rust, Go | — |
| 1.3.0 | 2026-08-26 | 167 | 135 | 13 | Python, JS, Rust, Go | — |
| 1.2.0 | 2026-08-17 | 167 | 24 | 13 | Python, JS, Rust, Go | — |
| 1.1.0 | 2026-08-16 | 61 | 24 | 13 | Python, JS, Rust, Go | — |
| 1.0.0 | 2026-07-29 | 61 | 24 | 12 | Python, JS, Rust, Go | — |