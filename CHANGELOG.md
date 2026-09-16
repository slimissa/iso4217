# Changelog

All notable changes to the ISO 4217 Currency Registry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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