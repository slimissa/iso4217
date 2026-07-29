# ISO 4217 Currency Registry — JavaScript/Node.js Wrapper

A zero-dependency JavaScript interface to the canonical [ISO 4217 currency registry](https://github.com/slimissa/iso4217). Provides `Currency` and `CurrencyRegistry` classes with minor/major unit conversion, peg information, and country relationship lookup.

```javascript
const { CurrencyRegistry } = require('iso4217-registry');

const registry = new CurrencyRegistry();
const usd = registry.currency('USD');

console.log(usd.toMinor(100.50));   // 10050 (cents)
console.log(usd.fromMinor(10050));  // 100.5 (dollars)
console.log(usd.format(100.50));    // "$100.50"

// Find all currencies pegged to USD
const usdPegged = registry.peggedTo('USD');
for (const c of usdPegged) {
  console.log(`${c.code} pegged at ${c.pegRate} since ${c.peggedSince}`);
}
```

---

## Installation

```bash
npm install iso4217-registry
```

Zero dependencies. Works on Node.js 12+ anywhere.

---

## Quick Start

### Look up a currency

```javascript
const { CurrencyRegistry } = require('iso4217-registry');
const registry = new CurrencyRegistry();

// Active ISO 4217 currency
const usd = registry.active('USD');
const eur = registry.active('EUR');

// Any currency (active, withdrawn, or non-ISO like BTC)
const btc = registry.currency('BTC');

// Check existence
registry.has('JPY');  // true
registry.has('XXX');  // false
```

### Basic properties

```javascript
const jpy = registry.active('JPY');

jpy.code;          // "JPY"
jpy.numeric;       // "392"
jpy.name;          // "Japanese Yen"
jpy.minorUnits;    // 0  (no subdivision)
jpy.symbol;        // "¥"
jpy.entity;        // "Japan"
jpy.centralBank;   // "Bank of Japan"
```

### Minor/major unit conversion

```javascript
const usd = registry.active('USD');
const kwd = registry.active('KWD');
const btc = registry.currency('BTC');

// Major to minor (float → int)
usd.toMinor(100.50);       // 10050  (dollars → cents)
kwd.toMinor(1.500);        // 1500   (dinars → fils)
btc.toMinor(0.00000001);   // 1      (BTC → satoshis)

// Minor to major (int → float)
usd.fromMinor(10050);      // 100.5
const jpy = registry.active('JPY');
jpy.fromMinor(500);        // 500    (no subdivision)
```

### Formatting

```javascript
usd.format(100.50);        // "$100.50"
jpy.format(500);           // "¥500"
eur.format(1234.56);       // "€1,234.56"
```

Uses `toLocaleString('en-US')` for proper thousands separators in financial contexts.

### Peg information

```javascript
const aed = registry.active('AED');

aed.isPegged;          // true
aed.isIndependent;     // false
aed.peggedTo;          // "USD"
aed.pegRate;           // 3.6725
aed.peggedSince;       // "1997-11-01"
aed.pegBandPct;        // 0.0  (fixed peg)

// Special cases
const kwd = registry.active('KWD');
kwd.peggedTo;          // "Currency basket"
kwd.pegRate;           // null  (undisclosed basket)

const dkk = registry.active('DKK');
dkk.peggedTo;          // "EUR"
dkk.pegBandPct;        // 2.25  (ERM II band)
```

### Country relationships

```javascript
const usd = registry.active('USD');

for (const country of usd.countries) {
  console.log(`${country.name} (${country.code}): ${country.relationship}`);
}

// United States (US): issuing
// Ecuador (EC): adopting
// Panama (PA): adopting
// Puerto Rico (PR): territory
// ...

// Filter by relationship type
usd.issuingCountries();   // Only the sovereign issuer
usd.adoptingCountries();  // Dollarized/euroized countries
```

### Filtering and queries

```javascript
// All currencies pegged to EUR
const eurPegged = registry.peggedTo('EUR');

// All independently floating currencies
const independent = registry.independent();

// All currencies with 3 minor units (dinar currencies)
const threeDecimal = registry.withMinorUnits(3);

// Currencies issued by Switzerland
const swiss = registry.issuedBy('CH');

// Currencies used in Liechtenstein
const liechtenstein = registry.usedIn('LI');
```

### Summary statistics

```javascript
registry.summary();
// {
//   version: "1.0.0",
//   updated: "2026-07-29",
//   amendment: 179,
//   activeCurrencies: 61,
//   withdrawnCurrencies: 24,
//   nonIsoCurrencies: 12,
//   peggedCurrencies: 11,
//   independentCurrencies: 50,
//   minorUnitsDistribution: { 0: 5, 2: 49, 3: 7 }
// }
```

### Iteration

```javascript
// Iterate over all active currencies
for (const c of registry) {
  if (c.isPegged) {
    console.log(`${c.code}: pegged to ${c.peggedTo}`);
  }
}

// Or get an array
const all = registry.allActive();
console.log(`${all.length} active currencies`);
```

### Historical currencies

```javascript
const dem = registry.withdrawn('DEM');

dem.code;              // "DEM"
dem.name;              // "German Mark"
dem.withdrawnDate;     // "1999-01-01"
dem.replacedBy;        // "EUR"
dem.conversionRate;    // 1.95583

// Normalize historical prices
const historicalPriceDEM = 100;
const historicalPriceEUR = historicalPriceDEM / dem.conversionRate;
```

### Non-ISO currencies (crypto, commodities)

```javascript
const btc = registry.currency('BTC');
btc.minorUnits;     // 8
btc.toMinor(0.5);   // 50000000

const eth = registry.currency('ETH');
eth.minorUnits;     // 18

const gold = registry.currency('XAU');
gold.type;          // "commodity"
```

---

## Registry file location

The wrapper finds `iso4217.json` automatically:

1. Explicit path: `new CurrencyRegistry('/path/to/iso4217.json')`
2. Same directory as the module
3. Project root (two levels up from `wrappers/javascript/`)
4. Current working directory

If you install via npm, the JSON is bundled with the package and found automatically.

---

## API Reference

### `CurrencyRegistry`

| Constructor / Method | Returns | Description |
|----------------------|---------|-------------|
| `new CurrencyRegistry(path?)` | `CurrencyRegistry` | Load registry from JSON file |
| `.currency(code)` | `Currency \| null` | Look up any currency (active, withdrawn, non-ISO) |
| `.active(code)` | `Currency \| null` | Look up an active ISO 4217 currency |
| `.withdrawn(code)` | `Currency \| null` | Look up a withdrawn ISO 4217 currency |
| `.nonIso(code)` | `Currency \| null` | Look up a non-ISO currency |
| `.allActive()` | `Currency[]` | All active ISO currencies |
| `.allWithdrawn()` | `Currency[]` | All withdrawn ISO currencies |
| `.allNonIso()` | `Currency[]` | All non-ISO currencies |
| `.allCurrencies()` | `Currency[]` | All currencies across all categories |
| `.peggedTo(anchor)` | `Currency[]` | Currencies pegged to a specific anchor |
| `.independent()` | `Currency[]` | Independently floating currencies |
| `.withMinorUnits(n)` | `Currency[]` | Currencies with N minor units |
| `.issuedBy(cc)` | `Currency[]` | Currencies issued by a country |
| `.usedIn(cc)` | `Currency[]` | Currencies used in a country |
| `.has(code)` | `boolean` | Check if a currency code exists |
| `.summary()` | `Object` | Registry statistics |

**Properties:** `version`, `updated`, `amendment`, `amendmentDate`, `activeCount`, `withdrawnCount`, `nonIsoCount`, `peggedCount`, `independentCount`, `size`

**Supports:** `for (const c of registry)`, `registry.has('USD')`

### `Currency`

| Property | Type | Description |
|----------|------|-------------|
| `.code` | `string` | ISO 4217 alphabetic code |
| `.numeric` | `string` | ISO 4217 numeric code (3 digits) |
| `.name` | `string` | Official English name |
| `.minorUnits` | `number` | Decimal places (0, 2, 3, 8, 18) |
| `.symbol` | `string` | Display symbol |
| `.entity` | `string` | Issuing entity |
| `.centralBank` | `string` | Central bank name |
| `.peggedTo` | `string \| null` | Anchor currency or basket |
| `.peggedSince` | `string \| null` | Peg establishment date |
| `.pegRate` | `number \| null` | Official peg rate |
| `.pegBandPct` | `number \| null` | Peg band percentage |
| `.isIndependent` | `boolean` | Floats independently |
| `.isPegged` | `boolean` | Convenience: `peggedTo !== null` |
| `.note` | `string \| null` | Special case note |
| `.countries` | `Array` | Country references |
| `.withdrawnDate` | `string \| null` | Withdrawal date (withdrawn only) |
| `.replacedBy` | `string \| null` | Replacement code (withdrawn only) |
| `.conversionRate` | `number \| null` | Conversion rate (withdrawn only) |
| `.type` | `string \| null` | Type for non-ISO currencies |
| `.marketCapRank` | `number \| null` | Market cap rank (crypto/stablecoins) |
| `.pegMechanism` | `string \| null` | Peg mechanism (stablecoins) |

| Method | Returns | Description |
|--------|---------|-------------|
| `.toMinor(amount)` | `number` | Major → minor units |
| `.fromMinor(amount)` | `number` | Minor → major units |
| `.format(amount)` | `string` | Formatted with symbol |
| `.issuingCountries()` | `Array` | Sovereign issuing countries |
| `.adoptingCountries()` | `Array` | Countries that adopted this currency |
| `.toJSON()` | `Object` | Raw data object |

---

## TypeScript

Type definitions are included. Import with full type support:

```typescript
import { CurrencyRegistry, Currency } from 'iso4217-registry';

const registry = new CurrencyRegistry();
const usd: Currency | null = registry.active('USD');

if (usd) {
  const cents: number = usd.toMinor(100.50);
  console.log(cents); // 10050
}
```

The `index.d.ts` file ships with the package and is declared in `package.json` via the `"types"` field.

---

## Differences from the Python wrapper

This JavaScript wrapper follows JavaScript conventions while maintaining the same behavior as the [Python wrapper](https://github.com/slimissa/iso4217/tree/main/wrappers/python):

| Feature | Python | JavaScript |
|---------|--------|------------|
| Property naming | `minor_units` | `minorUnits` |
| Null checks | `None` | `null` |
| Lookup method | `registry.non_iso("BTC")` | `registry.nonIso("BTC")` |
| Existence check | `"USD" in registry` | `registry.has("USD")` |
| Singleton | `currency("USD")` | No singleton (explicit `new`) |
| Iteration | `for c in registry:` | `for (const c of registry)` |
| File discovery | Same 4-step lookup | Same 4-step lookup |

---

## Development

```bash
git clone https://github.com/slimissa/iso4217.git
cd iso4217/wrappers/javascript
npm install

# Run tests
npm test

# Lint
npm run lint
```

---

## License

Apache 2.0 — same as the [ISO 4217 registry](https://github.com/slimissa/iso4217). Use it anywhere.
