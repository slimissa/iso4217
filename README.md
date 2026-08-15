# ISO 4217 Currency Registry

**A versioned, machine-readable registry of ISO 4217 currency codes — 61 actively traded currencies covering all G20 economies and major trading pairs, expanding toward full ISO 4217 coverage.**

One JSON file. Zero dependencies. Works with every language.

> **Coverage status:** this registry currently covers 61 of the ~180 currencies active under ISO 4217. It is not yet a complete implementation of the standard. See [Coverage](#coverage) below for what's included and what's planned for v1.1.0.

[![Validate](https://github.com/slimissa/iso4217/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/slimissa/iso4217/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Schema Version](https://img.shields.io/badge/schema-1.0.0-green.svg)](./schema.json)
[![Registry Version](https://img.shields.io/badge/registry-1.0.0-orange.svg)](./iso4217.json)

---

## Why?

Every quant library, trading system, payment processor, and fintech app maintains its own currency list. They're often outdated, inconsistent, or just wrong. Some hardcode a few majors with no versioning. Some use a CSV from a 2015 Wikipedia scrape with no schema. Some are missing minor units or peg data entirely.

**This project provides one versioned, schema-validated JSON file that any tool can depend on — instead of every project hand-rolling and hand-maintaining its own.** It currently covers the currencies most quant, trading, and payment systems actually touch day to day (G20 economies, major and minor trading pairs); it does not yet cover the full ISO 4217 list. See [Coverage](#coverage).

- **Tempus** uses it for compile-time `Price<USD>` validation
- **Python quant libraries** use it for currency-aware calculations
- **Go trading systems** use it for foreign key constraints
- **Rust finance crates** use it for compile-time currency verification
- **JavaScript fintech apps** use it for payment processing

The registry is language-agnostic by design. The JSON is the contract.

---

## Quick Start

### Direct download

```bash
curl -O https://raw.githubusercontent.com/slimissa/iso4217/main/iso4217.json
```

### Python

```python
from iso4217 import currency

usd = currency("USD")
print(usd.to_minor(100.50))   # 10050 (cents)
print(usd.format(100.50))     # "$100.50"
```

```bash
pip install iso4217-registry
```

### JavaScript

```javascript
const { CurrencyRegistry } = require('iso4217-registry');
const registry = new CurrencyRegistry();

const jpy = registry.active('JPY');
console.log(jpy.toMinor(500));  // 500
```

```bash
npm install iso4217-registry
```

### Rust

```rust
use iso4217::CurrencyRegistry;

let registry = CurrencyRegistry::load().unwrap();
let usd = registry.active("USD").unwrap();
assert_eq!(usd.to_minor(100.50), 10050);
```

```bash
cargo add iso4217
```

### Go

```go
import iso4217 "github.com/slimissa/iso4217-go"

registry, _ := iso4217.Load()
usd := registry.Active("USD")
fmt.Println(usd.ToMinor(100.50))  // 10050
```

```bash
go get github.com/slimissa/iso4217-go
```

---

## Registry Contents

| Category | Count | Description |
|----------|-------|-------------|
| Active ISO currencies | 61 of ~180 | Currently circulating currencies with full metadata — see [Coverage](#coverage) |
| Withdrawn ISO currencies | 24 | Historical currencies with replacement info and conversion rates |
| Cryptocurrencies | 2 | Major cryptocurrencies by market capitalization |
| Stablecoins | 3 | Major stablecoins with peg mechanisms |
| Commodities | 4 | Precious metals with ISO-compatible codes |
| Special purpose | 2 | IMF units, offshore variants |

---

## Coverage

**v1.0.0 includes 61 of the ~180 currencies currently active under ISO 4217.** This is not full ISO 4217 coverage. It is the set of currencies most quant, trading, and payment tooling actually needs first: all G20 economies, the major and minor FX trading pairs, and the most commonly Gulf-pegged and Nordic/Eastern European currencies.

**Included in v1.0.0:** all 61 active codes currently in `iso4217.json` — USD, EUR, JPY, GBP, and the rest of the G20/major-pair set, plus commonly-pegged Gulf currencies (AED, SAR, QAR, BHD, OMR, KWD, JOD) and non-Euro European currencies (CZK, PLN, HUF, RON, DKK, ISK, BGN).

**Not yet included, targeted for v1.1.0** (106 currencies, grouped by region):

| Region | Currencies |
|---|---|
| CFA franc zones (Central & West Africa) | XAF, XOF |
| Other Sub-Saharan Africa | AOA, BIF, BWP, CDF, CVE, DJF, ERN, ETB, GMD, GNF, KMF, LRD, LSL, MGA, MRU, MUR, MWK, MZN, NAD, RWF, SCR, SDG, SLE, SOS, SSP, SZL, TZS, UGX, ZMW, ZWG |
| Central Asia / Caucasus | ALL, AMD, AZN, BYN, GEL, KGS, TJS, TMT, UZS |
| Caribbean | ANG, AWG, BBD, BMD, BSD, BZD, CUC, CUP, DOP, GYD, HTG, JMD, KYD, SVC, TTD, XCD |
| Middle East / South Asia | AFN, BTN, IRR, MVR, NPR, SYP, YER |
| Southeast Asia / Pacific | BND, FJD, KHR, KPW, LAK, MMK, MNT, MOP, TOP, VUV, WST, XPF |
| Pacific / Atlantic territories | FKP, GIP, PGK, SBD, SHP |
| Latin America | BOB, BOV, GTQ, HNL, NIO, PAB, PYG, SRD, UYI, UYU, UYW, VES |
| Europe (non-Euro) | BAM, MDL, MKD, RSD |
| IMF / settlement-only units (no public circulation) | CHE, CHW, CLF, COU, MXV, USN, USS, VED |
| Other | STN |

This list is derived from a curated cross-check against the ISO 4217 active-code set (`tools/parse_source.py::ACTIVE_ISO_CODES`), not a live source. It has not yet been re-verified against SWIFT/SIX Group source data for v1.1.0 — treat it as a work-in-progress target list, not a commitment to exact scope or timing.

If you need a currency from the v1.1.0 list today, open an issue or a PR against `iso4217.json` — see [Contributing](#contributing).

### What's in a currency entry

```json
{
  "code": "USD",
  "numeric": "840",
  "name": "US Dollar",
  "minor_units": 2,
  "symbol": "$",
  "entity": "United States",
  "central_bank": "Federal Reserve System",
  "pegged_to": null,
  "is_independent": true,
  "countries": [
    { "code": "US", "name": "United States", "relationship": "issuing" },
    { "code": "EC", "name": "Ecuador", "relationship": "adopting" },
    { "code": "PA", "name": "Panama", "relationship": "adopting" }
  ]
}
```

Every active currency includes:
- **ISO 4217** alphabetic and numeric codes. Numeric codes are unique within active currencies but may overlap with withdrawn codes due to historical reuse (e.g., MXN/MXN_OLD share 484, since Mexico reused the numeric code after the 1993 revaluation). **Do not use numeric code as a unique key across active + withdrawn** — use the alphabetic `code` for that instead. `tools/validate.py` enforces uniqueness within each of active-only and withdrawn-only, and warns (without failing) on any active/withdrawn overlap.
- **Minor units** — the number of decimal places (0 for JPY, 2 for USD, 3 for KWD, 8 for BTC)
- **Peg information** — anchor currency, rate, band, and establishment date
- **Central bank** — official name of the monetary authority
- **Country relationships** — every country/territory with its relationship to the currency (issuing, adopting, territory, parallel, local_issue)
- **Market convention notes** — where ISO and market practice diverge (e.g., IDR)

Withdrawn currencies include withdrawal dates, replacement codes, and official conversion rates — including all Eurozone irrevocable fixing rates.

---

## Wrappers

Each wrapper is idiomatic to its language while maintaining identical behavior across all four:

| Language | Package | Import |
|----------|---------|--------|
| Python | `pip install iso4217-registry` | `from iso4217 import CurrencyRegistry` |
| JavaScript | `npm install iso4217-registry` | `const { CurrencyRegistry } = require('iso4217-registry')` |
| Rust | `cargo add iso4217` | `use iso4217::CurrencyRegistry;` |
| Go | `go get github.com/slimissa/iso4217-go` | `import iso4217 "github.com/slimissa/iso4217-go"` |

### Consistent API across languages

| Operation | Python | JavaScript | Rust | Go |
|-----------|--------|------------|------|-----|
| Load registry | `CurrencyRegistry()` | `new CurrencyRegistry()` | `CurrencyRegistry::load()` | `iso4217.Load()` |
| Look up currency | `.active("USD")` | `.active("USD")` | `.active("USD")` | `.Active("USD")` |
| Get minor units | `.minor_units` | `.minorUnits` | `.minor_units` | `.MinorUnits` |
| Convert to minor | `.to_minor(100.50)` | `.toMinor(100.50)` | `.to_minor(100.50)` | `.ToMinor(100.50)` |
| Format with symbol | `.format(100.50)` | `.format(100.50)` | `.format(100.50)` | `.Format(100.50)` |
| Filter pegged to USD | `.pegged_to("USD")` | `.peggedTo("USD")` | `.pegged_to("USD")` | `.PeggedTo("USD")` |

---

## Validation

The registry is validated through a multi-layer defense:

| Layer | What It Checks | Tool |
|-------|---------------|------|
| **Schema** | JSON structure, types, required fields | `tools/validate.py` + `schema.json` |
| **Integrity** | Required fields, value ranges, format patterns | `tools/validate.py` |
| **Business logic** | Peg consistency, minor unit conventions, conversion rates | `tools/validate.py` |
| **Cross-reference** | No duplicate codes, valid peg targets, no ISO/non-ISO overlap | `tools/validate.py` |
| **Ground truth** | Historical facts — Eurozone rates, numeric codes, peg relationships | `tests/test_iso_codes.py` |
| **Cross-language** | Identical behavior across all four wrappers | `tests/cross_language_consistency.json` |

```bash
# Run all validations
python3 tools/validate.py

# Run the full test suite (92 tests)
python3 -m pytest tests/ -v
```

---

## Project Structure

```
iso4217/
├── iso4217.json              # The registry — single source of truth
├── schema.json               # JSON Schema for validation
├── README.md                 # This file
├── LICENSE                   # Apache 2.0
├── CHANGELOG.md              # Version history
├── CONTRIBUTING.md           # How to contribute
├── .gitignore
├── wrappers/
│   ├── python/               # pip install iso4217-registry
│   ├── javascript/           # npm install iso4217-registry
│   ├── rust/                 # cargo add iso4217
│   └── go/                   # go get github.com/slimissa/iso4217-go
├── tests/
│   ├── cross_language_consistency.json
│   ├── test_iso_codes.py
│   ├── test_validate_schema.py
│   └── test_wrappers.py
├── tools/
│   ├── validate.py           # 6-layer validation
│   ├── update_from_iso.py    # Fetch + diff + apply pipeline
│   └── parse_source.py       # Wikipedia table parser
└── .github/
    ├── workflows/
    │   └── validate.yml      # CI on every push
    └── ISSUE_TEMPLATE/
        └── currency_update.md
```

---

## Versioning

The registry follows [Semantic Versioning](https://semver.org/):
- **Major**: Breaking schema changes (removed or renamed required fields)
- **Minor**: New currencies added, or new optional fields added (backward-compatible)
- **Patch**: Data corrections

The current version is always in `iso4217.json` → `meta.version`.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines on data corrections, new currencies, wrapper ports, and tooling improvements.

**Quick correction workflow:**
1. Edit `iso4217.json`
2. Run `python3 tools/validate.py` — must pass with 0 errors
3. Run `python3 -m pytest tests/ -v` — all tests must pass
4. Submit a PR with your source cited

---

## Adopted By

| Project | How It Uses This Registry |
|---------|--------------------------|
| **[Tempus](https://github.com/slimissa/Tempus)** | Compile-time `Price<USD>` validation — the compiler loads this registry to verify currency codes, minor units, and conversion logic |

*Using this registry in your project? Open a PR to add your name here.*

---

## License

Apache 2.0 — use it anywhere, no attribution required. The currency data in this registry is factual information. The compilation, schema, tooling, and wrappers are licensed works.

---

## Author

**Le P'tit** — [github.com/slimissa](https://github.com/slimissa)