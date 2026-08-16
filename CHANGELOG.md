# Changelog

All notable changes to the ISO 4217 Currency Registry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

#### Python Wrapper (`wrappers/python/`)
- `Currency` class with full property access and conversion methods
- `CurrencyRegistry` class with lookup, filtering, and summary statistics
- Minor/major unit conversion (`to_minor`, `from_minor`)
- Formatting with currency symbol
- Peg information access (anchor, rate, band, date)
- Country relationship queries (issuing, adopting countries)
- Filtering: pegged_to, independent, with_minor_units, issued_by, used_in
- Singleton convenience functions: `currency()`, `active()`, `pegged_to()`, `all_active()`
- Smart file discovery for `iso4217.json` (module directory → project root → cwd)
- Full type hints (mypy strict compatible)
- `setup.py` for PyPI distribution
- Comprehensive README with API reference

#### JavaScript Wrapper (`wrappers/javascript/`)
- `Currency` class with all properties in camelCase convention
- `CurrencyRegistry` class with Map-based O(1) lookups
- Identical API surface to Python wrapper (adapted to JavaScript idioms)
- TypeScript declarations (`index.d.ts`) with full JSDoc
- `package.json` for npm distribution
- Comprehensive README with API reference and cross-wrapper comparison table

#### Rust Crate (`wrappers/rust/`)
- `Currency` struct with all fields and conversion methods
- `CurrencyRegistry` struct with HashMap-based lookups
- Compile-time embedding via `include_str!()` — zero runtime file I/O
- `RegistrySummary` struct for statistics
- Serde-based JSON deserialization
- Comprehensive test suite (30+ tests)
- `Cargo.toml` for crates.io distribution
- Comprehensive README with API reference

#### Go Module (`wrappers/go/`)
- `Currency` struct with pointer types for optional fields
- `CurrencyRegistry` with singleton pattern via `sync.Once`
- Compile-time embedding via `//go:embed` — zero runtime file I/O
- `RegistrySummary` struct for statistics
- Standard library only — zero dependencies beyond `encoding/json`
- Comprehensive test suite (40+ tests including benchmarks)
- `go.mod` for module distribution
- Comprehensive README with API reference

#### Tools
- `tools/validate.py` — 6-layer validation: schema, meta, source, integrity, cross-reference, statistical anomaly detection
- `tools/update_from_iso.py` — semi-automated workflow for fetching source data (SWIFT, Wikipedia, SIX Group), diffing against current registry, and applying changes with human review
- `tools/parse_source.py` — Wikipedia table parser with active/withdrawn/non-ISO classification using ground-truth code sets

#### Tests
- `tests/cross_language_consistency.json` — 11 currencies with conversion, formatting, and property test vectors; lookup, filter, and summary contract tests
- `tests/test_iso_codes.py` — 52 ground-truth assertions organized into 7 test classes (MinorUnits, Pegs, Independence, Withdrawn, NumericCodes, NonISO, Countries)
- `tests/test_validate_schema.py` — 17 schema and integrity validation tests
- `tests/test_wrappers.py` — 14 cross-wrapper consistency tests using the shared test vectors

#### Documentation
- Root `README.md` with project overview, quick start, and schema documentation
- Wrapper-specific READMEs for Python, JavaScript, Rust, and Go
- `CONTRIBUTING.md` with guidelines for data corrections, new currencies, wrappers, and tools
- `CHANGELOG.md` (this file)
- `LICENSE` (Apache 2.0)

#### CI/CD
- GitHub Actions workflow for validation on every push and PR
- Structured error codes for machine-parsable output

### Verified

- All active currency codes against ISO 4217 amendment 179
- All numeric codes cross-referenced with SWIFT public table
- All minor unit counts verified against central bank specifications where available
- All Eurozone conversion rates verified against ECB irrevocable fixing rates
- All peg rates verified against central bank announcements
- Schema validation: 0 errors, 0 warnings
- Test suite: 83/83 passing
- Python wrapper: mypy strict mode clean
- Rust crate: `cargo test` passing, `cargo clippy` clean
- Go module: `go test ./...` passing, `go vet ./...` clean

---

## [Unreleased]

_(no changes yet)_

---

## [1.1.0] — 2026-08-15

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
- CI now runs `validate.py --allow-partial`, temporarily, until v1.1.0 ships full ISO 4217 coverage

### Docs
- Added a `## Coverage` section to README.md: honestly states 61/~180 active-currency scope, lists what's included in v1.0.0 and what's targeted for v1.1.0 (grouped by region), and removes prior "canonical"/"complete" claims that overstated coverage
- Documented the MXN/MXN_OLD numeric code reuse in README's schema section
- Updated CONTRIBUTING.md to document the `tools/sync_wrappers.py` step as required before committing changes to `iso4217.json`

### Planned for v1.2.0
- Expand to full ~160 active ISO 4217 currencies (currently 61 actively traded;
  106 known-missing codes identified via `tools/parse_source.py`'s ground-truth set)
- Add remaining ~100 withdrawn currencies
- CI/CD matrix testing across all four wrapper languages
- Automated ISO amendment monitoring

### Planned for v1.3.0
- SQL dump export for direct database import
- CSV export
- Additional language wrappers (C#, Java, Swift, Kotlin, Ruby)
- CLI tool for registry queries (`iso4217 USD --to-minor 100.50`)

---

## Version History

| Version | Date | Active | Withdrawn | Non-ISO | Wrappers |
|---------|------|--------|-----------|---------|----------|
| 1.1.0 | 2026-08-15 | 61 | 24 | 13 | Python, JS, Rust, Go |
| 1.0.0 | 2026-07-29 | 61 | 24 | 12 | Python, JS, Rust, Go |