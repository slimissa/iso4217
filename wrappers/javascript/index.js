/**
 * ISO 4217 Currency Registry — JavaScript/Node.js Wrapper
 *
 * A minimal, zero-dependency JavaScript interface to the canonical ISO 4217
 * currency registry. Provides Currency and CurrencyRegistry classes with
 * minor/major unit conversion, peg information access, and country
 * relationship lookup.
 *
 * Usage:
 *   const { CurrencyRegistry } = require('iso4217-registry');
 *   const registry = new CurrencyRegistry();
 *   const usd = registry.currency('USD');
 *   console.log(usd.toMinor(100.50));  // 10050
 *   console.log(usd.format(100.50));   // "$100.50"
 *
 * License: Apache 2.0
 */

'use strict';

// ---------------------------------------------------------------------------
// Registry data loading
// ---------------------------------------------------------------------------

/**
 * Resolve the path to iso4217.json.
 *
 * Lookup order:
 *   1. Explicit path passed to constructor
 *   2. Same directory as this module
 *   3. Two levels up (wrappers/javascript -> project root)
 *   4. Current working directory
 *
 * @param {string|null} [explicitPath=null]
 * @returns {string} Resolved path
 * @throws {Error} If the registry file cannot be found
 */
function resolveDataPath(explicitPath) {
  if (explicitPath) {
    const fs = require('fs');
    if (fs.existsSync(explicitPath)) {
      return explicitPath;
    }
    throw new Error(`Registry file not found: ${explicitPath}`);
  }

  const path = require('path');
  const fs = require('fs');

  const candidates = [
    // Same directory as this module
    path.join(__dirname, 'iso4217.json'),
    // Two levels up (project root)
    path.join(__dirname, '..', '..', 'iso4217.json'),
    // Current working directory
    path.join(process.cwd(), 'iso4217.json'),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    'Cannot find iso4217.json. ' +
    'Place it next to index.js, in the project root, ' +
    'or pass an explicit path to CurrencyRegistry().'
  );
}

/**
 * Load and parse the registry JSON.
 *
 * @param {string|null} [explicitPath=null]
 * @returns {Object} Parsed registry data
 */
// ---------------------------------------------------------------------------
// Registry data validation (v1.9.0, F13)
// ---------------------------------------------------------------------------
// One strict pass over the parsed JSON, before any Currency is built. The same contract is implemented in the
// Python, Go and Rust wrappers and tested against tests/cross_language_consistency.json
// ("malformed_registry_tests"). The rules are in docs/WRAPPER_VALIDATION.md.

const MAX_MINOR_UNITS = 36;

/**
 * Thrown by `new CurrencyRegistry()` when the registry data is malformed: not valid JSON, or outside the contract in
 * docs/WRAPPER_VALIDATION.md. The message is "malformed registry data: <JSON path>: <reason>". A missing file is still
 * a plain Error: that is I/O, not data.
 */
class RegistryDataError extends Error {
  constructor(message) {
    super(message);
    this.name = 'RegistryDataError';
  }
}

const STRING_FIELDS = ['numeric', 'symbol', 'entity', 'central_bank', 'pegged_to', 'peg_type', 'pegged_since', 'note',
  'withdrawn_date', 'replaced_by', 'type', 'peg_mechanism', 'classification', 'source_url'];
const NUMBER_FIELDS = ['peg_rate', 'peg_band_pct', 'conversion_rate'];
const INTEGER_FIELDS = ['market_cap_rank'];
const BOOLEAN_FIELDS = ['is_independent', 'numeric_reused'];
const ENTRY_LISTS = [
  ['currencies', ['active', 'withdrawn']],
  ['non_iso', ['cryptocurrencies', 'stablecoins', 'commodities', 'special_purpose']],
];

function isObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function jsonKind(v) {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  return typeof v === 'object' ? 'object' : typeof v;
}

function malformed(path, reason) {
  throw new RegistryDataError(`malformed registry data: ${path}: ${reason}`);
}

const KIND_CHECKS = {
  string: (v) => typeof v === 'string',
  number: (v) => typeof v === 'number' && Number.isFinite(v),
  integer: (v) => Number.isInteger(v),
  boolean: (v) => typeof v === 'boolean',
  array: (v) => Array.isArray(v),
  object: isObject,
};

function checkKind(value, kind, path) {
  if (!KIND_CHECKS[kind](value)) malformed(path, `expected ${kind}, got ${jsonKind(value)}`);
}

function has(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function checkOptional(obj, key, kind, path) {
  if (has(obj, key) && obj[key] !== null) checkKind(obj[key], kind, `${path}.${key}`);
}

function validateEntry(entry, path) {
  checkKind(entry, 'object', path);
  for (const [key, kind] of [['code', 'string'], ['name', 'string'], ['minor_units', 'integer']]) {
    if (!has(entry, key)) malformed(`${path}.${key}`, 'required field is missing');
    checkKind(entry[key], kind, `${path}.${key}`);
  }
  if (entry.code === '') malformed(`${path}.code`, 'must not be empty');
  if (entry.minor_units < 0 || entry.minor_units > MAX_MINOR_UNITS) {
    malformed(`${path}.minor_units`, `expected an integer from 0 to ${MAX_MINOR_UNITS}, got ${entry.minor_units}`);
  }
  STRING_FIELDS.forEach((k) => checkOptional(entry, k, 'string', path));
  NUMBER_FIELDS.forEach((k) => checkOptional(entry, k, 'number', path));
  INTEGER_FIELDS.forEach((k) => checkOptional(entry, k, 'integer', path));
  BOOLEAN_FIELDS.forEach((k) => checkOptional(entry, k, 'boolean', path));
  checkOptional(entry, 'countries', 'array', path);
  (entry.countries || []).forEach((country, i) => {
    const cpath = `${path}.countries[${i}]`;
    checkKind(country, 'object', cpath);
    if (!has(country, 'code')) malformed(`${cpath}.code`, 'required field is missing');
    checkKind(country.code, 'string', `${cpath}.code`);
    checkOptional(country, 'name', 'string', cpath);
    checkOptional(country, 'relationship', 'string', cpath);
  });
  checkOptional(entry, 'code_lifetime', 'object', path);
  if (entry.code_lifetime) {
    const lpath = `${path}.code_lifetime`;
    if (!has(entry.code_lifetime, 'to')) malformed(`${lpath}.to`, 'required field is missing');
    checkKind(entry.code_lifetime.to, 'string', `${lpath}.to`);
    checkOptional(entry.code_lifetime, 'from', 'string', lpath);
  }
}

/**
 * Throws RegistryDataError unless `data` satisfies the contract in docs/WRAPPER_VALIDATION.md.
 * @param {*} data
 */
function validateRegistryData(data) {
  checkKind(data, 'object', '$');
  for (const section of ['meta', 'source', 'currencies', 'non_iso']) {
    if (has(data, section)) checkKind(data[section], 'object', `$.${section}`);
  }
  const meta = data.meta || {};
  const source = data.source || {};
  checkOptional(meta, 'version', 'string', '$.meta');
  checkOptional(meta, 'updated', 'string', '$.meta');
  checkOptional(source, 'last_amendment_applied', 'integer', '$.source');
  checkOptional(source, 'last_amendment_date', 'string', '$.source');
  for (const [section, keys] of ENTRY_LISTS) {
    const group = data[section] || {};
    for (const key of keys) {
      if (!has(group, key)) continue;
      checkKind(group[key], 'array', `$.${section}.${key}`);
      group[key].forEach((entry, i) => validateEntry(entry, `$.${section}.${key}[${i}]`));
    }
  }
}

function loadRegistryData(explicitPath) {
  const fs = require('fs');
  const resolved = resolveDataPath(explicitPath);
  const raw = fs.readFileSync(resolved, 'utf-8');
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    throw new RegistryDataError(`malformed registry data: $: invalid JSON: ${e.message}`);
  }
  validateRegistryData(data);
  return data;
}

// ---------------------------------------------------------------------------
// Currency
// ---------------------------------------------------------------------------

/**
 * 10^n, exact as a double for n <= 22. Every wrapper takes 10^n from the same exact table, so the one floating-point
 * multiplication in the conversion is the same in all four languages (ADR 0013, D2).
 */
const POW10_EXACT = [
  1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11,
  1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
];

/** 2^63: a rounded amount whose magnitude is at or above it does not fit in an int64. */
const INT64_LIMIT = 9223372036854775808;

/**
 * Round to the nearest integer, ties away from zero (2.5 -> 3, -2.5 -> -3), exactly.
 *
 * This matches Go's math.Round and Rust's f64::round(), and deliberately does NOT match JS's built-in Math.round(),
 * which rounds half toward +Infinity (Math.round(-2.5) === -2). It also avoids Math.floor(x + 0.5): in doubles
 * 0.49999999999999994 + 0.5 is 1, and above 2^52 the addition loses the half, so that form is wrong at the edges.
 * p - Math.trunc(p) is exact for doubles, so the comparison with 0.5 is exact (ADR 0013, D2).
 *
 * @param {number} p - a finite double
 * @returns {number} an integer-valued double (may be -0)
 */
function roundHalfAwayFromZero(p) {
  const t = Math.trunc(p);
  return Math.abs(p - t) >= 0.5 ? t + Math.sign(p) : t;
}

/**
 * Insert a comma every three digits of a string of digits, counting from the right.
 * @param {string} digits
 * @returns {string}
 */
function groupThousands(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Represents a single currency from the ISO 4217 registry.
 *
 * Provides read-only access to all currency properties plus convenience
 * methods for converting between major and minor currency units.
 *
 * @class Currency
 */
class Currency {
  /**
   * @param {Object} data - Raw currency data from the registry JSON
   */
  constructor(data) {
    this._data = Object.freeze ? Object.freeze({ ...data }) : data;
  }

  // -- Basic properties ---------------------------------------------------

  /** @returns {string} ISO 4217 alphabetic code (e.g., "USD") */
  get code() {
    return this._data.code;
  }

  /** @returns {string} ISO 4217 numeric code as 3-digit string (e.g., "840") */
  get numeric() {
    return this._data.numeric || '';
  }

  /** @returns {string} Official English name (e.g., "US Dollar") */
  get name() {
    return this._data.name;
  }

  /**
   * Number of decimal places for the minor currency unit.
   *
   * 0 = no subdivision (JPY, KRW, VND).
   * 2 = standard cents/pence (USD, EUR, GBP).
   * 3 = dinar subdivisions (KWD, BHD, OMR, JOD, TND, LYD, IQD).
   * 8 = Bitcoin.
   * 18 = Ethereum.
   *
   * @returns {number}
   */
  get minorUnits() {
    return this._data.minor_units;
  }

  /** @returns {string} Primary display symbol (may be empty) */
  get symbol() {
    return this._data.symbol || '';
  }

  /** @returns {string} Issuing entity or monetary authority */
  get entity() {
    return this._data.entity || '';
  }

  /** @returns {string} Official name of the central bank */
  get centralBank() {
    return this._data.central_bank || '';
  }

  // -- Peg properties -----------------------------------------------------

  /**
   * The currency or basket this currency is pegged to.
   * @returns {string|null} ISO 4217 code, basket description, or null if floating
   */
  get peggedTo() {
    return this._data.pegged_to || null;
  }

  /**
   * How to interpret `peggedTo`.
   *
   * - "single": peggedTo is a parseable ISO 4217 code (e.g. AED -> "USD").
   * - "basket": peggedTo is a free-text description of a weighted basket
   *   peg (e.g. MAD -> "EUR+USD basket").
   * - "undisclosed": pegged, but the peg mechanism/composition is not
   *   public (e.g. KWD -> "Currency basket").
   * - null: not pegged.
   *
   * Do not assume `peggedTo` is a parseable currency code without checking
   * `pegType === "single"` first — MAD and KWD have free-text peggedTo
   * values that will not match a currency code.
   *
   * @returns {string|null}
   */
  get pegType() {
    return this._data.peg_type || null;
  }

  /** @returns {string|null} Date the peg was established in ISO 8601 format */
  get peggedSince() {
    return this._data.pegged_since || null;
  }

  /**
   * Official peg rate (units of this currency per 1 unit of anchor).
   * @returns {number|null} Peg rate or null for baskets/undisclosed pegs
   */
  get pegRate() {
    return this._data.peg_rate != null ? this._data.peg_rate : null;
  }

  /**
   * Allowed deviation from the peg as a percentage.
   * 0.0 = fixed peg. null = not applicable or undisclosed.
   * @returns {number|null}
   */
  get pegBandPct() {
    return this._data.peg_band_pct != null ? this._data.peg_band_pct : null;
  }

  /**
   * True if the currency floats independently or is a managed float
   * without a fixed anchor. False if hard-pegged or currency board.
   * @returns {boolean}
   */
  get isIndependent() {
    return this._data.is_independent === true;
  }

  /** @returns {boolean} True if this currency is pegged to something */
  get isPegged() {
    return this.peggedTo !== null;
  }

  // -- Note ---------------------------------------------------------------

  /** @returns {string|null} Optional note for special cases */
  get note() {
    return this._data.note || null;
  }

  // -- Countries ----------------------------------------------------------

  /**
   * Countries and territories where this currency is primary legal tender.
   * Each entry: { code, name, relationship }
   * @returns {Array<{code: string, name: string, relationship: string}>}
   */
  get countries() {
    return this._data.countries || [];
  }

  /**
   * Countries that are the sovereign issuer of this currency.
   * @returns {Array<{code: string, name: string, relationship: string}>}
   */
  issuingCountries() {
    return this.countries.filter(c => c.relationship === 'issuing');
  }

  /**
   * Countries that use this currency without being the issuer.
   * @returns {Array<{code: string, name: string, relationship: string}>}
   */
  adoptingCountries() {
    return this.countries.filter(c => c.relationship === 'adopting');
  }

  // -- Withdrawn properties -----------------------------------------------

  /** @returns {string|null} Withdrawal date (withdrawn currencies only) */
  get withdrawnDate() {
    return this._data.withdrawn_date || null;
  }

  /** @returns {string|null} Replacement currency code (withdrawn currencies only) */
  get replacedBy() {
    return this._data.replaced_by || null;
  }

  /** @returns {number|null} Official conversion rate (withdrawn currencies only) */
  get conversionRate() {
    return this._data.conversion_rate != null ? this._data.conversion_rate : null;
  }

  // -- Non-ISO properties -------------------------------------------------

  /** @returns {string|null} Type for non-ISO currencies (cryptocurrency, stablecoin, etc.) */
  get type() {
    return this._data.type || null;
  }

  /** @returns {number|null} Market cap rank (crypto/stablecoins only) */
  get marketCapRank() {
    return this._data.market_cap_rank != null ? this._data.market_cap_rank : null;
  }

  /** @returns {string|null} Peg mechanism (stablecoins only) */
  get pegMechanism() {
    return this._data.peg_mechanism || null;
  }

  // -- v1.6.0 properties --------------------------------------------------

  /**
   * Classification of an active currency: "circulating", "fund",
   * "settlement", or "indexation". `null` for withdrawn and non-ISO
   * entries, and for v1.5.x registries that predate this field.
   * @returns {string|null}
   */
  get classification() {
    return this._data.classification || null;
  }

  /**
   * True if this active currency's numeric code also appears on a
   * withdrawn entry. `null` for withdrawn and non-ISO entries, and
   * for v1.5.x registries.
   * @returns {boolean|null}
   */
  get numericReused() {
    const v = this._data.numeric_reused;
    return v === undefined ? null : v;
  }

  /**
   * URL of the entry's primary source. Present on every active and
   * withdrawn entry as of v1.6.0.
   * @returns {string|null}
   */
  get sourceUrl() {
    return this._data.source_url || null;
  }

  /**
   * Withdrawn code's full valid range: `{ from: string|null, to: string }`.
   * `null` for active and non-ISO entries.
   * @returns {object|null}
   */
  get codeLifetime() {
    return this._data.code_lifetime || null;
  }

  // -- Conversion ---------------------------------------------------------

  /**
   * Convert a major currency amount to minor units.
   *
   * @param {number} majorAmount - Amount in major units (e.g., 100.50 for $100.50)
   * @returns {number} Integer amount in minor units (e.g., 10050 for cents)
   * @throws {Error} If majorAmount is NaN or infinite
   * @throws {RangeError} If the rounded result does not fit in an int64 (|result| >= 2^63); the message says
   *   "amount too large" (ADR 0013, D3)
   *
   * @example
   * usd.toMinor(100.50);   // 10050
   * jpy.toMinor(500);      // 500
   * kwd.toMinor(1.500);    // 1500
   * btc.toMinor(0.00000001); // 1
   */
  toMinor(majorAmount) {
    if (!Number.isFinite(majorAmount)) {
      throw new Error(`Cannot convert ${majorAmount} to minor units`);
    }

    const p = majorAmount * POW10_EXACT[this.minorUnits];
    if (!Number.isFinite(p)) {
      throw new RangeError(`Cannot convert ${majorAmount} to minor units: amount too large for int64 minor units`);
    }
    const r = roundHalfAwayFromZero(p);
    if (Math.abs(r) >= INT64_LIMIT) {
      throw new RangeError(`Cannot convert ${majorAmount} to minor units: amount too large for int64 minor units`);
    }
    return r === 0 ? 0 : r; // never -0
  }

  /**
   * Convert minor units to a major currency amount.
   *
   * @param {number} minorAmount - Integer amount in minor units
   * @returns {number} Float amount in major units
   *
   * @example
   * usd.fromMinor(10050);  // 100.5
   * jpy.fromMinor(500);    // 500
   */
  fromMinor(minorAmount) {
    if (!Number.isFinite(minorAmount)) {
      throw new Error(`Cannot convert ${minorAmount} from minor units`);
    }

    const factor = Math.pow(10, this.minorUnits);
    return minorAmount / factor;
  }

  // -- Display ------------------------------------------------------------

  /**
   * Format a major currency amount with the currency symbol.
   *
   * The amount is rounded exactly as toMinor() rounds it (half away from zero) and its digits are printed from that
   * rounded value, so format() and toMinor() cannot disagree. It does not use Intl: the result does not depend on the
   * runtime's locale data. It never throws for a number: NaN is "nan", infinity (or an amount whose scaled value
   * overflows) is "inf" or "-inf" after the symbol. Fractional currencies get comma thousands separators; 0-decimal
   * currencies print ungrouped (ADR 0013, D5 and D6).
   *
   * @param {number} majorAmount - Amount in major units
   * @returns {string} Formatted string like "$100.50" or "¥500"
   * @throws {TypeError} If majorAmount is not a number
   *
   * @example
   * usd.format(100.50);   // "$100.50"
   * jpy.format(500);      // "¥500"
   * usd.format(NaN);      // "$nan"
   */
  format(majorAmount) {
    if (typeof majorAmount !== 'number') {
      throw new TypeError(`Cannot format ${majorAmount}: expected a number`);
    }
    const symbol = this.symbol;
    if (Number.isNaN(majorAmount)) {
      return `${symbol}nan`;
    }
    const signBit = majorAmount < 0 || Object.is(majorAmount, -0);
    const p = majorAmount * POW10_EXACT[this.minorUnits];
    if (!Number.isFinite(p)) {
      return `${symbol}${signBit ? '-' : ''}inf`; // infinity, or a finite amount whose scaled value overflowed
    }
    const n = this.minorUnits;
    const r = roundHalfAwayFromZero(p);
    // Sign comes from the sign bit of the amount when there are decimals, and from the rounded value when there are
    // none: a negative amount that rounds to zero prints "$-0.00" but "\u00a50" (today's behavior in all four wrappers).
    const negative = (signBit && (n > 0 || r !== 0)) || (n === 0 && r < 0);
    let digits = BigInt(Math.abs(r)).toString(); // exact digits of an integer-valued double
    if (n > 0) {
      digits = digits.padStart(n + 1, '0');
      const split = digits.length - n;
      digits = `${groupThousands(digits.slice(0, split))}.${digits.slice(split)}`;
    }
    return `${symbol}${negative ? '-' : ''}${digits}`;
  }

  // -- Serialization ------------------------------------------------------

  /**
   * Return the raw data object for this currency.
   * @returns {Object}
   */
  toJSON() {
    return { ...this._data };
  }

  /**
   * Return a string representation.
   * @returns {string}
   */
  toString() {
    const peg = this.peggedTo ? `, pegged to ${this.peggedTo}` : '';
    return `${this.code} — ${this.name} (minor_units=${this.minorUnits}${peg})`;
  }

  /**
   * Custom inspection for console.log / Node.js util.inspect.
   * @returns {string}
   */
  [Symbol.for('nodejs.util.inspect.custom')]() {
    return this.toString();
  }
}

// ---------------------------------------------------------------------------
// CurrencyRegistry
// ---------------------------------------------------------------------------

/**
 * The main registry interface for looking up ISO 4217 currencies.
 *
 * Loads the canonical iso4217.json file and provides lookup methods
 * for active, withdrawn, and non-ISO currencies.
 *
 * @class CurrencyRegistry
 */
class CurrencyRegistry {
  /**
   * Initialize the registry from a JSON file.
   *
   * @param {string|null} [dataPath=null] - Path to iso4217.json
   * @throws {Error} If the registry file cannot be found
   * @throws {RegistryDataError} If the data is malformed (docs/WRAPPER_VALIDATION.md)
   */
  constructor(dataPath) {
    this._data = loadRegistryData(dataPath);

    /** @type {Map<string, Currency>} */
    this._active = new Map();

    /** @type {Map<string, Currency>} */
    this._withdrawn = new Map();

    /** @type {Map<string, Currency>} */
    this._nonIso = new Map();

    /** @type {Map<string, Currency>} */
    this._all = new Map();

    this._buildIndexes();
  }

  /**
   * Build lookup indexes from the raw data.
   * @private
   */
  _buildIndexes() {
    const currencies = this._data.currencies || {};

    // Active currencies
    for (const c of (currencies.active || [])) {
      const currency = new Currency(c);
      this._active.set(c.code, currency);
      this._all.set(c.code, currency);
    }

    // Withdrawn currencies
    for (const c of (currencies.withdrawn || [])) {
      const currency = new Currency(c);
      this._withdrawn.set(c.code, currency);
      this._all.set(c.code, currency);
    }

    // Non-ISO currencies
    const nonIso = this._data.non_iso || {};
    for (const category of ['cryptocurrencies', 'stablecoins', 'commodities', 'special_purpose']) {
      for (const c of (nonIso[category] || [])) {
        const currency = new Currency(c);
        this._nonIso.set(c.code, currency);
        this._all.set(c.code, currency);
      }
    }
  }

  // -- Metadata -----------------------------------------------------------

  /** @returns {string} Semantic version of the registry data */
  get version() {
    return (this._data.meta && this._data.meta.version) || 'unknown';
  }

  /** @returns {string} Date the registry was last updated (ISO 8601) */
  get updated() {
    return (this._data.meta && this._data.meta.updated) || 'unknown';
  }

  /** @returns {number} Most recent ISO 4217 amendment applied */
  get amendment() {
    return (this._data.source && this._data.source.last_amendment_applied) || 0;
  }

  /** @returns {string} Date of the most recent amendment applied */
  get amendmentDate() {
    return (this._data.source && this._data.source.last_amendment_date) || 'unknown';
  }

  // -- Lookup methods -----------------------------------------------------

  /**
   * Look up any currency by code (case-insensitive).
   * Searches active, withdrawn, and non-ISO currencies.
   *
   * @param {string} code - Currency code (e.g., "USD", "usd", "Btc")
   * @returns {Currency|null}
   */
  currency(code) {
    return this._all.get(code.toUpperCase()) || null;
  }

  /**
   * Look up an active ISO 4217 currency by code (case-insensitive).
   *
   * @param {string} code - Currency code (e.g., "USD", "eur")
   * @returns {Currency|null}
   */
  active(code) {
    return this._active.get(code.toUpperCase()) || null;
  }

  /**
   * Look up a withdrawn ISO 4217 currency by code (case-insensitive).
   *
   * @param {string} code - Currency code (e.g., "DEM", "frf")
   * @returns {Currency|null}
   */
  withdrawn(code) {
    return this._withdrawn.get(code.toUpperCase()) || null;
  }

  /**
   * Look up a non-ISO currency by code (case-insensitive).
   *
   * @param {string} code - Currency code (e.g., "BTC", "xau")
   * @returns {Currency|null}
   */
  nonIso(code) {
    return this._nonIso.get(code.toUpperCase()) || null;
  }

  // -- Collection accessors -----------------------------------------------

  /**
   * Return all active ISO 4217 currencies.
   * @returns {Currency[]}
   */
  allActive() {
    return Array.from(this._active.values());
  }

  /**
   * Return all withdrawn ISO 4217 currencies.
   * @returns {Currency[]}
   */
  allWithdrawn() {
    return Array.from(this._withdrawn.values());
  }

  /**
   * Return all non-ISO currencies (crypto, stablecoins, commodities).
   * @returns {Currency[]}
   */
  allNonIso() {
    return Array.from(this._nonIso.values());
  }

  /**
   * Return all currencies across all categories.
   * @returns {Currency[]}
   */
  allCurrencies() {
    return Array.from(this._all.values());
  }

  // -- Filtering ----------------------------------------------------------

  /**
   * Find all active currencies pegged to a specific anchor currency.
   *
   * @param {string} anchorCode - ISO 4217 code of the anchor (e.g., "USD", "EUR")
   * @returns {Currency[]}
   *
   * @example
   * Only currencies with pegType === "single" are considered — a currency
   * pegged to a basket or an undisclosed mix (e.g. MAD's "EUR+USD basket")
   * is not "pegged to USD" just because "USD" appears in its peggedTo
   * description, even though the anchor is a component of the basket.
   * Use `allActive()` and inspect `pegType`/`peggedTo` directly if you
   * need basket-aware search.
   *
   * @example
   * registry.peggedTo("USD");
   * // [Currency { code: 'AED', ... }, Currency { code: 'SAR', ... }, ...]
   */
  peggedTo(anchorCode) {
    const anchor = anchorCode.toUpperCase();
    const result = [];

    for (const c of this._active.values()) {
      if (c.pegType === 'single' && c.peggedTo !== null && c.peggedTo.toUpperCase() === anchor) {
        result.push(c);
      }
    }

    return result;
  }

  /**
   * Return all active currencies that are independently floating.
   * @returns {Currency[]}
   */
  independent() {
    const result = [];
    for (const c of this._active.values()) {
      if (c.isIndependent) {
        result.push(c);
      }
    }
    return result;
  }

  /**
   * Find all active currencies with a specific number of minor units.
   *
   * @param {number} n - Number of minor units (0, 2, 3, etc.)
   * @returns {Currency[]}
   *
   * @example
   * registry.withMinorUnits(3);
   * // [Currency { code: 'BHD', ... }, Currency { code: 'JOD', ... }, ...]
   */
  withMinorUnits(n) {
    const result = [];
    for (const c of this._active.values()) {
      if (c.minorUnits === n) {
        result.push(c);
      }
    }
    return result;
  }

  /**
   * Find all active currencies where a country is the issuer.
   *
   * @param {string} countryCode - ISO 3166-1 alpha-2 country code
   * @returns {Currency[]}
   */
  issuedBy(countryCode) {
    const code = countryCode.toUpperCase();
    const result = [];

    for (const c of this._active.values()) {
      if (c.countries.some(country =>
        country.code === code && country.relationship === 'issuing'
      )) {
        result.push(c);
      }
    }

    return result;
  }

  /**
   * Find all active currencies used in a country (any relationship).
   *
   * @param {string} countryCode - ISO 3166-1 alpha-2 country code
   * @returns {Currency[]}
   */
  usedIn(countryCode) {
    const code = countryCode.toUpperCase();
    const result = [];

    for (const c of this._active.values()) {
      if (c.countries.some(country => country.code === code)) {
        result.push(c);
      }
    }

    return result;
  }

  /**
   * Find all active currencies with the given classification.
   *
   * @param {string} cls - One of "circulating", "fund", "settlement",
   *   "indexation".
   * @returns {Currency[]} Active currencies whose classification matches.
   *   Empty array if none match or if the registry predates v1.6.0.
   */
  byClassification(cls) {
    const result = [];
    for (const c of this._active.values()) {
      if (c.classification === cls) {
        result.push(c);
      }
    }
    return result;
  }

  // -- Statistics ---------------------------------------------------------

  /** @returns {number} Number of active ISO 4217 currencies */
  get activeCount() {
    return this._active.size;
  }

  /** @returns {number} Number of withdrawn ISO 4217 currencies */
  get withdrawnCount() {
    return this._withdrawn.size;
  }

  /** @returns {number} Number of non-ISO currencies */
  get nonIsoCount() {
    return this._nonIso.size;
  }

  /** @returns {number} Number of active currencies that are pegged */
  get peggedCount() {
    let count = 0;
    for (const c of this._active.values()) {
      if (c.isPegged) count++;
    }
    return count;
  }

  /** @returns {number} Number of active currencies that float independently */
  get independentCount() {
    let count = 0;
    for (const c of this._active.values()) {
      if (c.isIndependent) count++;
    }
    return count;
  }

  /**
   * Return a summary object with registry statistics.
   * @returns {Object}
   */
  summary() {
    const muDist = {};
    for (const c of this._active.values()) {
      const mu = c.minorUnits;
      muDist[mu] = (muDist[mu] || 0) + 1;
    }

    // Sort keys numerically
    const sortedDist = {};
    Object.keys(muDist)
      .map(Number)
      .sort((a, b) => a - b)
      .forEach(k => { sortedDist[k] = muDist[k]; });

    return {
      version: this.version,
      updated: this.updated,
      amendment: this.amendment,
      activeCurrencies: this.activeCount,
      withdrawnCurrencies: this.withdrawnCount,
      nonIsoCurrencies: this.nonIsoCount,
      peggedCurrencies: this.peggedCount,
      independentCurrencies: this.independentCount,
      minorUnitsDistribution: sortedDist,
    };
  }

  // -- Iteration ----------------------------------------------------------

  /**
   * Iterate over all active currencies.
   * @returns {Iterator<Currency>}
   */
  [Symbol.iterator]() {
    return this._active.values();
  }

  /**
   * Number of active currencies.
   * @returns {number}
   */
  get size() {
    return this._active.size;
  }

  /**
   * Check if a currency code exists in the registry (any category).
   * @param {string} code
   * @returns {boolean}
   */
  has(code) {
    return this._all.has(code.toUpperCase());
  }

  // -- Display ------------------------------------------------------------

  toString() {
    return `CurrencyRegistry(version=${this.version}, active=${this.activeCount}, withdrawn=${this.withdrawnCount}, nonIso=${this.nonIsoCount})`;
  }

  [Symbol.for('nodejs.util.inspect.custom')]() {
    return this.toString();
  }
}

// ---------------------------------------------------------------------------
// Module exports
// ---------------------------------------------------------------------------

module.exports = {
  Currency,
  CurrencyRegistry,
  RegistryDataError,
};