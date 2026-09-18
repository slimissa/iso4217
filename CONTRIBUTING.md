# Contributing to the ISO 4217 Currency Registry

Thank you for helping keep this registry accurate, complete, and useful. This document explains how to contribute — whether you're fixing a typo, adding a currency, porting a wrapper to a new language, or improving the tooling.

---

## Code of Conduct

- Be respectful. Assume good faith.
- Cite your sources. Every currency data change must reference an authoritative source.
- One logical change per pull request. Don't bundle a currency correction with a wrapper rewrite.
- Keep discussions focused on data accuracy and code quality.

---

## What to Contribute

### 1. Currency Data (`iso4217.json`)

**Corrections to existing currencies:**

If you find incorrect data — wrong minor units, missing countries, incorrect peg rates — open an issue with the title `Correction: USD minor_units` and provide:

- The exact field(s) that need changing
- The correct value(s)
- A link to an official source:
  - [SIX Group amendment summary](https://www.currency-iso.org/en/home/amendments.html)
  - Central bank official website
  - SWIFT ISO 4217 public table
  - Official government publication

**Adding new active currencies:**

Active ISO 4217 currencies must be listed in the current ISO 4217 standard. Provide the ISO amendment number or official source confirming the addition.

**Adding withdrawn currencies:**

Withdrawn currencies must have been valid ISO 4217 codes. Include:
- `withdrawn_date`: When it ceased to be legal tender
- `replaced_by`: The ISO 4217 code of the replacement
- `conversion_rate`: The official conversion rate (units of old currency per 1 unit of replacement)

**Adding non-ISO currencies:**

Non-ISO currencies are accepted under these guidelines:

| Category | Inclusion Threshold | Required Fields |
|----------|-------------------|-----------------|
| Cryptocurrencies | Top 10 by market cap (CoinGecko) | `type: "cryptocurrency"`, `market_cap_rank`, `introduced`, `is_independent`, `note` |
| Stablecoins | Top 10 by market cap | `type: "stablecoin"`, `pegged_to`, `peg_mechanism`, `is_independent`, `note` |
| Commodities | Widely traded with X-prefix convention | `type: "commodity"`, `is_independent`, `note` explaining it's not a currency |
| Special purpose | IMF units, offshore variants | `type` explaining the category, `iso_status`, `note` explaining ISO relationship |

All non-ISO currencies must have a `note` field clearly stating they are not ISO 4217 codes.

### 2. Schema (`schema.json`)

Schema changes must be backward-compatible. Adding new optional fields is fine. Removing or renaming required fields requires a major version bump and coordination across all wrappers. Discuss schema changes in an issue before submitting a PR.

### 3. Wrappers (Python, JavaScript, Rust, Go)

**Bug fixes and performance improvements** to existing wrappers are welcome. Each wrapper's API is idiomatic to its language but must maintain behavioral consistency with the other wrappers. All wrappers must pass the cross-language consistency tests in `tests/cross_language_consistency.json`.

**New language wrappers** are encouraged. A new wrapper must:

1. Load `iso4217.json` (embedded at compile time preferred, file discovery at runtime acceptable)
2. Implement the full API surface: `Currency` with all properties, `CurrencyRegistry` with all lookup/filter/summary methods
3. Pass all assertions in `tests/cross_language_consistency.json`
4. Include a `README.md` following the same structure as existing wrappers
5. Include comprehensive tests

Open an issue with the title `New wrapper: [Language]` before starting work to coordinate and avoid duplication.

### 4. Command-Line Interface (`wrappers/python/iso4217_cli.py`)

The CLI is a presentation layer over the Python wrapper. It must never re-implement query logic — every lookup and filter delegates to `CurrencyRegistry`. If you add a filter to the CLI, add the corresponding method to the wrapper first, and cross-check the two in `wrappers/python/tests/test_cli.py`.

Changes to the CLI are welcome under these constraints:

1. Every subcommand's `--help` must continue to show a worked example and the four-line exit-code table.
2. Machine output modes (`--json`, `--jsonl`, `--tsv`, `--csv`, `--raw`) must remain mutually exclusive; passing two is a usage error (exit 2).
3. No ANSI escapes may leak into piped output or machine modes. Tests assert on the absence of `\x1b[` — do not weaken this.
4. The four exit codes are part of the public contract:
   - **0** — success
   - **1** — code not found in the registry
   - **2** — usage error (bad flag, missing argument, mutually exclusive flags)
   - **3** — data error (registry file missing or invalid)
5. Adding a new subcommand requires a matching test class, an `_add_epilog` call for its `--help`, and an entry in `SUBCOMMANDS`.

### 5. Export Generators (`tools/export_sql.py`, `tools/export_csv.py`)

The export generators are the mechanism by which the JSON registry becomes usable in databases and spreadsheets. Both follow identical discipline:

- **Deterministic** — the same registry produces byte-identical output on every run. Nothing derived from the wall clock, the filesystem, or the environment may appear in the output.
- **Committed artifacts** — the four SQL files and the four CSV/TSV files live in the repo root, and CI verifies they match what the generator would produce. `--check` mode is the enforcement mechanism.
- **Atomic writes** — output is written to a temporary sibling and renamed into place. A crash mid-write never leaves partial output.
- **Aligned exit codes** — 0 success; 1 mismatch; 2 fatal error; 3 missing files.

Any change to a generator must keep `--check` passing against the committed files. If a change alters the output format, regenerate the artifacts in the same commit and explain the diff in the PR description.

### 6. Tools (`tools/validate.py`, `tools/sync_wrappers.py`, `tools/refresh_market_caps.py`, `tools/check_amendments.py`, `tools/update_from_iso.py`, `tools/parse_source.py`)

Improvements to any of the tools are welcome. The validation tool in particular should catch every class of data error before it reaches users. New validation rules must:

1. Be documented in `tools/validate.py`'s module docstring
2. Have a corresponding test in `tests/test_validate_schema.py`
3. Fire on a synthetic failure fixture, not just on the current registry

### 7. Documentation

Fixes to READMEs, API reference corrections, additional examples, and typo fixes are always appreciated. The project's README is a contract: if it says a command produces a specific output, that command must produce that output on the current registry.

---

## Development Setup

```bash
git clone https://github.com/slimissa/iso4217.git
cd "iso4217 registry"

# Python tooling — a virtual environment is required on Debian/Ubuntu
# and recommended everywhere (PEP 668 refuses system-wide pip installs).
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Install the wrapper editable, with its dev extras
pip install -e "wrappers/python[dev]"

# The dev extras include: pytest, pytest-cov, mypy, jsonschema, pyyaml
# After this, the `iso4217` command is available on your PATH.

# JavaScript wrapper
cd wrappers/javascript
npm install
cd ../..

# Rust wrapper
cd wrappers/rust
cargo build
cd ../..

# Go wrapper
cd wrappers/go
go build ./...
cd ../..
```

The `pyyaml` dependency is required to run the workflow verification snippets in this document. It is installed automatically by `pip install -e "wrappers/python[dev]"`; installing it manually is only necessary if you skip the `[dev]` extra.

---

## Making Changes

### For Data Changes (`iso4217.json`)

Every derived artifact must be regenerated in the same commit. CI rejects PRs where any derived file is stale — the three `check-*` export jobs run in parallel and all must pass before the slower wrapper matrix starts.

1. Edit `iso4217.json`
2. Run `python3 tools/validate.py` — must pass with 0 errors
3. Regenerate every derived artifact:
   ```bash
   python3 tools/export_sql.py       # four SQL files
   python3 tools/export_csv.py       # four CSV/TSV files
   python3 tools/export_parquet.py   # one Parquet file
   python3 tools/sync_wrappers.py    # Go and Rust embedded copies
   ```
   `sync_wrappers.py` copies the root `iso4217.json` into `wrappers/go/iso4217.json` and `wrappers/rust/iso4217.json`, which are compiled into those wrappers at build time (`go:embed`, `include_str!`) and do **not** update on their own. Skipping this step leaves Go and Rust silently running against stale data. CI will fail the build if these copies aren't in sync with root, but running it locally first saves you a failed PR.
4. Run the full test suite:
   ```bash
   python3 -m pytest tests/ wrappers/python/tests/ -q
   ```
   Expect **768 tests passing** as of v1.5.0. The count changes when tests are added or removed — a PR that changes the count should update the number referenced in this document and in `CHANGELOG.md`.
5. Confirm the CLI resolves against the updated registry:
   ```bash
   pytest wrappers/python/tests/test_cli.py -q
   ```
6. Update `CHANGELOG.md` under `[Unreleased]`
7. If adding currencies, update `source.last_amendment_applied` and `source.last_verified`
8. Commit `iso4217.json`, the eight flat-file artifacts (`iso4217.sql`, `iso4217.postgresql.sql`, `iso4217.mysql.sql`, `iso4217.sqlite.sql`, `iso4217.csv`, `iso4217.excel.csv`, `iso4217.european.csv`, `iso4217.tsv`), and the regenerated `wrappers/go/iso4217.json` and `wrappers/rust/iso4217.json` in the same commit
9. Commit with a descriptive message: `Add AFN, ALL, AMD to active currencies (ISO amendment 179)`

Any tool that writes to `iso4217.json` must be listed in the write-capable tools table in `docs/LAYERS.md`. Adding a new write path without adding it to that table is a review blocker.

### For Wrapper Changes

1. Make your changes to the wrapper code
2. Run the wrapper's test suite
3. Run the cross-language consistency tests: `python3 -m pytest tests/test_wrappers.py -v`
4. Update the wrapper's README if the API surface changed
5. If the change affects all wrappers (new API method, changed behavior), open an issue to coordinate updates across languages
6. If the change affects the Python wrapper's `Currency` class, run `pytest wrappers/python/tests/test_cli.py -q` to confirm the CLI still resolves — the CLI is a thin presentation layer over the wrapper, and a wrapper regression will surface there first

### For CLI Changes

1. Make your changes to `wrappers/python/iso4217_cli.py`
2. Run the CLI test suite: `pytest wrappers/python/tests/test_cli.py -q`
3. Verify the four smoke tests from the CI job pass locally:
   ```bash
   iso4217 lookup USD --json | python3 -c "import sys, json; d = json.load(sys.stdin); assert d['code'] == 'USD', d"
   iso4217 validate USD XYZ; [ $? -eq 1 ] && echo "exit 1 OK"
   iso4217 list --pegged-to USD --raw code | wc -l
   ```
4. If you added a subcommand, update `SUBCOMMANDS`, add an `_add_epilog` call for its `--help`, add a test class in `test_cli.py`, and update the README's Command-line interface section
5. If you added an output mode, update `_add_output_flags` and add an assertion to `TestOutputFormats::test_mutually_exclusive_flags_exit_2`

### For Export Generator Changes

1. Make your changes to `tools/export_sql.py` or `tools/export_csv.py`
2. Run the generator's test suite: `pytest tests/test_export_sql.py -q` or `pytest tests/test_export_csv.py -q`
3. Regenerate the corresponding artifacts and confirm `--check` passes:
   ```bash
   python3 tools/export_sql.py && python3 tools/export_sql.py --check
   python3 tools/export_csv.py && python3 tools/export_csv.py --check
   ```
4. If the change alters the output format, update the generator's module docstring, the `DIALECT_FILES` / `DIALECT_LABELS` constants if applicable, and any related tests
5. Commit the generator, its tests, and the regenerated artifacts together

### For Tooling Changes

1. Make your changes
2. Run the full test suite: `python3 -m pytest tests/ wrappers/python/tests/ -q`
3. Run the validator on the registry: `python3 tools/validate.py`
4. Add tests for new functionality

---

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b correction/usd-minor-units`
3. Make your changes
4. Run every gate before submitting:
   ```bash
   # Validator — 0 errors expected
   python3 tools/validate.py

   # Full test suite
   python3 -m pytest tests/ wrappers/python/tests/ -q

   # Export drift checks
   python3 tools/export_sql.py --check
   python3 tools/export_csv.py --check
   ```
   **PRs with failing tests, stale export artifacts, or `wrappers/go/iso4217.json` / `wrappers/rust/iso4217.json` out of sync with root will not be reviewed.**
5. Update `CHANGELOG.md` under `[Unreleased]`
6. Submit a PR with a clear description:
   - What changed
   - Why it changed (link to source/issue)
   - How you verified the change (test output, validation output)
   - If the change touches `iso4217.json`, list every regenerated artifact in the PR description

---

## Commit Messages

Use descriptive, imperative-mood commit messages:

```
Add BGN to active currencies with EUR peg
Fix KWD minor_units from 2 to 3
Correct DEM conversion rate to match irrevocable EUR fixing rate
Add missing issuing country for CHF
Fix Python wrapper format() thousands separator for 0-decimal currencies
Add --registry flag to iso4217 CLI
Fix CLI --raw flag placement in argv normalization
Regenerate SQL and CSV exports after adding AFN
```

Conventional Commit prefixes (`feat:`, `fix:`, `ci:`, `test:`, `docs:`, `chore:`) are used in the repository's history for the larger changes but are not required. What matters is that the message is clear, imperative, and specific enough to be found later by `git log --grep`.

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Change | Version Bump |
|--------|-------------|
| Breaking schema changes (removed/renamed required fields) | Major (`1.0.0` → `2.0.0`) |
| New currencies added or new optional fields | Minor (`1.0.0` → `1.1.0`) |
| Data corrections (no structural changes) | Patch (`1.0.0` → `1.0.1`) |
| New export format (SQL, CSV, CLI, or a new dialect) | Minor for the registry |
| Wrapper bug fixes | Patch for that wrapper |
| New wrapper language | Minor for the project |
| CLI-only change (new subcommand, new output mode) | Minor for the Python package |

The **registry data version** is in `iso4217.json` → `meta.version`. Each **wrapper's version** is independent and lives in its own package manifest (`wrappers/python/setup.py`, `wrappers/javascript/package.json`, `wrappers/rust/Cargo.toml`, `wrappers/go/go.mod`). A wrapper-only release does not require a registry bump and vice versa — the two versions track different things.

As of v1.5.0: registry is `1.5.0`, Python package is `1.1.0`.

---

## Review Priorities

When reviewing PRs, maintainers will check, in order:

1. **Data accuracy** — is every currency fact backed by an authoritative source?
2. **Schema compliance** — does `iso4217.json` validate against `schema.json`?
3. **Test coverage** — do all 768 tests pass? Are new tests added for new functionality?
4. **Cross-wrapper consistency** — does the change maintain API parity across wrappers?
5. **Export drift** — do `export_sql.py --check` and `export_csv.py --check` both exit 0?
6. **CLI behavior** — do all 171 CLI tests pass? Do the three CI smoke tests pass locally?
7. **Documentation** — is `CHANGELOG.md` updated? Is the README accurate if the public surface changed?

A PR that touches `iso4217.json` but doesn't regenerate the eight flat-file artifacts will fail CI at the `check-sql-export`, `check-csv-export`, or `check-cli` job. A PR that touches the Python wrapper but doesn't update the CLI's behavior when relevant will fail at `check-cli`. These gates exist so a maintainer can review the logic without also having to verify that nothing else broke.

---

## The CI Job Map

Six top-level jobs run on every push and PR. Understanding what each one protects makes it obvious when a change needs more than a code edit:

| Job | What it protects | What makes it fail |
|-----|------------------|---------------------|
| `check-wrapper-sync` | Go and Rust wrappers running against stale data | Editing root `iso4217.json` without running `sync_wrappers.py` |
| `check-sql-export` | The four committed SQL files staying in sync with the registry | Editing `iso4217.json` without running `export_sql.py` |
| `check-csv-export` | The four committed CSV/TSV files staying in sync with the registry | Editing `iso4217.json` without running `export_csv.py` |
| `check-cli` | The CLI resolving correctly against the installed wrapper | A wrapper regression, a broken `setup.py` entry point, or a CLI test failure |
| `validate-json` | The registry's structural and business-logic integrity | Any validation error from `tools/validate.py` or a pytest failure |
| `validate-wrappers` (×4) | Cross-language API parity | Any wrapper diverging from the cross-language consistency vectors |

The first four jobs run in parallel. All four must pass before `validate-json` and `validate-wrappers` start.

---

## Getting Help

- **Questions?** Open an issue with the `question` label
- **Not sure if something is correct?** Open an issue with the `discussion` label
- **Found a bug but can't fix it?** Open an issue with the `bug` label and as much detail as possible
- **Not sure whether a change belongs in the registry, a wrapper, a generator, or the CLI?** Open an issue first — it's cheaper than a rejected PR

---

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License, the same as this project. All currency data in this registry is factual information and not subject to copyright, but the compilation, schema, tooling, and wrappers are licensed works.