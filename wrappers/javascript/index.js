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
function loadRegistryData(explicitPath) {
  const fs = require('fs');
  const resolved = resolveDataPath(explicitPath);
  const raw = fs.readFileSync(resolved, 'utf-8');
  return JSON.parse(raw);
}

// ---------------------------------------------------------------------------
// Currency
// ---------------------------------------------------------------------------

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
    return this._data.is_independent !== false;
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

  // -- Conversion ---------------------------------------------------------

  /**
   * Convert a major currency amount to minor units.
   *
   * @param {number} majorAmount - Amount in major units (e.g., 100.50 for $100.50)
   * @returns {number} Integer amount in minor units (e.g., 10050 for cents)
   * @throws {Error} If majorAmount is NaN or infinite
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

    const factor = Math.pow(10, this.minorUnits);
    // Use Math.round to handle floating-point imprecision
    return Math.round(majorAmount * factor);
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
   * @param {number} majorAmount - Amount in major units
   * @returns {string} Formatted string like "$100.50" or "¥500"
   *
   * @example
   * usd.format(100.50);   // "$100.50"
   * jpy.format(500);      // "¥500"
   */
  format(majorAmount) {
    if (this.minorUnits === 0) {
      return `${this.symbol}${Math.round(majorAmount)}`;
    }

    const formatted = majorAmount.toLocaleString('en-US', {
      minimumFractionDigits: this.minorUnits,
      maximumFractionDigits: this.minorUnits,
    });

    return `${this.symbol}${formatted}`;
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
   * @throws {Error} If the registry file cannot be found or parsed
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
   * registry.peggedTo("USD");
   * // [Currency { code: 'AED', ... }, Currency { code: 'SAR', ... }, ...]
   */
  peggedTo(anchorCode) {
    const anchor = anchorCode.toUpperCase();
    const result = [];

    for (const c of this._active.values()) {
      if (c.peggedTo !== null && typeof c.peggedTo === 'string') {
        if (c.peggedTo.toUpperCase().includes(anchor)) {
          result.push(c);
        }
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
};