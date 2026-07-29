# ISO 4217 Currency Registry — Go Module

A zero-dependency Go interface to the canonical [ISO 4217 currency registry](https://github.com/slimissa/iso4217). Provides `Currency` and `CurrencyRegistry` types with minor/major unit conversion, peg information, and country relationship lookup.

The registry data is embedded at compile time via `//go:embed`. No file I/O at runtime. No network calls. No dependencies beyond the standard library.

```go
package main

import (
    "fmt"
    iso4217 "github.com/slimissa/iso4217-go"
)

func main() {
    registry, err := iso4217.Load()
    if err != nil {
        panic(err)
    }

    usd := registry.Active("USD")
    fmt.Println(usd.ToMinor(100.50))  // 10050
    fmt.Println(usd.Format(100.50))   // "$100.50"

    // Find all currencies pegged to USD
    for _, c := range registry.PeggedTo("USD") {
        fmt.Printf("%s pegged at %v since %s\n",
            c.Code, *c.PegRate, *c.PeggedSince)
    }
}
```

---

## Installation

```bash
go get github.com/slimissa/iso4217-go
```

Zero dependencies. Standard library only. Works on Go 1.21+.

---

## Quick Start

### Look up a currency

```go
import iso4217 "github.com/slimissa/iso4217-go"

registry, err := iso4217.Load()
if err != nil {
    panic(err)
}

// Active ISO 4217 currency
usd := registry.Active("USD")
eur := registry.Active("EUR")

// Any currency (active, withdrawn, or non-ISO like BTC)
btc := registry.Currency("BTC")

// Check existence
fmt.Println(registry.Contains("JPY"))  // true
fmt.Println(registry.Contains("XXX"))  // false

// Case-insensitive lookup
fmt.Println(registry.Active("usd") != nil)  // true
fmt.Println(registry.Active("Usd") != nil)  // true
```

### Basic properties

```go
jpy := registry.Active("JPY")

fmt.Println(jpy.Code)         // "JPY"
fmt.Println(jpy.Numeric)      // "392"
fmt.Println(jpy.Name)         // "Japanese Yen"
fmt.Println(jpy.MinorUnits)   // 0  (no subdivision)
fmt.Println(jpy.Symbol)       // "¥"
fmt.Println(jpy.Entity)       // "Japan"
fmt.Println(jpy.CentralBank)  // "Bank of Japan"
```

### Minor/major unit conversion

```go
usd := registry.Active("USD")
kwd := registry.Active("KWD")
btc := registry.Currency("BTC")

// Major to minor (float64 → int64)
usd.ToMinor(100.50)        // 10050  (dollars → cents)
kwd.ToMinor(1.500)         // 1500   (dinars → fils)
btc.ToMinor(0.000_000_01)  // 1      (BTC → satoshis)

// Minor to major (int64 → float64)
usd.FromMinor(10050)       // 100.5
jpy := registry.Active("JPY")
jpy.FromMinor(500)         // 500.0  (no subdivision)
```

### Formatting

```go
usd.Format(100.50)    // "$100.50"
jpy.Format(500.0)     // "¥500"
eur.Format(1234.56)   // "€1234.56"
```

### Peg information

```go
aed := registry.Active("AED")

fmt.Println(aed.IsPegged())         // true
fmt.Println(aed.IsIndependent)      // false
fmt.Println(*aed.PeggedTo)          // "USD"
fmt.Println(*aed.PegRate)           // 3.6725
fmt.Println(*aed.PeggedSince)       // "1997-11-01"
fmt.Println(*aed.PegBandPct)        // 0.0  (fixed peg)

// Special cases
kwd := registry.Active("KWD")
fmt.Println(*kwd.PeggedTo)          // "Currency basket"
fmt.Println(kwd.PegRate)            // nil  (undisclosed basket)

dkk := registry.Active("DKK")
fmt.Println(*dkk.PeggedTo)          // "EUR"
fmt.Println(*dkk.PegBandPct)        // 2.25  (ERM II band)
```

### Country relationships

```go
usd := registry.Active("USD")

for _, country := range usd.Countries {
    fmt.Printf("%s (%s): %s\n", country.Name, country.Code, country.Relationship)
}

// United States (US): issuing
// Ecuador (EC): adopting
// Panama (PA): adopting
// Puerto Rico (PR): territory
// ...

// Filter by relationship type
issuers := usd.IssuingCountries()    // Only the sovereign issuer
adopters := usd.AdoptingCountries()  // Dollarized/euroized countries
```

### Filtering and queries

```go
// All currencies pegged to EUR
eurPegged := registry.PeggedTo("EUR")

// All independently floating currencies
independent := registry.Independent()

// All currencies with 3 minor units (dinar currencies)
threeDecimal := registry.WithMinorUnits(3)

// Currencies issued by Switzerland
swiss := registry.IssuedBy("CH")

// Currencies used in Liechtenstein
liechtenstein := registry.UsedIn("LI")
```

### Summary statistics

```go
summary := registry.Summary()

fmt.Printf("Version: %s\n", summary.Version)
fmt.Printf("Active: %d\n", summary.ActiveCurrencies)
fmt.Printf("Pegged: %d\n", summary.PeggedCurrencies)
fmt.Printf("Independent: %d\n", summary.IndependentCurrencies)

// Distribution of minor units
for units, count := range summary.MinorUnitsDistribution {
    fmt.Printf("  minor_units=%d: %d currencies\n", units, count)
}
```

### Historical currencies

```go
dem := registry.Withdrawn("DEM")

fmt.Println(dem.Name)                  // "German Mark"
fmt.Println(*dem.WithdrawnDate)        // "1999-01-01"
fmt.Println(*dem.ReplacedBy)           // "EUR"
fmt.Println(*dem.ConversionRate)       // 1.95583

// Normalize historical prices
historicalPriceDEM := 100.0
historicalPriceEUR := historicalPriceDEM / *dem.ConversionRate
```

### Non-ISO currencies (crypto, commodities)

```go
btc := registry.Currency("BTC")
fmt.Println(btc.MinorUnits)    // 8
fmt.Println(btc.ToMinor(0.5))  // 50000000

eth := registry.Currency("ETH")
fmt.Println(eth.MinorUnits)    // 18

gold := registry.NonISO("XAU")
fmt.Println(*gold.Type)        // "commodity"
```

---

## Singleton Pattern

`Load()` returns a singleton — the registry is parsed once on first call and cached. Subsequent calls return the same instance with no additional cost.

```go
// Safe to call from multiple goroutines
go func() {
    r, _ := iso4217.Load()
    // use r
}()

go func() {
    r, _ := iso4217.Load()
    // same instance, no re-parsing
}()
```

Use `MustLoad()` for package-level initialization where a failure is fatal:

```go
var registry = iso4217.MustLoad()

func init() {
    fmt.Printf("Loaded %d active currencies\n", registry.ActiveCount())
}
```

---

## Compile-Time Embedding

The registry data is embedded directly into your binary:

```go
//go:embed ../../../iso4217.json
var registryJSON []byte
```

This means:

- **Zero file I/O at runtime** — the data lives in the binary's data segment
- **Zero network calls** — works offline, in containers, in WebAssembly
- **Zero configuration** — no `ISO4217_PATH` env var, no config file
- **Fast startup** — parsed once, then pure `map[string]*Currency` lookups

The tradeoff is binary size — the registry JSON is ~80KB uncompressed. With Go's efficient binary format, the actual impact is negligible.

---

## API Reference

### `CurrencyRegistry`

| Method | Returns | Description |
|--------|---------|-------------|
| `Load()` | `(*CurrencyRegistry, error)` | Load registry from embedded JSON (singleton) |
| `MustLoad()` | `*CurrencyRegistry` | Load or panic — for package-level init |
| `.Currency(code)` | `*Currency` | Look up any currency (active, withdrawn, non-ISO) |
| `.Active(code)` | `*Currency` | Look up an active ISO 4217 currency |
| `.Withdrawn(code)` | `*Currency` | Look up a withdrawn ISO 4217 currency |
| `.NonISO(code)` | `*Currency` | Look up a non-ISO currency |
| `.AllActive()` | `[]*Currency` | All active ISO currencies |
| `.AllWithdrawn()` | `[]*Currency` | All withdrawn ISO currencies |
| `.AllNonISO()` | `[]*Currency` | All non-ISO currencies |
| `.AllCurrencies()` | `[]*Currency` | All currencies across all categories |
| `.PeggedTo(anchor)` | `[]*Currency` | Currencies pegged to a specific anchor |
| `.Independent()` | `[]*Currency` | Independently floating currencies |
| `.WithMinorUnits(n)` | `[]*Currency` | Currencies with N minor units |
| `.IssuedBy(cc)` | `[]*Currency` | Currencies issued by a country |
| `.UsedIn(cc)` | `[]*Currency` | Currencies used in a country |
| `.Contains(code)` | `bool` | Check if a currency code exists |
| `.Summary()` | `RegistrySummary` | Registry statistics |

**Accessors:** `Version()`, `Updated()`, `Amendment()`, `AmendmentDate()`, `ActiveCount()`, `WithdrawnCount()`, `NonISOCount()`, `PeggedCount()`, `IndependentCount()`

### `Currency`

| Field | Type | Description |
|-------|------|-------------|
| `.Code` | `string` | ISO 4217 alphabetic code |
| `.Numeric` | `string` | ISO 4217 numeric code (3 digits) |
| `.Name` | `string` | Official English name |
| `.MinorUnits` | `int` | Decimal places (0, 2, 3, 8, 18) |
| `.Symbol` | `string` | Display symbol |
| `.Entity` | `string` | Issuing entity |
| `.CentralBank` | `string` | Central bank name |
| `.PeggedTo` | `*string` | Anchor currency or basket, or nil |
| `.PeggedSince` | `*string` | Peg establishment date, or nil |
| `.PegRate` | `*float64` | Official peg rate, or nil |
| `.PegBandPct` | `*float64` | Peg band percentage, or nil |
| `.IsIndependent` | `bool` | Floats independently |
| `.Note` | `*string` | Special case note, or nil |
| `.Countries` | `[]Country` | Country references |
| `.WithdrawnDate` | `*string` | Withdrawal date (withdrawn only) |
| `.ReplacedBy` | `*string` | Replacement code (withdrawn only) |
| `.ConversionRate` | `*float64` | Conversion rate (withdrawn only) |
| `.Type` | `*string` | Type for non-ISO currencies |
| `.MarketCapRank` | `*int` | Market cap rank (crypto/stablecoins) |
| `.PegMechanism` | `*string` | Peg mechanism (stablecoins) |

| Method | Returns | Description |
|--------|---------|-------------|
| `.IsPegged()` | `bool` | True if pegged to something |
| `.IssuingCountries()` | `[]Country` | Sovereign issuing countries |
| `.AdoptingCountries()` | `[]Country` | Countries that adopted this currency |
| `.ToMinor(amount)` | `int64` | Major → minor units |
| `.FromMinor(amount)` | `float64` | Minor → major units |
| `.Format(amount)` | `string` | Formatted with symbol |
| `.String()` | `string` | Human-readable representation |

### `Country`

| Field | Type | Description |
|-------|------|-------------|
| `.Code` | `string` | ISO 3166-1 alpha-2 country code |
| `.Name` | `string` | Human-readable country name |
| `.Relationship` | `string` | "issuing", "adopting", "territory", "parallel", or "local_issue" |

### `RegistrySummary`

| Field | Type | Description |
|-------|------|-------------|
| `.Version` | `string` | Registry version |
| `.Updated` | `string` | Last update date |
| `.Amendment` | `int` | ISO amendment number |
| `.ActiveCurrencies` | `int` | Count of active currencies |
| `.WithdrawnCurrencies` | `int` | Count of withdrawn currencies |
| `.NonISOCurrencies` | `int` | Count of non-ISO currencies |
| `.PeggedCurrencies` | `int` | Count of pegged currencies |
| `.IndependentCurrencies` | `int` | Count of independent currencies |
| `.MinorUnitsDistribution` | `map[int]int` | Distribution of minor_units |

---

## Pointer Semantics for Optional Fields

Fields that may not exist use Go pointer types:

```go
// Currency with a peg
aed.PeggedTo   // *string → &"USD"
aed.PegRate    // *float64 → &3.6725

// Currency without a peg
usd.PeggedTo   // *string → nil
usd.PegRate    // *float64 → nil

// Checking
if c.PeggedTo != nil {
    fmt.Println("Pegged to:", *c.PeggedTo)
}
```

This is idiomatic Go — `nil` means "not present", a pointer means "present with this value". It distinguishes between "USD peg rate is 0.0" (which would be wrong) and "no peg rate" (which is correct for floating currencies).

---

## Differences from other wrappers

This Go module follows Go conventions while maintaining the same behavior as the [Python](https://github.com/slimissa/iso4217/tree/main/wrappers/python), [JavaScript](https://github.com/slimissa/iso4217/tree/main/wrappers/javascript), and [Rust](https://github.com/slimissa/iso4217/tree/main/wrappers/rust) wrappers:

| Feature | Python | JavaScript | Rust | Go |
|---------|--------|------------|------|-----|
| Property naming | `minor_units` | `minorUnits` | `minor_units` | `MinorUnits` |
| Null/none | `None` | `null` | `Option<T>` | `*T` (nil) |
| Lookup method | `registry.non_iso("BTC")` | `registry.nonIso("BTC")` | `registry.non_iso("BTC")` | `registry.NonISO("BTC")` |
| Existence check | `"USD" in registry` | `registry.has("USD")` | `registry.contains("USD")` | `registry.Contains("USD")` |
| Loading | File discovery at runtime | File discovery at runtime | `include_str!` at compile time | `//go:embed` at compile time |
| Singleton | Lazy module-level | Explicit `new` | Explicit `load()` | `sync.Once` in `Load()` |
| Error handling | Exceptions | Exceptions | `Result<T, String>` / panics | `error` return / panics |

---

## Development

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217/wrappers/go

# Build
go build ./...

# Run tests
go test ./...

# Run tests with verbose output
go test -v ./...

# Run benchmarks
go test -bench=. -benchmem ./...

# Run tests with race detector
go test -race ./...
```

---

## License

Apache 2.0 — same as the [ISO 4217 registry](https://github.com/slimissa/iso4217). Use it anywhere.