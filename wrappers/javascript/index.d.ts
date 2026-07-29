/**
 * ISO 4217 Currency Registry — TypeScript Declarations
 *
 * Type definitions for the iso4217-registry JavaScript package.
 * Provides full type information for Currency and CurrencyRegistry classes.
 *
 * Usage:
 *   import { CurrencyRegistry, Currency } from 'iso4217-registry';
 *
 * License: Apache 2.0
 */

// ---------------------------------------------------------------------------
// Country reference
// ---------------------------------------------------------------------------

/**
 * A country or territory where a currency is used.
 */
export interface CountryReference {
  /** ISO 3166-1 alpha-2 country code (e.g., "US", "FR") */
  code: string;

  /** Human-readable country or territory name */
  name: string;

  /**
   * Relationship of this country/territory to the currency.
   *
   * - `"issuing"` — sovereign issuer and monetary authority
   * - `"adopting"` — uses the currency without being the issuer (dollarization, euroization)
   * - `"territory"` — dependent territory of the issuing country
   * - `"parallel"` — circulates alongside a local currency at fixed parity
   * - `"local_issue"` — issues local banknotes/coins denominated in this currency
   */
  relationship: 'issuing' | 'adopting' | 'territory' | 'parallel' | 'local_issue';
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
 * @example
 * const usd = registry.active('USD');
 * console.log(usd.toMinor(100.50));  // 10050
 * console.log(usd.format(100.50));   // "$100.50"
 */
export declare class Currency {
  /**
   * @internal — Constructed internally by CurrencyRegistry.
   * Users should not call this directly.
   */
  private constructor();

  // -- Basic properties ---------------------------------------------------

  /** ISO 4217 alphabetic currency code (e.g., "USD") */
  readonly code: string;

  /** ISO 4217 numeric currency code as a 3-digit string (e.g., "840") */
  readonly numeric: string;

  /** Official English name of the currency (e.g., "US Dollar") */
  readonly name: string;

  /**
   * Number of decimal places for the minor currency unit.
   *
   * 0 = no subdivision (JPY, KRW, VND).
   * 2 = standard cents/pence (USD, EUR, GBP).
   * 3 = dinar subdivisions (KWD, BHD, OMR, JOD, TND, LYD, IQD).
   * 8 = Bitcoin.
   * 18 = Ethereum.
   */
  readonly minorUnits: number;

  /** Primary display symbol. May be empty string if none exists. */
  readonly symbol: string;

  /** Issuing entity or monetary authority. */
  readonly entity: string;

  /** Official name of the central bank. */
  readonly centralBank: string;

  // -- Peg properties -----------------------------------------------------

  /**
   * The currency or basket this currency is pegged to.
   *
   * Returns an ISO 4217 code, a basket description (e.g., "EUR+USD basket"),
   * or `null` if freely floating.
   */
  readonly peggedTo: string | null;

  /** Date the peg was established in ISO 8601 format (YYYY-MM-DD), or `null`. */
  readonly peggedSince: string | null;

  /**
   * Official peg rate (units of this currency per 1 unit of anchor).
   * `null` for basket pegs or undisclosed pegs.
   */
  readonly pegRate: number | null;

  /**
   * Allowed deviation from the peg as a percentage.
   * 0.0 = fixed peg. `null` = not applicable or undisclosed.
   */
  readonly pegBandPct: number | null;

  /**
   * `true` if the currency floats independently or is a managed float
   * without a fixed anchor. `false` if hard-pegged or currency board.
   */
  readonly isIndependent: boolean;

  /** Convenience property: `true` if this currency is pegged to something. */
  readonly isPegged: boolean;

  // -- Note ---------------------------------------------------------------

  /** Optional note for special cases or market conventions. */
  readonly note: string | null;

  // -- Countries ----------------------------------------------------------

  /**
   * Countries and territories where this currency is primary legal tender.
   * Each entry has `code`, `name`, and `relationship` fields.
   */
  readonly countries: CountryReference[];

  /**
   * Returns countries that are the sovereign issuer of this currency.
   */
  issuingCountries(): CountryReference[];

  /**
   * Returns countries that use this currency without being the issuer
   * (dollarized, euroized, etc.).
   */
  adoptingCountries(): CountryReference[];

  // -- Withdrawn properties (only present on withdrawn currencies) --------

  /** Withdrawal date in ISO 8601 format, or `null` for active currencies. */
  readonly withdrawnDate: string | null;

  /** ISO 4217 code of the replacement currency, or `null`. */
  readonly replacedBy: string | null;

  /** Official conversion rate (units of this currency per 1 unit of replacement). */
  readonly conversionRate: number | null;

  // -- Non-ISO properties (only present on non-ISO currencies) ------------

  /**
   * Type classification for non-ISO currencies.
   * `"cryptocurrency"`, `"stablecoin"`, `"commodity"`, `"basket"`,
   * `"offshore"`, `"unit_of_account"`, `"other"`, or `null` for ISO currencies.
   */
  readonly type: string | null;

  /** Market cap rank at time of inclusion (crypto/stablecoins only). */
  readonly marketCapRank: number | null;

  /** Peg mechanism for stablecoins (e.g., "Fiat-collateralized"). */
  readonly pegMechanism: string | null;

  // -- Conversion ---------------------------------------------------------

  /**
   * Convert a major currency amount to minor units.
   *
   * @param majorAmount - Amount in major units (e.g., 100.50 for $100.50)
   * @returns Integer amount in minor units (e.g., 10050 for cents)
   * @throws {Error} If majorAmount is NaN or infinite
   *
   * @example
   * usd.toMinor(100.50);       // 10050
   * jpy.toMinor(500);          // 500
   * kwd.toMinor(1.500);        // 1500
   * btc.toMinor(0.00000001);   // 1
   */
  toMinor(majorAmount: number): number;

  /**
   * Convert minor units to a major currency amount.
   *
   * @param minorAmount - Integer amount in minor units (e.g., 10050 for cents)
   * @returns Float amount in major units (e.g., 100.5 for $100.50)
   * @throws {Error} If minorAmount is NaN or infinite
   *
   * @example
   * usd.fromMinor(10050);  // 100.5
   * jpy.fromMinor(500);    // 500
   */
  fromMinor(minorAmount: number): number;

  /**
   * Format a major currency amount with the currency symbol.
   *
   * Uses en-US locale for thousands separators (financial convention).
   *
   * @param majorAmount - Amount in major units
   * @returns Formatted string like "$100.50" or "¥500"
   *
   * @example
   * usd.format(100.50);        // "$100.50"
   * usd.format(1234567.89);    // "$1,234,567.89"
   * jpy.format(500);           // "¥500"
   */
  format(majorAmount: number): string;

  // -- Serialization ------------------------------------------------------

  /**
   * Return the raw data object for this currency.
   * Useful for serialization or custom processing.
   */
  toJSON(): Record<string, unknown>;

  /**
   * Return a human-readable string representation.
   */
  toString(): string;
}

// ---------------------------------------------------------------------------
// Registry summary
// ---------------------------------------------------------------------------

/**
 * Summary statistics returned by CurrencyRegistry.summary().
 */
export interface RegistrySummary {
  /** Semantic version of the registry data */
  version: string;

  /** Date the registry was last updated (ISO 8601) */
  updated: string;

  /** Most recent ISO 4217 amendment number applied */
  amendment: number;

  /** Number of active ISO 4217 currencies */
  activeCurrencies: number;

  /** Number of withdrawn ISO 4217 currencies */
  withdrawnCurrencies: number;

  /** Number of non-ISO currencies (crypto, stablecoins, commodities, etc.) */
  nonIsoCurrencies: number;

  /** Number of active currencies that are pegged */
  peggedCurrencies: number;

  /** Number of active currencies that float independently */
  independentCurrencies: number;

  /**
   * Distribution of minor_units values across active currencies.
   * Keys are the minor_units value (0, 2, 3, etc.), values are counts.
   *
   * @example { 0: 5, 2: 49, 3: 7 }
   */
  minorUnitsDistribution: Record<number, number>;
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
 * @example
 * const registry = new CurrencyRegistry();
 * const usd = registry.active('USD');
 * const pegged = registry.peggedTo('USD');
 *
 * for (const c of registry) {
 *   console.log(c.code);
 * }
 */
export declare class CurrencyRegistry {
  /**
   * Initialize the registry from a JSON file.
   *
   * The registry file is discovered automatically:
   * 1. Explicit path passed to constructor
   * 2. Same directory as the module
   * 3. Two levels up (project root from wrappers/javascript/)
   * 4. Current working directory
   *
   * @param dataPath - Optional explicit path to iso4217.json
   * @throws {Error} If the registry file cannot be found or parsed
   */
  constructor(dataPath?: string | null);

  // -- Metadata -----------------------------------------------------------

  /** Semantic version of the registry data (e.g., "1.0.0") */
  readonly version: string;

  /** Date the registry was last updated in ISO 8601 format */
  readonly updated: string;

  /** Most recent ISO 4217 amendment number applied */
  readonly amendment: number;

  /** Date of the most recent amendment applied */
  readonly amendmentDate: string;

  // -- Lookup methods -----------------------------------------------------

  /**
   * Look up any currency by code (case-insensitive).
   * Searches active, withdrawn, and non-ISO currencies in that order.
   *
   * @param code - Currency code (e.g., "USD", "usd", "Btc")
   * @returns Currency object or `null` if not found
   */
  currency(code: string): Currency | null;

  /**
   * Look up an active ISO 4217 currency by code (case-insensitive).
   *
   * @param code - Currency code (e.g., "USD", "eur")
   * @returns Currency object or `null` if not found or not active
   */
  active(code: string): Currency | null;

  /**
   * Look up a withdrawn ISO 4217 currency by code (case-insensitive).
   *
   * @param code - Currency code (e.g., "DEM", "frf")
   * @returns Currency object or `null` if not found or not withdrawn
   */
  withdrawn(code: string): Currency | null;

  /**
   * Look up a non-ISO currency by code (case-insensitive).
   * Includes cryptocurrencies, stablecoins, commodities, and special purpose codes.
   *
   * @param code - Currency code (e.g., "BTC", "xau")
   * @returns Currency object or `null` if not found
   */
  nonIso(code: string): Currency | null;

  // -- Collection accessors -----------------------------------------------

  /** Return all active ISO 4217 currencies. */
  allActive(): Currency[];

  /** Return all withdrawn ISO 4217 currencies. */
  allWithdrawn(): Currency[];

  /** Return all non-ISO currencies (crypto, stablecoins, commodities, special purpose). */
  allNonIso(): Currency[];

  /** Return all currencies across all categories. */
  allCurrencies(): Currency[];

  // -- Filtering ----------------------------------------------------------

  /**
   * Find all active currencies pegged to a specific anchor currency.
   *
   * @param anchorCode - ISO 4217 code of the anchor (e.g., "USD", "EUR")
   * @returns Array of Currency objects pegged to the given anchor
   *
   * @example
   * registry.peggedTo('USD');
   * // [Currency { code: 'AED', ... }, Currency { code: 'SAR', ... }, ...]
   */
  peggedTo(anchorCode: string): Currency[];

  /**
   * Return all active currencies that are independently floating.
   */
  independent(): Currency[];

  /**
   * Find all active currencies with a specific number of minor units.
   *
   * @param n - Number of minor units (0, 2, 3, etc.)
   *
   * @example
   * registry.withMinorUnits(3);
   * // [Currency { code: 'BHD', ... }, Currency { code: 'JOD', ... }, ...]
   */
  withMinorUnits(n: number): Currency[];

  /**
   * Find all active currencies where a country is the issuer.
   *
   * @param countryCode - ISO 3166-1 alpha-2 country code (e.g., "CH", "GB")
   */
  issuedBy(countryCode: string): Currency[];

  /**
   * Find all active currencies used in a country (any relationship).
   *
   * @param countryCode - ISO 3166-1 alpha-2 country code
   */
  usedIn(countryCode: string): Currency[];

  // -- Statistics ---------------------------------------------------------

  /** Number of active ISO 4217 currencies. */
  readonly activeCount: number;

  /** Number of withdrawn ISO 4217 currencies. */
  readonly withdrawnCount: number;

  /** Number of non-ISO currencies. */
  readonly nonIsoCount: number;

  /** Number of active currencies that are pegged. */
  readonly peggedCount: number;

  /** Number of active currencies that float independently. */
  readonly independentCount: number;

  /**
   * Number of active currencies. Same as `activeCount`.
   * Enables `registry.size` usage.
   */
  readonly size: number;

  /**
   * Return a summary object with registry statistics.
   * Useful for logging, monitoring, and sanity checks.
   */
  summary(): RegistrySummary;

  // -- Existence check ----------------------------------------------------

  /**
   * Check if a currency code exists in the registry (any category).
   *
   * @param code - Currency code (case-insensitive)
   * @returns `true` if the code exists in any category
   */
  has(code: string): boolean;

  // -- Iteration ----------------------------------------------------------

  /**
   * Iterate over all active currencies.
   * Enables `for (const c of registry)` syntax.
   */
  [Symbol.iterator](): Iterator<Currency>;

  // -- Display ------------------------------------------------------------

  /** Return a human-readable string representation. */
  toString(): string;
}