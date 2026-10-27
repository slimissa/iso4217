// Package iso4217 provides a zero-dependency Go interface to the canonical
// ISO 4217 currency registry.
//
// Provides Currency and CurrencyRegistry types with minor/major unit
// conversion, peg information access, and country relationship lookup.
//
// The registry data is embedded at compile time via embed.FS.
// No file I/O at runtime. No network calls. No dependencies beyond the
// standard library.
//
// Usage:
//
//	package main
//
//	import (
//	    "fmt"
//	    "github.com/slimissa/iso4217-go"
//	)
//
//	func main() {
//	    registry, err := iso4217.Load()
//	    if err != nil {
//	        panic(err)
//	    }
//
//	    usd := registry.Active("USD")
//	    fmt.Println(usd.ToMinor(100.50))  // 10050
//	    fmt.Println(usd.Format(100.50))   // "$100.50"
//
//	    for _, c := range registry.PeggedTo("USD") {
//	        fmt.Printf("%s pegged at %v since %s\n",
//	            c.Code, c.PegRate, c.PeggedSince)
//	    }
//	}
//
// License: Apache 2.0
package iso4217

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strconv"
	"strings"
	"sync"
)

//go:embed iso4217.json
var registryJSON []byte

// ---------------------------------------------------------------------------
// Raw JSON structures (private — used only for unmarshaling)
// ---------------------------------------------------------------------------

type rawRegistry struct {
	Meta      *rawMeta      `json:"meta"`
	Source    *rawSource    `json:"source"`
	Currencies *rawCurrencies `json:"currencies"`
	NonISO    *rawNonISO    `json:"non_iso"`
}

type rawMeta struct {
	Version *string `json:"version"`
	Updated *string `json:"updated"`
}

type rawSource struct {
	LastAmendmentApplied *int    `json:"last_amendment_applied"`
	LastAmendmentDate    *string `json:"last_amendment_date"`
}

type rawCurrencies struct {
	Active    []rawCurrency `json:"active"`
	Withdrawn []rawCurrency `json:"withdrawn"`
}

type rawNonISO struct {
	Cryptocurrencies []rawCurrency `json:"cryptocurrencies"`
	Stablecoins      []rawCurrency `json:"stablecoins"`
	Commodities      []rawCurrency `json:"commodities"`
	SpecialPurpose   []rawCurrency `json:"special_purpose"`
}

type rawCurrency struct {
	Code        string       `json:"code"`
	Numeric     string       `json:"numeric"`
	Name        string       `json:"name"`
	MinorUnits  int          `json:"minor_units"`
	Symbol      string       `json:"symbol"`
	Entity      string       `json:"entity"`
	CentralBank string       `json:"central_bank"`
	PeggedTo    *string      `json:"pegged_to"`
	PegType     *string      `json:"peg_type"`
	PeggedSince *string      `json:"pegged_since"`
	PegRate     *float64     `json:"peg_rate"`
	PegBandPct  *float64     `json:"peg_band_pct"`
	IsIndependent *bool      `json:"is_independent"`
	Note        *string      `json:"note"`
	Countries   []rawCountry `json:"countries"`
	// Withdrawn fields
	WithdrawnDate  *string  `json:"withdrawn_date"`
	ReplacedBy     *string  `json:"replaced_by"`
	ConversionRate *float64 `json:"conversion_rate"`
	// Non-ISO fields
	Type          *string `json:"type"`
	MarketCapRank *int    `json:"market_cap_rank"`
	PegMechanism  *string `json:"peg_mechanism"`
	// v1.6.0 fields
	Classification *string          `json:"classification"`
	NumericReused  *bool            `json:"numeric_reused"`
	SourceURL      *string          `json:"source_url"`
	CodeLifetime   *RawCodeLifetime `json:"code_lifetime"`
}

type RawCodeLifetime struct {
	From *string `json:"from"`
	To   string  `json:"to"`
}

type rawCountry struct {
	Code         string `json:"code"`
	Name         string `json:"name"`
	Relationship string `json:"relationship"`
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

// Country represents a country or territory where a currency is used.
type Country struct {
	// ISO 3166-1 alpha-2 country code (e.g., "US", "FR").
	Code string `json:"code"`
	// Human-readable country or territory name.
	Name string `json:"name"`
	// Relationship to the currency: "issuing", "adopting", "territory",
	// "parallel", or "local_issue".
	Relationship string `json:"relationship"`
}

// Currency represents a single currency from the ISO 4217 registry.
//
// Provides read-only access to all currency properties plus convenience
// methods for converting between major and minor currency units.
type Currency struct {
	// ISO 4217 alphabetic currency code (e.g., "USD").
	Code string `json:"code"`
	// ISO 4217 numeric currency code as a 3-digit string (e.g., "840").
	Numeric string `json:"numeric"`
	// Official English name of the currency (e.g., "US Dollar").
	Name string `json:"name"`
	// Number of decimal places for the minor currency unit.
	//
	// 0 = no subdivision (JPY, KRW).
	// 2 = standard cents/pence (USD, EUR).
	// 3 = dinar subdivisions (KWD, BHD, OMR, JOD, TND, LYD, IQD).
	// 8 = Bitcoin. 18 = Ethereum.
	MinorUnits int `json:"minor_units"`
	// Primary display symbol. May be empty if none exists.
	Symbol string `json:"symbol"`
	// Issuing entity or monetary authority.
	Entity string `json:"entity"`
	// Official name of the central bank.
	CentralBank string `json:"central_bank"`
	// The currency or basket this currency is pegged to, or nil if floating.
	PeggedTo *string `json:"pegged_to"`
	// How to interpret PeggedTo: "single" (a parseable ISO 4217 code, e.g.
	// AED -> "USD"), "basket" (free-text weighted-basket description, e.g.
	// MAD -> "EUR+USD basket"), "undisclosed" (pegged but mechanism not
	// public, e.g. KWD -> "Currency basket"), or nil if not pegged.
	//
	// Do not assume PeggedTo is a parseable currency code without checking
	// PegType != nil && *PegType == "single" first.
	PegType *string `json:"peg_type"`
	// Date the peg was established (ISO 8601), or nil.
	PeggedSince *string `json:"pegged_since"`
	// Official peg rate (units of this currency per 1 unit of anchor), or nil.
	PegRate *float64 `json:"peg_rate"`
	// Allowed deviation from the peg as a percentage. 0.0 = fixed peg.
	PegBandPct *float64 `json:"peg_band_pct"`
	// True if the currency floats independently; false if hard-pegged.
	IsIndependent bool `json:"is_independent"`
	// Optional note for special cases or market conventions.
	Note *string `json:"note"`
	// Countries and territories where this currency is primary legal tender.
	Countries []Country `json:"countries"`
	// Withdrawal date (withdrawn currencies only).
	WithdrawnDate *string `json:"withdrawn_date,omitempty"`
	// Replacement currency code (withdrawn currencies only).
	ReplacedBy *string `json:"replaced_by,omitempty"`
	// Official conversion rate (withdrawn currencies only).
	ConversionRate *float64 `json:"conversion_rate,omitempty"`
	// Type for non-ISO currencies ("cryptocurrency", "stablecoin", etc.).
	Type *string `json:"type,omitempty"`
	// Market cap rank (crypto/stablecoins only).
	MarketCapRank *int `json:"market_cap_rank,omitempty"`
	// Peg mechanism for stablecoins (e.g., "Fiat-collateralized").
	PegMechanism *string `json:"peg_mechanism,omitempty"`
	// Classification of active currencies: "circulating", "fund",
	// "settlement", or "indexation". Nil for withdrawn entries.
	Classification *string `json:"classification,omitempty"`
	// NumericReused is true when this active currency's numeric code
	// also appears on a withdrawn entry.
	NumericReused *bool `json:"numeric_reused,omitempty"`
	// SourceURL is the URL of the entry's primary source.
	SourceURL *string `json:"source_url,omitempty"`
	// CodeLifetime is the withdrawn code's full valid range.
	CodeLifetime *CodeLifetime `json:"code_lifetime,omitempty"`
}

// CodeLifetime represents the valid range of a withdrawn code.
type CodeLifetime struct {
	// From is the ISO assignment date, or nil when undocumented.
	From *string `json:"from"`
	// To is the withdrawal date. Equal to Currency.WithdrawnDate.
	To string `json:"to"`
}

// IsPegged returns true if this currency is pegged to something.
func (c *Currency) IsPegged() bool {
	return c.PeggedTo != nil
}

// IssuingCountries returns countries that are the sovereign issuer
// of this currency.
func (c *Currency) IssuingCountries() []Country {
	var result []Country
	for _, country := range c.Countries {
		if country.Relationship == "issuing" {
			result = append(result, country)
		}
	}
	return result
}

// AdoptingCountries returns countries that use this currency without
// being the issuer (dollarized, euroized, etc.).
func (c *Currency) AdoptingCountries() []Country {
	var result []Country
	for _, country := range c.Countries {
		if country.Relationship == "adopting" {
			result = append(result, country)
		}
	}
	return result
}

// Errors returned by ToMinorChecked (ADR 0013, docs/decisions/wrapper-numeric-contract.md).
var (
	// ErrNonFinite is returned for a NaN or infinite amount.
	ErrNonFinite = errors.New("amount is not a finite number")
	// ErrOverflow is returned when the amount, scaled to minor units and rounded, does not fit in an int64
	// (|result| >= 2^63), or when scaling it overflows float64. The message says "amount too large".
	ErrOverflow = errors.New("amount too large for int64 minor units")
)

// pow10Exact[n] is 10^n, exact as a float64 for n <= 22. Every wrapper takes 10^n from the same exact table, so the
// one floating-point multiplication in the conversion is the same in all four languages.
var pow10Exact = [...]float64{
	1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11,
	1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
}

// int64Limit is 2^63: a rounded amount whose magnitude is at or above it cannot be returned as int64.
const int64Limit = 9223372036854775808.0

// roundScaled returns x*10^n rounded half away from zero, as an integer-valued float64.
//
// The product is one IEEE-double multiplication; the round is exact (p-trunc(p) is exact for doubles), so there is no
// floor(x+0.5) and no int64 conversion of an out-of-range float. It returns ErrNonFinite for NaN and infinite x and
// ErrOverflow when the product itself overflows float64. It does not apply the int64 bound.
func (c *Currency) roundScaled(x float64) (float64, error) {
	if math.IsNaN(x) || math.IsInf(x, 0) {
		return 0, ErrNonFinite
	}
	if c.MinorUnits < 0 || c.MinorUnits >= len(pow10Exact) {
		return 0, fmt.Errorf("minor units %d is outside 0..%d", c.MinorUnits, len(pow10Exact)-1)
	}
	p := x * pow10Exact[c.MinorUnits]
	if math.IsInf(p, 0) {
		return 0, ErrOverflow
	}
	r := math.Trunc(p)
	if math.Abs(p-r) >= 0.5 {
		r += math.Copysign(1, p)
	}
	return r, nil
}

// ToMinorChecked converts a major currency amount to minor units, rounding half away from zero, and returns an error
// instead of a wrong number: ErrNonFinite for NaN and infinity, ErrOverflow when the result does not fit in an int64.
// Test with errors.Is.
func (c *Currency) ToMinorChecked(majorAmount float64) (int64, error) {
	r, err := c.roundScaled(majorAmount)
	if err != nil {
		return 0, fmt.Errorf("cannot convert %v to minor units: %w", majorAmount, err)
	}
	if math.Abs(r) >= int64Limit {
		return 0, fmt.Errorf("cannot convert %v to minor units: %w", majorAmount, ErrOverflow)
	}
	return int64(r), nil
}

// ToMinor converts a major currency amount to minor units.
//
// Examples:
//
//	usd.ToMinor(100.50)       // 10050
//	jpy.ToMinor(500.0)        // 500
//	kwd.ToMinor(1.500)        // 1500
//	btc.ToMinor(0.000_000_01) // 1
//
// Panics if majorAmount is NaN, infinite, or too large for an int64 amount of minor units (the panic value is a string
// containing "amount too large"). Use ToMinorChecked to receive an error instead.
func (c *Currency) ToMinor(majorAmount float64) int64 {
	m, err := c.ToMinorChecked(majorAmount)
	if err != nil {
		panic(fmt.Sprintf("Cannot convert %v to minor units: %v", majorAmount, err))
	}
	return m
}

// FromMinor converts minor units to a major currency amount.
//
// Examples:
//
//	usd.FromMinor(10050)  // 100.5
//	jpy.FromMinor(500)    // 500.0
func (c *Currency) FromMinor(minorAmount int64) float64 {
	factor := math.Pow(10, float64(c.MinorUnits))
	return float64(minorAmount) / factor
}

// Format returns a major currency amount formatted with the currency symbol.
//
// The amount is rounded exactly as ToMinor rounds it (half away from zero) and its digits are printed from that
// rounded value, so Format and ToMinor cannot disagree. It never panics: NaN is "nan", infinity (or an amount whose
// scaled value overflows float64) is "inf" or "-inf" after the symbol. 2-decimal and other fractional currencies get
// comma thousands separators; 0-decimal currencies print ungrouped (ADR 0013, D5, D6).
//
// Examples:
//
//	usd.Format(100.50)   // "$100.50"
//	usd.Format(1000.00)  // "$1,000.00"
//	jpy.Format(500.0)    // "¥500"
//	usd.Format(math.NaN()) // "$nan"
func (c *Currency) Format(majorAmount float64) string {
	switch {
	case math.IsNaN(majorAmount):
		return c.Symbol + "nan"
	case math.IsInf(majorAmount, 1):
		return c.Symbol + "inf"
	case math.IsInf(majorAmount, -1):
		return c.Symbol + "-inf"
	}
	r, err := c.roundScaled(majorAmount)
	if err != nil { // a finite amount whose scaled value overflows float64
		if majorAmount < 0 {
			return c.Symbol + "-inf"
		}
		return c.Symbol + "inf"
	}
	n := c.MinorUnits
	// Sign comes from the sign bit of the amount when there are decimals, and from the rounded value when there are
	// none: a negative amount that rounds to zero prints "$-0.00" but "¥0" (today's behavior in all four wrappers).
	negative := (math.Signbit(majorAmount) && (n > 0 || r != 0)) || (n == 0 && r < 0)
	digits := strconv.FormatFloat(math.Abs(r), 'f', 0, 64) // exact digits of an integer-valued float64
	if n > 0 {
		if len(digits) < n+1 {
			digits = strings.Repeat("0", n+1-len(digits)) + digits
		}
		digits = groupThousands(digits[:len(digits)-n]) + "." + digits[len(digits)-n:]
	}
	if negative {
		return c.Symbol + "-" + digits
	}
	return c.Symbol + digits
}

// groupThousands inserts a comma every three digits, counting from the right. Go's fmt has no grouping verb.
func groupThousands(digits string) string {
	var b strings.Builder
	for i, d := range digits {
		if i > 0 && (len(digits)-i)%3 == 0 {
			b.WriteByte(',')
		}
		b.WriteRune(d)
	}
	return b.String()
}

// String returns a human-readable string representation.
func (c *Currency) String() string {
	return fmt.Sprintf("%s — %s (minor_units=%d)", c.Code, c.Name, c.MinorUnits)
}

// ---------------------------------------------------------------------------
// RegistrySummary
// ---------------------------------------------------------------------------

// RegistrySummary contains summary statistics for the registry.
type RegistrySummary struct {
	// Semantic version of the registry data.
	Version string `json:"version"`
	// Date the registry was last updated (ISO 8601).
	Updated string `json:"updated"`
	// Most recent ISO 4217 amendment number applied.
	Amendment int `json:"amendment"`
	// Number of active ISO 4217 currencies.
	ActiveCurrencies int `json:"active_currencies"`
	// Number of withdrawn ISO 4217 currencies.
	WithdrawnCurrencies int `json:"withdrawn_currencies"`
	// Number of non-ISO currencies.
	NonISOCurrencies int `json:"non_iso_currencies"`
	// Number of active currencies that are pegged.
	PeggedCurrencies int `json:"pegged_currencies"`
	// Number of active currencies that float independently.
	IndependentCurrencies int `json:"independent_currencies"`
	// Distribution of minor_units values across active currencies.
	MinorUnitsDistribution map[int]int `json:"minor_units_distribution"`
}

// ---------------------------------------------------------------------------
// CurrencyRegistry
// ---------------------------------------------------------------------------

// CurrencyRegistry is the main registry interface for looking up
// ISO 4217 currencies.
//
// Loads the canonical iso4217.json data at compile time via go:embed.
// Provides lookup methods for active, withdrawn, and non-ISO currencies.
type CurrencyRegistry struct {
	version        string
	updated        string
	amendment      int
	amendmentDate  string
	active         map[string]*Currency
	withdrawn      map[string]*Currency
	nonISO         map[string]*Currency
	all            map[string]*Currency
}

var (
	loadOnce sync.Once
	registry *CurrencyRegistry
	loadErr  error
)

// ---------------------------------------------------------------------------
// Registry data validation (v1.9.0, F13)
// ---------------------------------------------------------------------------
// One strict pass over the generic parsed JSON, before any typed decoding. The same contract is implemented in the
// Python, JavaScript and Rust wrappers and tested against tests/cross_language_consistency.json
// ("malformed_registry_tests"). The rules are in docs/WRAPPER_VALIDATION.md.

// ErrMalformedRegistry is wrapped by every error Load returns for malformed registry data. The message reads
// "malformed registry data: <JSON path>: <reason>". Test for it with errors.Is.
var ErrMalformedRegistry = errors.New("malformed registry data")

const maxMinorUnits = 36

var (
	stringFields  = []string{"numeric", "symbol", "entity", "central_bank", "pegged_to", "peg_type", "pegged_since", "note", "withdrawn_date", "replaced_by", "type", "peg_mechanism", "classification", "source_url"}
	numberFields  = []string{"peg_rate", "peg_band_pct", "conversion_rate"}
	integerFields = []string{"market_cap_rank"}
	booleanFields = []string{"is_independent", "numeric_reused"}
	entryLists    = []struct {
		section string
		keys    []string
	}{
		{"currencies", []string{"active", "withdrawn"}},
		{"non_iso", []string{"cryptocurrencies", "stablecoins", "commodities", "special_purpose"}},
	}
)

func malformed(path, reason string) error {
	return fmt.Errorf("%w: %s: %s", ErrMalformedRegistry, path, reason)
}

func jsonKind(v interface{}) string {
	switch v.(type) {
	case nil:
		return "null"
	case bool:
		return "boolean"
	case float64:
		return "number"
	case string:
		return "string"
	case []interface{}:
		return "array"
	}
	return "object"
}

func kindOK(v interface{}, kind string) bool {
	switch kind {
	case "string":
		_, ok := v.(string)
		return ok
	case "number":
		_, ok := v.(float64)
		return ok
	case "integer":
		f, ok := v.(float64)
		return ok && f == math.Trunc(f)
	case "boolean":
		_, ok := v.(bool)
		return ok
	case "array":
		_, ok := v.([]interface{})
		return ok
	}
	_, ok := v.(map[string]interface{})
	return ok
}

func checkKind(v interface{}, kind, path string) error {
	if !kindOK(v, kind) {
		return malformed(path, fmt.Sprintf("expected %s, got %s", kind, jsonKind(v)))
	}
	return nil
}

func checkOptional(obj map[string]interface{}, key, kind, path string) error {
	if v, ok := obj[key]; ok && v != nil {
		return checkKind(v, kind, path+"."+key)
	}
	return nil
}

func checkOptionalAll(obj map[string]interface{}, keys []string, kind, path string) error {
	for _, k := range keys {
		if err := checkOptional(obj, k, kind, path); err != nil {
			return err
		}
	}
	return nil
}

func validateEntry(v interface{}, path string) error {
	if err := checkKind(v, "object", path); err != nil {
		return err
	}
	entry := v.(map[string]interface{})
	for _, req := range [][2]string{{"code", "string"}, {"name", "string"}, {"minor_units", "integer"}} {
		val, ok := entry[req[0]]
		if !ok {
			return malformed(path+"."+req[0], "required field is missing")
		}
		if err := checkKind(val, req[1], path+"."+req[0]); err != nil {
			return err
		}
	}
	if entry["code"].(string) == "" {
		return malformed(path+".code", "must not be empty")
	}
	if mu := entry["minor_units"].(float64); mu < 0 || mu > maxMinorUnits {
		return malformed(path+".minor_units", fmt.Sprintf("expected an integer from 0 to %d, got %v", maxMinorUnits, mu))
	}
	for _, group := range []struct {
		keys []string
		kind string
	}{{stringFields, "string"}, {numberFields, "number"}, {integerFields, "integer"}, {booleanFields, "boolean"}} {
		if err := checkOptionalAll(entry, group.keys, group.kind, path); err != nil {
			return err
		}
	}
	if err := checkOptional(entry, "countries", "array", path); err != nil {
		return err
	}
	if countries, ok := entry["countries"].([]interface{}); ok {
		for i, cv := range countries {
			cpath := fmt.Sprintf("%s.countries[%d]", path, i)
			if err := checkKind(cv, "object", cpath); err != nil {
				return err
			}
			country := cv.(map[string]interface{})
			code, ok := country["code"]
			if !ok {
				return malformed(cpath+".code", "required field is missing")
			}
			if err := checkKind(code, "string", cpath+".code"); err != nil {
				return err
			}
			if err := checkOptionalAll(country, []string{"name", "relationship"}, "string", cpath); err != nil {
				return err
			}
		}
	}
	if err := checkOptional(entry, "code_lifetime", "object", path); err != nil {
		return err
	}
	if life, ok := entry["code_lifetime"].(map[string]interface{}); ok {
		lpath := path + ".code_lifetime"
		to, present := life["to"]
		if !present {
			return malformed(lpath+".to", "required field is missing")
		}
		if err := checkKind(to, "string", lpath+".to"); err != nil {
			return err
		}
		if err := checkOptional(life, "from", "string", lpath); err != nil {
			return err
		}
	}
	return nil
}

// validateRegistryData checks the generic parsed JSON against the contract in docs/WRAPPER_VALIDATION.md.
func validateRegistryData(v interface{}) error {
	if err := checkKind(v, "object", "$"); err != nil {
		return err
	}
	root := v.(map[string]interface{})
	for _, section := range []string{"meta", "source", "currencies", "non_iso"} {
		if val, ok := root[section]; ok {
			if err := checkKind(val, "object", "$."+section); err != nil {
				return err
			}
		}
	}
	meta, _ := root["meta"].(map[string]interface{})
	source, _ := root["source"].(map[string]interface{})
	if err := checkOptionalAll(meta, []string{"version", "updated"}, "string", "$.meta"); err != nil {
		return err
	}
	if err := checkOptional(source, "last_amendment_applied", "integer", "$.source"); err != nil {
		return err
	}
	if err := checkOptional(source, "last_amendment_date", "string", "$.source"); err != nil {
		return err
	}
	for _, list := range entryLists {
		group, _ := root[list.section].(map[string]interface{})
		for _, key := range list.keys {
			val, ok := group[key]
			if !ok {
				continue
			}
			path := "$." + list.section + "." + key
			if err := checkKind(val, "array", path); err != nil {
				return err
			}
			for i, e := range val.([]interface{}) {
				if err := validateEntry(e, fmt.Sprintf("%s[%d]", path, i)); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

// Load returns the singleton CurrencyRegistry, loading it from the
// embedded JSON data on first call. Subsequent calls return the cached
// instance.
//
// The registry data is embedded in the binary at compile time — no file I/O,
// no network calls. Malformed data returns an error wrapping ErrMalformedRegistry.
func Load() (*CurrencyRegistry, error) {
	loadOnce.Do(func() {
		registry, loadErr = loadRegistry()
	})
	return registry, loadErr
}

// MustLoad is like Load but panics if the registry cannot be loaded.
// Useful for package-level initialization where a failure is fatal.
func MustLoad() *CurrencyRegistry {
	r, err := Load()
	if err != nil {
		panic(fmt.Sprintf("iso4217: failed to load registry: %v", err))
	}
	return r
}

func loadRegistry() (*CurrencyRegistry, error) {
	return loadRegistryFrom(registryJSON)
}

// loadRegistryFrom builds a registry from JSON bytes: generic parse, strict validation, then typed decoding.
func loadRegistryFrom(data []byte) (*CurrencyRegistry, error) {
	var generic interface{}
	if err := json.Unmarshal(data, &generic); err != nil {
		return nil, fmt.Errorf("%w: $: invalid JSON: %v", ErrMalformedRegistry, err)
	}
	if err := validateRegistryData(generic); err != nil {
		return nil, err
	}
	var raw rawRegistry
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("%w: $: %v", ErrMalformedRegistry, err)
	}

	r := &CurrencyRegistry{
		active:    make(map[string]*Currency),
		withdrawn: make(map[string]*Currency),
		nonISO:    make(map[string]*Currency),
		all:       make(map[string]*Currency),
	}

	// Metadata
	if raw.Meta != nil {
		if raw.Meta.Version != nil {
			r.version = *raw.Meta.Version
		}
		if raw.Meta.Updated != nil {
			r.updated = *raw.Meta.Updated
		}
	}
	if r.version == "" {
		r.version = "unknown"
	}
	if r.updated == "" {
		r.updated = "unknown"
	}

	if raw.Source != nil {
		if raw.Source.LastAmendmentApplied != nil {
			r.amendment = *raw.Source.LastAmendmentApplied
		}
		if raw.Source.LastAmendmentDate != nil {
			r.amendmentDate = *raw.Source.LastAmendmentDate
		}
	}
	if r.amendmentDate == "" {
		r.amendmentDate = "unknown"
	}

	// Active currencies
	if raw.Currencies != nil {
		for _, c := range raw.Currencies.Active {
			currency := newCurrency(c)
			r.active[strings.ToUpper(currency.Code)] = currency
			r.all[strings.ToUpper(currency.Code)] = currency
		}

		// Withdrawn currencies
		for _, c := range raw.Currencies.Withdrawn {
			currency := newCurrency(c)
			r.withdrawn[strings.ToUpper(currency.Code)] = currency
			r.all[strings.ToUpper(currency.Code)] = currency
		}
	}

	// Non-ISO currencies
	if raw.NonISO != nil {
		addNonISO := func(currencies []rawCurrency) {
			for _, c := range currencies {
				currency := newCurrency(c)
				r.nonISO[strings.ToUpper(currency.Code)] = currency
				r.all[strings.ToUpper(currency.Code)] = currency
			}
		}

		addNonISO(raw.NonISO.Cryptocurrencies)
		addNonISO(raw.NonISO.Stablecoins)
		addNonISO(raw.NonISO.Commodities)
		addNonISO(raw.NonISO.SpecialPurpose)
	}

	return r, nil
}

func newCurrency(raw rawCurrency) *Currency {
	isIndependent := false
	if raw.IsIndependent != nil {
    	isIndependent = *raw.IsIndependent
	}

	return &Currency{
		Code:           raw.Code,
		Numeric:        raw.Numeric,
		Name:           raw.Name,
		MinorUnits:     raw.MinorUnits,
		Symbol:         raw.Symbol,
		Entity:         raw.Entity,
		CentralBank:    raw.CentralBank,
		PeggedTo:       raw.PeggedTo,
		PegType:        raw.PegType,
		PeggedSince:    raw.PeggedSince,
		PegRate:        raw.PegRate,
		PegBandPct:     raw.PegBandPct,
		IsIndependent:  isIndependent,
		Note:           raw.Note,
		Countries:      convertCountries(raw.Countries),
		WithdrawnDate:  raw.WithdrawnDate,
		ReplacedBy:     raw.ReplacedBy,
		ConversionRate: raw.ConversionRate,
		Type:           raw.Type,
		MarketCapRank:  raw.MarketCapRank,
		PegMechanism:   raw.PegMechanism,
		Classification: raw.Classification,
		NumericReused:  raw.NumericReused,
		SourceURL:      raw.SourceURL,
		CodeLifetime:   convertCodeLifetime(raw.CodeLifetime),
	}
}

func convertCountries(raw []rawCountry) []Country {
	countries := make([]Country, len(raw))
	for i, rc := range raw {
		countries[i] = Country{
			Code:         rc.Code,
			Name:         rc.Name,
			Relationship: rc.Relationship,
		}
	}
	return countries
}

func convertCodeLifetime(raw *RawCodeLifetime) *CodeLifetime {
	if raw == nil {
		return nil
	}
	return &CodeLifetime{
		From: raw.From,
		To:   raw.To,
	}
}

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------

// Version returns the semantic version of the registry data.
func (r *CurrencyRegistry) Version() string {
	return r.version
}

// Updated returns the date the registry was last updated (ISO 8601).
func (r *CurrencyRegistry) Updated() string {
	return r.updated
}

// Amendment returns the most recent ISO 4217 amendment number applied.
func (r *CurrencyRegistry) Amendment() int {
	return r.amendment
}

// AmendmentDate returns the date of the most recent amendment applied.
func (r *CurrencyRegistry) AmendmentDate() string {
	return r.amendmentDate
}

// ---------------------------------------------------------------------------
// Lookup methods
// ---------------------------------------------------------------------------

// Currency looks up any currency by code (case-insensitive).
// Searches active, withdrawn, and non-ISO currencies.
func (r *CurrencyRegistry) Currency(code string) *Currency {
	return r.all[strings.ToUpper(code)]
}

// Active looks up an active ISO 4217 currency by code (case-insensitive).
func (r *CurrencyRegistry) Active(code string) *Currency {
	return r.active[strings.ToUpper(code)]
}

// Withdrawn looks up a withdrawn ISO 4217 currency by code (case-insensitive).
func (r *CurrencyRegistry) Withdrawn(code string) *Currency {
	return r.withdrawn[strings.ToUpper(code)]
}

// NonISO looks up a non-ISO currency by code (case-insensitive).
func (r *CurrencyRegistry) NonISO(code string) *Currency {
	return r.nonISO[strings.ToUpper(code)]
}

// ---------------------------------------------------------------------------
// Collection accessors
// ---------------------------------------------------------------------------

// AllActive returns all active ISO 4217 currencies.
func (r *CurrencyRegistry) AllActive() []*Currency {
	result := make([]*Currency, 0, len(r.active))
	for _, c := range r.active {
		result = append(result, c)
	}
	return result
}

// AllWithdrawn returns all withdrawn ISO 4217 currencies.
func (r *CurrencyRegistry) AllWithdrawn() []*Currency {
	result := make([]*Currency, 0, len(r.withdrawn))
	for _, c := range r.withdrawn {
		result = append(result, c)
	}
	return result
}

// AllNonISO returns all non-ISO currencies.
func (r *CurrencyRegistry) AllNonISO() []*Currency {
	result := make([]*Currency, 0, len(r.nonISO))
	for _, c := range r.nonISO {
		result = append(result, c)
	}
	return result
}

// AllCurrencies returns all currencies across all categories.
func (r *CurrencyRegistry) AllCurrencies() []*Currency {
	result := make([]*Currency, 0, len(r.all))
	for _, c := range r.all {
		result = append(result, c)
	}
	return result
}

// ---------------------------------------------------------------------------
// Filtering
// ---------------------------------------------------------------------------

// PeggedTo returns all active currencies pegged to a specific anchor currency.
//
// Only currencies with PegType == "single" are considered — a currency
// pegged to a basket or an undisclosed mix (e.g. MAD's "EUR+USD basket")
// is not "pegged to USD" just because "USD" appears in its PeggedTo
// description, even though the anchor is a component of the basket.
// Use AllActive and inspect PegType/PeggedTo directly for basket-aware search.
func (r *CurrencyRegistry) PeggedTo(anchorCode string) []*Currency {
	anchor := strings.ToUpper(anchorCode)
	var result []*Currency
	for _, c := range r.active {
		if c.PegType != nil && *c.PegType == "single" &&
			c.PeggedTo != nil && strings.ToUpper(*c.PeggedTo) == anchor {
			result = append(result, c)
		}
	}
	return result
}

// Independent returns all active currencies that are independently floating.
func (r *CurrencyRegistry) Independent() []*Currency {
	var result []*Currency
	for _, c := range r.active {
		if c.IsIndependent {
			result = append(result, c)
		}
	}
	return result
}

// WithMinorUnits returns all active currencies with a specific number
// of minor units.
func (r *CurrencyRegistry) WithMinorUnits(n int) []*Currency {
	var result []*Currency
	for _, c := range r.active {
		if c.MinorUnits == n {
			result = append(result, c)
		}
	}
	return result
}

// IssuedBy returns all active currencies where a country is the issuer.
func (r *CurrencyRegistry) IssuedBy(countryCode string) []*Currency {
	code := strings.ToUpper(countryCode)
	var result []*Currency
	for _, c := range r.active {
		for _, country := range c.Countries {
			if country.Code == code && country.Relationship == "issuing" {
				result = append(result, c)
				break
			}
		}
	}
	return result
}

// UsedIn returns all active currencies used in a country (any relationship).
func (r *CurrencyRegistry) UsedIn(countryCode string) []*Currency {
	code := strings.ToUpper(countryCode)
	var result []*Currency
	for _, c := range r.active {
		for _, country := range c.Countries {
			if country.Code == code {
				result = append(result, c)
				break
			}
		}
	}
	return result
}

// ByClassification returns all active currencies with the given
// classification ("circulating", "fund", "settlement", "indexation").
//
// Returns an empty slice if none match, or if the registry predates
// v1.6.0 and no entry carries a classification field.
func (r *CurrencyRegistry) ByClassification(cls string) []*Currency {
	var result []*Currency
	for _, c := range r.active {
		if c.Classification != nil && *c.Classification == cls {
			result = append(result, c)
		}
	}
	return result
}

// ---------------------------------------------------------------------------
// Statistics
// ---------------------------------------------------------------------------

// ActiveCount returns the number of active ISO 4217 currencies.
func (r *CurrencyRegistry) ActiveCount() int {
	return len(r.active)
}

// WithdrawnCount returns the number of withdrawn ISO 4217 currencies.
func (r *CurrencyRegistry) WithdrawnCount() int {
	return len(r.withdrawn)
}

// NonISOCount returns the number of non-ISO currencies.
func (r *CurrencyRegistry) NonISOCount() int {
	return len(r.nonISO)
}

// PeggedCount returns the number of active currencies that are pegged.
func (r *CurrencyRegistry) PeggedCount() int {
	count := 0
	for _, c := range r.active {
		if c.IsPegged() {
			count++
		}
	}
	return count
}

// IndependentCount returns the number of active currencies that float independently.
func (r *CurrencyRegistry) IndependentCount() int {
	count := 0
	for _, c := range r.active {
		if c.IsIndependent {
			count++
		}
	}
	return count
}

// Contains returns true if a currency code exists in the registry
// (any category).
func (r *CurrencyRegistry) Contains(code string) bool {
	_, ok := r.all[strings.ToUpper(code)]
	return ok
}

// Summary returns a summary with registry statistics.
func (r *CurrencyRegistry) Summary() RegistrySummary {
	dist := make(map[int]int)
	for _, c := range r.active {
		dist[c.MinorUnits]++
	}

	return RegistrySummary{
		Version:                r.version,
		Updated:                r.updated,
		Amendment:              r.amendment,
		ActiveCurrencies:       len(r.active),
		WithdrawnCurrencies:    len(r.withdrawn),
		NonISOCurrencies:       len(r.nonISO),
		PeggedCurrencies:       r.PeggedCount(),
		IndependentCurrencies:  r.IndependentCount(),
		MinorUnitsDistribution: dist,
	}
}

// String returns a human-readable string representation.
func (r *CurrencyRegistry) String() string {
	return fmt.Sprintf(
		"CurrencyRegistry(version=%s, active=%d, withdrawn=%d, non_iso=%d)",
		r.version, len(r.active), len(r.withdrawn), len(r.nonISO),
	)
}