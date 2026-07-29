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
	"fmt"
	"math"
	"strings"
	"sync"
)

//go:embed ../../../iso4217.json
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

// ToMinor converts a major currency amount to minor units.
//
// Examples:
//
//	usd.ToMinor(100.50)       // 10050
//	jpy.ToMinor(500.0)        // 500
//	kwd.ToMinor(1.500)        // 1500
//	btc.ToMinor(0.000_000_01) // 1
//
// Panics if majorAmount is NaN or infinite.
func (c *Currency) ToMinor(majorAmount float64) int64 {
	if math.IsNaN(majorAmount) || math.IsInf(majorAmount, 0) {
		panic(fmt.Sprintf("Cannot convert %v to minor units", majorAmount))
	}
	factor := math.Pow(10, float64(c.MinorUnits))
	return int64(math.Round(majorAmount * factor))
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
// Examples:
//
//	usd.Format(100.50)  // "$100.50"
//	jpy.Format(500.0)   // "¥500"
func (c *Currency) Format(majorAmount float64) string {
	if c.MinorUnits == 0 {
		return fmt.Sprintf("%s%d", c.Symbol, int64(math.Round(majorAmount)))
	}
	return fmt.Sprintf("%s%.*f", c.Symbol, c.MinorUnits, majorAmount)
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

// Load returns the singleton CurrencyRegistry, loading it from the
// embedded JSON data on first call. Subsequent calls return the cached
// instance.
//
// The registry data is embedded in the binary at compile time — no file I/O,
// no network calls.
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
	var raw rawRegistry
	if err := json.Unmarshal(registryJSON, &raw); err != nil {
		return nil, fmt.Errorf("failed to parse registry JSON: %w", err)
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
	isIndependent := true
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
func (r *CurrencyRegistry) PeggedTo(anchorCode string) []*Currency {
	anchor := strings.ToUpper(anchorCode)
	var result []*Currency
	for _, c := range r.active {
		if c.PeggedTo != nil && strings.Contains(strings.ToUpper(*c.PeggedTo), anchor) {
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