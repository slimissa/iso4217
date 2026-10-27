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
const REGISTRY_JSON: &str = include_str!("../iso4217.json");

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
    peg_type: Option<String>,
    pegged_since: Option<String>,
    peg_rate: Option<f64>,
    peg_band_pct: Option<f64>,
    #[serde(default)]
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
    // v1.6.0 fields
    classification: Option<String>,
    numeric_reused: Option<bool>,
    source_url: Option<String>,
    code_lifetime: Option<RawCodeLifetime>,
}

#[derive(Debug, Deserialize, Clone)]
struct RawCodeLifetime {
    from: Option<String>,
    to: String,
}

#[derive(Debug, Deserialize)]
struct RawNonIso {
    cryptocurrencies: Option<Vec<RawCurrency>>,
    stablecoins: Option<Vec<RawCurrency>>,
    commodities: Option<Vec<RawCurrency>>,
    special_purpose: Option<Vec<RawCurrency>>,
}


#[derive(Debug, Deserialize, Clone)]
struct RawCountry {
    code: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    relationship: String,
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
/// # use iso4217::CurrencyRegistry;
/// # let registry = CurrencyRegistry::load().unwrap();
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
    /// How to interpret `pegged_to`.
    ///
    /// - `"single"`: `pegged_to` is a parseable ISO 4217 code (e.g. AED -> `"USD"`).
    /// - `"basket"`: `pegged_to` is a free-text description of a weighted
    ///   basket peg (e.g. MAD -> `"EUR+USD basket"`).
    /// - `"undisclosed"`: pegged, but the peg mechanism/composition is not
    ///   public (e.g. KWD -> `"Currency basket"`).
    /// - `None`: not pegged.
    ///
    /// Do not assume `pegged_to` is a parseable currency code without
    /// checking `peg_type.as_deref() == Some("single")` first.
    pub peg_type: Option<String>,
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
    /// Classification of active currencies: "circulating", "fund",
    /// "settlement", or "indexation". None for withdrawn entries.
    pub classification: Option<String>,
    /// True when this active currency's numeric code also appears on a
    /// withdrawn entry.
    pub numeric_reused: Option<bool>,
    /// URL of the entry's primary source.
    pub source_url: Option<String>,
    /// The withdrawn code's full valid range.
    pub code_lifetime: Option<CodeLifetime>,
}

/// The valid range of a withdrawn code.
#[derive(Debug, Clone)]
pub struct CodeLifetime {
    /// ISO assignment date, or None when undocumented.
    pub from: Option<String>,
    /// Withdrawal date. Equal to `Currency::withdrawn_date`.
    pub to: String,
}

/// Why [`Currency::try_to_minor`] could not return a number (ADR 0013,
/// `docs/decisions/wrapper-numeric-contract.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MinorError {
    /// The amount is NaN or infinite.
    NonFinite,
    /// The amount, scaled to minor units and rounded, does not fit in an `i64` (`|result| >= 2^63`), or scaling it
    /// overflowed `f64`. The message says "amount too large".
    Overflow,
}

impl fmt::Display for MinorError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MinorError::NonFinite => write!(f, "amount is not a finite number"),
            MinorError::Overflow => write!(f, "amount too large for i64 minor units"),
        }
    }
}

impl std::error::Error for MinorError {}

/// `10^n`, exact as an `f64` for `n <= 22`. Every wrapper takes `10^n` from the same exact table, so the one
/// floating-point multiplication in the conversion is the same in all four languages.
const POW10_EXACT: [f64; 23] = [
    1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20,
    1e21, 1e22,
];

/// `2^63`: a rounded amount whose magnitude is at or above it cannot be returned as an `i64`.
const I64_LIMIT: f64 = 9_223_372_036_854_775_808.0;

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

    /// `x * 10^n` rounded half away from zero, as an integer-valued `f64`.
    ///
    /// The product is one IEEE-double multiplication; the round is exact (`p - trunc(p)` is exact for doubles), so
    /// there is no `floor(x + 0.5)` and no `as i64` cast of an out-of-range float. The int64 bound is not applied here.
    fn round_scaled(&self, x: f64) -> Result<f64, MinorError> {
        if !x.is_finite() {
            return Err(MinorError::NonFinite);
        }
        let scale = POW10_EXACT.get(self.minor_units as usize).ok_or(MinorError::Overflow)?;
        let p = x * scale;
        if !p.is_finite() {
            return Err(MinorError::Overflow);
        }
        let mut r = p.trunc();
        if (p - r).abs() >= 0.5 {
            r += p.signum();
        }
        Ok(r)
    }

    /// Convert a major currency amount to minor units, rounding half away from zero, and return an error instead of
    /// a wrong number: [`MinorError::NonFinite`] for NaN and infinity, [`MinorError::Overflow`] when the result does
    /// not fit in an `i64`.
    ///
    /// # Examples
    ///
    /// ```rust
    /// # use iso4217::{CurrencyRegistry, MinorError};
    /// # let registry = CurrencyRegistry::load().unwrap();
    /// # let usd = registry.active("USD").unwrap();
    /// assert_eq!(usd.try_to_minor(100.50), Ok(10050));
    /// assert_eq!(usd.try_to_minor(1e17), Err(MinorError::Overflow));
    /// assert_eq!(usd.try_to_minor(f64::NAN), Err(MinorError::NonFinite));
    /// ```
    pub fn try_to_minor(&self, major_amount: f64) -> Result<i64, MinorError> {
        let r = self.round_scaled(major_amount)?;
        if r.abs() >= I64_LIMIT {
            return Err(MinorError::Overflow);
        }
        Ok(r as i64)
    }

    /// Convert a major currency amount to minor units.
    ///
    /// # Examples
    ///
    /// ```rust
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
    /// # let usd = registry.active("USD").unwrap();
    /// # let jpy = registry.active("JPY").unwrap();
    /// # let kwd = registry.active("KWD").unwrap();
    /// # let btc = registry.non_iso("BTC").unwrap();
    /// assert_eq!(usd.to_minor(100.50), 10050);
    /// assert_eq!(jpy.to_minor(500.0), 500);
    /// assert_eq!(kwd.to_minor(1.500), 1500);
    /// assert_eq!(btc.to_minor(0.000_000_01), 1);
    /// ```
    ///
    /// # Panics
    ///
    /// Panics if `major_amount` is NaN, infinite, or too large for an `i64` amount of minor units (the message says
    /// "amount too large"). Use [`Currency::try_to_minor`] to receive an error instead.
    pub fn to_minor(&self, major_amount: f64) -> i64 {
        match self.try_to_minor(major_amount) {
            Ok(minor) => minor,
            Err(MinorError::NonFinite) => panic!("Cannot convert NaN or infinity to minor units"),
            Err(e) => panic!("Cannot convert {} to minor units: {}", major_amount, e),
        }
    }

    /// Convert minor units to a major currency amount.
    ///
    /// # Examples
    ///
    /// ```rust
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
    /// # let usd = registry.active("USD").unwrap();
    /// # let jpy = registry.active("JPY").unwrap();
    /// assert_eq!(usd.from_minor(10050), 100.5);
    /// assert_eq!(jpy.from_minor(500), 500.0);
    /// ```
    pub fn from_minor(&self, minor_amount: i64) -> f64 {
        let factor = 10_f64.powi(self.minor_units as i32);
        minor_amount as f64 / factor
    }

    /// Format a major currency amount with the currency symbol.
    ///
    /// The amount is rounded exactly as [`Currency::to_minor`] rounds it (half away from zero) and its digits are
    /// printed from that rounded value, so `format` and `to_minor` cannot disagree. It never panics: NaN is `nan`,
    /// infinity (or an amount whose scaled value overflows `f64`) is `inf` or `-inf` after the symbol. Fractional
    /// currencies get comma thousands separators; 0-decimal currencies print ungrouped (ADR 0013, D5 and D6).
    ///
    /// # Examples
    ///
    /// ```rust
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
    /// # let usd = registry.active("USD").unwrap();
    /// # let jpy = registry.active("JPY").unwrap();
    /// assert_eq!(usd.format(100.50), "$100.50");
    /// assert_eq!(usd.format(1000.00), "$1,000.00");
    /// assert_eq!(jpy.format(500.0), "¥500");
    /// assert_eq!(usd.format(f64::NAN), "$nan");
    /// ```
    pub fn format(&self, major_amount: f64) -> String {
        let infinity = |negative: bool| format!("{}{}inf", self.symbol, if negative { "-" } else { "" });
        if major_amount.is_nan() {
            return format!("{}nan", self.symbol);
        }
        if major_amount.is_infinite() {
            return infinity(major_amount < 0.0);
        }
        let r = match self.round_scaled(major_amount) {
            Ok(r) => r,
            // a finite amount whose scaled value overflows f64
            Err(_) => return infinity(major_amount < 0.0),
        };
        let n = self.minor_units as usize;
        // Sign comes from the sign bit of the amount when there are decimals, and from the rounded value when there
        // are none: a negative amount that rounds to zero prints "$-0.00" but "¥0" (today's behavior in all four).
        let negative = (major_amount.is_sign_negative() && (n > 0 || r != 0.0)) || (n == 0 && r < 0.0);
        let mut digits = format!("{:.0}", r.abs()); // exact digits of an integer-valued f64
        if n > 0 {
            if digits.len() < n + 1 {
                digits = format!("{}{}", "0".repeat(n + 1 - digits.len()), digits);
            }
            let split = digits.len() - n;
            digits = format!("{}.{}", group_thousands(&digits[..split]), &digits[split..]);
        }
        format!("{}{}{}", self.symbol, if negative { "-" } else { "" }, digits)
    }
}

/// Inserts a comma every three digits, counting from the right. Rust's standard formatting has no grouping flag.
fn group_thousands(digits: &str) -> String {
    let n = digits.len();
    let mut grouped = String::with_capacity(n + n / 3);
    for (i, digit) in digits.chars().enumerate() {
        if i > 0 && (n - i) % 3 == 0 {
            grouped.push(',');
        }
        grouped.push(digit);
    }
    grouped
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
            peg_type: raw.peg_type,
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
                        classification: raw.classification,
            numeric_reused: raw.numeric_reused,
            source_url: raw.source_url,
            code_lifetime: raw.code_lifetime.map(|l| CodeLifetime {
                from: l.from,
                to: l.to,
            }),
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
// ---------------------------------------------------------------------------
// Registry data validation (v1.9.0, F13)
// ---------------------------------------------------------------------------
// One strict pass over the parsed serde_json::Value, before any typed decoding. The same contract is implemented in
// the Python, JavaScript and Go wrappers and tested against tests/cross_language_consistency.json
// ("malformed_registry_tests"). The rules are in docs/WRAPPER_VALIDATION.md.
//
// Malformed data is reported as `Err(String)` whose text starts with `malformed registry data: ` followed by the
// JSON path and the reason.

const MAX_MINOR_UNITS: i64 = 36;

const STRING_FIELDS: [&str; 14] = [
    "numeric", "symbol", "entity", "central_bank", "pegged_to", "peg_type", "pegged_since", "note",
    "withdrawn_date", "replaced_by", "type", "peg_mechanism", "classification", "source_url",
];
const NUMBER_FIELDS: [&str; 3] = ["peg_rate", "peg_band_pct", "conversion_rate"];
const INTEGER_FIELDS: [&str; 1] = ["market_cap_rank"];
const BOOLEAN_FIELDS: [&str; 2] = ["is_independent", "numeric_reused"];

type JsonMap = serde_json::Map<String, serde_json::Value>;

fn json_kind(v: &serde_json::Value) -> &'static str {
    match v {
        serde_json::Value::Null => "null",
        serde_json::Value::Bool(_) => "boolean",
        serde_json::Value::Number(_) => "number",
        serde_json::Value::String(_) => "string",
        serde_json::Value::Array(_) => "array",
        serde_json::Value::Object(_) => "object",
    }
}

fn malformed(path: &str, reason: &str) -> String {
    format!("malformed registry data: {}: {}", path, reason)
}

fn check_kind(v: &serde_json::Value, kind: &str, path: &str) -> Result<(), String> {
    let ok = match kind {
        "string" => v.is_string(),
        "number" => v.is_number(),
        "integer" => v.is_i64() || v.is_u64(),
        "boolean" => v.is_boolean(),
        "array" => v.is_array(),
        _ => v.is_object(),
    };
    if ok {
        Ok(())
    } else {
        Err(malformed(path, &format!("expected {}, got {}", kind, json_kind(v))))
    }
}

fn check_optional(obj: &JsonMap, key: &str, kind: &str, path: &str) -> Result<(), String> {
    match obj.get(key) {
        Some(v) if !v.is_null() => check_kind(v, kind, &format!("{}.{}", path, key)),
        _ => Ok(()),
    }
}

fn require<'a>(obj: &'a JsonMap, key: &str, kind: &str, path: &str) -> Result<&'a serde_json::Value, String> {
    let full = format!("{}.{}", path, key);
    let v = obj.get(key).ok_or_else(|| malformed(&full, "required field is missing"))?;
    check_kind(v, kind, &full)?;
    Ok(v)
}

fn validate_entry(entry: &serde_json::Value, path: &str) -> Result<(), String> {
    check_kind(entry, "object", path)?;
    let obj = entry.as_object().expect("checked above");
    let code = require(obj, "code", "string", path)?;
    require(obj, "name", "string", path)?;
    let minor_units = require(obj, "minor_units", "integer", path)?;
    if code.as_str() == Some("") {
        return Err(malformed(&format!("{}.code", path), "must not be empty"));
    }
    match minor_units.as_i64() {
        Some(n) if (0..=MAX_MINOR_UNITS).contains(&n) => {}
        _ => {
            return Err(malformed(
                &format!("{}.minor_units", path),
                &format!("expected an integer from 0 to {}, got {}", MAX_MINOR_UNITS, minor_units),
            ))
        }
    }
    for key in STRING_FIELDS {
        check_optional(obj, key, "string", path)?;
    }
    for key in NUMBER_FIELDS {
        check_optional(obj, key, "number", path)?;
    }
    for key in INTEGER_FIELDS {
        check_optional(obj, key, "integer", path)?;
    }
    for key in BOOLEAN_FIELDS {
        check_optional(obj, key, "boolean", path)?;
    }
    check_optional(obj, "countries", "array", path)?;
    if let Some(countries) = obj.get("countries").and_then(|v| v.as_array()) {
        for (i, country) in countries.iter().enumerate() {
            let cpath = format!("{}.countries[{}]", path, i);
            check_kind(country, "object", &cpath)?;
            let cobj = country.as_object().expect("checked above");
            require(cobj, "code", "string", &cpath)?;
            check_optional(cobj, "name", "string", &cpath)?;
            check_optional(cobj, "relationship", "string", &cpath)?;
        }
    }
    check_optional(obj, "code_lifetime", "object", path)?;
    if let Some(life) = obj.get("code_lifetime").and_then(|v| v.as_object()) {
        let lpath = format!("{}.code_lifetime", path);
        require(life, "to", "string", &lpath)?;
        check_optional(life, "from", "string", &lpath)?;
    }
    Ok(())
}

/// The contract treats a null optional entry field as absent. serde would reject `null` for a field typed as a
/// plain `Vec`, so nulls are dropped from the entries before typed decoding (the other wrappers treat them as absent
/// by construction).
fn drop_null_fields(root: &mut serde_json::Value) {
    let lists: [(&str, &[&str]); 2] = [
        ("currencies", &["active", "withdrawn"]),
        ("non_iso", &["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]),
    ];
    for (section, keys) in lists {
        if let Some(group) = root.get_mut(section).and_then(|v| v.as_object_mut()) {
            for key in keys {
                if let Some(list) = group.get_mut(*key).and_then(|v| v.as_array_mut()) {
                    for entry in list {
                        if let Some(obj) = entry.as_object_mut() {
                            obj.retain(|_, v| !v.is_null());
                        }
                    }
                }
            }
        }
    }
}

/// Checks the parsed JSON against the contract in docs/WRAPPER_VALIDATION.md.
fn validate_registry_data(root: &serde_json::Value) -> Result<(), String> {
    check_kind(root, "object", "$")?;
    let obj = root.as_object().expect("checked above");
    for section in ["meta", "source", "currencies", "non_iso"] {
        if let Some(v) = obj.get(section) {
            check_kind(v, "object", &format!("$.{}", section))?;
        }
    }
    let empty = JsonMap::new();
    let meta = obj.get("meta").and_then(|v| v.as_object()).unwrap_or(&empty);
    let source = obj.get("source").and_then(|v| v.as_object()).unwrap_or(&empty);
    check_optional(meta, "version", "string", "$.meta")?;
    check_optional(meta, "updated", "string", "$.meta")?;
    check_optional(source, "last_amendment_applied", "integer", "$.source")?;
    check_optional(source, "last_amendment_date", "string", "$.source")?;
    let lists: [(&str, &[&str]); 2] = [
        ("currencies", &["active", "withdrawn"]),
        ("non_iso", &["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]),
    ];
    for (section, keys) in lists {
        let group = obj.get(section).and_then(|v| v.as_object()).unwrap_or(&empty);
        for key in keys {
            if let Some(list) = group.get(*key) {
                let lpath = format!("$.{}.{}", section, key);
                check_kind(list, "array", &lpath)?;
                for (i, entry) in list.as_array().expect("checked above").iter().enumerate() {
                    validate_entry(entry, &format!("{}[{}]", lpath, i))?;
                }
            }
        }
    }
    Ok(())
}

/// Loads the canonical iso4217.json data at compile time via `include_str!()`.
/// Provides lookup methods for active, withdrawn, and non-ISO currencies.
///
/// # Examples
///
/// ```rust
/// # use iso4217::CurrencyRegistry;
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
    /// Returns `Err` if the embedded JSON is malformed: not valid JSON, or outside the
    /// contract in docs/WRAPPER_VALIDATION.md. The text starts with
    /// `malformed registry data: ` followed by the JSON path and the reason. This should
    /// never happen with a valid registry file, but is surfaced for safety.
    pub fn load() -> Result<Self, String> {
        Self::load_from_str(REGISTRY_JSON)
    }

    /// Builds a registry from JSON text: generic parse, strict validation, typed decoding.
    fn load_from_str(json: &str) -> Result<Self, String> {
        let mut value: serde_json::Value = serde_json::from_str(json)
            .map_err(|e| format!("malformed registry data: $: invalid JSON: {}", e))?;
        validate_registry_data(&value)?;
        drop_null_fields(&mut value);
        let raw: RawRegistry = serde_json::from_value(value)
            .map_err(|e| format!("malformed registry data: $: {}", e))?;

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
    /// Only currencies with `peg_type == Some("single")` are considered — a
    /// currency pegged to a basket or an undisclosed mix (e.g. MAD's
    /// `"EUR+USD basket"`) is not "pegged to USD" just because `"USD"`
    /// appears in its `pegged_to` description, even though the anchor is a
    /// component of the basket. Use [`all_active`](Self::all_active) and
    /// inspect `peg_type`/`pegged_to` directly for basket-aware search.
    ///
    /// ```rust
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
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
                c.peg_type.as_deref() == Some("single")
                    && c.pegged_to
                        .as_ref()
                        .map(|p| p.to_uppercase() == anchor)
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
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
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

    /// Find all active currencies with the given classification.
    ///
    /// `cls` is one of `"circulating"`, `"fund"`, `"settlement"`, or
    /// `"indexation"`. Returns an empty `Vec` if none match.
    ///
    /// ```rust
    /// # use iso4217::CurrencyRegistry;
    /// # let registry = CurrencyRegistry::load().unwrap();
    /// let funds = registry.by_classification("fund");
    /// assert!(!funds.is_empty());
    /// ```
    pub fn by_classification(&self, cls: &str) -> Vec<&Currency> {
        self.active
            .values()
            .filter(|c| c.classification.as_deref() == Some(cls))
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
    fn malformed_registry_fixture_is_rejected_with_the_prefix_and_the_path() {
        let raw = std::fs::read_to_string("../../tests/cross_language_consistency.json")
            .expect("failed to read fixture");
        let fixture: serde_json::Value = serde_json::from_str(&raw).expect("failed to parse fixture");
        let tests = &fixture["malformed_registry_tests"];
        let malformed = tests["malformed"].as_array().expect("malformed list");
        assert!(malformed.len() >= 30, "fixture has only {} malformed cases", malformed.len());
        for case in malformed {
            let id = case["id"].as_str().unwrap();
            let path = case["path"].as_str().unwrap();
            let text = serde_json::to_string(&case["registry"]).unwrap();
            match CurrencyRegistry::load_from_str(&text) {
                Ok(_) => panic!("{}: the registry was accepted", id),
                Err(msg) => {
                    assert!(msg.starts_with("malformed registry data: "), "{}: {}", id, msg);
                    assert!(msg.contains(path), "{}: expected path {} in: {}", id, path, msg);
                }
            }
        }
    }

    #[test]
    fn valid_fixture_registries_are_accepted() {
        let raw = std::fs::read_to_string("../../tests/cross_language_consistency.json")
            .expect("failed to read fixture");
        let fixture: serde_json::Value = serde_json::from_str(&raw).expect("failed to parse fixture");
        for case in fixture["malformed_registry_tests"]["valid"].as_array().expect("valid list") {
            let text = serde_json::to_string(&case["registry"]).unwrap();
            if let Err(msg) = CurrencyRegistry::load_from_str(&text) {
                panic!("{}: {}", case["id"], msg);
            }
        }
    }

    #[test]
    fn invalid_json_is_a_malformed_registry_error() {
        let err = CurrencyRegistry::load_from_str("{").unwrap_err();
        assert!(err.starts_with("malformed registry data: $: invalid JSON"), "{}", err);
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
        assert_eq!(usd.format(1000.00), "$1,000.00");
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

    // -----------------------------------------------------------------
    // Cross-language consistency (issue #4)
    //
    // Ports tests/cross_language_consistency.json — the same file
    // tests/test_wrappers.py checks for the Python wrapper — so a
    // divergence between wrappers shows up here instead of only in
    // Python. Path is relative to the crate root (wrappers/rust), which
    // is `cargo test`'s working directory.
    // -----------------------------------------------------------------

    #[derive(Deserialize)]
    struct ClcConversion {
        major: f64,
        minor: i64,
        #[serde(default)]
        lossy: bool,
    }

    #[derive(Deserialize)]
    struct ClcFormatting {
        major: f64,
        formatted: String,
    }

    #[derive(Deserialize)]
    struct ClcTestVector {
        code: String,
        minor_units: u8,
        #[serde(default)]
        is_independent: Option<bool>,
        #[serde(default)]
        is_pegged: Option<bool>,
        #[serde(default)]
        pegged_to: Option<String>,
        #[serde(default)]
        peg_type: Option<String>,
        #[serde(default)]
        peg_rate: Option<f64>,
        #[serde(default)]
        peg_band_pct: Option<f64>,
        #[serde(default)]
        withdrawn: bool,
        #[serde(default)]
        replaced_by: Option<String>,
        #[serde(default)]
        conversion_rate: Option<f64>,
        #[serde(default)]
        conversions: Vec<ClcConversion>,
        #[serde(default)]
        formatting: Vec<ClcFormatting>,
    }

    #[derive(Deserialize)]
    struct ClcLookupTest {
        method: String,
        lookups: Vec<String>,
        #[serde(default)]
        expected_code: Option<String>,
        #[serde(default)]
        expected_null: bool,
    }

    #[derive(Deserialize)]
    #[serde(untagged)]
    enum ClcArgument {
        Str(String),
        Num(f64),
    }

    #[derive(Deserialize)]
    struct ClcFilterTest {
        method: String,
        #[serde(default)]
        argument: Option<ClcArgument>,
        #[serde(default)]
        expected_contains: Vec<String>,
        #[serde(default)]
        expected_not_contains: Vec<String>,
    }

    #[derive(Deserialize)]
    struct ClcSummaryTest {
        expected_keys: Vec<String>,
    }

    #[derive(Deserialize)]
    struct CrossLanguageConsistency {
        test_vectors: Vec<ClcTestVector>,
        #[serde(default)]
        lookup_tests: Vec<ClcLookupTest>,
        #[serde(default)]
        filter_tests: Vec<ClcFilterTest>,
        #[serde(default)]
        summary_tests: Vec<ClcSummaryTest>,
    }

    fn load_consistency_vectors() -> CrossLanguageConsistency {
        let raw = std::fs::read_to_string("../../tests/cross_language_consistency.json")
            .expect("failed to read cross_language_consistency.json");
        serde_json::from_str(&raw).expect("failed to parse cross_language_consistency.json")
    }

    // Rust-idiom translation of the JSON's "method" field for lookup_tests.
    // Method names ("active", "withdrawn", "currency") happen to already
    // be valid Rust identifiers, but Rust has no dynamic dispatch by
    // string, so this is an explicit match rather than reflection.
    fn clc_lookup<'a>(reg: &'a CurrencyRegistry, method: &str, code: &str) -> Option<&'a Currency> {
        match method {
            "active" => reg.active(code),
            "withdrawn" => reg.withdrawn(code),
            "currency" => reg.currency(code),
            other => panic!("no Rust mapping for lookup method '{other}'"),
        }
    }

    // Rust-idiom translation of the JSON's "method" field for filter_tests
    // ("pegged_to", "with_minor_units", "independent").
    fn clc_filter<'a>(reg: &'a CurrencyRegistry, test: &ClcFilterTest) -> Vec<&'a Currency> {
        match test.method.as_str() {
            "pegged_to" => {
                let arg = match &test.argument {
                    Some(ClcArgument::Str(s)) => s,
                    _ => panic!("pegged_to argument is not a string"),
                };
                reg.pegged_to(arg)
            }
            "with_minor_units" => {
                let arg = match &test.argument {
                    Some(ClcArgument::Num(n)) => *n as u8,
                    _ => panic!("with_minor_units argument is not a number"),
                };
                reg.with_minor_units(arg)
            }
            "independent" => reg.independent(),
            "by_classification" => {
                let arg = match &test.argument {
                    Some(ClcArgument::Str(s)) => s,
                    _ => panic!("by_classification argument is not a string"),
                };
                reg.by_classification(arg)
            }
            other => panic!("no Rust mapping for filter method '{other}'"),
        }
    }

    // RegistrySummary's field names are already snake_case and match the
    // JSON's expected_keys verbatim (unlike Go's PascalCase field names
    // requiring a json-tag reflection check, or JS's intentionally
    // camelCase summary() requiring a key-name map — see those wrappers'
    // tests for that divergence). Because Rust field access is checked at
    // compile time, listing the real field names here means a rename that
    // breaks this contract fails the build, not just this assertion.
    fn clc_summary_has_key(key: &str) -> bool {
        matches!(
            key,
            "version"
                | "updated"
                | "active_currencies"
                | "withdrawn_currencies"
                | "non_iso_currencies"
                | "pegged_currencies"
                | "independent_currencies"
                | "minor_units_distribution"
        )
    }

    #[test]
    fn test_cross_language_consistency_conversion_vectors() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found in registry", v.code));
            for conv in &v.conversions {
                let result = c.to_minor(conv.major);
                assert_eq!(result, conv.minor, "{}.to_minor({}) = {}, expected {}", v.code, conv.major, result, conv.minor);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_conversion_round_trip() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found in registry", v.code));
            for conv in &v.conversions {
                // "lossy" entries are rounding-boundary values not exactly
                // representable in integer minor units (e.g. USD 100.005
                // rounds to 10001, whose true inverse is 100.01, not the
                // original 100.005).
                if conv.lossy {
                    continue;
                }
                let back = c.from_minor(conv.minor);
                assert_eq!(back, conv.major, "{} round-trip failed: {} -> {} -> {}", v.code, conv.major, conv.minor, back);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_conversion_handles_zero() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found", v.code));
            assert_eq!(c.to_minor(0.0), 0, "{}.to_minor(0.0) should be 0", v.code);
            assert_eq!(c.from_minor(0), 0.0, "{}.from_minor(0) should be 0.0", v.code);
        }
    }

    #[test]
    fn test_cross_language_consistency_formatting_vectors() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found in registry", v.code));
            for fmt_vec in &v.formatting {
                let result = c.format(fmt_vec.major);
                assert_eq!(
                    result, fmt_vec.formatted,
                    "{}.format({}) = '{}', expected '{}'",
                    v.code, fmt_vec.major, result, fmt_vec.formatted
                );
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_minor_units_values() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found", v.code));
            assert_eq!(c.minor_units, v.minor_units, "{}.minor_units = {}, expected {}", v.code, c.minor_units, v.minor_units);
        }
    }

    #[test]
    fn test_cross_language_consistency_peg_properties() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found", v.code));

            if let Some(expected) = v.is_independent {
                assert_eq!(c.is_independent, expected, "{}.is_independent = {}, expected {}", v.code, c.is_independent, expected);
            }
            if let Some(expected) = v.is_pegged {
                assert_eq!(c.is_pegged(), expected, "{}.is_pegged() = {}, expected {}", v.code, c.is_pegged(), expected);
            }
            if let Some(expected) = &v.pegged_to {
                assert_eq!(c.pegged_to.as_deref(), Some(expected.as_str()), "{}.pegged_to mismatch", v.code);
            }
            if let Some(expected) = &v.peg_type {
                assert_eq!(c.peg_type.as_deref(), Some(expected.as_str()), "{}.peg_type mismatch", v.code);
            }
            if let Some(expected) = v.peg_rate {
                assert_eq!(c.peg_rate, Some(expected), "{}.peg_rate mismatch", v.code);
            }
            if let Some(expected) = v.peg_band_pct {
                assert_eq!(c.peg_band_pct, Some(expected), "{}.peg_band_pct mismatch", v.code);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_withdrawn_properties() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            if !v.withdrawn {
                continue;
            }
            let c = reg.currency(&v.code).unwrap_or_else(|| panic!("{} not found", v.code));
            if let Some(expected) = &v.replaced_by {
                assert_eq!(c.replaced_by.as_deref(), Some(expected.as_str()), "{}.replaced_by mismatch", v.code);
            }
            if let Some(expected) = v.conversion_rate {
                assert_eq!(c.conversion_rate, Some(expected), "{}.conversion_rate mismatch", v.code);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_case_insensitive_lookup() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for t in &vectors.lookup_tests {
            if t.expected_null {
                for code in &t.lookups {
                    let result = clc_lookup(&reg, &t.method, code);
                    assert!(result.is_none(), "{}('{}') should return None", t.method, code);
                }
            } else {
                let expected_code = t.expected_code.as_deref().expect("expected_code missing");
                for code in &t.lookups {
                    let result = clc_lookup(&reg, &t.method, code);
                    let result = result.unwrap_or_else(|| panic!("{}('{}') returned None", t.method, code));
                    assert_eq!(result.code, expected_code, "{}('{}').code mismatch", t.method, code);
                }
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_filter_vectors() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for t in &vectors.filter_tests {
            let results = clc_filter(&reg, t);
            let result_codes: std::collections::HashSet<&str> = results.iter().map(|c| c.code.as_str()).collect();

            for expected in &t.expected_contains {
                assert!(result_codes.contains(expected.as_str()), "{}() should contain {}", t.method, expected);
            }
            for excluded in &t.expected_not_contains {
                assert!(!result_codes.contains(excluded.as_str()), "{}() should NOT contain {}", t.method, excluded);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_summary_has_expected_keys() {
        let vectors = load_consistency_vectors();
        for t in &vectors.summary_tests {
            for key in &t.expected_keys {
                assert!(clc_summary_has_key(key), "RegistrySummary missing field '{}'", key);
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_registry_contains_all_test_vector_codes() {
        let reg = registry();
        let vectors = load_consistency_vectors();
        for v in &vectors.test_vectors {
            assert!(reg.currency(&v.code).is_some(), "{} from test vectors not found in registry", v.code);
        }
    }

    #[test]
    fn test_cross_language_consistency_negative_amounts() {
        let reg = registry();
        let usd = reg.currency("USD").unwrap();
        assert_eq!(usd.to_minor(-100.50), -10050);
        assert_eq!(usd.to_minor(-0.01), -1);
        assert_eq!(usd.from_minor(-10050), -100.5);
        assert_eq!(usd.from_minor(-1), -0.01);
    }

    #[derive(Deserialize)]
    struct ClcClassificationBlock {
        #[serde(default)]
        expected: Option<std::collections::HashMap<String, String>>,
        #[serde(default)]
        method: Option<String>,
        #[serde(default)]
        argument: Option<ClcArgument>,
        #[serde(default)]
        expected_contains: Vec<String>,
        #[serde(default)]
        expected_not_contains: Vec<String>,
    }

    #[derive(Deserialize)]
    struct ClcClassificationFile {
        #[serde(default)]
        classification_tests: Vec<ClcClassificationBlock>,
    }

    fn load_classification_vectors() -> ClcClassificationFile {
        let raw = std::fs::read_to_string("../../tests/cross_language_consistency.json")
            .expect("failed to read fixture");
        serde_json::from_str(&raw).expect("failed to parse fixture")
    }

    #[test]
    fn test_cross_language_consistency_classification_values() {
        let reg = registry();
        let v = load_classification_vectors();
        for block in &v.classification_tests {
            if let Some(expected) = &block.expected {
                for (code, expected_cls) in expected {
                    let c = reg.currency(code)
                        .unwrap_or_else(|| panic!("{} not found", code));
                    assert_eq!(
                        c.classification.as_deref(),
                        Some(expected_cls.as_str()),
                        "{} classification mismatch", code
                    );
                }
            }
        }
    }

    #[test]
    fn test_cross_language_consistency_by_classification() {
        let reg = registry();
        let v = load_classification_vectors();
        for block in &v.classification_tests {
            if block.method.as_deref() != Some("by_classification") {
                continue;
            }
            let arg = match &block.argument {
                Some(ClcArgument::Str(s)) => s,
                _ => panic!("by_classification argument is not a string"),
            };
            let results = reg.by_classification(arg);
            let codes: std::collections::HashSet<&str> =
                results.iter().map(|c| c.code.as_str()).collect();
            for expected in &block.expected_contains {
                assert!(codes.contains(expected.as_str()),
                    "by_classification({}) should contain {}", arg, expected);
            }
            for excluded in &block.expected_not_contains {
                assert!(!codes.contains(excluded.as_str()),
                    "by_classification({}) should NOT contain {}", arg, excluded);
            }
        }
    }
}