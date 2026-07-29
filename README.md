# ISO 4217 Currency Registry

**A canonical, versioned, machine-readable registry of ISO 4217 currency codes.**

One JSON file. Zero dependencies. Works with every language.

[![Validate](https://github.com/slimissa/iso4217/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/slimissa/iso4217/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Schema Version](https://img.shields.io/badge/schema-1.0.0-green.svg)](./schema.json)
[![Registry Version](https://img.shields.io/badge/registry-1.0.0-orange.svg)](./iso4217.json)

---

## Why?

Every quant library, trading system, payment processor, and fintech app maintains its own currency list. They're often outdated, incomplete, or just wrong. Some hardcode a few majors. Some use a CSV from a 2015 Wikipedia scrape. Some are missing minor units. Some are missing entire currencies. None are canonical.

**This project provides a single source of truth that any tool can depend on.**

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
| Active ISO currencies | 61 | Currently circulating currencies with full metadata |
| Withdrawn ISO currencies | 24 | Historical currencies with replacement info and conversion rates |
| Cryptocurrencies | 2 | Major cryptocurrencies by market capitalization |
| Stablecoins | 3 | Major stablecoins with peg mechanisms |
| Commodities | 4 | Precious metals with ISO-compatible codes |
| Special purpose | 2 | IMF units, offshore variants |

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
- **ISO 4217** alphabetic and numeric codes
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

# Run the full test suite (83 tests)
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
- **Major**: Currencies added or removed
- **Minor**: New optional fields added (backward-compatible)
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