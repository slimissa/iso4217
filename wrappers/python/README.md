# ISO 4217 Currency Registry — Python Wrapper

A zero-dependency Python interface to the canonical [ISO 4217 currency registry](https://github.com/slimissa/iso4217). Provides `Currency` and `CurrencyRegistry` classes with full type hints, minor/major unit conversion, peg information, and country relationship lookup.

```python
from iso4217 import currency, pegged_to

usd = currency("USD")
print(usd.to_minor(100.50))   # 10050 (cents)
print(usd.from_minor(10050))  # 100.5 (dollars)
print(usd.format(100.50))     # "$100.50"

# Find all currencies pegged to USD
for c in pegged_to("USD"):
    print(f"{c.code} pegged at {c.peg_rate} since {c.pegged_since}")
```

---

## Installation

```bash
pip install iso4217-registry
```

No dependencies. Works on Python 3.8+ anywhere.

---

## Quick Start

### Look up a currency

```python
from iso4217 import CurrencyRegistry

registry = CurrencyRegistry()

# Active ISO 4217 currency
usd = registry.active("USD")
eur = registry.active("EUR")

# Any currency (active, withdrawn, or non-ISO like BTC)
btc = registry.currency("BTC")

# Check existence
"JPY" in registry  # True
"XXX" in registry  # False
```

### Basic properties

```python
jpy = registry.active("JPY")

jpy.code          # "JPY"
jpy.numeric       # "392"
jpy.name          # "Japanese Yen"
jpy.minor_units   # 0  (no subdivision)
jpy.symbol        # "¥"
jpy.entity        # "Japan"
jpy.central_bank  # "Bank of Japan"
```

### Minor/major unit conversion

```python
usd = registry.active("USD")
kwd = registry.active("KWD")
btc = registry.currency("BTC")

# Major to minor (float → int)
usd.to_minor(100.50)      # 10050  (dollars → cents)
kwd.to_minor(1.500)       # 1500   (dinars → fils)
btc.to_minor(0.00000001)  # 1      (BTC → satoshis)

# Minor to major (int → float)
usd.from_minor(10050)     # 100.5
jpy = registry.active("JPY")
jpy.from_minor(500)       # 500.0  (no subdivision)
```

### Formatting

```python
usd.format(100.50)   # "$100.50"
jpy.format(500)      # "¥500"
eur.format(1234.56)  # "€1,234.56"
```

### Peg information

```python
aed = registry.active("AED")

aed.is_pegged         # True
aed.is_independent    # False
aed.pegged_to         # "USD"
aed.peg_rate          # 3.6725
aed.pegged_since      # "1997-11-01"
aed.peg_band_pct      # 0.0  (fixed peg)

# Special cases
kwd = registry.active("KWD")
kwd.pegged_to         # "Currency basket"
kwd.peg_rate          # None  (undisclosed basket)

dkk = registry.active("DKK")
dkk.pegged_to         # "EUR"
dkk.peg_band_pct      # 2.25  (ERM II band)
```

### Country relationships

```python
usd = registry.active("USD")

for country in usd.countries:
    print(f"{country['name']} ({country['code']}): {country['relationship']}")

# United States (US): issuing
# Ecuador (EC): adopting
# Panama (PA): adopting
# Puerto Rico (PR): territory
# ...

# Filter by relationship type
usd.issuing_countries()   # Only the sovereign issuer
usd.adopting_countries()  # Dollarized/euroized countries
```

### Filtering and queries

```python
# All currencies pegged to EUR
eur_pegged = registry.pegged_to("EUR")

# All independently floating currencies
independent = registry.independent()

# All currencies with 3 minor units (dinar currencies)
three_decimal = registry.with_minor_units(3)

# Currencies issued by Switzerland
swiss = registry.issued_by("CH")

# Currencies used in Liechtenstein
liechtenstein = registry.used_in("LI")
```

### Summary statistics

```python
registry.summary()
# {
#     "version": "1.0.0",
#     "updated": "2026-07-29",
#     "amendment": 179,
#     "active_currencies": 61,
#     "withdrawn_currencies": 24,
#     "non_iso_currencies": 12,
#     "pegged_currencies": 11,
#     "independent_currencies": 50,
#     "minor_units_distribution": {0: 5, 2: 49, 3: 7},
# }
```

### Historical currencies

```python
dem = registry.withdrawn("DEM")

dem.code             # "DEM"
dem.name             # "German Mark"
dem.withdrawn_date   # "1999-01-01"
dem.replaced_by      # "EUR"
dem.conversion_rate  # 1.95583

# Normalize historical prices
historical_price_dem = 100.0
historical_price_eur = historical_price_dem / dem.conversion_rate
```

### Non-ISO currencies (crypto, commodities)

```python
btc = registry.currency("BTC")
btc.minor_units    # 8
btc.to_minor(0.5)  # 50000000

eth = registry.currency("ETH")
eth.minor_units    # 18

gold = registry.currency("XAU")
gold.type          # "commodity"
```

---

## Module-level convenience

For quick scripts and notebooks, use the module-level functions:

```python
from iso4217 import currency, active, pegged_to, all_active

# Quick lookups (case-insensitive)
usd = currency("usd")
btc = currency("BTC")

# Only active ISO currencies
eur = active("EUR")

# Filter pegged currencies
usd_pegged = pegged_to("USD")

# Iterate all active
for c in all_active():
    if c.is_pegged:
        print(f"{c.code}: pegged to {c.pegged_to}")
```

---

## Registry file location

The wrapper finds `iso4217.json` automatically:

1. Explicit path: `CurrencyRegistry("/path/to/iso4217.json")`
2. Same directory as the module
3. Project root (two levels up from `wrappers/python/`)
4. Current working directory

If you install via pip, the JSON is bundled with the package and found automatically.

---

## API Reference

### `CurrencyRegistry`

| Method | Returns | Description |
|--------|---------|-------------|
| `CurrencyRegistry(path=None)` | `CurrencyRegistry` | Load registry from JSON file |
| `.currency(code)` | `Currency \| None` | Look up any currency (active, withdrawn, non-ISO) |
| `.active(code)` | `Currency \| None` | Look up an active ISO 4217 currency |
| `.withdrawn(code)` | `Currency \| None` | Look up a withdrawn ISO 4217 currency |
| `.non_iso(code)` | `Currency \| None` | Look up a non-ISO currency |
| `.all_active()` | `List[Currency]` | All active ISO currencies |
| `.all_withdrawn()` | `List[Currency]` | All withdrawn ISO currencies |
| `.all_non_iso()` | `List[Currency]` | All non-ISO currencies |
| `.all_currencies()` | `List[Currency]` | All currencies across all categories |
| `.pegged_to(anchor)` | `List[Currency]` | Currencies pegged to a specific anchor |
| `.independent()` | `List[Currency]` | Independently floating currencies |
| `.with_minor_units(n)` | `List[Currency]` | Currencies with N minor units |
| `.issued_by(cc)` | `List[Currency]` | Currencies issued by a country |
| `.used_in(cc)` | `List[Currency]` | Currencies used in a country |
| `.summary()` | `Dict` | Registry statistics |

**Properties:** `version`, `updated`, `amendment`, `amendment_date`, `active_count`, `withdrawn_count`, `non_iso_count`, `pegged_count`, `independent_count`

**Supports:** `len(registry)`, `"USD" in registry`, `for c in registry`

### `Currency`

| Property | Type | Description |
|----------|------|-------------|
| `.code` | `str` | ISO 4217 alphabetic code |
| `.numeric` | `str` | ISO 4217 numeric code (3 digits) |
| `.name` | `str` | Official English name |
| `.minor_units` | `int` | Decimal places (0, 2, 3, 8, 18) |
| `.symbol` | `str` | Display symbol |
| `.entity` | `str` | Issuing entity |
| `.central_bank` | `str` | Central bank name |
| `.pegged_to` | `str \| None` | Anchor currency or basket |
| `.pegged_since` | `str \| None` | Peg establishment date |
| `.peg_rate` | `float \| None` | Official peg rate |
| `.peg_band_pct` | `float \| None` | Peg band percentage |
| `.is_independent` | `bool` | Floats independently |
| `.is_pegged` | `bool` | Convenience: `pegged_to is not None` |
| `.note` | `str \| None` | Special case note |
| `.countries` | `List[Dict]` | Country references |
| `.withdrawn_date` | `str \| None` | Withdrawal date (withdrawn only) |
| `.replaced_by` | `str \| None` | Replacement code (withdrawn only) |
| `.conversion_rate` | `float \| None` | Conversion rate (withdrawn only) |

| Method | Returns | Description |
|--------|---------|-------------|
| `.to_minor(amount)` | `int` | Major → minor units |
| `.from_minor(amount)` | `float` | Minor → major units |
| `.format(amount)` | `str` | Formatted with symbol |
| `.issuing_countries()` | `List[Dict]` | Sovereign issuing countries |
| `.adopting_countries()` | `List[Dict]` | Countries that adopted this currency |
| `.to_dict()` | `Dict` | Raw data dictionary |

---

## Development

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217/wrappers/python
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy iso4217.py

# Validate registry data
python ../../tools/validate.py
```

---

## License

Apache 2.0 — same as the [ISO 4217 registry](https://github.com/slimissa/iso4217). Use it anywhere.
