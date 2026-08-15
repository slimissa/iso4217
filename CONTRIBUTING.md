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
| Cryptocurrencies | Top 10 by market cap (CoinMarketCap) | `type: "cryptocurrency"`, `market_cap_rank`, `introduced`, `note` |
| Stablecoins | Top 5 by market cap | `type: "stablecoin"`, `pegged_to`, `peg_mechanism`, `note` |
| Commodities | Widely traded with X-prefix convention | `type: "commodity"`, `note` explaining it's not a currency |
| Special purpose | IMF units, offshore variants | `type` explaining the category, `note` explaining ISO relationship |

All non-ISO currencies must have a `note` field clearly stating they are not ISO 4217 codes.

### 2. Schema (`schema.json`)

Schema changes must be backward-compatible. Adding new optional fields is fine. Removing or renaming required fields requires a major version bump and coordination across all wrappers. Discuss schema changes in an issue before submitting a PR.

### 3. Wrappers

**Bug fixes and performance improvements** to existing wrappers (Python, JavaScript, Rust, Go) are welcome. Each wrapper's API is idiomatic to its language but must maintain behavioral consistency with the other wrappers. All wrappers must pass the cross-language consistency tests in `tests/cross_language_consistency.json`.

**New language wrappers** are encouraged. A new wrapper must:

1. Load `iso4217.json` (embedded at compile time preferred, file discovery at runtime acceptable)
2. Implement the full API surface: `Currency` with all properties, `CurrencyRegistry` with all lookup/filter/summary methods
3. Pass all assertions in `tests/cross_language_consistency.json`
4. Include a `README.md` following the same structure as existing wrappers
5. Include comprehensive tests

Open an issue with the title `New wrapper: [Language]` before starting work to coordinate and avoid duplication.

### 4. Tools

Improvements to `tools/validate.py`, `tools/update_from_iso.py`, and `tools/parse_source.py` are welcome. The validation tool in particular should catch every class of data error before it reaches users.

### 5. Documentation

Fixes to READMEs, API reference corrections, additional examples, and typo fixes are always appreciated.

---

## Development Setup

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217

# Python tooling
pip install -r tools/requirements.txt  # if it exists, or:
pip install jsonschema pytest

# JavaScript wrapper
cd wrappers/javascript
npm install

# Rust wrapper
cd wrappers/rust
cargo build

# Go wrapper
cd wrappers/go
go build ./...
```

---

## Making Changes

### For Data Changes

1. Edit `iso4217.json`
2. Run `python3 tools/validate.py` — must pass with 0 errors
3. Run `python3 -m pytest tests/ -v` — all 83+ tests must pass
4. Run `python3 tools/sync_wrappers.py` — copies the root `iso4217.json` into `wrappers/go/iso4217.json` and `wrappers/rust/iso4217.json`, which are compiled into those wrappers at build time (`go:embed`, `include_str!`) and do **not** update on their own. Skipping this step leaves Go and Rust silently running against stale data. CI will fail the build if these copies aren't in sync with root, but running it locally first saves you a failed PR.
5. Update `CHANGELOG.md` under `[Unreleased]`
6. If adding currencies, update `source.last_amendment_applied` and `source.last_verified`
7. Commit `iso4217.json` together with the regenerated `wrappers/go/iso4217.json` and `wrappers/rust/iso4217.json` in the same commit
8. Commit with a descriptive message: `Add AFN, ALL, AMD to active currencies (ISO amendment 179)`

### For Wrapper Changes

1. Make your changes to the wrapper code
2. Run the wrapper's test suite
3. Run the cross-language consistency tests: `python3 -m pytest tests/test_wrappers.py -v`
4. Update the wrapper's README if the API surface changed
5. If the change affects all wrappers (new API method, changed behavior), open an issue to coordinate updates across languages

### For Tooling Changes

1. Make your changes
2. Run the full test suite: `python3 -m pytest tests/ -v`
3. Run the validator on the registry: `python3 tools/validate.py`
4. Add tests for new functionality

---

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b correction/usd-minor-units`
3. Make your changes
4. Run the full test suite, the validator, and (if you touched `iso4217.json`) `tools/sync_wrappers.py` — **PRs with failing tests, or with `wrappers/go/iso4217.json` / `wrappers/rust/iso4217.json` out of sync with root, will not be reviewed**
5. Update `CHANGELOG.md` under `[Unreleased]`
6. Submit a PR with a clear description:
   - What changed
   - Why it changed (link to source/issue)
   - How you verified the change (test output, validation output)

---

## Commit Messages

Use descriptive, imperative-mood commit messages:

```
Add BGN to active currencies with EUR peg
Fix KWD minor_units from 2 to 3
Correct DEM conversion rate to match irrevocable EUR fixing rate
Add missing issuing country for CHF
Fix Python wrapper format() thousands separator for 0-decimal currencies
```

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Change | Version Bump |
|--------|-------------|
| Breaking schema changes (removed/renamed required fields) | Major (`1.0.0` → `2.0.0`) |
| New currencies added or new optional fields | Minor (`1.0.0` → `1.1.0`) |
| Data corrections (no structural changes) | Patch (`1.0.0` → `1.0.1`) |
| Wrapper bug fixes | Patch for that wrapper |
| New wrapper language | Minor for the project |

The registry data version is in `iso4217.json` → `meta.version`. Each wrapper has its own version in its package manifest.

---

## Review Priorities

When reviewing PRs, maintainers will check:

1. **Data accuracy**: Is every currency fact backed by an authoritative source?
2. **Schema compliance**: Does `iso4217.json` validate against `schema.json`?
3. **Test coverage**: Do all 83+ tests pass? Are new tests added for new functionality?
4. **Cross-wrapper consistency**: Does the change maintain API parity across wrappers?
5. **Documentation**: Are changelogs updated? Are READMEs accurate?

---

## Getting Help

- **Questions?** Open an issue with the `question` label
- **Not sure if something is correct?** Open an issue with the `discussion` label
- **Found a bug but can't fix it?** Open an issue with the `bug` label and as much detail as possible

---

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License, the same as this project. All currency data in this registry is factual information and not subject to copyright, but the compilation, schema, tooling, and wrappers are licensed works.