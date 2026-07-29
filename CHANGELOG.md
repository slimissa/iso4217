```markdown
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

### Planned for v1.1.0
- Expand to full ~160 active ISO 4217 currencies (currently 61 actively traded)
- Add remaining ~100 withdrawn currencies
- Cross-language consistency tests for JavaScript, Rust, and Go wrappers
- CI/CD matrix testing across all four wrapper languages
- Automated ISO amendment monitoring

### Planned for v1.2.0
- SQL dump export for direct database import
- CSV export
- Additional language wrappers (C#, Java, Swift, Kotlin, Ruby)
- CLI tool for registry queries (`iso4217 USD --to-minor 100.50`)

---

## Version History

| Version | Date | Active | Withdrawn | Non-ISO | Wrappers |
|---------|------|--------|-----------|---------|----------|
| 1.0.0 | 2026-07-29 | 61 | 24 | 12 | Python, JS, Rust, Go |
```