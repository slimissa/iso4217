# ISO 4217 Currency Registry

**A canonical, versioned, machine-readable registry of ISO 4217 currency codes — 167 active currencies covering the complete ISO 4217 standard, including all G20 economies, major and minor trading pairs, and every currently-assigned code.**

One JSON file. Zero dependencies. Every language, database, spreadsheet, and shell.

[![Validate](https://github.com/slimissa/iso4217/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/slimissa/iso4217/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Schema Version](https://img.shields.io/badge/schema-1.1.0-green.svg)](./schema.json)
[![Registry Version](https://img.shields.io/badge/registry-1.5.0-orange.svg)](./iso4217.json)
---

## Why?

Every quant library, trading system, payment processor, and fintech app maintains its own currency list. They're often outdated, inconsistent, or just wrong. Some hardcode a few majors with no versioning. Some use a CSV from a 2015 Wikipedia scrape with no schema. Some are missing minor units or peg data entirely.

**This project provides one versioned, schema-validated JSON file that any tool can depend on — instead of every project hand-rolling and hand-maintaining its own.** It covers the complete ISO 4217 active-currency list, with full metadata: central banks, peg information, country relationships, and market convention notes.

- **Tempus** uses it for compile-time `Price<CCY>` validation
- **Python quant libraries** use it for currency-aware calculations
- **Go trading systems** use it for foreign key constraints
- **Rust finance crates** use it for compile-time currency verification
- **JavaScript fintech apps** use it for payment processing
- **Database teams** get a ready-made seed file — one command, no JSON parsing.
- **Analysts, engineers, and researchers** each get a zero-friction entry point — no JSON parser, no driver, no setup.
- **Shell users, CI pipelines, and scripts** get the same registry with one command — no Python, no CSV, no JSON, no jq.
- **Analytics teams** get a typed, columnar file that every dataframe library and SQL engine reads natively — no casting, no null sentinels.

The registry is language-agnostic by design. The JSON is the contract. The SQL, CSV, and CLI exports are three ways to consume it without writing a parser.

---

## Quick Start

### Direct download

```bash
curl -O https://raw.githubusercontent.com/slimissa/iso4217/v1.5.0/iso4217.json
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

### Direct download (SQL)

Four files, one per dialect, each self-contained and idempotent — safe to run twice.

| File | Target |
|------|--------|
| [`iso4217.sql`](./iso4217.sql) | ANSI SQL-92 — portable default; works on PostgreSQL, MySQL 8+, MariaDB 10.4+, SQLite 3.37+, SQL Server 2016+, Oracle 12c+, IBM Db2 |
| [`iso4217.postgresql.sql`](./iso4217.postgresql.sql) | PostgreSQL 12+ — includes a commented `INSERT ... ON CONFLICT (code) DO NOTHING` alternative for append-only imports |
| [`iso4217.mysql.sql`](./iso4217.mysql.sql) | MySQL 8+ / MariaDB 10.4+ — `ENGINE=InnoDB`, `utf8mb4` |
| [`iso4217.sqlite.sql`](./iso4217.sqlite.sql) | SQLite 3.37+ — `STRICT` tables for real type enforcement |

Import in one line:

```bash
psql -f iso4217.postgresql.sql            # PostgreSQL
mysql < iso4217.mysql.sql                 # MySQL / MariaDB
sqlite3 registry.db < iso4217.sqlite.sql  # SQLite
psql -f iso4217.sql                       # any SQL-92 engine
```

**What's in them:** one `currencies` table, seven columns (`code`, `numeric_code`, `name`, `minor_units`, `symbol`, `entity`, `status`), one `INSERT` per active and withdrawn ISO 4217 code. `status` is `'active'` or `'withdrawn'`, enforced by a CHECK constraint. `code` is the primary key. The table is FK-ready — add `FOREIGN KEY (currency) REFERENCES currencies(code)` to any transaction table and start joining.

**What's intentionally absent:** pegs, countries, central banks, withdrawn-date metadata, and non-ISO instruments (crypto, stablecoins, commodities). The SQL export is a reference table for foreign keys, not a relational mirror of the JSON. If you need those fields, read [`iso4217.json`](./iso4217.json) directly — the SQL is the wrong tool for the job, by design.

### Direct download (CSV / TSV)

Four files, one per audience. No BOM except where Excel needs it; LF line endings everywhere; headers always present.

| File | Audience |
|------|----------|
| [`iso4217.csv`](./iso4217.csv) | Universal — every CSV parser on every platform |
| [`iso4217.excel.csv`](./iso4217.excel.csv) | Excel on Windows — UTF-8 BOM so symbols render without an encoding prompt |
| [`iso4217.european.csv`](./iso4217.european.csv) | European Excel locales — semicolon-delimited so FR/DE/ES/IT open it without an import dialog |
| [`iso4217.tsv`](./iso4217.tsv) | Terminal, clipboard, Google Sheets, SQL clients — tab-separated |

Load in one line:

```python
# Python — pandas
import pandas as pd
df = pd.read_csv('iso4217.csv')

# Python — standard library
import csv
with open('iso4217.csv', encoding='utf-8', newline='') as f:
    for row in csv.DictReader(f):
        ...
```

```javascript
// JavaScript — d3
d3.csv('iso4217.csv').then(rows => { /* ... */ });
```

```go
// Go — encoding/csv
f, _ := os.Open("iso4217.csv")
r := csv.NewReader(f)
records, _ := r.ReadAll()
```

```rust
// Rust — csv crate
let mut rdr = csv::Reader::from_path("iso4217.csv")?;
for result in rdr.records() { /* ... */ }
```

**Eleven columns** — SQL's seven plus four peg columns: `is_independent`, `pegged_to`, `peg_type`, `peg_rate`. SQL stays minimal because it's for foreign keys; CSV earns the peg metadata because it's for human analysis. The first seven column names are identical to the SQL export's, so joining the two is a straight comparison on `code`.

**No comment header.** The four files start with the column-name row — a leading comment block would break `pandas.read_csv` without `skiprows` and violate RFC 4180. Version matching is derived from `meta.updated` in [`iso4217.json`](./iso4217.json), not from anything inside the CSV.

### Direct download (Parquet)

One Parquet file, columnar, typed, compressed. The analytics format.

| File | Consumer |
|------|----------|
| [`iso4217.parquet`](./iso4217.parquet) | pandas, Polars, DuckDB, Spark, every warehouse loader |

```python
# Python - pandas
import pandas as pd
df = pd.read_parquet('iso4217.parquet')
```

```python
# Python - DuckDB
import duckdb
duckdb.query("SELECT * FROM 'iso4217.parquet' WHERE is_independent")
```

```python
# Python - Polars
import polars as pl
df = pl.read_parquet('iso4217.parquet')
```

```scala
// Spark
val df = spark.read.parquet("iso4217.parquet")
```

**Three differences from the CSV export.** The column names are identical, but three types differ because Parquet has a type system that CSV does not:

- **`minor_units` is a native integer** (`int8`), not the string `"2"`. A query like `WHERE minor_units = 3` works without casting.
- **`is_independent` is a native boolean**, not the strings `'true'`/`'false'`. A filter like `WHERE is_independent` works directly.
- **`pegged_to`, `peg_type`, `peg_rate` use `null`** for "not applicable", not empty strings. `WHERE pegged_to IS NOT NULL` correctly returns only pegged currencies.

**Footer metadata.** The Parquet file carries three keys in its footer: `iso4217.version`, `iso4217.updated`, and `iso4217.amendment`. A consumer who receives only the `.parquet` file can tell which registry version produced it without opening the JSON.

The full schema rationale is in [`docs/decisions/parquet-schema.md`](./docs/decisions/parquet-schema.md).

### Command-line interface

`pip install iso4217-registry` also provides an `iso4217` command. Eight subcommands, all read-only, all offline:

```bash
iso4217 lookup USD                   # all fields for one currency
iso4217 list --pegged-to USD         # filter across the registry
iso4217 minor 100.50 USD             # major → minor units    (→ 10050)
iso4217 major 10050 USD              # minor → major units    (→ 100.5)
iso4217 format 1000 USD              # symbol + separators    (→ $1,000.00)
iso4217 peg AED                      # peg details only
iso4217 info                         # registry metadata
iso4217 validate USD EUR JPY         # exit 0 if all exist, 1 otherwise
```

Every command supports four machine-readable modes:

- `--json` — one object (single lookup, peg, info) or an array (list, multi-lookup)
- `--jsonl` — newline-delimited JSON, one object per line
- `--tsv` / `--csv` — columns match `iso4217.tsv` and `iso4217.csv` byte for byte
- `--raw FIELD` — bare value only, one per line for lists

Pipe-friendly by design:

```bash
# Every currency pegged to USD, formatted as "$100.00"
iso4217 list --pegged-to USD --raw code | xargs -I{} iso4217 format 100 {}

# Branch on "not in the registry" vs. "you typed the command wrong"
if ! iso4217 validate "$USER_INPUT" 2>/dev/null; then
    case $? in
        1) echo "unknown code: $USER_INPUT" ;;
        2) echo "usage error" ;;
    esac
fi
```

**Exit codes** — 0 success; 1 code not found; 2 usage error (bad flag, missing argument); 3 registry file missing or invalid. Scripts can branch on the difference between "not in the registry" and "you typed the command wrong."

Color is on when stdout is a TTY, off when piped. Override with `ISO4217_COLOR=never|auto|always`. Machine modes always disable color, so `diff` and golden-file tests stay stable.

---

## Registry Contents

| Category | Count | Description |
|----------|-------|-------------|
| Active ISO 4217 currencies | **167 of 167** | **Complete ISO 4217 active coverage** — every currently-assigned alphabetic code |
| Withdrawn ISO currencies | **135 of 135** | Complete historical coverage with revaluation chains and conversion rates |
| Cryptocurrencies | 7 | BTC, ETH, and five others from the top 10 by market cap |
| Stablecoins | 6 | USDT, USDC, DAI, and three others from the top 10 by market cap |
| Commodities | 4 | Precious metals with ISO-compatible codes |
| Special purpose | 4 | IMF units, offshore variants |

The counts are **inclusive**: BTC and ETH are among the seven cryptocurrencies, not excluded from them. Same for USDT, USDC, and DAI among the six stablecoins. The selection rule was *start with the top 10 by market cap, keep the seven or six most widely held and most frequently referenced in financial systems, and document the exclusions in the CHANGELOG*. The v1.4.0 CHANGELOG entries record which entries were excluded and why.

---

## Coverage

**v1.5.0 includes all 167 currencies currently active under ISO 4217, plus all 135 withdrawn currencies and 21 non-ISO instruments.** This is complete coverage of the standard — every active code, every historical revaluation chain, and the major cryptocurrencies, stablecoins, and precious-metal commodity codes in active financial use.

The registry contains three distinct layers:

| Layer | Count | Purpose |
|-------|-------|---------|
| **Active ISO 4217** | 167 | Currently circulating currencies — fiat only |
| **Withdrawn ISO 4217** | 135 | Historical currencies with revaluation chains and conversion rates |
| **Non-ISO** | 21 | Cryptocurrencies (7), stablecoins (6), commodities (4), special purpose (4) |

The top-level shape of `iso4217.json`:

```
{
  "meta":     { "version": "1.5.1", "updated": "2026-09-15", ... },
  "source":   { "standard": "ISO 4217:2015", "last_amendment_applied": 179, ... },
  "currencies": {
    "active":    [ /* 167 entries, each with a code field */ ],
    "withdrawn": [ /* 135 entries, each with a code field */ ]
  },
  "non_iso": {
    "cryptocurrencies": [ /* 7 entries */ ],
    "stablecoins":      [ /* 6 entries */ ],
    "commodities":      [ /* 4 entries */ ],
    "special_purpose":  [ /* 4 entries */ ]
  }
}
```

`status` is not a field in the JSON — the SQL and CSV exporters derive it from which array the entry came from. Every currency in `currencies.active` becomes `status = 'active'`; every currency in `currencies.withdrawn` becomes `status = 'withdrawn'`. Non-ISO entries never receive a `status` at all, because they are excluded from the SQL and CSV exports by design.

**Included:** every code in `tools/parse_source.py::ACTIVE_ISO_CODES` — the curated 167-code ground-truth set cross-checked against ISO 4217 amendment 179.

**Classification notes:**

- **Fund codes** (BOV, CHE, CHW, CLF, COU, MXV, USN, USS, UYI, UYW, VED) are included as active ISO codes with explicit `note` fields explaining they are indexation or settlement units, not circulating currencies.
- **Effectively withdrawn codes** (CUC, SVC) remain listed as active because ISO 4217 has not formally withdrawn them, but their `note` fields flag their demonetization status.
- **Pegged currencies** have full peg metadata: anchor, type (`single`/`basket`/`undisclosed`), rate, band, and establishment date where applicable.

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
  "peg_type": null,
  "is_independent": true,
  "countries": [
    { "code": "US", "name": "United States", "relationship": "issuing" },
    { "code": "EC", "name": "Ecuador", "relationship": "adopting" },
    { "code": "PA", "name": "Panama", "relationship": "adopting" }
  ]
}
```

**Field name mapping:** the JSON field is `numeric`; the SQL and CSV column is `numeric_code`. The rename exists because `numeric` is a reserved word in ANSI SQL and would require quoting in every query on every dialect. The values are identical — `"840"` in JSON becomes `840` in the `numeric_code` column. A consumer joining the two should map `numeric` to `numeric_code` explicitly.

Every active currency includes:
- **ISO 4217** alphabetic and numeric codes. Numeric codes are unique within active currencies but may overlap with withdrawn codes due to historical reuse (e.g., MXN/MXN_OLD share 484, since Mexico reused the numeric code after the 1993 revaluation). **Do not use numeric code as a unique key across active + withdrawn** — use the alphabetic `code` for that instead. `tools/validate.py` enforces uniqueness within each of active-only and withdrawn-only, and warns (without failing) on any active/withdrawn overlap.
- **Minor units** — the number of decimal places (0 for JPY, 2 for USD, 3 for KWD, 8 for BTC, 4 for CLF/UYW fund codes)
- **Peg information** — anchor currency, type, rate, band, and establishment date
- **Central bank** — official name of the monetary authority
- **Country relationships** — every country/territory with its relationship to the currency (issuing, adopting, territory, parallel, local_issue)
- **Market convention notes** — where ISO and market practice diverge (e.g., IDR, CUC, SVC)

Withdrawn currencies include withdrawal dates, replacement codes, and official conversion rates — including all Eurozone irrevocable fixing rates.

**Withdrawn code convention.** ISO 4217 assigns three-letter codes. When a withdrawal chain produces more than one entry competing for the same code stem, the registry uses a synthetic identifier of the form `<STEM>_<OLD>` — for example, `MXN_OLD` disambiguates the pre-1993 Mexican peso from the active `MXN`. Consumers must treat `code` as an opaque string of length 3–7 and declare any SQL column that references it as `VARCHAR(7)`, not `CHAR(3)`. The full rationale is in [docs/decisions/withdrawn-codes.md](./docs/decisions/withdrawn-codes.md).

---

## Wrappers

Each wrapper is idiomatic to its language while maintaining identical behavior across all four:

| Language | Package | Import |
|----------|---------|--------|
| Python | `pip install iso4217-registry` | `from iso4217 import CurrencyRegistry` |
| JavaScript | `npm install iso4217-registry` | `const { CurrencyRegistry } = require('iso4217-registry')` |
| Rust | `cargo add iso4217` | `use iso4217::CurrencyRegistry;` |
| Go | `go get github.com/slimissa/iso4217-go` | `import iso4217 "github.com/slimissa/iso4217-go"` |

The Python package also installs the `iso4217` CLI. See [Command-line interface](#command-line-interface) above.

### Consistent API across languages

| Operation | Python | JavaScript | Rust | Go |
|-----------|--------|------------|------|-----|
| Load registry | `CurrencyRegistry()` | `new CurrencyRegistry()` | `CurrencyRegistry::load()` | `iso4217.Load()` |
| Look up currency | `.active("USD")` | `.active("USD")` | `.active("USD")` | `.Active("USD")` |
| Get minor units | `.minor_units` | `.minorUnits` | `.minor_units` | `.MinorUnits` |
| Convert to minor | `.to_minor(100.50)` | `.toMinor(100.50)` | `.to_minor(100.50)` | `.ToMinor(100.50)` |
| Format with symbol | `.format(100.50)` | `.format(100.50)` | `.format(100.50)` | `.Format(100.50)` |
| Filter pegged to USD | `.pegged_to("USD")` | `.peggedTo("USD")` | `.pegged_to("USD")` | `.PeggedTo("USD")` |
| Peg type discrimination | `.peg_type` | `.pegType` | `.peg_type` | `.PegType` |

### Exports (all regenerated from the same JSON)

| Format | Dialects | Regenerated by | Verified by |
|--------|----------|----------------|-------------|
| SQL | ANSI, PostgreSQL, MySQL, SQLite | `tools/export_sql.py` | `tools/export_sql.py --check` in CI |
| CSV / TSV | RFC 4180, Excel, European, TSV | `tools/export_csv.py` | `tools/export_csv.py --check` in CI |
| CLI | one binary, eight subcommands, five output modes | *(part of the wrapper)* | `pytest wrappers/python/tests/test_cli.py` in CI |

Every export is committed to the repository and re-verified on every push. A stale artifact fails CI before it reaches `main`.

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
| **Coverage** | Active count ≥ 150 (MIN_ACTIVE_CURRENCIES) — enforced without flag | `tools/validate.py` |
| **Export drift** | SQL, CSV, and CLI outputs match the current registry | CI jobs `check-sql-export`, `check-csv-export`, `check-cli` |

For the full provenance story — where each field comes from, how often it is refreshed, what the amendment monitor actually checks, and what the registry's known limitations are — see [docs/PROVENANCE.md](./docs/PROVENANCE.md).

```bash
# Run all validations
python3 tools/validate.py

# Run the full test suite
python3 -m pytest tests/ -v

# Verify exports are in sync with the registry
python3 tools/export_sql.py --check
python3 tools/export_csv.py --check
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
│
├── iso4217.sql               # SQL export — ANSI SQL-92 (portable)
├── iso4217.postgresql.sql    # SQL export — PostgreSQL 12+
├── iso4217.mysql.sql         # SQL export — MySQL 8+ / MariaDB 10.4+
├── iso4217.sqlite.sql        # SQL export — SQLite 3.37+
├── iso4217.csv               # CSV export — RFC 4180
├── iso4217.excel.csv         # CSV export — Excel-compatible (UTF-8 BOM)
├── iso4217.european.csv      # CSV export — semicolon-delimited
├── iso4217.tsv               # TSV export — tab-separated
│
├── wrappers/
│   ├── python/               # pip install iso4217-registry
│   │   ├── iso4217.py        # Currency, CurrencyRegistry
│   │   ├── iso4217_cli.py    # iso4217 command-line interface
│   │   ├── setup.py
│   │   └── tests/
│   │       └── test_cli.py   # CLI test suite
│   ├── javascript/           # npm install iso4217-registry
│   ├── rust/                 # cargo add iso4217
│   └── go/                   # go get github.com/slimissa/iso4217-go
│
├── tests/
│   ├── cross_language_consistency.json
│   ├── test_iso_codes.py
│   ├── test_validate_schema.py
│   ├── test_export_sql.py
│   ├── test_export_csv.py
│   └── test_wrappers.py
│
├── tools/
│   ├── validate.py           # 6-layer validation
│   ├── export_sql.py         # SQL export generator (--check for CI)
│   ├── export_csv.py         # CSV/TSV export generator (--check for CI)
│   ├── refresh_market_caps.py # Crypto/stablecoin rank refresh
│   ├── sync_wrappers.py      # Wrapper copy synchronization
│   ├── check_amendments.py   # Weekly ISO amendment monitor
│   ├── update_from_iso.py    # Fetch + diff + apply pipeline
│   ├── parse_source.py       # Wikipedia table classifier
│   └── generate_v1_2_skeletons.py  # Skeleton generator (historical tool)
│
└── .github/
    ├── workflows/
    │   ├── validate.yml      # CI on every push
    │   └── monitor.yml       # Weekly ISO amendment monitor
    └── ISSUE_TEMPLATE/
        └── currency_update.md
```

---

## Versioning

The registry follows [Semantic Versioning](https://semver.org/):
- **Major**: Breaking schema changes (removed or renamed required fields)
- **Minor**: New currencies added, or new optional fields added (backward-compatible)
- **Patch**: Data corrections

The current version is always in `iso4217.json` → `meta.version`. The Python package version (`wrappers/python/setup.py`) is independent — it tracks the wrapper's own API, not the registry data. As of v1.5.0, the registry is at `1.5.0` and the Python package at `1.1.0`.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines on data corrections, new currencies, wrapper ports, and tooling improvements.

**Quick correction workflow:**

1. Edit `iso4217.json`
2. Run `python3 tools/validate.py` — must pass with 0 errors
3. Regenerate every derived artifact:
   ```bash
   python3 tools/export_sql.py       # four SQL files
   python3 tools/export_csv.py       # four CSV/TSV files
   python3 tools/sync_wrappers.py    # Go and Rust embedded copies
   ```
4. Run the full suite — `python3 -m pytest tests/ wrappers/python/tests/ -q` — all tests must pass
5. Run `pytest wrappers/python/tests/test_cli.py -q` to confirm the CLI still resolves against the updated registry
6. Submit a PR with your source cited, including all regenerated artifacts

CI rejects PRs where any derived file is stale. The three export checks (`check-sql-export`, `check-csv-export`, `check-cli`) run in parallel and gate the slower wrapper matrix.

---

## Consumed By

### Within the QuantOS ecosystem

| Project | How it consumes this registry |
|---------|------------------------------|
| **[Tempus](https://github.com/slimissa/Tempus)** | Compile-time `Price<CCY>` validation. The compiler generates its currency table from this registry via `make update-registry`. |
| **[LAS_Shell](https://github.com/slimissa/Las_shell)** | *(planned)* Pipeline-stage currency validation — risk gates and audit logging will consume the same registry. |

The Tempus integration is the reference example. Its generator reads `iso4217.json`, filters out non-ISO instruments, and emits a C array that the compiler links into every binary:

```c
// Tempus compiler — generated by `make update-registry`
// Reads iso4217.json at build time, emits currency_table.c
static const CurrencyInfo CURRENCY_TABLE[] = {
    { "USD", "840", 2, "$",  "United States" },
    { "EUR", "978", 2, "€",  "European Union" },
    { "JPY", "392", 0, "¥",  "Japan" },
    /* ... 164 more entries ... */
};
```

The registry version is captured in a `#define` alongside the table, so runtime code can assert compatibility at startup.

### External adopters

None yet. If you use this registry, open a PR to add yourself — a one-line table row is all it takes.

### How to adopt

The registry is designed to be consumed three ways:

- **From the JSON directly** — the file is the contract. Pin a tag, read it, done.
- **Via a wrapper** — `pip install iso4217-registry` (Python), `npm install iso4217-registry` (JavaScript), `cargo add iso4217` (Rust), `go get github.com/slimissa/iso4217-go` (Go).
- **Via an export** — SQL, CSV, or CLI. All three regenerate from the same source, and CI rejects PRs where any derived file is stale.

---

## License

Apache 2.0 — use it anywhere, no attribution required. The currency data in this registry is factual information. The compilation, schema, tooling, and wrappers are licensed works.

---

## Author

**Le P'tit** — [github.com/slimissa](https://github.com/slimissa)

---

## What's next

The registry is usable from every language and every tool the ecosystem touches. The next release is a second registry — ISO 3166 country codes — built to the same shape: same JSON schema discipline, same four wrappers, same SQL/CSV/CLI exports, same CI gates. Any table that joins against `currencies` will eventually be able to join against `countries`.

*One source of truth per standard. One consumption pattern across all of them.*