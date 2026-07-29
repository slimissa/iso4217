//! ISO 4217 Currency Registry — Rust Crate
//!
//! A zero-dependency Rust interface to the canonical ISO 4217 currency registry.
//! Provides `Currency` and `CurrencyRegistry` types with minor/major unit
//! conversion, peg information access, and country relationship lookup.
//!
//! The registry data is embedded at compile time via `include_str!()`.
//! No file I/O at runtime. No network calls. No dependencies beyond `serde`
//! and `serde_json` for JSON parsing.
//!
//! # Quick Start
//!
//! ```rust
//! use iso4217::CurrencyRegistry;
//!
//! let registry = CurrencyRegistry::load().expect("Failed to load registry");
//! let usd = registry.active("USD").expect("USD not found");
//!
//! assert_eq!(usd.code, "USD");
//! assert_eq!(usd.minor_units, 2);
//! assert_eq!(usd.to_minor(100.50), 10050);
//! assert_eq!(usd.format(100.50), "$100.50");
//!
//! // Find all currencies pegged to USD
//! for c in registry.pegged_to("USD") {
//!     println!("{} pegged at {} since {}",
//!         c.code,
//!         c.peg_rate.unwrap_or(0.0),
//!         c.pegged_since.as_deref().unwrap_or("unknown")
//!     );
//! }
//! ```
//!
//! License: Apache 2.0

use serde::Deserialize;
use std::collections::HashMap;
use std::fmt;

// ---------------------------------------------------------------------------
// Embedded registry data
// ---------------------------------------------------------------------------

/// The canonical iso4217.json file, embedded at compile time.
///
/// This means the crate has zero runtime dependencies on file I/O.
/// The registry data lives in the binary.
const REGISTRY_JSON: &str = include_str!("../../../iso4217.json");

// ---------------------------------------------------------------------------
// Raw JSON structures (private — used only for deserialization)
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct RawRegistry {
    meta: Option<RawMeta>,
    source: Option<RawSource>,
    currencies: Option<RawCurrencies>,
    non_iso: Option<RawNonIso>,
}

#[derive(Debug, Deserialize)]
struct RawMeta {
    version: Option<String>,
    updated: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawSource {
    last_amendment_applied: Option<u32>,
    last_amendment_date: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawCurrencies {
    active: Option<Vec<RawCurrency>>,
    withdrawn: Option<Vec<RawCurrency>>,
}

#[derive(Debug, Deserialize)]
struct RawNonIso {
    cryptocurrencies: Option<Vec<RawCurrency>>,
    stablecoins: Option<Vec<RawCurrency>>,
    commodities: Option<Vec<RawCurrency>>,
    special_purpose: Option<Vec<RawCurrency>>,
}

#[derive(Debug, Deserialize, Clone)]
struct RawCurrency {
    code: String,
    #[serde(default)]
    numeric: String,
    name: String,
    minor_units: u8,
    #[serde(default)]
    symbol: String,
    #[serde(default)]
    entity: String,
    #[serde(default)]
    central_bank: String,
    // Peg fields
    pegged_to: Option<String>,
    pegged_since: Option<String>,
    peg_rate: Option<f64>,
    peg_band_pct: Option<f64>,
    #[serde(default = "default_true")]
    is_independent: bool,
    // Optional fields
    note: Option<String>,
    #[serde(default)]
    countries: Vec<RawCountry>,
    // Withdrawn fields
    withdrawn_date: Option<String>,
    replaced_by: Option<String>,
    conversion_rate: Option<f64>,
    // Non-ISO fields
    #[serde(rename = "type")]
    currency_type: Option<String>,
    market_cap_rank: Option<u32>,
    peg_mechanism: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct RawCountry {
    code: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    relationship: String,
}

fn default_true() -> bool {
    true
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/// A country or territory where a currency is used.
#[derive(Debug, Clone)]
pub struct Country {
    /// ISO 3166-1 alpha-2 country code (e.g., "US", "FR").
    pub code: String,
    /// Human-readable country or territory name.
    pub name: String,
    /// Relationship to the currency: "issuing", "adopting", "territory",
    /// "parallel", or "local_issue".
    pub relationship: String,
}

impl From<RawCountry> for Country {
    fn from(raw: RawCountry) -> Self {
        Country {
            code: raw.code,
            name: raw.name,
            relationship: raw.relationship,
        }
    }
}

/// Represents a single currency from the ISO 4217 registry.
///
/// Provides read-only access to all currency properties plus convenience
/// methods for converting between major and minor currency units.
///
/// # Examples
///
/// ```rust
/// let usd = registry.active("USD").unwrap();
/// assert_eq!(usd.to_minor(100.50), 10050);
/// assert_eq!(usd.from_minor(10050), 100.5);
/// println!("{}", usd.format(100.50)); // "$100.50"
/// ```
#[derive(Debug, Clone)]
pub struct Currency {
    /// ISO 4217 alphabetic currency code (e.g., "USD").
    pub code: String,
    /// ISO 4217 numeric currency code as a 3-digit string (e.g., "840").
    pub numeric: String,
    /// Official English name of the currency (e.g., "US Dollar").
    pub name: String,
    /// Number of decimal places for the minor currency unit.
    ///
    /// 0 = no subdivision (JPY, KRW).
    /// 2 = standard cents/pence (USD, EUR).
    /// 3 = dinar subdivisions (KWD, BHD, OMR, JOD, TND, LYD, IQD).
    /// 8 = Bitcoin. 18 = Ethereum.
    pub minor_units: u8,
    /// Primary display symbol. May be empty string if none exists.
    pub symbol: String,
    /// Issuing entity or monetary authority.
    pub entity: String,
    /// Official name of the central bank.
    pub central_bank: String,
    /// The currency or basket this currency is pegged to, or `None` if floating.
    pub pegged_to: Option<String>,
    /// Date the peg was established (ISO 8601), or `None`.
    pub pegged_since: Option<String>,
    /// Official peg rate (units of this currency per 1 unit of anchor), or `None`.
    pub peg_rate: Option<f64>,
    /// Allowed deviation from the peg as a percentage. 0.0 = fixed peg.
    pub peg_band_pct: Option<f64>,
    /// `true` if the currency floats independently; `false` if hard-pegged.
    pub is_independent: bool,
    /// Optional note for special cases or market conventions.
    pub note: Option<String>,
    /// Countries and territories where this currency is primary legal tender.
    pub countries: Vec<Country>,
    /// Withdrawal date (withdrawn currencies only).
    pub withdrawn_date: Option<String>,
    /// Replacement currency code (withdrawn currencies only).
    pub replaced_by: Option<String>,
    /// Official conversion rate (withdrawn currencies only).
    pub conversion_rate: Option<f64>,
    /// Type for non-ISO currencies ("cryptocurrency", "stablecoin", etc.).
    pub currency_type: Option<String>,
    /// Market cap rank (crypto/stablecoins only).
    pub market_cap_rank: Option<u32>,
    /// Peg mechanism for stablecoins (e.g., "Fiat-collateralized").
    pub peg_mechanism: Option<String>,
}

impl Currency {
    /// `true` if this currency is pegged to something.
    pub fn is_pegged(&self) -> bool {
        self.pegged_to.is_some()
    }

    /// Returns countries that are the sovereign issuer of this currency.
    pub fn issuing_countries(&self) -> Vec<&Country> {
        self.countries
            .iter()
            .filter(|c| c.relationship == "issuing")
            .collect()
    }

    /// Returns countries that use this currency without being the issuer.
    pub fn adopting_countries(&self) -> Vec<&Country> {
        self.countries
            .iter()
            .filter(|c| c.relationship == "adopting")
            .collect()
    }

    /// Convert a major currency amount to minor units.
    ///
    /// # Examples
    ///
    /// ```rust
    /// assert_eq!(usd.to_minor(100.50), 10050);
    /// assert_eq!(jpy.to_minor(500.0), 500);
    /// assert_eq!(kwd.to_minor(1.500), 1500);
    /// assert_eq!(btc.to_minor(0.000_000_01), 1);
    /// ```
    ///
    /// # Panics
    ///
    /// Panics if `major_amount` is NaN or infinite.
    pub fn to_minor(&self, major_amount: f64) -> i64 {
        assert!(
            major_amount.is_finite(),
            "Cannot convert NaN or infinity to minor units"
        );
        let factor = 10_f64.powi(self.minor_units as i32);
        (major_amount * factor).round() as i64
    }

    /// Convert minor units to a major currency amount.
    ///
    /// # Examples
    ///
    /// ```rust
    /// assert_eq!(usd.from_minor(10050), 100.5);
    /// assert_eq!(jpy.from_minor(500), 500.0);
    /// ```
    pub fn from_minor(&self, minor_amount: i64) -> f64 {
        let factor = 10_f64.powi(self.minor_units as i32);
        minor_amount as f64 / factor
    }

    /// Format a major currency amount with the currency symbol.
    ///
    /// # Examples
    ///
    /// ```rust
    /// assert_eq!(usd.format(100.50), "$100.50");
    /// assert_eq!(jpy.format(500.0), "¥500");
    /// ```
    pub fn format(&self, major_amount: f64) -> String {
        if self.minor_units == 0 {
            format!("{}{}", self.symbol, major_amount.round() as i64)
        } else {
            format!("{}{:.prec$}", self.symbol, major_amount, prec = self.minor_units as usize)
        }
    }
}

impl fmt::Display for Currency {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{} — {} (minor_units={})",
            self.code, self.name, self.minor_units
        )
    }
}

impl From<RawCurrency> for Currency {
    fn from(raw: RawCurrency) -> Self {
        Currency {
            code: raw.code,
            numeric: raw.numeric,
            name: raw.name,
            minor_units: raw.minor_units,
            symbol: raw.symbol,
            entity: raw.entity,
            central_bank: raw.central_bank,
            pegged_to: raw.pegged_to,
            pegged_since: raw.pegged_since,
            peg_rate: raw.peg_rate,
            peg_band_pct: raw.peg_band_pct,
            is_independent: raw.is_independent,
            note: raw.note,
            countries: raw.countries.into_iter().map(Country::from).collect(),
            withdrawn_date: raw.withdrawn_date,
            replaced_by: raw.replaced_by,
            conversion_rate: raw.conversion_rate,
            currency_type: raw.currency_type,
            market_cap_rank: raw.market_cap_rank,
            peg_mechanism: raw.peg_mechanism,
        }
    }
}

// ---------------------------------------------------------------------------
// CurrencyRegistry
// ---------------------------------------------------------------------------

/// Summary statistics for the registry.
#[derive(Debug, Clone)]
pub struct RegistrySummary {
    /// Semantic version of the registry data.
    pub version: String,
    /// Date the registry was last updated (ISO 8601).
    pub updated: String,
    /// Most recent ISO 4217 amendment number applied.
    pub amendment: u32,
    /// Number of active ISO 4217 currencies.
    pub active_currencies: usize,
    /// Number of withdrawn ISO 4217 currencies.
    pub withdrawn_currencies: usize,
    /// Number of non-ISO currencies.
    pub non_iso_currencies: usize,
    /// Number of active currencies that are pegged.
    pub pegged_currencies: usize,
    /// Number of active currencies that float independently.
    pub independent_currencies: usize,
    /// Distribution of minor_units values across active currencies.
    pub minor_units_distribution: HashMap<u8, usize>,
}

/// The main registry interface for looking up ISO 4217 currencies.
///
/// Loads the canonical iso4217.json data at compile time via `include_str!()`.
/// Provides lookup methods for active, withdrawn, and non-ISO currencies.
///
/// # Examples
///
/// ```rust
/// use iso4217::CurrencyRegistry;
///
/// let registry = CurrencyRegistry::load().unwrap();
/// let usd = registry.active("USD").unwrap();
/// let pegged = registry.pegged_to("USD");
///
/// for c in registry.all_active() {
///     println!("{}", c);
/// }
/// ```
#[derive(Debug)]
pub struct CurrencyRegistry {
    version: String,
    updated: String,
    amendment: u32,
    amendment_date: String,
    active: HashMap<String, Currency>,
    withdrawn: HashMap<String, Currency>,
    non_iso: HashMap<String, Currency>,
    all: HashMap<String, Currency>,
}

impl CurrencyRegistry {
    /// Load the registry from the embedded JSON data.
    ///
    /// This parses the JSON at call time. The data is embedded in the binary
    /// at compile time — no file I/O, no network calls.
    ///
    /// # Errors
    ///
    /// Returns `Err` if the embedded JSON cannot be parsed. This should never
    /// happen with a valid registry file, but is surfaced for safety.
    pub fn load() -> Result<Self, String> {
        let raw: RawRegistry = serde_json::from_str(REGISTRY_JSON)
            .map_err(|e| format!("Failed to parse registry JSON: {}", e))?;

        let mut active = HashMap::new();
        let mut withdrawn = HashMap::new();
        let mut non_iso = HashMap::new();
        let mut all = HashMap::new();

        // Active currencies
        if let Some(ref currencies) = raw.currencies {
            if let Some(ref active_list) = currencies.active {
                for c in active_list {
                    let code = c.code.clone();
                    let currency = Currency::from(c.clone());
                    active.insert(code.clone(), currency.clone());
                    all.insert(code, currency);
                }
            }

            // Withdrawn currencies
            if let Some(ref withdrawn_list) = currencies.withdrawn {
                for c in withdrawn_list {
                    let code = c.code.clone();
                    let currency = Currency::from(c.clone());
                    withdrawn.insert(code.clone(), currency.clone());
                    all.insert(code, currency);
                }
            }
        }

        // Non-ISO currencies
        if let Some(ref non_iso_data) = raw.non_iso {
            let categories: Vec<&Option<Vec<RawCurrency>>> = vec![
                &non_iso_data.cryptocurrencies,
                &non_iso_data.stablecoins,
                &non_iso_data.commodities,
                &non_iso_data.special_purpose,
            ];

            for category in categories {
                if let Some(list) = category {
                    for c in list {
                        let code = c.code.clone();
                        let currency = Currency::from(c.clone());
                        non_iso.insert(code.clone(), currency.clone());
                        all.insert(code, currency);
                    }
                }
            }
        }

        let version = raw
            .meta
            .as_ref()
            .and_then(|m| m.version.clone())
            .unwrap_or_else(|| "unknown".to_string());

        let updated = raw
            .meta
            .as_ref()
            .and_then(|m| m.updated.clone())
            .unwrap_or_else(|| "unknown".to_string());

        let amendment = raw
            .source
            .as_ref()
            .and_then(|s| s.last_amendment_applied)
            .unwrap_or(0);

        let amendment_date = raw
            .source
            .as_ref()
            .and_then(|s| s.last_amendment_date.clone())
            .unwrap_or_else(|| "unknown".to_string());

        Ok(CurrencyRegistry {
            version,
            updated,
            amendment,
            amendment_date,
            active,
            withdrawn,
            non_iso,
            all,
        })
    }

    // -- Metadata -----------------------------------------------------------

    /// Semantic version of the registry data.
    pub fn version(&self) -> &str {
        &self.version
    }

    /// Date the registry was last updated (ISO 8601).
    pub fn updated(&self) -> &str {
        &self.updated
    }

    /// Most recent ISO 4217 amendment number applied.
    pub fn amendment(&self) -> u32 {
        self.amendment
    }

    /// Date of the most recent amendment applied.
    pub fn amendment_date(&self) -> &str {
        &self.amendment_date
    }

    // -- Lookup methods -----------------------------------------------------

    /// Look up any currency by code (case-insensitive).
    ///
    /// Searches active, withdrawn, and non-ISO currencies in that order.
    pub fn currency(&self, code: &str) -> Option<&Currency> {
        self.all.get(&code.to_uppercase())
    }

    /// Look up an active ISO 4217 currency by code (case-insensitive).
    pub fn active(&self, code: &str) -> Option<&Currency> {
        self.active.get(&code.to_uppercase())
    }

    /// Look up a withdrawn ISO 4217 currency by code (case-insensitive).
    pub fn withdrawn(&self, code: &str) -> Option<&Currency> {
        self.withdrawn.get(&code.to_uppercase())
    }

    /// Look up a non-ISO currency by code (case-insensitive).
    pub fn non_iso(&self, code: &str) -> Option<&Currency> {
        self.non_iso.get(&code.to_uppercase())
    }

    // -- Collection accessors -----------------------------------------------

    /// Return all active ISO 4217 currencies.
    pub fn all_active(&self) -> Vec<&Currency> {
        self.active.values().collect()
    }

    /// Return all withdrawn ISO 4217 currencies.
    pub fn all_withdrawn(&self) -> Vec<&Currency> {
        self.withdrawn.values().collect()
    }

    /// Return all non-ISO currencies.
    pub fn all_non_iso(&self) -> Vec<&Currency> {
        self.non_iso.values().collect()
    }

    /// Return all currencies across all categories.
    pub fn all_currencies(&self) -> Vec<&Currency> {
        self.all.values().collect()
    }

    // -- Filtering ----------------------------------------------------------

    /// Find all active currencies pegged to a specific anchor currency.
    ///
    /// ```rust
    /// let usd_pegged = registry.pegged_to("USD");
    /// for c in usd_pegged {
    ///     println!("{} is pegged to USD", c.code);
    /// }
    /// ```
    pub fn pegged_to(&self, anchor_code: &str) -> Vec<&Currency> {
        let anchor = anchor_code.to_uppercase();
        self.active
            .values()
            .filter(|c| {
                c.pegged_to
                    .as_ref()
                    .map(|p| p.to_uppercase().contains(&anchor))
                    .unwrap_or(false)
            })
            .collect()
    }

    /// Return all active currencies that are independently floating.
    pub fn independent(&self) -> Vec<&Currency> {
        self.active
            .values()
            .filter(|c| c.is_independent)
            .collect()
    }

    /// Find all active currencies with a specific number of minor units.
    ///
    /// ```rust
    /// let three_decimal = registry.with_minor_units(3);
    /// // Returns BHD, JOD, KWD, LYD, OMR, TND, IQD
    /// ```
    pub fn with_minor_units(&self, n: u8) -> Vec<&Currency> {
        self.active
            .values()
            .filter(|c| c.minor_units == n)
            .collect()
    }

    /// Find all active currencies where a country is the issuer.
    pub fn issued_by(&self, country_code: &str) -> Vec<&Currency> {
        let code = country_code.to_uppercase();
        self.active
            .values()
            .filter(|c| {
                c.countries
                    .iter()
                    .any(|country| country.code == code && country.relationship == "issuing")
            })
            .collect()
    }

    /// Find all active currencies used in a country (any relationship).
    pub fn used_in(&self, country_code: &str) -> Vec<&Currency> {
        let code = country_code.to_uppercase();
        self.active
            .values()
            .filter(|c| c.countries.iter().any(|country| country.code == code))
            .collect()
    }

    // -- Statistics ---------------------------------------------------------

    /// Number of active ISO 4217 currencies.
    pub fn active_count(&self) -> usize {
        self.active.len()
    }

    /// Number of withdrawn ISO 4217 currencies.
    pub fn withdrawn_count(&self) -> usize {
        self.withdrawn.len()
    }

    /// Number of non-ISO currencies.
    pub fn non_iso_count(&self) -> usize {
        self.non_iso.len()
    }

    /// Number of active currencies that are pegged.
    pub fn pegged_count(&self) -> usize {
        self.active.values().filter(|c| c.is_pegged()).count()
    }

    /// Number of active currencies that float independently.
    pub fn independent_count(&self) -> usize {
        self.active.values().filter(|c| c.is_independent).count()
    }

    /// Return a summary with registry statistics.
    pub fn summary(&self) -> RegistrySummary {
        let mut minor_units_distribution = HashMap::new();
        for c in self.active.values() {
            *minor_units_distribution.entry(c.minor_units).or_insert(0) += 1;
        }

        RegistrySummary {
            version: self.version.clone(),
            updated: self.updated.clone(),
            amendment: self.amendment,
            active_currencies: self.active.len(),
            withdrawn_currencies: self.withdrawn.len(),
            non_iso_currencies: self.non_iso.len(),
            pegged_currencies: self.pegged_count(),
            independent_currencies: self.independent_count(),
            minor_units_distribution,
        }
    }

    // -- Existence check ----------------------------------------------------

    /// Check if a currency code exists in the registry (any category).
    pub fn contains(&self, code: &str) -> bool {
        self.all.contains_key(&code.to_uppercase())
    }

    // -- Iteration ----------------------------------------------------------

    /// Iterate over all active currencies.
    pub fn iter(&self) -> impl Iterator<Item = &Currency> {
        self.active.values()
    }
}

impl fmt::Display for CurrencyRegistry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "CurrencyRegistry(version={}, active={}, withdrawn={}, non_iso={})",
            self.version,
            self.active.len(),
            self.withdrawn.len(),
            self.non_iso.len()
        )
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn registry() -> CurrencyRegistry {
        CurrencyRegistry::load().expect("Failed to load registry")
    }

    #[test]
    fn test_load_registry() {
        let reg = registry();
        assert!(!reg.version().is_empty());
        assert!(reg.active_count() > 50, "Expected >50 active currencies");
        assert!(reg.withdrawn_count() > 0, "Expected withdrawn currencies");
    }

    #[test]
    fn test_lookup_usd() {
        let reg = registry();
        let usd = reg.active("USD").expect("USD should exist");
        assert_eq!(usd.code, "USD");
        assert_eq!(usd.numeric, "840");
        assert_eq!(usd.minor_units, 2);
        assert_eq!(usd.name, "US Dollar");
        assert!(usd.is_independent);
        assert!(!usd.is_pegged());
    }

    #[test]
    fn test_lookup_case_insensitive() {
        let reg = registry();
        assert!(reg.active("usd").is_some());
        assert!(reg.active("Usd").is_some());
        assert!(reg.active("USD").is_some());
    }

    #[test]
    fn test_lookup_jpy() {
        let reg = registry();
        let jpy = reg.active("JPY").expect("JPY should exist");
        assert_eq!(jpy.minor_units, 0);
        assert_eq!(jpy.to_minor(500.0), 500);
        assert_eq!(jpy.from_minor(500), 500.0);
    }

    #[test]
    fn test_lookup_kwd() {
        let reg = registry();
        let kwd = reg.active("KWD").expect("KWD should exist");
        assert_eq!(kwd.minor_units, 3);
        assert_eq!(kwd.to_minor(1.500), 1500);
        assert_eq!(kwd.from_minor(1500), 1.5);
    }

    #[test]
    fn test_to_minor_usd() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        assert_eq!(usd.to_minor(100.50), 10050);
        assert_eq!(usd.to_minor(0.01), 1);
        assert_eq!(usd.to_minor(0.00), 0);
    }

    #[test]
    fn test_from_minor_usd() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        assert_eq!(usd.from_minor(10050), 100.5);
        assert_eq!(usd.from_minor(1), 0.01);
    }

    #[test]
    #[should_panic(expected = "Cannot convert NaN")]
    fn test_to_minor_nan_panics() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        usd.to_minor(f64::NAN);
    }

    #[test]
    #[should_panic(expected = "Cannot convert NaN")]
    fn test_to_minor_infinity_panics() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        usd.to_minor(f64::INFINITY);
    }

    #[test]
    fn test_format_usd() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        assert_eq!(usd.format(100.50), "$100.50");
        assert_eq!(usd.format(0.99), "$0.99");
    }

    #[test]
    fn test_format_jpy() {
        let reg = registry();
        let jpy = reg.active("JPY").unwrap();
        assert_eq!(jpy.format(500.0), "¥500");
    }

    #[test]
    fn test_pegged_currencies() {
        let reg = registry();
        let usd_pegged = reg.pegged_to("USD");
        // AED, SAR, QAR, JOD, BHD, OMR, HKD should all be pegged to USD
        assert!(!usd_pegged.is_empty());
        let codes: Vec<&str> = usd_pegged.iter().map(|c| c.code.as_str()).collect();
        assert!(codes.contains(&"AED"));
        assert!(codes.contains(&"SAR"));
    }

    #[test]
    fn test_aed_peg() {
        let reg = registry();
        let aed = reg.active("AED").unwrap();
        assert_eq!(aed.pegged_to.as_deref(), Some("USD"));
        assert!(!aed.is_independent);
        assert!(aed.is_pegged());
        assert_eq!(aed.peg_rate, Some(3.6725));
    }

    #[test]
    fn test_dkk_peg() {
        let reg = registry();
        let dkk = reg.active("DKK").unwrap();
        assert_eq!(dkk.pegged_to.as_deref(), Some("EUR"));
        assert_eq!(dkk.peg_band_pct, Some(2.25));
    }

    #[test]
    fn test_withdrawn_dem() {
        let reg = registry();
        let dem = reg.withdrawn("DEM").expect("DEM should exist");
        assert_eq!(dem.name, "German Mark");
        assert_eq!(dem.replaced_by.as_deref(), Some("EUR"));
        assert_eq!(dem.conversion_rate, Some(1.95583));
    }

    #[test]
    fn test_non_iso_btc() {
        let reg = registry();
        let btc = reg.non_iso("BTC").expect("BTC should exist");
        assert_eq!(btc.minor_units, 8);
        assert_eq!(btc.to_minor(0.000_000_01), 1);
    }

    #[test]
    fn test_contains() {
        let reg = registry();
        assert!(reg.contains("USD"));
        assert!(reg.contains("usd"));
        assert!(!reg.contains("XXX"));
    }

    #[test]
    fn test_with_minor_units() {
        let reg = registry();
        let three = reg.with_minor_units(3);
        let codes: Vec<&str> = three.iter().map(|c| c.code.as_str()).collect();
        assert!(codes.contains(&"KWD"));
        assert!(codes.contains(&"BHD"));
        assert!(codes.contains(&"OMR"));
        assert!(codes.contains(&"JOD"));
        assert!(codes.contains(&"TND"));
        assert!(codes.contains(&"LYD"));
        assert!(codes.contains(&"IQD"));
    }

    #[test]
    fn test_independent() {
        let reg = registry();
        let independent = reg.independent();
        let codes: Vec<&str> = independent.iter().map(|c| c.code.as_str()).collect();
        assert!(codes.contains(&"USD"));
        assert!(codes.contains(&"EUR"));
        assert!(codes.contains(&"JPY"));
        // Pegged currencies should not be in independent list
        assert!(!codes.contains(&"AED"));
    }

    #[test]
    fn test_summary() {
        let reg = registry();
        let summary = reg.summary();
        assert_eq!(summary.active_currencies, reg.active_count());
        assert!(summary.pegged_currencies > 0);
        assert!(summary.independent_currencies > 0);
        assert!(summary.minor_units_distribution.contains_key(&2));
    }

    #[test]
    fn test_issuing_countries() {
        let reg = registry();
        let chf = reg.active("CHF").unwrap();
        let issuing = chf.issuing_countries();
        assert_eq!(issuing.len(), 1);
        assert_eq!(issuing[0].code, "CH");
        assert_eq!(issuing[0].relationship, "issuing");
    }

    #[test]
    fn test_adopting_countries() {
        let reg = registry();
        let usd = reg.active("USD").unwrap();
        let adopting = usd.adopting_countries();
        let codes: Vec<&str> = adopting.iter().map(|c| c.code.as_str()).collect();
        assert!(codes.contains(&"EC")); // Ecuador
        assert!(codes.contains(&"PA")); // Panama
        assert!(codes.contains(&"SV")); // El Salvador
    }
}