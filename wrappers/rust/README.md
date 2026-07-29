# ISO 4217 Currency Registry — Rust Crate

A zero-dependency Rust interface to the canonical [ISO 4217 currency registry](https://github.com/slimissa/iso4217). Provides `Currency` and `CurrencyRegistry` types with minor/major unit conversion, peg information, and country relationship lookup.

The registry data is embedded at compile time via `include_str!()`. No file I/O at runtime. No network calls. No dependencies beyond `serde` and `serde_json` for JSON parsing.

```rust
use iso4217::CurrencyRegistry;

let registry = CurrencyRegistry::load().expect("Failed to load registry");
let usd = registry.active("USD").expect("USD not found");

assert_eq!(usd.code, "USD");
assert_eq!(usd.to_minor(100.50), 10050);
assert_eq!(usd.format(100.50), "$100.50");

// Find all currencies pegged to USD
for c in registry.pegged_to("USD") {
    println!("{} pegged at {} since {}",
        c.code,
        c.peg_rate.unwrap_or(0.0),
        c.pegged_since.as_deref().unwrap_or("unknown")
    );
}
```

---

## Installation

Add to your `Cargo.toml`:

```toml
[dependencies]
iso4217 = "1.0"
```

Or:

```bash
cargo add iso4217
```

The registry JSON is embedded in the binary at compile time — nothing to download, no files to ship separately.

---

## Quick Start

### Look up a currency

```rust
use iso4217::CurrencyRegistry;

let registry = CurrencyRegistry::load()?;

// Active ISO 4217 currency
let usd = registry.active("USD");
let eur = registry.active("EUR");

// Any currency (active, withdrawn, or non-ISO like BTC)
let btc = registry.currency("BTC");

// Check existence
assert!(registry.contains("JPY"));
assert!(!registry.contains("XXX"));

// Case-insensitive lookup
assert!(registry.active("usd").is_some());
assert!(registry.active("Usd").is_some());
```

### Basic properties

```rust
let jpy = registry.active("JPY").unwrap();

assert_eq!(jpy.code, "JPY");
assert_eq!(jpy.numeric, "392");
assert_eq!(jpy.name, "Japanese Yen");
assert_eq!(jpy.minor_units, 0);  // no subdivision
assert_eq!(jpy.symbol, "¥");
assert_eq!(jpy.entity, "Japan");
assert_eq!(jpy.central_bank, "Bank of Japan");
```

### Minor/major unit conversion

```rust
let usd = registry.active("USD").unwrap();
let kwd = registry.active("KWD").unwrap();
let btc = registry.currency("BTC").unwrap();

// Major to minor (f64 → i64)
usd.to_minor(100.50);        // 10050  (dollars → cents)
kwd.to_minor(1.500);         // 1500   (dinars → fils)
btc.to_minor(0.000_000_01);  // 1      (BTC → satoshis)

// Minor to major (i64 → f64)
usd.from_minor(10050);       // 100.5
let jpy = registry.active("JPY").unwrap();
jpy.from_minor(500);         // 500.0  (no subdivision)
```

### Formatting

```rust
usd.format(100.50);          // "$100.50"
jpy.format(500.0);           // "¥500"
eur.format(1234.56);         // "€1,234.56"
```

### Peg information

```rust
let aed = registry.active("AED").unwrap();

assert!(aed.is_pegged());
assert!(!aed.is_independent);
assert_eq!(aed.pegged_to.as_deref(), Some("USD"));
assert_eq!(aed.peg_rate, Some(3.6725));
assert_eq!(aed.pegged_since.as_deref(), Some("1997-11-01"));
assert_eq!(aed.peg_band_pct, Some(0.0));  // fixed peg

// Special cases
let kwd = registry.active("KWD").unwrap();
assert_eq!(kwd.pegged_to.as_deref(), Some("Currency basket"));
assert_eq!(kwd.peg_rate, None);  // undisclosed basket

let dkk = registry.active("DKK").unwrap();
assert_eq!(dkk.pegged_to.as_deref(), Some("EUR"));
assert_eq!(dkk.peg_band_pct, Some(2.25));  // ERM II band
```

### Country relationships

```rust
let usd = registry.active("USD").unwrap();

for country in &usd.countries {
    println!("{} ({}): {}", country.name, country.code, country.relationship);
}

// United States (US): issuing
// Ecuador (EC): adopting
// Panama (PA): adopting
// Puerto Rico (PR): territory
// ...

// Filter by relationship type
let issuers = usd.issuing_countries();    // Only the sovereign issuer
let adopters = usd.adopting_countries();  // Dollarized/euroized countries
```

### Filtering and queries

```rust
// All currencies pegged to EUR
let eur_pegged = registry.pegged_to("EUR");

// All independently floating currencies
let independent = registry.independent();

// All currencies with 3 minor units (dinar currencies)
let three_decimal = registry.with_minor_units(3);

// Currencies issued by Switzerland
let swiss = registry.issued_by("CH");

// Currencies used in Liechtenstein
let liechtenstein = registry.used_in("LI");
```

### Summary statistics

```rust
let summary = registry.summary();

println!("Version: {}", summary.version);
println!("Active currencies: {}", summary.active_currencies);
println!("Pegged currencies: {}", summary.pegged_currencies);
println!("Independent currencies: {}", summary.independent_currencies);

// Distribution of minor units
for (units, count) in &summary.minor_units_distribution {
    println!("  minor_units={}: {} currencies", units, count);
}
```

### Iteration

```rust
// Iterate over all active currencies
for c in registry.iter() {
    if c.is_pegged() {
        println!("{}: pegged to {:?}", c.code, c.pegged_to);
    }
}

// Or collect into a Vec
let all: Vec<&Currency> = registry.all_active();
println!("{} active currencies", all.len());
```

### Historical currencies

```rust
let dem = registry.withdrawn("DEM").expect("DEM should exist");

assert_eq!(dem.name, "German Mark");
assert_eq!(dem.withdrawn_date.as_deref(), Some("1999-01-01"));
assert_eq!(dem.replaced_by.as_deref(), Some("EUR"));
assert_eq!(dem.conversion_rate, Some(1.95583));

// Normalize historical prices
let historical_price_dem = 100.0;
let historical_price_eur = historical_price_dem / dem.conversion_rate.unwrap();
```

### Non-ISO currencies (crypto, commodities)

```rust
let btc = registry.currency("BTC").unwrap();
assert_eq!(btc.minor_units, 8);
assert_eq!(btc.to_minor(0.5), 50_000_000);

let eth = registry.currency("ETH").unwrap();
assert_eq!(eth.minor_units, 18);

let gold = registry.non_iso("XAU").unwrap();
assert_eq!(gold.currency_type.as_deref(), Some("commodity"));
```

---

## Compile-Time Embedding

The registry data is embedded directly into your binary:

```rust
const REGISTRY_JSON: &str = include_str!("../../../iso4217.json");
```

This means:

- **Zero file I/O at runtime** — the data lives in `.rodata`
- **Zero network calls** — works offline, in containers, in WASM
- **Zero configuration** — no `ISO4217_PATH` env var, no config file
- **Fast startup** — parsed once, then pure `HashMap` lookups

The tradeoff is binary size — the registry JSON is ~80KB uncompressed. With `opt-level = "s"` and `lto = true`, the compiled impact is minimal.

---

## API Reference

### `CurrencyRegistry`

| Method | Returns | Description |
|--------|---------|-------------|
| `CurrencyRegistry::load()` | `Result<Self, String>` | Load registry from embedded JSON |
| `.currency(code)` | `Option<&Currency>` | Look up any currency (active, withdrawn, non-ISO) |
| `.active(code)` | `Option<&Currency>` | Look up an active ISO 4217 currency |
| `.withdrawn(code)` | `Option<&Currency>` | Look up a withdrawn ISO 4217 currency |
| `.non_iso(code)` | `Option<&Currency>` | Look up a non-ISO currency |
| `.all_active()` | `Vec<&Currency>` | All active ISO currencies |
| `.all_withdrawn()` | `Vec<&Currency>` | All withdrawn ISO currencies |
| `.all_non_iso()` | `Vec<&Currency>` | All non-ISO currencies |
| `.all_currencies()` | `Vec<&Currency>` | All currencies across all categories |
| `.pegged_to(anchor)` | `Vec<&Currency>` | Currencies pegged to a specific anchor |
| `.independent()` | `Vec<&Currency>` | Independently floating currencies |
| `.with_minor_units(n)` | `Vec<&Currency>` | Currencies with N minor units |
| `.issued_by(cc)` | `Vec<&Currency>` | Currencies issued by a country |
| `.used_in(cc)` | `Vec<&Currency>` | Currencies used in a country |
| `.contains(code)` | `bool` | Check if a currency code exists |
| `.iter()` | `impl Iterator<Item=&Currency>` | Iterate over all active currencies |
| `.summary()` | `RegistrySummary` | Registry statistics |

**Accessors:** `version()`, `updated()`, `amendment()`, `amendment_date()`, `active_count()`, `withdrawn_count()`, `non_iso_count()`, `pegged_count()`, `independent_count()`

### `Currency`

| Field | Type | Description |
|-------|------|-------------|
| `.code` | `String` | ISO 4217 alphabetic code |
| `.numeric` | `String` | ISO 4217 numeric code (3 digits) |
| `.name` | `String` | Official English name |
| `.minor_units` | `u8` | Decimal places (0, 2, 3, 8, 18) |
| `.symbol` | `String` | Display symbol |
| `.entity` | `String` | Issuing entity |
| `.central_bank` | `String` | Central bank name |
| `.pegged_to` | `Option<String>` | Anchor currency or basket |
| `.pegged_since` | `Option<String>` | Peg establishment date |
| `.peg_rate` | `Option<f64>` | Official peg rate |
| `.peg_band_pct` | `Option<f64>` | Peg band percentage |
| `.is_independent` | `bool` | Floats independently |
| `.note` | `Option<String>` | Special case note |
| `.countries` | `Vec<Country>` | Country references |
| `.withdrawn_date` | `Option<String>` | Withdrawal date (withdrawn only) |
| `.replaced_by` | `Option<String>` | Replacement code (withdrawn only) |
| `.conversion_rate` | `Option<f64>` | Conversion rate (withdrawn only) |
| `.currency_type` | `Option<String>` | Type for non-ISO currencies |
| `.market_cap_rank` | `Option<u32>` | Market cap rank (crypto/stablecoins) |
| `.peg_mechanism` | `Option<String>` | Peg mechanism (stablecoins) |

| Method | Returns | Description |
|--------|---------|-------------|
| `.is_pegged()` | `bool` | `true` if pegged to something |
| `.issuing_countries()` | `Vec<&Country>` | Sovereign issuing countries |
| `.adopting_countries()` | `Vec<&Country>` | Countries that adopted this currency |
| `.to_minor(amount)` | `i64` | Major → minor units |
| `.from_minor(amount)` | `f64` | Minor → major units |
| `.format(amount)` | `String` | Formatted with symbol |

### `Country`

| Field | Type | Description |
|-------|------|-------------|
| `.code` | `String` | ISO 3166-1 alpha-2 country code |
| `.name` | `String` | Human-readable country name |
| `.relationship` | `String` | "issuing", "adopting", "territory", "parallel", or "local_issue" |

### `RegistrySummary`

| Field | Type | Description |
|-------|------|-------------|
| `.version` | `String` | Registry version |
| `.updated` | `String` | Last update date |
| `.amendment` | `u32` | ISO amendment number |
| `.active_currencies` | `usize` | Count of active currencies |
| `.withdrawn_currencies` | `usize` | Count of withdrawn currencies |
| `.non_iso_currencies` | `usize` | Count of non-ISO currencies |
| `.pegged_currencies` | `usize` | Count of pegged currencies |
| `.independent_currencies` | `usize` | Count of independent currencies |
| `.minor_units_distribution` | `HashMap<u8, usize>` | Distribution of minor_units |

---

## Differences from other wrappers

This Rust crate follows Rust conventions while maintaining the same behavior as the [Python](https://github.com/slimissa/iso4217/tree/main/wrappers/python) and [JavaScript](https://github.com/slimissa/iso4217/tree/main/wrappers/javascript) wrappers:

| Feature | Python | JavaScript | Rust |
|---------|--------|------------|------|
| Property naming | `minor_units` | `minorUnits` | `minor_units` |
| Null/none | `None` | `null` | `Option<T>` |
| Lookup method | `registry.non_iso("BTC")` | `registry.nonIso("BTC")` | `registry.non_iso("BTC")` |
| Existence check | `"USD" in registry` | `registry.has("USD")` | `registry.contains("USD")` |
| Loading | File discovery at runtime | File discovery at runtime | Embedded at compile time |
| Iteration | `for c in registry:` | `for (const c of registry)` | `for c in registry.iter()` |
| Error handling | Exceptions | Exceptions | `Result<T, String>` / panics |

---

## Development

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217/wrappers/rust

# Build
cargo build

# Run tests
cargo test

# Run with release optimizations
cargo build --release

# Generate docs
cargo doc --open
```

---

## License

Apache 2.0 — same as the [ISO 4217 registry](https://github.com/slimissa/iso4217). Use it anywhere.
