# ISO 4217 Currency Registry

**A canonical, versioned, machine-readable registry of ISO 4217 currency codes — 167 active currencies covering the complete ISO 4217 standard, 135 withdrawn currencies with revaluation chains, and 21 commonly used non-ISO instruments.**

One JSON file is the source of truth. Everything else — SQL, CSV, Parquet, four language wrappers, a command-line tool, and three analytical tables — is regenerated from it and re-verified on every push.

[![Validate](https://github.com/slimissa/iso4217/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/slimissa/iso4217/actions/workflows/validate.yml)
[![Version and Hygiene](https://github.com/slimissa/iso4217/actions/workflows/version-and-hygiene.yml/badge.svg?branch=main)](https://github.com/slimissa/iso4217/actions/workflows/version-and-hygiene.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Schema Version](https://img.shields.io/badge/schema-1.4.0-green.svg)](./schema.json)
[![Registry Version](https://img.shields.io/badge/registry-1.7.11-orange.svg)](./iso4217.json)

---

## Contents

1. [At a glance](#at-a-glance)
2. [Why this exists](#why-this-exists)
3. [Where to start](#where-to-start)
4. [Quick start](#quick-start)
5. [The data model: three layers](#the-data-model-three-layers)
6. [The registry file](#the-registry-file)
7. [Flat exports: SQL, CSV, TSV, Parquet](#flat-exports-sql-csv-tsv-parquet)
8. [Countries and aggregated tables](#countries-and-aggregated-tables)
9. [Worked example: 200 stores](#worked-example-200-stores)
10. [Command-line interface](#command-line-interface)
11. [Language wrappers](#language-wrappers)
12. [Validation](#validation)
13. [Continuous integration](#continuous-integration)
14. [Release pipeline](#release-pipeline)
15. [Versioning](#versioning)
16. [Project structure](#project-structure)
17. [Documentation index](#documentation-index)
18. [Contributing](#contributing)
19. [Known limitations](#known-limitations)
20. [FAQ](#faq)
21. [Consumed by](#consumed-by)
22. [License and author](#license-and-author)
23. [What's next](#whats-next)

---

## At a glance

| | |
|---|---|
| **Active ISO 4217 currencies** | 167 — every currently assigned alphabetic code |
| **Withdrawn ISO 4217 currencies** | 135 — with replacement code, conversion rate, and withdrawal date |
| **Non-ISO instruments** | 21 — 7 cryptocurrencies, 6 stablecoins, 4 commodities, 4 special-purpose |
| **ISO amendment applied** | 179 (dated 2025-06-15) |
| **Source of truth** | [`iso4217.json`](./iso4217.json), validated against [`schema.json`](./schema.json) |
| **Export formats** | SQL (4 dialects), CSV/TSV (4 variants), Parquet (1 flat file) |
| **Analytical tables** | 1 curated Parquet projection, 3 aggregated Parquet files |
| **Wrappers** | Python, JavaScript, Rust, Go — identical behavior, one shared test fixture |
| **CLI** | `iso4217`, eight read-only subcommands, installed with the Python wrapper |
| **Runtime dependencies** | None. The JSON is the contract. |
| **Build-time dependency** | `pyarrow`, for the Parquet generators only |
| **License** | Apache 2.0 |

---

## Why this exists

Every quant library, trading system, payment processor, and fintech app maintains its own currency list. They are often outdated, inconsistent, or wrong. Some hardcode a few majors with no versioning. Some use a CSV from a 2015 Wikipedia scrape with no schema. Some are missing minor units or peg data entirely.

This project provides one versioned, schema-validated file that any tool can depend on, instead of every project hand-rolling and hand-maintaining its own. It carries the metadata a currency list usually lacks: minor units, central banks, peg anchors and rates, country relationships, withdrawal chains, and a source link for every entry.

The registry is language-agnostic by design. The JSON is the contract; the SQL, CSV, Parquet, wrapper, and CLI forms are ways to consume it without writing a parser.

The registry's central argument is that currency data is a **join dimension**: every fact table needs it and no fact table should own it. The [worked example](#worked-example-200-stores) shows what happens when it does not.

---

## Where to start

| If you are... | Start with |
|---------------|------------|
| A programmer who wants a library | [Language wrappers](#language-wrappers) |
| A database engineer | [`iso4217.sql`](./iso4217.sql) and its dialect variants — see [Flat exports](#flat-exports-sql-csv-tsv-parquet) |
| An analyst in Excel, Sheets, pandas, or DuckDB | [`iso4217.csv`](./iso4217.csv) or [`iso4217.parquet`](./iso4217.parquet) |
| A shell user | The [`iso4217` command](#command-line-interface) |
| Asking "which currencies circulate in which region?" | [`currencies_by_region.parquet`](#currencies_by_regionparquet) |
| Evaluating whether to trust the data | [`docs/PROVENANCE.md`](./docs/PROVENANCE.md) and [Known limitations](#known-limitations) |
| Wanting to see it used | [`examples/stores-200`](./examples/stores-200) |
| Contributing a correction | [`CONTRIBUTING.md`](./CONTRIBUTING.md) |
| Building a registry of your own with the same release discipline | [`RELEASE_PATTERN.md`](./RELEASE_PATTERN.md) |

---

## Quick start

### Direct download

```bash
curl -O https://raw.githubusercontent.com/slimissa/iso4217/main/iso4217.json
```

For anything reproducible, pin a release tag instead of `main`, for example `.../iso4217/v1.7.7/iso4217.json`. Tags are immutable. The available versions are listed in [`CHANGELOG.md`](./CHANGELOG.md).

### From a clone

The language packages are installed from a clone of this repository. Publication to PyPI, npm, and crates.io is deferred; see [What's next](#whats-next).

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217
```

**Python** (3.8+, no dependencies; also installs the `iso4217` command):

```bash
pip install ./wrappers/python
```

```python
from iso4217 import currency

usd = currency("USD")
print(usd.to_minor(100.50))   # 10050 (cents)
print(usd.format(100.50))     # "$100.50"
```

**JavaScript** (Node, no dependencies; TypeScript types included):

```javascript
const { CurrencyRegistry } = require('./wrappers/javascript');
const registry = new CurrencyRegistry();

const jpy = registry.active('JPY');
console.log(jpy.toMinor(500));  // 500 (yen has no minor unit)
```

**Rust** (edition 2021) — add a path dependency to `Cargo.toml`:

```toml
[dependencies]
iso4217 = { path = "wrappers/rust" }
```

```rust
use iso4217::CurrencyRegistry;

let registry = CurrencyRegistry::load().unwrap();
let usd = registry.active("USD").unwrap();
assert_eq!(usd.to_minor(100.50), 10050);
```

**Go** (1.21+) — the module path is `github.com/slimissa/iso4217-go`; its source is [`wrappers/go`](./wrappers/go). From a clone, point a `replace` directive at it:

```go
// go.mod:  replace github.com/slimissa/iso4217-go => ../iso4217/wrappers/go
import iso4217 "github.com/slimissa/iso4217-go"

registry, _ := iso4217.Load()
usd := registry.Active("USD")
fmt.Println(usd.ToMinor(100.50))  // 10050
```

**Any SQL database:**

```bash
psql -f iso4217.postgresql.sql            # PostgreSQL
mysql < iso4217.mysql.sql                 # MySQL / MariaDB
sqlite3 registry.db < iso4217.sqlite.sql  # SQLite
psql -f iso4217.sql                       # any SQL-92 engine
```

**pandas / DuckDB:**

```python
import pandas as pd
df = pd.read_parquet("iso4217.parquet")

import duckdb
duckdb.query("SELECT code, name FROM 'iso4217.parquet' WHERE is_independent AND status = 'active'")
```

---

## The data model: three layers

The repository follows a three-layer model, documented in [`docs/LAYERS.md`](./docs/LAYERS.md). It is a discipline, not something enforced by one tool, and it is what makes every artifact reproducible.

| Layer | What lives here | Rule |
|-------|-----------------|------|
| **RAW** | [`iso4217.json`](./iso4217.json) | Never modified by tooling. Every field change is a human commit. |
| **CURATED** | SQL, CSV, TSV, Parquet exports; the countries projection; wrapper copies; the CLI | Regenerated from RAW by deterministic tools. Never hand-edited. Each generator has a `--check` mode that CI runs. |
| **AGGREGATED** | `currencies_by_region.parquet`, `pegs_summary.parquet`, `coverage_timeline.parquet` | Answers questions rather than reproducing facts. Reads CURATED, never RAW. |

**The rule that governs the layers:** a layer may only assume what the layer below it guarantees. The aggregated layer reads CURATED, never RAW. `tools/export_aggregated.py` enforces this structurally: it has no registry loader and no `--registry` flag, it accepts only Parquet, the vendored ISO 3166 snapshot, and the changelog as inputs, and it rejects any JSON input that looks like the RAW registry.

One aggregated file, `coverage_timeline.parquet`, reads `CHANGELOG.md`, a release document rather than a data layer. That is the single sanctioned exception; the reasoning is in [ADR 0007](./docs/decisions/aggregated-layer-0007.md).

Every generated artifact is committed to the repository. A stale artifact fails CI before it reaches `main`.

| Artifact | Layer | Generator | CI gate |
|----------|-------|-----------|---------|
| `iso4217.sql`, `.postgresql.sql`, `.mysql.sql`, `.sqlite.sql` | CURATED | `tools/export_sql.py` | `check-sql-export` |
| `iso4217.csv`, `.excel.csv`, `.european.csv`, `.tsv` | CURATED | `tools/export_csv.py` | `check-csv-export` |
| `iso4217.parquet` | CURATED | `tools/export_parquet.py` | `check-parquet-export` |
| `iso4217.countries.parquet` | CURATED | `tools/export_countries_parquet.py` | `check-countries-parquet` |
| `wrappers/{python,go,rust}/iso4217.json` | CURATED | `tools/sync_wrappers.py` | `sync-wrappers-check`, `check-wrapper-sync` |
| `currencies_by_region.parquet`, `pegs_summary.parquet`, `coverage_timeline.parquet` | AGGREGATED | `tools/export_aggregated.py` | `check-aggregated-export` |

Regeneration order follows the layers: CURATED first, then AGGREGATED. `export_aggregated.py` reads `iso4217.parquet` and `iso4217.countries.parquet`, so it must run after both.

---

## The registry file

[`iso4217.json`](./iso4217.json) has three top-level sections besides `meta` and `source`:

```text
meta        version, updated, amendment, amendment_date, schema_version, license
source      standard, maintenance agency, last verification date, sources used
currencies  active[]    167 entries
            withdrawn[] 135 entries
non_iso     cryptocurrencies[], stablecoins[], commodities[], special_purpose[]
```

### An active entry

```json
{
  "code": "AED",
  "source_url": "https://www.iso.org/obp/ui/#iso:code:4217:AED",
  "numeric_reused": false,
  "classification": "circulating",
  "numeric": "784",
  "name": "UAE Dirham",
  "minor_units": 2,
  "symbol": "د.إ",
  "entity": "United Arab Emirates",
  "central_bank": "Central Bank of the UAE",
  "pegged_to": "USD",
  "peg_type": "single",
  "pegged_since": "1997-11-01",
  "peg_rate": 3.6725,
  "peg_band_pct": 0.0,
  "is_independent": false,
  "countries": [
    { "code": "AE", "name": "United Arab Emirates", "relationship": "issuing" }
  ]
}
```

`peg_rate` is the number of units of this currency per one unit of the anchor: 3.6725 AED per USD.

### A withdrawn entry

```json
{
  "code": "ATS",
  "code_lifetime": { "from": null, "to": "1999-01-01" },
  "source_url": "https://www.iso.org/obp/ui/#iso:code:4217:ATS",
  "numeric": "040",
  "name": "Austrian Schilling",
  "minor_units": 2,
  "symbol": "S",
  "entity": "Austria",
  "withdrawn_date": "1999-01-01",
  "replaced_by": "EUR",
  "conversion_rate": 13.7603
}
```

### A non-ISO entry

```json
{
  "code": "BTC",
  "name": "Bitcoin",
  "minor_units": 8,
  "symbol": "₿",
  "type": "cryptocurrency",
  "entity": "Decentralized",
  "introduced": "2009-01-03",
  "market_cap_rank": 1,
  "note": "Not an ISO 4217 code. Included due to widespread financial market usage.",
  "is_independent": true
}
```

Non-ISO fields vary by type; [`schema.json`](./schema.json) is the authority.

### Field reference

| Field | Where | Meaning |
|-------|-------|---------|
| `code` | all | Three-letter alphabetic code. Primary key within its array. |
| `numeric` | ISO entries | Three-digit numeric code, as a string (leading zeros preserved). |
| `name`, `symbol`, `entity` | all | Display name, symbol (may be an empty string), and issuing entity. |
| `minor_units` | all | Decimal places: ISO currencies use 0, 2, 3, or 4; non-ISO instruments may use more (BTC uses 8). The schema allows 0–18. |
| `source_url` | ISO entries | Link to the entry in the ISO 4217 online browsing platform. |
| `classification` | active | What kind of unit it is. See [Enums](#enums). |
| `numeric_reused` | active | `true` if the entry's numeric code also appears on a withdrawn entry. Required on every active entry. See [ADR 0008](./docs/decisions/numeric-code-reuse.md). |
| `central_bank` | active | Monetary authority. |
| `is_independent` | active, non-ISO | Active: `true` if the currency floats independently or under a managed float, `false` if hard-pegged. Non-ISO: whether the instrument trades independently of another asset. |
| `pegged_to`, `peg_type`, `pegged_since`, `peg_rate`, `peg_band_pct` | active | Peg description. Meaningful only when `pegged_to` is set. |
| `countries[]` | active | Countries that use the currency, each with a `relationship`. Exactly one is `issuing`. |
| `note` | some | Free-text provenance or caveat. |
| `code_lifetime` | withdrawn | `{from, to}`. See [Known limitations](#known-limitations). |
| `withdrawn_date`, `replaced_by`, `conversion_rate` | withdrawn | When the code ended, what replaced it, and the conversion factor. |

### Coverage

| Group | Count | Notes |
|-------|-------|-------|
| Active ISO currencies | 167 | 156 circulating, 10 fund, 1 indexation |
| Pegged active currencies | 46 | 44 single-anchor (all with a numeric `peg_rate`), 1 basket (MAD), 1 undisclosed (KWD) |
| Withdrawn ISO currencies | 135 | Every one has `replaced_by`, `withdrawn_date`, `conversion_rate`, and `code_lifetime.to` |
| Cryptocurrencies | 7 | Selected from the top 10 by market cap |
| Stablecoins | 6 | Selected from the top stablecoins by market cap |
| Commodities | 4 | Precious metals with ISO-compatible codes |
| Special purpose | 4 | IMF units, offshore variants |

The non-ISO counts are inclusive: BTC and ETH are among the seven cryptocurrencies, not excluded from them. The selection rule is documented in the CHANGELOG entries for v1.4.0, which record which entries were excluded and why.

### Enums

Four closed vocabularies appear in the registry. Every value is one of those listed; no other value is valid.

**`classification`** — active currencies only

| Value | Meaning | Count |
|-------|---------|-------|
| `circulating` | Primary legal tender. USD, EUR, JPY. | 156 |
| `fund` | Fund, unit of account, or complementary currency. CLF, USN, CHE. | 10 |
| `indexation` | Indexation unit. VED. | 1 |
| `settlement` | Reserved for a companion to a circulating currency. Defined, currently unused. | 0 |

**`peg_type`** — active currencies, when `pegged_to` is set

| Value | Meaning |
|-------|---------|
| `single` | `pegged_to` is a bare three-letter ISO code. AED → `"USD"`. |
| `basket` | `pegged_to` is a free-text description of a weighted basket. MAD → `"EUR+USD basket"`. |
| `undisclosed` | Pegged, but the mechanism is not public. KWD → `"Currency basket"`. |

**`countries[].relationship`** — active currencies only

| Value | Meaning |
|-------|---------|
| `issuing` | Sovereign issuer. Exactly one per currency. |
| `adopting` | Uses the currency without issuing it. Ecuador, Panama. |
| `territory` | Dependent territory of the issuing country. |
| `parallel` | Circulates alongside a local currency at fixed parity. |
| `local_issue` | Issues local banknotes or coins denominated in this currency. |

**`status`** — derived, in SQL, CSV, and Parquet only

| Value | Meaning |
|-------|---------|
| `active` | The entry is in `currencies.active`. |
| `withdrawn` | The entry is in `currencies.withdrawn`. |

`status` is not a JSON field. The exporters derive it from which array the entry lives in; the JSON represents status by position.

Design decisions behind these fields are recorded as ADRs: [classification](./docs/decisions/classification-enum.md) (0003), [numeric reuse flag](./docs/decisions/numeric-reuse-flag.md) (0004), [source URL and note split](./docs/decisions/note-source-split.md) (0005), [code lifetime](./docs/decisions/code-lifetime.md) (0006).

---

## Flat exports: SQL, CSV, TSV, Parquet

All flat exports are regenerated from `iso4217.json`, committed, and verified byte-for-byte (SQL, CSV) or logically (Parquet) in CI.

### SQL

Four files, one per dialect, each self-contained and idempotent — safe to run twice.

| File | Target |
|------|--------|
| [`iso4217.sql`](./iso4217.sql) | ANSI SQL-92 — portable default; PostgreSQL, MySQL 8+, MariaDB 10.4+, SQLite 3.37+, SQL Server 2016+, Oracle 12c+, IBM Db2 |
| [`iso4217.postgresql.sql`](./iso4217.postgresql.sql) | PostgreSQL 12+ — includes a commented `INSERT ... ON CONFLICT (code) DO NOTHING` alternative |
| [`iso4217.mysql.sql`](./iso4217.mysql.sql) | MySQL 8+ / MariaDB 10.4+ — `ENGINE=InnoDB`, `utf8mb4` |
| [`iso4217.sqlite.sql`](./iso4217.sqlite.sql) | SQLite 3.37+ — `STRICT` tables for real type enforcement |

**What is in them:** one `currencies` table with seven columns (`code`, `numeric_code`, `name`, `minor_units`, `symbol`, `entity`, `status`), one `INSERT` per active and withdrawn ISO 4217 code. `status` is `'active'` or `'withdrawn'`, enforced by a `CHECK` constraint. `code` is the primary key. The table is foreign-key-ready: add `FOREIGN KEY (currency) REFERENCES currencies(code)` to any transaction table and start joining.

**What is intentionally absent:** pegs, countries, central banks, withdrawal metadata, and non-ISO instruments. The SQL export is a reference table for foreign keys, not a relational mirror of the JSON. If you need those fields, read the JSON, or use the CSV or Parquet.

### CSV and TSV

Four files, one per audience. No byte-order mark except where Excel needs it; LF line endings everywhere; headers always present.

| File | Audience |
|------|----------|
| [`iso4217.csv`](./iso4217.csv) | Universal — every CSV parser on every platform |
| [`iso4217.excel.csv`](./iso4217.excel.csv) | Excel on Windows — UTF-8 BOM so symbols render without an encoding prompt |
| [`iso4217.european.csv`](./iso4217.european.csv) | European Excel locales — semicolon-delimited so it opens without an import dialog |
| [`iso4217.tsv`](./iso4217.tsv) | Terminal, clipboard, Google Sheets, SQL clients — tab-separated |

Eleven columns: SQL's seven plus four peg and independence columns (`is_independent`, `pegged_to`, `peg_type`, `peg_rate`). The first seven names match the SQL export's, so joining the two is a straight comparison on `code`. There is no comment header: a leading comment block would break `pandas.read_csv` and violate RFC 4180.

```python
import pandas as pd
df = pd.read_csv("iso4217.csv")
```

### Parquet

[`iso4217.parquet`](./iso4217.parquet) — columnar, typed, snappy-compressed, readable by pandas, Polars, DuckDB, Spark, and every warehouse loader. 302 rows: 167 active and 135 withdrawn.

Columns, in order: `code`, `numeric_code`, `name`, `minor_units`, `symbol`, `entity`, `status`, `is_independent`, `pegged_to`, `peg_type`, `peg_rate`.

Three differences from the CSV, because Parquet has a type system:

- `minor_units` is a native integer, not the string `"2"`. `WHERE minor_units = 3` works without casting.
- `is_independent` is a native boolean. `WHERE is_independent` works directly.
- `pegged_to`, `peg_type`, and `peg_rate` use `null` for "not applicable", not empty strings. `WHERE pegged_to IS NOT NULL` returns only pegged currencies.

**Footer metadata.** The file carries `iso4217.version`, `iso4217.updated`, and `iso4217.amendment` in its footer, so a consumer who receives only the `.parquet` file can tell which registry version produced it.

The schema rationale is in [ADR 0002](./docs/decisions/parquet-schema.md). That decision applies to this flat, eleven-column file; it is the reason `countries[]` lives in a separate file.

### Comparison semantics

`--check` on a Parquet generator compares logical content — row count, column names, types, every value, and footer metadata — not bytes, because the Parquet format permits different but equivalent physical layouts. Two runs of a generator on the same inputs and the same `pyarrow` version do produce identical bytes.

---

## Countries and aggregated tables

Four more Parquet files answer questions the flat file cannot. One is a CURATED projection; three are AGGREGATED. All are deterministic, sorted on a total key, and carry no wall-clock timestamps.

### `iso4217.countries.parquet`

**CURATED.** Which countries use which currency, and how? One row per (currency, country) pair — a flattening of `countries[]`, not an aggregate. 268 rows. Generated from RAW by `tools/export_countries_parquet.py`.

| Column | Type | Notes |
|--------|------|-------|
| `currency_code` | string | |
| `country_code` | string | ISO 3166-1 alpha-2 |
| `country_name` | string | |
| `relationship` | string | `issuing`, `adopting`, `territory`, `parallel`, or `local_issue` |
| `status` | string | `active` or `withdrawn`, derived from which array the entry is in |
| `classification` | string, nullable | A denormalized currency attribute. Carried here because no other CURATED artifact exposes it. Null for withdrawn entries. |

Sorted by (`status`, `currency_code`, `country_code`). Footer keys: `iso4217.version`, `iso4217.updated`, `iso4217.countries_rows`. Only active entries carry `countries[]` today, so every row is `active`.

### `currencies_by_region.parquet`

**AGGREGATED.** Which currencies circulate in each world region, and in how many of its countries? One row per (region, currency). 178 rows.

| Column | Type | Notes |
|--------|------|-------|
| `region` | string, nullable | ISO 3166 region. Null for two codes the snapshot does not classify. |
| `subregion` | string, nullable | Set when every country in the group shares one subregion; null otherwise. Informational, not a grouping key. |
| `currency_code` | string | |
| `currency_name` | string | |
| `classification` | string | |
| `is_pegged` | bool | `pegged_to IS NOT NULL` |
| `country_count` | int | Distinct countries in this region that use the currency, across all relationships |

Sorted by `region` (nulls last), then `currency_code`. Four properties are worth knowing before you join to it:

- **The join key is the pair `(region, currency_code)`.** USD and EUR circulate in several regions, so joining on currency alone returns several rows per currency and overcounts anything you sum.
- **The ISO 3166 join uses the snapshot's `countries.active` list only.** The snapshot's withdrawn list reuses two live codes (`SK`, `AI`) for historical entities; merging both lists would file Slovakia and Anguilla in the wrong regions.
- **`XK` (Kosovo) and `TW` (Taiwan) have a null region.** The ISO 3166 snapshot does not place them in a region. The registry keeps them as rows with a null region rather than dropping them or inventing a label.
- **Null does not equal null.** Join on region with `IS NOT DISTINCT FROM`, or an ordinary `=` join will silently drop those rows.

An unresolvable country code stops the generator with exit code 2 and names the code. It is never dropped silently.

### `pegs_summary.parquet`

**AGGREGATED.** Which currencies anchor single-currency pegs, how many currencies hang off each, and at what rates? One row per anchor currency. 8 rows.

| Column | Type | Notes |
|--------|------|-------|
| `anchor_code` | string | |
| `anchor_name` | string | From the active entry with this code |
| `currency_count` | int | Currencies that peg to this anchor |
| `median_rate` | float64, nullable | Median of member `peg_rate` values |
| `min_rate`, `max_rate` | float64, nullable | |
| `currencies` | list of string | Sorted member codes |

Sorted by `anchor_code`. It covers only `peg_type = 'single'`; basket and undisclosed pegs (MAD, KWD) have no single anchor and are not in the file. The rate statistics are arithmetic over per-currency exchange rates whose magnitudes can differ widely within one anchor (EUR anchors both BAM, near 1.96, and XOF, near 656): they are not a "typical rate".

### `coverage_timeline.parquet`

**AGGREGATED.** How did the registry's coverage change across releases? One row per released version, sorted by version ascending. 23 rows.

| Column | Type | Notes |
|--------|------|-------|
| `version` | string | From a `## [X.Y.Z]` heading in the changelog |
| `date` | string, nullable | ISO 8601. Null if a heading carries a placeholder date. |
| `active_count` | int, nullable | |
| `withdrawn_count` | int, nullable | |
| `non_iso_count` | int, nullable | |
| `source` | string | `changelog` |

Counts come from the changelog's `## Version History` table and are null for versions that table does not list (today, every version after 1.5.0). They are never extrapolated. The table counts currencies per release; it does not say when any individual currency began.

### Footer metadata on the aggregated files

All three carry `iso4217.version` and `iso4217.updated`, copied from the CURATED inputs' footers, and `iso4217.rows`. If the two CURATED Parquet inputs disagree on version, the generator stops rather than join across two registry releases.

---

## Worked example: 200 stores

[`examples/stores-200`](./examples/stores-200) is a self-contained demo: a fictional chain of 200 stores in 25 countries, a year of daily revenue (73,200 rows), and six business questions answered by joining that fact table to the registry's Parquet files with DuckDB.

```bash
cd examples/stores-200
pip install -r requirements.txt     # pyarrow and duckdb; the registry itself needs neither
python3 generate_facts.py
python3 analyze.py
```

It is a companion, not part of the release pipeline. It demonstrates, with real numbers:

- why a fact table should carry only a currency code and let the registry supply region, minor units, and peg data;
- the cost of joining on currency alone (several rows per store, a large overcount);
- what an ordinary `=` join does to the stores in countries with no region;
- which registry artifact answers which class of question — and where the flat file would have been enough.

Its [README](./examples/stores-200/README.md) separates what is real (country codes, currencies, minor units, peg rates) from what is synthetic (stores, revenue, exchange rates for unpegged currencies).

---

## Command-line interface

Installing the Python wrapper (`pip install ./wrappers/python`) also provides an `iso4217` command. Eight subcommands, all read-only, all offline:

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

Every command supports machine-readable output modes:

- `--json` — one object (single lookup, peg, info) or an array (list, multi-lookup)
- `--jsonl` — newline-delimited JSON, one object per line
- `--tsv` / `--csv` — columns match `iso4217.tsv` and `iso4217.csv`
- `--raw FIELD` — the bare value only, one per line for lists

`lookup` accepts `-` to read codes from standard input, one per line.

```bash
# Every currency pegged to USD, formatted as "$100.00"
iso4217 list --pegged-to USD --raw code | xargs -I{} iso4217 format 100 {}

# Branch on "not in the registry" versus "you typed the command wrong"
if ! iso4217 validate "$USER_INPUT" 2>/dev/null; then
    case $? in
        1) echo "unknown code: $USER_INPUT" ;;
        2) echo "usage error" ;;
    esac
fi
```

**Exit codes:** 0 success; 1 code not found; 2 usage error (bad flag, missing argument); 3 registry file missing or invalid. Scripts can tell "not in the registry" from "you typed the command wrong".

Color is on when stdout is a terminal and off when piped. Override with `ISO4217_COLOR=never|auto|always`. Machine modes always disable color, so `diff` and golden-file tests stay stable.

---

## Language wrappers

Each wrapper is idiomatic to its language and behaves identically across all four. They are verified against one shared fixture, [`tests/cross_language_consistency.json`](./tests/cross_language_consistency.json), by `tools/check_cross_language.sh`.

| Language | Package name | Source | Import |
|----------|--------------|--------|--------|
| Python 3.8+ | `iso4217-registry` | [`wrappers/python`](./wrappers/python) | `from iso4217 import CurrencyRegistry` |
| JavaScript | `iso4217-registry` | [`wrappers/javascript`](./wrappers/javascript) | `const { CurrencyRegistry } = require('iso4217-registry')` |
| Rust (2021) | `iso4217` | [`wrappers/rust`](./wrappers/rust) | `use iso4217::CurrencyRegistry;` |
| Go 1.21+ | `github.com/slimissa/iso4217-go` | [`wrappers/go`](./wrappers/go) | `import iso4217 "github.com/slimissa/iso4217-go"` |

Each wrapper has its own README with the full API. The Python, Go, and Rust directories hold a byte-identical copy of `iso4217.json`, kept in sync by `tools/sync_wrappers.py`.

### One API, four spellings

| Operation | Python | JavaScript | Rust | Go |
|-----------|--------|------------|------|----|
| Load registry | `CurrencyRegistry()` | `new CurrencyRegistry()` | `CurrencyRegistry::load()` | `iso4217.Load()` |
| Look up an active currency | `.active("USD")` | `.active("USD")` | `.active("USD")` | `.Active("USD")` |
| Minor units | `.minor_units` | `.minorUnits` | `.minor_units` | `.MinorUnits` |
| Convert to minor units | `.to_minor(100.50)` | `.toMinor(100.50)` | `.to_minor(100.50)` | `.ToMinor(100.50)` |
| Format with symbol | `.format(100.50)` | `.format(100.50)` | `.format(100.50)` | `.Format(100.50)` |
| Currencies pegged to an anchor | `.pegged_to("USD")` | `.peggedTo("USD")` | `.pegged_to("USD")` | `.PeggedTo("USD")` |
| Peg type | `.peg_type` | `.pegType` | `.peg_type` | `.PegType` |
| Classification | `.classification` | `.classification` | `.classification` | `.Classification` |
| Filter by classification | `.by_classification(...)` | `.byClassification(...)` | `.by_classification(...)` | `.ByClassification(...)` |

Peg-type discrimination exists because `pegged_to("USD")` once returned MAD: "USD" is a substring of MAD's basket description, "EUR+USD basket". All four wrappers now match exactly and only when `peg_type` is `single`.

---

## Validation

The registry is validated through a multi-layer defense. Each check has one tool and one failure mode.

| Layer | What it checks | Tool |
|-------|----------------|------|
| **Schema** | JSON structure, types, required fields | `tools/validate.py` + `schema.json` |
| **Integrity** | Required fields, value ranges, format patterns | `tools/validate.py` |
| **Business logic** | Peg consistency, minor-unit conventions, conversion rates | `tools/validate.py` |
| **Cross-reference** | No duplicate codes, valid peg targets, no ISO/non-ISO overlap | `tools/validate.py` |
| **Coverage** | Active count at least 150 (`MIN_ACTIVE_CURRENCIES`), enforced without a flag | `tools/validate.py` |
| **Ground truth** | Historical facts: eurozone rates, numeric codes, peg relationships | `tests/test_iso_codes.py` |
| **Cross-language** | Identical behavior across all four wrappers | `tests/cross_language_consistency.json` |
| **Country codes** | Every `countries[].code` resolves in the ISO 3166 snapshot | `tools/check_country_codes.py` |
| **Mojibake** | No UTF-8 / Latin-1 round-trip corruption in any text file | `tools/check_mojibake.py` |
| **Registry freshness** | `meta.updated` within 180 days (one day of timezone skew tolerated) | `tools/check_registry_freshness.py` |
| **Snapshot freshness** | Vendored snapshots within their `review_by` window | `tools/check_snapshot_freshness.py` |
| **Version consistency** | All 11 version sites across 2 axes agree | `tools/check_version_consistency.py` |
| **Wrapper sync** | Wrapper copies match the root registry | `tools/sync_wrappers.py --check` |
| **Export drift** | SQL, CSV, Parquet, countries, and aggregated outputs match their inputs | each generator's `--check` |
| **Amendment monitoring** | A new ISO 4217 amendment is detected | `tools/check_amendments.py`, weekly |

Both freshness tools take `--today YYYY-MM-DD`, so the date logic can be tested without changing the system clock.

```bash
# Run all validations
python3 tools/validate.py

# Run the test suites
python3 -m pytest tests/ -q
python3 -m pytest wrappers/python/tests/ -q

# Verify every generated artifact is in sync
python3 tools/export_sql.py --check
python3 tools/export_csv.py --check
python3 tools/export_parquet.py --check
python3 tools/export_countries_parquet.py --check
python3 tools/export_aggregated.py --check
python3 tools/sync_wrappers.py --check

# Run the fast convention checks
python3 tools/check_version_consistency.py
python3 tools/check_mojibake.py
python3 tools/check_country_codes.py
python3 tools/check_registry_freshness.py
python3 tools/check_snapshot_freshness.py
python3 tools/check_release_claims.py <version>

# Run all four wrapper test suites against the shared fixture
bash tools/check_cross_language.sh
```

For where each field comes from, how often it is refreshed, and what the amendment monitor does and does not check, see [`docs/PROVENANCE.md`](./docs/PROVENANCE.md).

---

## Continuous integration

Three workflows in [`.github/workflows`](./.github/workflows):

| Workflow | Runs on | Jobs |
|----------|---------|------|
| **Version and Hygiene** (fast) | every push to `main`, every tag push, pull requests | `check-version`, `check-mojibake`, `sync-wrappers-check`, `check-country-codes`, `check-registry-freshness`, `check-snapshot-freshness`, `check-countries-parquet`, `check-aggregated-export`, `check-readme-drift`, `check-verification-doc` |
| **Validate Registry** (slow) | push | `check-wrapper-sync`, `check-sql-export`, `check-csv-export`, `check-parquet-export`, `check-cli`, `validate-json`, and a `validate-wrappers` matrix, one per language |
| **Monitor ISO Amendments** | weekly, Monday 08:00 UTC | `check-amendments` |

CI rejects any pull request where a derived file is stale. The release gate (below) re-runs validation, every export `--check`, and the freshness checks before anything is committed.

---

## Release pipeline

Releases are cut by [`scripts/release.sh`](./scripts/release.sh):

```bash
bash scripts/release.sh <version> --dry-run   # preview every site and gate
bash scripts/release.sh <version>             # release
bash scripts/release.sh <version> --force     # re-run on an existing tag
```

The script is deterministic and refuses to start unless the working tree is clean, the branch is `main`, `HEAD` is at `origin/main`, the tag is free, the changelog has a section for the version, and the version-consistency check currently passes. Then it:

1. **Bumps eight version sites:** `VERSION`, the changelog heading and date, `iso4217.json` `meta.version` and `meta.updated`, the README registry badge, and the Python, JavaScript, and Rust package manifests.
2. **Regenerates sixteen files:** 4 SQL, 4 CSV/TSV, `iso4217.parquet`, `iso4217.countries.parquet`, the 3 aggregated files, and the 3 wrapper copies of the JSON — in layer order.
3. **Runs a seventeen-check gate:** `validate.py`, version consistency, the five export `--check` modes, wrapper sync, release claims, mojibake, snapshot freshness, registry freshness, country codes, README drift, verification doc, the cross-language suite, and `pytest tests/`.
4. **Commits and pushes**, then **polls every workflow** until each completes.
5. **Tags** (annotated, with the first lines of the changelog section) only when everything is green.
6. **Writes a verification document**, `docs/v<version>-verification.md`, with the captured output of every check.

`pyarrow` is a build-time dependency of this script: the Parquet generators and their `--check` modes import it.

Each release has a manifest entry in [`tools/release_claims.json`](./tools/release_claims.json) — files that must exist and strings they must contain — checked by `tools/check_release_claims.py`. Claims describe state, not intent.

The eight invariants every release refuses on, plus the operator-hygiene rules, are in [`RELEASE_PATTERN.md`](./RELEASE_PATTERN.md). That document is shared with the ISO 3166 and ISO 10383 registries: three independent `release.sh` implementations, one convention. Tags are immutable.

---

## Versioning

The registry follows [Semantic Versioning](https://semver.org/):

- **Major** — breaking schema changes (removed or renamed required fields)
- **Minor** — new currencies, or new optional fields (backward-compatible)
- **Patch** — data corrections and non-breaking fixes, including tooling-only releases

Two version axes are tracked independently, because the data version and the format-contract version can move separately:

| Axis | Source of truth | Sites |
|------|-----------------|-------|
| **Registry** | [`VERSION`](./VERSION) | 8: `VERSION`, first released changelog heading, `iso4217.json` `meta.version`, the `iso4217.parquet` footer, the README registry badge, and the Python, JavaScript, and Rust manifests |
| **Schema** | `schema.json`'s `$id` | 3: `schema.json` `$id`, `iso4217.json` `meta.schema_version`, the README schema badge |

`tools/check_version_consistency.py` verifies all 11 sites on every push. [`axes.json`](./axes.json) declares the same axes as a stable contract for the sibling registries; the check encodes the sites in code and does not read that file.

Three deliberate exclusions:

- **Go is not a site.** Go modules carry no version in `go.mod`; the version is the git tag.
- **The other Parquet footers are not sites.** `iso4217.countries.parquet` and the three aggregated files also carry `iso4217.version`, but their own `--check` modes already fail when it is stale ([ADR 0007](./docs/decisions/aggregated-layer-0007.md)).
- **Wrapper package versions track the registry version.** The Python package `iso4217-registry` at a given version ships that version's registry.

The current version is in [`VERSION`](./VERSION) and the badge above.

---

## Project structure

```text
iso4217/
├── VERSION                       # Registry version — single source of truth
├── axes.json                     # Declares the two version axes and their 11 sites
├── iso4217.json                  # RAW — the registry
├── schema.json                   # JSON Schema for validation
├── README.md                     # This file
├── CHANGELOG.md                  # Version history
├── CONTRIBUTING.md               # How to contribute
├── RELEASE_PATTERN.md            # The release convention shared across three registries
├── LICENSE                       # Apache 2.0
├── windows-verify-manifest.txt   # Checksums used for the v1.5.1 Windows verification
├── .gitattributes                # LF endings for flat exports
├── .gitignore
│
├── iso4217.sql                   # CURATED — SQL, ANSI SQL-92 (portable)
├── iso4217.postgresql.sql        # CURATED — SQL, PostgreSQL 12+
├── iso4217.mysql.sql             # CURATED — SQL, MySQL 8+ / MariaDB 10.4+
├── iso4217.sqlite.sql            # CURATED — SQL, SQLite 3.37+
├── iso4217.csv                   # CURATED — CSV, RFC 4180
├── iso4217.excel.csv             # CURATED — CSV, Excel (UTF-8 BOM)
├── iso4217.european.csv          # CURATED — CSV, semicolon-delimited
├── iso4217.tsv                   # CURATED — TSV
├── iso4217.parquet               # CURATED — flat Parquet, 11 columns
├── iso4217.countries.parquet     # CURATED — one row per (currency, country)
├── currencies_by_region.parquet  # AGGREGATED — one row per (region, currency)
├── pegs_summary.parquet          # AGGREGATED — one row per anchor currency
├── coverage_timeline.parquet     # AGGREGATED — one row per released version
│
├── wrappers/
│   ├── python/                   # iso4217.py, iso4217_cli.py, setup.py, tests/
│   ├── javascript/               # index.js, index.d.ts, package.json, test.js
│   ├── rust/                     # Cargo.toml, src/
│   └── go/                       # go.mod, iso4217.go, iso4217_test.go
│
├── tools/
│   ├── validate.py                       # Six-layer validation
│   ├── export_sql.py                     # SQL generator (--check for CI)
│   ├── export_csv.py                     # CSV/TSV generator (--check)
│   ├── export_parquet.py                 # Flat Parquet generator (--check)
│   ├── export_countries_parquet.py       # Countries Parquet generator (--check)
│   ├── export_aggregated.py              # AGGREGATED-layer generator, 3 files (--check)
│   ├── sync_wrappers.py                  # Wrapper copy sync (--check)
│   ├── check_version_consistency.py      # 11 sites, 2 axes
│   ├── check_mojibake.py                 # UTF-8 / Latin-1 round-trip detector
│   ├── check_country_codes.py            # ISO 3166 join check
│   ├── check_readme_drift.py             # README claims vs the tree
│   ├── check_verification_doc.py         # Refuse to ship a placeholder doc
│   ├── check_registry_freshness.py       # meta.updated within 180 days
│   ├── check_snapshot_freshness.py       # Vendored snapshot review_by check
│   ├── check_release_claims.py           # Manifest verification at release time
│   ├── check_amendments.py               # Weekly ISO amendment monitor
│   ├── check_cross_language.sh           # Four wrappers, one fixture
│   ├── enrich_field.py                   # Field enrichment
│   ├── parse_source.py                   # Source table classifier
│   ├── update_from_iso.py                # Fetch, diff, and apply pipeline
│   ├── refresh_market_caps.py            # Crypto and stablecoin rank refresh
│   ├── iso3166_snapshot.json             # Vendored ISO 3166 reference
│   ├── iso3166_snapshot.meta.json        # Vendoring metadata and review_by date
│   ├── release_claims.json               # Per-version claims for check_release_claims
│   └── archive/                          # Historical one-off generators
│
├── scripts/
│   └── release.sh                        # Deterministic release pipeline
│
├── tests/
│   ├── cross_language_consistency.json   # Shared fixture for all four wrappers
│   ├── test_iso_codes.py
│   ├── test_validate_schema.py
│   ├── test_export_sql.py
│   ├── test_export_csv.py
│   ├── test_export_parquet.py
│   ├── test_export_countries_parquet.py
│   ├── test_export_aggregated.py
│   ├── test_check_registry_freshness.py
│   ├── test_check_snapshot_freshness.py
│   ├── test_update_from_iso.py
│   ├── test_refresh_market_caps.py
│   └── test_wrappers.py
│
├── examples/
│   └── stores-200/               # Companion demo: 200 stores, one registry, six queries
│
├── docs/
│   ├── PROVENANCE.md             # Per-field sourcing and known limits
│   ├── LAYERS.md                 # RAW / CURATED / AGGREGATED model
│   ├── JOINS.md                  # Cross-registry foreign-key graph (currency side)
│   ├── v<version>-verification.md  # One per release since v1.5.0
│   └── decisions/                # Architecture decision records
│       ├── withdrawn-codes.md            # ADR 0001
│       ├── parquet-schema.md             # ADR 0002
│       ├── classification-enum.md        # ADR 0003
│       ├── numeric-reuse-flag.md         # ADR 0004
│       ├── note-source-split.md          # ADR 0005
│       ├── code-lifetime.md              # ADR 0006
│       ├── aggregated-layer-0007.md      # ADR 0007
│       ├── numeric-code-reuse.md         # ADR 0008
│       ├── schema-version-consistency.md # ADR 0009
│       └── v1.6.0-candidates.md          # Deferred decisions
│
└── .github/
    ├── workflows/
    │   ├── validate.yml                  # Slow: export checks, CLI, wrapper matrix
    │   ├── version-and-hygiene.yml       # Fast: convention checks and export drift
    │   └── monitor-amendments.yml        # Weekly ISO amendment monitor
    └── ISSUE_TEMPLATE/
        └── currency_update.md
```

---

## Documentation index

| Document | What it answers |
|----------|-----------------|
| [`docs/LAYERS.md`](./docs/LAYERS.md) | Which layer does a file belong to, and what may a tool read? |
| [`docs/PROVENANCE.md`](./docs/PROVENANCE.md) | Where does each field come from, and how is it refreshed? |
| [`docs/JOINS.md`](./docs/JOINS.md) | Which other registries reference ISO 4217's `code`, and which does it reference? |
| [`docs/decisions/`](./docs/decisions) | Why was each design choice made? One ADR per decision. |
| [`RELEASE_PATTERN.md`](./RELEASE_PATTERN.md) | What invariants does every release refuse on? |
| [`CHANGELOG.md`](./CHANGELOG.md) | What changed in each release? |
| `docs/v<version>-verification.md` | What did the gate print when this version was released? |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | How do I propose a correction, a new currency, or a tooling change? |
| [`examples/stores-200/README.md`](./examples/stores-200/README.md) | How does a fact table use this registry? |
| `wrappers/*/README.md` | The full API of each language wrapper. |

---

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for data corrections, new currencies, wrapper ports, and tooling changes. Every currency data change must cite an authoritative source.

Quick correction workflow:

1. Edit `iso4217.json`.
2. Run `python3 tools/validate.py` — it must pass with 0 errors.
3. Regenerate every derived artifact, **in this order** (CURATED first, then AGGREGATED):

   ```bash
   python3 tools/export_sql.py                 # four SQL files
   python3 tools/export_csv.py                 # four CSV/TSV files
   python3 tools/export_parquet.py             # flat Parquet
   python3 tools/export_countries_parquet.py   # countries Parquet
   python3 tools/sync_wrappers.py              # Python, Go, and Rust JSON copies
   python3 tools/export_aggregated.py          # three aggregated files (reads the two above)
   ```

4. Run the fast convention checks:

   ```bash
   python3 tools/check_version_consistency.py
   python3 tools/check_mojibake.py
   python3 tools/check_country_codes.py
   bash tools/check_cross_language.sh
   ```

5. Run the full suite — `python3 -m pytest tests/ wrappers/python/tests/ -q` — all tests must pass.
6. Submit a pull request with your source cited and every regenerated artifact included.

Development setup, including the virtual environment the Python tooling needs on Debian and Ubuntu, is in [`CONTRIBUTING.md`](./CONTRIBUTING.md).

---

## Known limitations

Stated plainly, because a canonical registry is a claim and claims need their edges drawn.

- **`code_lifetime.from` is null for all 135 withdrawn entries.** None has a documented ISO assignment date. That is a fact about ISO's documentation, not an enrichment failure. If you have a primary source for any of them, open an issue.
- **The registry is a versioned snapshot, not a history.** `coverage_timeline.parquet` counts currencies per release; no artifact says when an individual active currency began. Questions like "did this currency exist in 2012?" cannot be answered from it.
- **Coverage counts are partial.** `coverage_timeline.parquet` has counts only for the versions the changelog's Version History table lists (1.0.0 through 1.5.0 today); later versions are null rather than inferred.
- **Two country codes have no region.** `XK` and `TW` are valid codes that the vendored ISO 3166 snapshot does not place in a region. They appear with a null region in `currencies_by_region.parquet`.
- **No exchange rates.** The registry records pegs, because a peg is a fact about a currency. It does not record market rates, because a rate is a fact about a day.
- **Basket pegs have no numeric rate.** MAD and KWD are pegged, but the registry has no single anchor or rate to give.
- **Non-ISO instruments are a selection, not a standard.** Cryptocurrencies, stablecoins, commodities, and special-purpose codes were chosen by documented rules and are kept in a separate array; they are never mixed into the ISO sets.
- **Only active entries carry `countries[]`.** Withdrawn entries have no country list.
- **Language packages are not yet published** to PyPI, npm, or crates.io; install from a clone.
- **The ISO 3166 snapshot is vendored**, byte-for-byte, and reviewed on a schedule (see `tools/iso3166_snapshot.meta.json`).

---

## FAQ

**Why is there no `countries` column in `iso4217.parquet`?**
That file mirrors the CSV's eleven columns, one row per currency. A one-to-many relationship does not fit a flat table without repeating rows or nesting a list. The relationship lives in `iso4217.countries.parquet` in the shape it actually has. See [ADR 0002](./docs/decisions/parquet-schema.md) and [ADR 0007](./docs/decisions/aggregated-layer-0007.md).

**Why does the aggregated tool refuse to read `iso4217.json`?**
So that every aggregate has an auditable upstream in a lower layer, and so the layering rule cannot be quietly bypassed. If an aggregate needs a column no CURATED file carries, the fix is to extend a CURATED generator.

**Why can one numeric code belong to two currencies?**
ISO reuses numeric codes after a currency is withdrawn. The `numeric_reused` flag marks active entries whose numeric code also appears on a withdrawn entry; see [ADR 0008](./docs/decisions/numeric-code-reuse.md).

**Is a currency with no recorded peg "freely floating"?**
No. "Not pegged" means no peg is recorded in the registry. `is_independent` and `peg_type` carry the distinctions the data supports.

**How do I know which registry version produced a Parquet file I was handed?**
Read its footer: every Parquet file here carries `iso4217.version` and `iso4217.updated`.

**Why are the exports committed instead of built on demand?**
So a consumer can download one file without running anything, and so any drift between the JSON and a derived file fails CI instead of reaching users.

**How are releases tested before they ship?**
`bash scripts/release.sh <version> --dry-run` prints every site, artifact, and gate check without changing anything.

---

## Consumed by

### Within the QuantOS ecosystem

| Project | How it consumes this registry |
|---------|-------------------------------|
| **[Tempus](https://github.com/slimissa/Tempus)** | Compile-time `Price<CCY>` validation. The compiler generates its currency table from this registry via `make update-registry`. |
| **[ISO 3166](https://github.com/slimissa/iso3166)** | This repository vendors a byte-for-byte snapshot of ISO 3166 at `tools/iso3166_snapshot.json`; every `countries[].code` must resolve in `countries.active[].alpha_2`, checked in CI. In the other direction, every ISO 3166 `currency_codes[]` entry must resolve here, validated in ISO 3166's release gate. |
| **[ISO 10383](https://github.com/slimissa/iso10383)** | Hosts the venue side of the cross-registry foreign-key graph at [`docs/JOINS.md`](https://github.com/slimissa/iso10383/blob/main/docs/JOINS.md). |
| **[LAS_Shell](https://github.com/slimissa/Las_shell)** | *(planned)* Pipeline-stage currency validation. |
| **The registry layer itself** | The currency-side graph is at [`docs/JOINS.md`](./docs/JOINS.md): every registry that references ISO 4217's `code`, in both directions. |

The Tempus integration is the reference example. Its generator reads `iso4217.json` at build time, filters out non-ISO instruments, and emits a C array the compiler links into every binary:

```c
// Tempus compiler — generated by `make update-registry`
static const CurrencyInfo CURRENCY_TABLE[] = {
    { "USD", "840", 2, "$",  "United States" },
    { "EUR", "978", 2, "€",  "European Union" },
    { "JPY", "392", 0, "¥",  "Japan" },
    /* ... 164 more entries ... */
};
```

The registry version is captured in a `#define` alongside the table, so runtime code can assert compatibility at startup.

### External adopters

None yet. If you use this registry, open a pull request to add yourself — a one-line table row is all it takes.

### How to adopt

- **From the JSON directly** — the file is the contract. Pin a tag, read it, done.
- **Via a wrapper** — Python, JavaScript, Rust, or Go, from a clone of this repository.
- **Via an export** — SQL, CSV, or Parquet. All regenerate from the same source, and CI rejects any pull request where a derived file is stale.
- **Via the aggregated tables** — when the question is about regions, pegs, or coverage over time rather than about one currency.

---

## License and author

Apache 2.0 — use it anywhere, no attribution required. The currency data in this registry is factual information. The compilation, schema, tooling, and wrappers are licensed works. See [`LICENSE`](./LICENSE).

**Le P'tit** — [github.com/slimissa](https://github.com/slimissa)

---

## What's next

The registry is complete. Both sibling registries have shipped under the same convention: ISO 3166 and ISO 10383. Three independent implementations of the shared release pattern exist, and [`RELEASE_PATTERN.md`](./RELEASE_PATTERN.md) documents what they share.

Remaining work is deferred with concrete triggers:

- **Wrapper publication to PyPI, npm, and crates.io** — when a downstream consumer needs a package-registry install rather than a repository clone.
- **Exchange Calendar** — the fourth registry, waiting on a third per-push workflow before the poll-all-runs check becomes relevant.
- **Asset Identifiers and Corporate Actions** — convention adoption when each ships its next release.
- **Additional cross-registry join edges** — when a downstream registry adds a currency field that references `iso4217.code`.
- **Per-currency start dates** — if a primary source ever exists, `code_lifetime.from` and an introduction date for active currencies would let the registry answer "did this currency exist on this date?".

None are imminent. The registry layer is done.

*One source of truth per standard. One consumption pattern across all of them.*
