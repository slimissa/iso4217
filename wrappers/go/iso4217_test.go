package iso4217

import (
	"encoding/json"
	"math"
	"os"
	"reflect"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

func testRegistry(t *testing.T) *CurrencyRegistry {
	t.Helper()
	r, err := Load()
	if err != nil {
		t.Fatalf("Failed to load registry: %v", err)
	}
	return r
}

// ---------------------------------------------------------------------------
// Loading tests
// ---------------------------------------------------------------------------

func TestLoad(t *testing.T) {
	r, err := Load()
	if err != nil {
		t.Fatalf("Load() returned error: %v", err)
	}
	if r == nil {
		t.Fatal("Load() returned nil registry")
	}
}

func TestLoadSingleton(t *testing.T) {
	r1, err1 := Load()
	if err1 != nil {
		t.Fatalf("First Load() failed: %v", err1)
	}
	r2, err2 := Load()
	if err2 != nil {
		t.Fatalf("Second Load() failed: %v", err2)
	}
	if r1 != r2 {
		t.Error("Load() returned different instances — singleton broken")
	}
}

func TestMustLoad(t *testing.T) {
	r := MustLoad()
	if r == nil {
		t.Fatal("MustLoad() returned nil")
	}
}

func TestLoadHasMetadata(t *testing.T) {
	r := testRegistry(t)

	if r.Version() == "" || r.Version() == "unknown" {
		t.Error("Version is empty or unknown")
	}
	if r.Updated() == "" || r.Updated() == "unknown" {
		t.Error("Updated is empty or unknown")
	}
}

func TestLoadHasCurrencies(t *testing.T) {
	r := testRegistry(t)

	if r.ActiveCount() < 50 {
		t.Errorf("Expected >50 active currencies, got %d", r.ActiveCount())
	}
	if r.WithdrawnCount() == 0 {
		t.Error("Expected withdrawn currencies, got 0")
	}
}

// ---------------------------------------------------------------------------
// Lookup tests
// ---------------------------------------------------------------------------

func TestActiveUSD(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")
	if usd == nil {
		t.Fatal("USD not found")
	}
	if usd.Code != "USD" {
		t.Errorf("Expected Code=USD, got %s", usd.Code)
	}
	if usd.Numeric != "840" {
		t.Errorf("Expected Numeric=840, got %s", usd.Numeric)
	}
	if usd.Name != "US Dollar" {
		t.Errorf("Expected Name='US Dollar', got '%s'", usd.Name)
	}
	if usd.MinorUnits != 2 {
		t.Errorf("Expected MinorUnits=2, got %d", usd.MinorUnits)
	}
}

func TestActiveCaseInsensitive(t *testing.T) {
	r := testRegistry(t)

	tests := []string{"usd", "Usd", "USD", "uSd"}
	for _, code := range tests {
		if r.Active(code) == nil {
			t.Errorf("Active(%q) returned nil — lookup should be case-insensitive", code)
		}
	}
}

func TestActiveNotFound(t *testing.T) {
	r := testRegistry(t)

	if c := r.Active("XXX"); c != nil {
		t.Errorf("Expected nil for 'XXX', got %v", c)
	}
}

func TestCurrencyFindsActive(t *testing.T) {
	r := testRegistry(t)

	usd := r.Currency("USD")
	if usd == nil {
		t.Fatal("Currency('USD') returned nil")
	}
}

func TestCurrencyFindsWithdrawn(t *testing.T) {
	r := testRegistry(t)

	dem := r.Currency("DEM")
	if dem == nil {
		t.Fatal("Currency('DEM') returned nil")
	}
}

func TestCurrencyFindsNonISO(t *testing.T) {
	r := testRegistry(t)

	btc := r.Currency("BTC")
	if btc == nil {
		t.Fatal("Currency('BTC') returned nil")
	}
}

func TestCurrencyNotFound(t *testing.T) {
	r := testRegistry(t)

	if c := r.Currency("XXX"); c != nil {
		t.Errorf("Expected nil for 'XXX', got %v", c)
	}
}

func TestContains(t *testing.T) {
	r := testRegistry(t)

	tests := []struct {
		code     string
		expected bool
	}{
		{"USD", true},
		{"usd", true},
		{"DEM", true},
		{"BTC", true},
		{"XXX", false},
		{"", false},
	}

	for _, tt := range tests {
		if got := r.Contains(tt.code); got != tt.expected {
			t.Errorf("Contains(%q) = %v, want %v", tt.code, got, tt.expected)
		}
	}
}

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

func TestJPYProperties(t *testing.T) {
	r := testRegistry(t)
	jpy := r.Active("JPY")
	if jpy == nil {
		t.Fatal("JPY not found")
	}

	if jpy.MinorUnits != 0 {
		t.Errorf("JPY MinorUnits = %d, want 0", jpy.MinorUnits)
	}
	if jpy.Symbol != "¥" {
		t.Errorf("JPY Symbol = %q, want '¥'", jpy.Symbol)
	}
}

func TestKWDProperties(t *testing.T) {
	r := testRegistry(t)
	kwd := r.Active("KWD")
	if kwd == nil {
		t.Fatal("KWD not found")
	}

	if kwd.MinorUnits != 3 {
		t.Errorf("KWD MinorUnits = %d, want 3", kwd.MinorUnits)
	}
}

func TestCHFProperties(t *testing.T) {
	r := testRegistry(t)
	chf := r.Active("CHF")
	if chf == nil {
		t.Fatal("CHF not found")
	}

	if chf.Entity != "Switzerland" {
		t.Errorf("CHF Entity = %q, want 'Switzerland'", chf.Entity)
	}
}

func TestBGNProperties(t *testing.T) {
	r := testRegistry(t)
	bgn := r.Active("BGN")
	if bgn == nil {
		t.Fatal("BGN not found")
	}

	if bgn.IsIndependent {
		t.Error("BGN should not be independent (pegged to EUR)")
	}
}

// ---------------------------------------------------------------------------
// Conversion tests
// ---------------------------------------------------------------------------

func TestToMinorUSD(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	tests := []struct {
		major float64
		minor int64
	}{
		{100.50, 10050},
		{0.01, 1},
		{0.00, 0},
		{1.00, 100},
		{0.99, 99},
		{9999999.99, 999999999},
	}

	for _, tt := range tests {
		if got := usd.ToMinor(tt.major); got != tt.minor {
			t.Errorf("USD.ToMinor(%v) = %d, want %d", tt.major, got, tt.minor)
		}
	}
}

func TestFromMinorUSD(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	tests := []struct {
		minor int64
		major float64
	}{
		{10050, 100.5},
		{1, 0.01},
		{0, 0.0},
		{100, 1.0},
	}

	for _, tt := range tests {
		if got := usd.FromMinor(tt.minor); got != tt.major {
			t.Errorf("USD.FromMinor(%d) = %v, want %v", tt.minor, got, tt.major)
		}
	}
}

func TestToMinorJPY(t *testing.T) {
	r := testRegistry(t)
	jpy := r.Active("JPY")

	if got := jpy.ToMinor(500.0); got != 500 {
		t.Errorf("JPY.ToMinor(500.0) = %d, want 500", got)
	}
}

func TestFromMinorJPY(t *testing.T) {
	r := testRegistry(t)
	jpy := r.Active("JPY")

	if got := jpy.FromMinor(500); got != 500.0 {
		t.Errorf("JPY.FromMinor(500) = %v, want 500.0", got)
	}
}

func TestToMinorKWD(t *testing.T) {
	r := testRegistry(t)
	kwd := r.Active("KWD")

	if got := kwd.ToMinor(1.500); got != 1500 {
		t.Errorf("KWD.ToMinor(1.500) = %d, want 1500", got)
	}
}

func TestFromMinorKWD(t *testing.T) {
	r := testRegistry(t)
	kwd := r.Active("KWD")

	if got := kwd.FromMinor(1500); got != 1.5 {
		t.Errorf("KWD.FromMinor(1500) = %v, want 1.5", got)
	}
}

func TestToMinorBTC(t *testing.T) {
	r := testRegistry(t)
	btc := r.Currency("BTC")
	if btc == nil {
		t.Fatal("BTC not found")
	}

	if got := btc.ToMinor(0.000_000_01); got != 1 {
		t.Errorf("BTC.ToMinor(0.000_000_01) = %d, want 1", got)
	}
}

func TestToMinorRoundTrip(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	tests := []float64{0.01, 0.50, 1.00, 100.50, 9999999.99}
	for _, amount := range tests {
		minor := usd.ToMinor(amount)
		major := usd.FromMinor(minor)
		if major != amount {
			t.Errorf("Round-trip failed: %v → %d → %v", amount, minor, major)
		}
	}
}

// ---------------------------------------------------------------------------
// Panic tests
// ---------------------------------------------------------------------------

func TestToMinorNaNPanics(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic for NaN, but did not panic")
		}
	}()

	usd.ToMinor(math.NaN())
}

func TestToMinorInfPanics(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic for +Inf, but did not panic")
		}
	}()

	usd.ToMinor(math.Inf(1))
}

func TestToMinorNegInfPanics(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic for -Inf, but did not panic")
		}
	}()

	usd.ToMinor(math.Inf(-1))
}

// ---------------------------------------------------------------------------
// Format tests
// ---------------------------------------------------------------------------

func TestFormatUSD(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	tests := []struct {
		amount   float64
		expected string
	}{
		{100.50, "$100.50"},
		{0.99, "$0.99"},
		{1000.00, "$1,000.00"},
		{0.00, "$0.00"},
	}

	for _, tt := range tests {
		if got := usd.Format(tt.amount); got != tt.expected {
			t.Errorf("USD.Format(%v) = %q, want %q", tt.amount, got, tt.expected)
		}
	}
}

func TestFormatJPY(t *testing.T) {
	r := testRegistry(t)
	jpy := r.Active("JPY")

	if got := jpy.Format(500.0); got != "¥500" {
		t.Errorf("JPY.Format(500.0) = %q, want '¥500'", got)
	}
}

func TestFormatEUR(t *testing.T) {
	r := testRegistry(t)
	eur := r.Active("EUR")

	if got := eur.Format(1234.56); got != "€1,234.56" {
		t.Errorf("EUR.Format(1234.56) = %q, want '€1,234.56'", got)
	}
}

// ---------------------------------------------------------------------------
// Peg tests
// ---------------------------------------------------------------------------

func TestAEDPeg(t *testing.T) {
	r := testRegistry(t)
	aed := r.Active("AED")
	if aed == nil {
		t.Fatal("AED not found")
	}

	if !aed.IsPegged() {
		t.Error("AED should be pegged")
	}
	if aed.IsIndependent {
		t.Error("AED should not be independent")
	}
	if aed.PeggedTo == nil {
		t.Fatal("AED PeggedTo is nil")
	}
	if *aed.PeggedTo != "USD" {
		t.Errorf("AED PeggedTo = %q, want 'USD'", *aed.PeggedTo)
	}
	if aed.PegRate == nil {
		t.Fatal("AED PegRate is nil")
	}
	if *aed.PegRate != 3.6725 {
		t.Errorf("AED PegRate = %v, want 3.6725", *aed.PegRate)
	}
	if aed.PegBandPct == nil {
		t.Fatal("AED PegBandPct is nil")
	}
	if *aed.PegBandPct != 0.0 {
		t.Errorf("AED PegBandPct = %v, want 0.0", *aed.PegBandPct)
	}
}

func TestDKPPeg(t *testing.T) {
	r := testRegistry(t)
	dkk := r.Active("DKK")
	if dkk == nil {
		t.Fatal("DKK not found")
	}

	if dkk.PeggedTo == nil {
		t.Fatal("DKK PeggedTo is nil")
	}
	if *dkk.PeggedTo != "EUR" {
		t.Errorf("DKK PeggedTo = %q, want 'EUR'", *dkk.PeggedTo)
	}
	if dkk.PegBandPct == nil {
		t.Fatal("DKK PegBandPct is nil")
	}
	if *dkk.PegBandPct != 2.25 {
		t.Errorf("DKK PegBandPct = %v, want 2.25", *dkk.PegBandPct)
	}
}

func TestUSDIndependent(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	if usd.IsPegged() {
		t.Error("USD should not be pegged")
	}
	if !usd.IsIndependent {
		t.Error("USD should be independent")
	}
}

func TestHKDIsPegged(t *testing.T) {
	r := testRegistry(t)
	hkd := r.Active("HKD")
	if hkd == nil {
		t.Fatal("HKD not found")
	}

	if !hkd.IsPegged() {
		t.Error("HKD should be pegged to USD")
	}
	if hkd.IsIndependent {
		t.Error("HKD should not be independent")
	}
}

// ---------------------------------------------------------------------------
// PeggedTo filter tests
// ---------------------------------------------------------------------------

func TestPeggedToUSD(t *testing.T) {
	r := testRegistry(t)
	pegged := r.PeggedTo("USD")

	if len(pegged) == 0 {
		t.Fatal("Expected currencies pegged to USD, got none")
	}

	codes := make(map[string]bool)
	for _, c := range pegged {
		codes[c.Code] = true
	}

	expected := []string{"AED", "SAR", "QAR", "HKD", "JOD", "BHD", "OMR"}
	for _, code := range expected {
		if !codes[code] {
			t.Errorf("Expected %s in USD-pegged list, not found", code)
		}
	}
}

func TestPeggedToEUR(t *testing.T) {
	r := testRegistry(t)
	pegged := r.PeggedTo("EUR")

	if len(pegged) == 0 {
		t.Fatal("Expected currencies pegged to EUR, got none")
	}

	codes := make(map[string]bool)
	for _, c := range pegged {
		codes[c.Code] = true
	}

	expected := []string{"DKK", "BGN"}
	for _, code := range expected {
		if !codes[code] {
			t.Errorf("Expected %s in EUR-pegged list, not found", code)
		}
	}
}

// ---------------------------------------------------------------------------
// Independent filter tests
// ---------------------------------------------------------------------------

func TestIndependent(t *testing.T) {
	r := testRegistry(t)
	independent := r.Independent()

	if len(independent) == 0 {
		t.Fatal("Expected independent currencies, got none")
	}

	codes := make(map[string]bool)
	for _, c := range independent {
		codes[c.Code] = true
	}

	// Major independent currencies must be present
	majors := []string{"USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD"}
	for _, code := range majors {
		if !codes[code] {
			t.Errorf("Expected %s in independent list", code)
		}
	}

	// Pegged currencies must NOT be present
	if codes["AED"] {
		t.Error("AED (pegged to USD) should not be in independent list")
	}
}

// ---------------------------------------------------------------------------
// WithMinorUnits filter tests
// ---------------------------------------------------------------------------

func TestWithMinorUnits3(t *testing.T) {
	r := testRegistry(t)
	three := r.WithMinorUnits(3)

	codes := make(map[string]bool)
	for _, c := range three {
		codes[c.Code] = true
	}

	expected := []string{"KWD", "BHD", "OMR", "JOD", "TND", "LYD", "IQD"}
	for _, code := range expected {
		if !codes[code] {
			t.Errorf("Expected %s in 3-minor-unit list", code)
		}
	}
}

func TestWithMinorUnits0(t *testing.T) {
	r := testRegistry(t)
	zero := r.WithMinorUnits(0)

	codes := make(map[string]bool)
	for _, c := range zero {
		codes[c.Code] = true
	}

	expected := []string{"JPY", "KRW", "VND", "ISK", "CLP"}
	for _, code := range expected {
		if !codes[code] {
			t.Errorf("Expected %s in 0-minor-unit list", code)
		}
	}
}

// ---------------------------------------------------------------------------
// Withdrawn currency tests
// ---------------------------------------------------------------------------

func TestWithdrawnDEM(t *testing.T) {
	r := testRegistry(t)
	dem := r.Withdrawn("DEM")
	if dem == nil {
		t.Fatal("DEM not found in withdrawn")
	}

	if dem.Name != "German Mark" {
		t.Errorf("DEM Name = %q, want 'German Mark'", dem.Name)
	}
	if dem.ReplacedBy == nil {
		t.Fatal("DEM ReplacedBy is nil")
	}
	if *dem.ReplacedBy != "EUR" {
		t.Errorf("DEM ReplacedBy = %q, want 'EUR'", *dem.ReplacedBy)
	}
	if dem.ConversionRate == nil {
		t.Fatal("DEM ConversionRate is nil")
	}
	if *dem.ConversionRate != 1.95583 {
		t.Errorf("DEM ConversionRate = %v, want 1.95583", *dem.ConversionRate)
	}
}

func TestWithdrawnFRF(t *testing.T) {
	r := testRegistry(t)
	frf := r.Withdrawn("FRF")
	if frf == nil {
		t.Fatal("FRF not found in withdrawn")
	}

	if frf.Name != "French Franc" {
		t.Errorf("FRF Name = %q, want 'French Franc'", frf.Name)
	}
}

func TestWithdrawnITL(t *testing.T) {
	r := testRegistry(t)
	itl := r.Withdrawn("ITL")
	if itl == nil {
		t.Fatal("ITL not found in withdrawn")
	}

	if itl.MinorUnits != 0 {
		t.Errorf("ITL MinorUnits = %d, want 0 (no subdivision)", itl.MinorUnits)
	}
}

// ---------------------------------------------------------------------------
// Non-ISO tests
// ---------------------------------------------------------------------------

func TestNonISOBTC(t *testing.T) {
	r := testRegistry(t)
	btc := r.NonISO("BTC")
	if btc == nil {
		t.Fatal("BTC not found in non-ISO")
	}

	if btc.MinorUnits != 8 {
		t.Errorf("BTC MinorUnits = %d, want 8", btc.MinorUnits)
	}
	if btc.ToMinor(0.000_000_01) != 1 {
		t.Error("BTC.ToMinor(0.000_000_01) != 1")
	}
}

func TestNonISOETH(t *testing.T) {
	r := testRegistry(t)
	eth := r.NonISO("ETH")
	if eth == nil {
		t.Fatal("ETH not found in non-ISO")
	}

	if eth.MinorUnits != 18 {
		t.Errorf("ETH MinorUnits = %d, want 18", eth.MinorUnits)
	}
}

func TestNonISOXAU(t *testing.T) {
	r := testRegistry(t)
	xau := r.NonISO("XAU")
	if xau == nil {
		t.Fatal("XAU not found in non-ISO")
	}

	if xau.Type == nil {
		t.Fatal("XAU Type is nil")
	}
	if *xau.Type != "commodity" {
		t.Errorf("XAU Type = %q, want 'commodity'", *xau.Type)
	}
}

func TestNonISODAI(t *testing.T) {
	r := testRegistry(t)
	dai := r.NonISO("DAI")
	if dai == nil {
		t.Fatal("DAI not found in non-ISO")
	}

	if dai.PegMechanism == nil {
		t.Fatal("DAI PegMechanism is nil")
	}
	if *dai.PegMechanism != "Crypto-overcollateralized" {
		t.Errorf("DAI PegMechanism = %q, want 'Crypto-overcollateralized'", *dai.PegMechanism)
	}
}

// ---------------------------------------------------------------------------
// Country relationship tests
// ---------------------------------------------------------------------------

func TestUSDIssuingCountries(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	issuers := usd.IssuingCountries()
	if len(issuers) != 1 {
		t.Errorf("USD should have 1 issuing country, got %d", len(issuers))
	}
	if len(issuers) > 0 && issuers[0].Code != "US" {
		t.Errorf("USD issuing country = %s, want 'US'", issuers[0].Code)
	}
}

func TestUSDAdoptingCountries(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	adopters := usd.AdoptingCountries()
	if len(adopters) == 0 {
		t.Error("USD should have adopting countries")
	}

	codes := make(map[string]bool)
	for _, c := range adopters {
		codes[c.Code] = true
	}

	expected := []string{"EC", "PA", "SV"}
	for _, code := range expected {
		if !codes[code] {
			t.Errorf("Expected %s in USD adopting countries", code)
		}
	}
}

func TestEURCountries(t *testing.T) {
	r := testRegistry(t)
	eur := r.Active("EUR")

	if len(eur.Countries) < 19 {
		t.Errorf("EUR should have at least 19 countries, got %d", len(eur.Countries))
	}

	// Germany must be an issuer
	found := false
	for _, c := range eur.Countries {
		if c.Code == "DE" && c.Relationship == "issuing" {
			found = true
			break
		}
	}
	if !found {
		t.Error("Germany (DE) should be an issuing country for EUR")
	}
}

func TestCHFCountries(t *testing.T) {
	r := testRegistry(t)
	chf := r.Active("CHF")

	issuers := chf.IssuingCountries()
	if len(issuers) != 1 {
		t.Errorf("CHF should have 1 issuing country, got %d", len(issuers))
	}
	if len(issuers) > 0 && issuers[0].Code != "CH" {
		t.Errorf("CHF issuing country = %s, want 'CH'", issuers[0].Code)
	}

	// Liechtenstein uses CHF
	found := false
	for _, c := range chf.Countries {
		if c.Code == "LI" {
			found = true
			break
		}
	}
	if !found {
		t.Error("Liechtenstein (LI) should be in CHF countries")
	}
}

// ---------------------------------------------------------------------------
// IssuedBy / UsedIn tests
// ---------------------------------------------------------------------------

func TestIssuedByCH(t *testing.T) {
	r := testRegistry(t)
	swiss := r.IssuedBy("CH")

	codes := make(map[string]bool)
	for _, c := range swiss {
		codes[c.Code] = true
	}

	if !codes["CHF"] {
		t.Error("CHF should be issued by Switzerland (CH)")
	}
}

func TestUsedInLI(t *testing.T) {
	r := testRegistry(t)
	used := r.UsedIn("LI")

	codes := make(map[string]bool)
	for _, c := range used {
		codes[c.Code] = true
	}

	if !codes["CHF"] {
		t.Error("CHF should be used in Liechtenstein (LI)")
	}
}

// ---------------------------------------------------------------------------
// Collection accessor tests
// ---------------------------------------------------------------------------

func TestAllActive(t *testing.T) {
	r := testRegistry(t)
	all := r.AllActive()

	if len(all) != r.ActiveCount() {
		t.Errorf("AllActive() len = %d, ActiveCount() = %d", len(all), r.ActiveCount())
	}
}

func TestAllWithdrawn(t *testing.T) {
	r := testRegistry(t)
	all := r.AllWithdrawn()

	if len(all) != r.WithdrawnCount() {
		t.Errorf("AllWithdrawn() len = %d, WithdrawnCount() = %d", len(all), r.WithdrawnCount())
	}
}

func TestAllCurrencies(t *testing.T) {
	r := testRegistry(t)
	all := r.AllCurrencies()

	expected := r.ActiveCount() + r.WithdrawnCount() + r.NonISOCount()
	if len(all) != expected {
		t.Errorf("AllCurrencies() len = %d, want %d", len(all), expected)
	}
}

// ---------------------------------------------------------------------------
// Summary tests
// ---------------------------------------------------------------------------

func TestSummary(t *testing.T) {
	r := testRegistry(t)
	s := r.Summary()

	if s.Version != r.Version() {
		t.Errorf("Summary.Version = %q, want %q", s.Version, r.Version())
	}
	if s.ActiveCurrencies != r.ActiveCount() {
		t.Errorf("Summary.ActiveCurrencies = %d, want %d", s.ActiveCurrencies, r.ActiveCount())
	}
	if s.WithdrawnCurrencies != r.WithdrawnCount() {
		t.Errorf("Summary.WithdrawnCurrencies = %d, want %d", s.WithdrawnCurrencies, r.WithdrawnCount())
	}
	if s.PeggedCurrencies != r.PeggedCount() {
		t.Errorf("Summary.PeggedCurrencies = %d, want %d", s.PeggedCurrencies, r.PeggedCount())
	}
	if s.IndependentCurrencies != r.IndependentCount() {
		t.Errorf("Summary.IndependentCurrencies = %d, want %d", s.IndependentCurrencies, r.IndependentCount())
	}
	if len(s.MinorUnitsDistribution) == 0 {
		t.Error("MinorUnitsDistribution should not be empty")
	}
	if _, ok := s.MinorUnitsDistribution[2]; !ok {
		t.Error("MinorUnitsDistribution should contain key 2 (standard cents/pence)")
	}
}

// ---------------------------------------------------------------------------
// String tests
// ---------------------------------------------------------------------------

func TestCurrencyString(t *testing.T) {
	r := testRegistry(t)
	usd := r.Active("USD")

	s := usd.String()
	if s == "" {
		t.Error("String() returned empty string")
	}
}

func TestRegistryString(t *testing.T) {
	r := testRegistry(t)

	s := r.String()
	if s == "" {
		t.Error("String() returned empty string")
	}
}

// ---------------------------------------------------------------------------
// Benchmark tests
// ---------------------------------------------------------------------------

func BenchmarkLoad(b *testing.B) {
	// Reset the singleton for each benchmark run to measure true load time.
	// In practice Load() is called once, but this measures parsing cost.
	for i := 0; i < b.N; i++ {
		// Direct load without singleton
		_, err := loadRegistry()
		if err != nil {
			b.Fatalf("loadRegistry() failed: %v", err)
		}
	}
}

func BenchmarkActive(b *testing.B) {
	r := MustLoad()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		_ = r.Active("USD")
	}
}

func BenchmarkCurrency(b *testing.B) {
	r := MustLoad()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		_ = r.Currency("USD")
	}
}

func BenchmarkToMinor(b *testing.B) {
	r := MustLoad()
	usd := r.Active("USD")
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		usd.ToMinor(100.50)
	}
}

func BenchmarkPeggedTo(b *testing.B) {
	r := MustLoad()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		r.PeggedTo("USD")
	}
}

func BenchmarkAllActive(b *testing.B) {
	r := MustLoad()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		r.AllActive()
	}
}

func BenchmarkSummary(b *testing.B) {
	r := MustLoad()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		r.Summary()
	}
}
// ---------------------------------------------------------------------------
// Cross-language consistency (issue #4)
//
// Ports tests/cross_language_consistency.json — the same file
// tests/test_wrappers.py checks for the Python wrapper — so a divergence
// between wrappers shows up here instead of only in Python. Path is
// relative to this package directory (wrappers/go), which is also the
// working directory `go test` runs from.
// ---------------------------------------------------------------------------

type clcConversion struct {
	Major float64 `json:"major"`
	Minor int64   `json:"minor"`
	Lossy bool    `json:"lossy"`
}

type clcFormatting struct {
	Major     float64 `json:"major"`
	Formatted string  `json:"formatted"`
}

type clcTestVector struct {
	Code           string           `json:"code"`
	Description    string           `json:"description"`
	MinorUnits     int              `json:"minor_units"`
	IsIndependent  *bool            `json:"is_independent"`
	IsPegged       *bool            `json:"is_pegged"`
	PeggedTo       *string          `json:"pegged_to"`
	PegType        *string          `json:"peg_type"`
	PegRate        *float64         `json:"peg_rate"`
	PegBandPct     *float64         `json:"peg_band_pct"`
	Withdrawn      bool             `json:"withdrawn"`
	ReplacedBy     *string          `json:"replaced_by"`
	ConversionRate *float64         `json:"conversion_rate"`
	Conversions    []clcConversion  `json:"conversions"`
	Formatting     []clcFormatting  `json:"formatting"`
}

type clcLookupTest struct {
	Description  string   `json:"description"`
	Lookups      []string `json:"lookups"`
	Method       string   `json:"method"`
	ExpectedCode string   `json:"expected_code"`
	ExpectedNull bool     `json:"expected_null"`
}

type clcFilterTest struct {
	Description         string      `json:"description"`
	Method              string      `json:"method"`
	Argument            interface{} `json:"argument"`
	ArgumentType        string      `json:"argument_type"`
	ExpectedContains    []string    `json:"expected_contains"`
	ExpectedNotContains []string    `json:"expected_not_contains"`
}

type clcSummaryTest struct {
	Description  string   `json:"description"`
	ExpectedKeys []string `json:"expected_keys"`
}

type crossLanguageConsistency struct {
	Description  string          `json:"description"`
	Version      string          `json:"version"`
	TestVectors  []clcTestVector `json:"test_vectors"`
	LookupTests  []clcLookupTest `json:"lookup_tests"`
	FilterTests  []clcFilterTest `json:"filter_tests"`
	SummaryTests []clcSummaryTest `json:"summary_tests"`
}

func loadConsistencyVectors(t *testing.T) crossLanguageConsistency {
	t.Helper()
	data, err := os.ReadFile("../../tests/cross_language_consistency.json")
	if err != nil {
		t.Fatalf("failed to read cross_language_consistency.json: %v", err)
	}
	var v crossLanguageConsistency
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatalf("failed to parse cross_language_consistency.json: %v", err)
	}
	return v
}

// clcLookup is the Go-idiom translation of the JSON's "method" field for
// lookup_tests. The JSON's method names ("active", "withdrawn", "currency")
// happen to match Go's exported method names case-insensitively, but Go
// requires an explicit switch rather than dynamic dispatch by string.
func clcLookup(t *testing.T, r *CurrencyRegistry, methodName, code string) *Currency {
	t.Helper()
	switch methodName {
	case "active":
		return r.Active(code)
	case "withdrawn":
		return r.Withdrawn(code)
	case "currency":
		return r.Currency(code)
	default:
		t.Fatalf("no Go mapping for lookup method %q", methodName)
		return nil
	}
}

// clcFilter is the Go-idiom translation of the JSON's "method" field for
// filter_tests ("pegged_to" -> PeggedTo, "with_minor_units" -> WithMinorUnits,
// "independent" -> Independent).
func clcFilter(t *testing.T, r *CurrencyRegistry, test clcFilterTest) []*Currency {
	t.Helper()
	switch test.Method {
	case "pegged_to":
		arg, ok := test.Argument.(string)
		if !ok {
			t.Fatalf("pegged_to argument is not a string: %v", test.Argument)
		}
		return r.PeggedTo(arg)
	case "with_minor_units":
		// encoding/json unmarshals JSON numbers into float64 when the
		// target is interface{}.
		argF, ok := test.Argument.(float64)
		if !ok {
			t.Fatalf("with_minor_units argument is not a number: %v", test.Argument)
		}
		return r.WithMinorUnits(int(argF))
	case "independent":
		return r.Independent()
	default:
		t.Fatalf("no Go mapping for filter method %q", test.Method)
		return nil
	}
}

// clcSummaryHasKey checks the RegistrySummary struct's json tags — the
// wire-format contract — rather than requiring a Go-idiom field-name map,
// since Go's json tags on RegistrySummary already match the JSON file's
// snake_case keys verbatim (unlike the JS wrapper's summary(), which
// intentionally uses camelCase — see wrappers/javascript/test.js for that
// divergence).
func clcSummaryHasKey(key string) bool {
	rt := reflect.TypeOf(RegistrySummary{})
	for i := 0; i < rt.NumField(); i++ {
		tag := rt.Field(i).Tag.Get("json")
		name := strings.Split(tag, ",")[0]
		if name == key {
			return true
		}
	}
	return false
}

func TestCrossLanguageConsistency(t *testing.T) {
	r := testRegistry(t)
	vectors := loadConsistencyVectors(t)

	t.Run("ConversionVectors", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found in registry", v.Code)
			}
			for _, conv := range v.Conversions {
				result := c.ToMinor(conv.Major)
				if result != conv.Minor {
					t.Errorf("%s.ToMinor(%v) = %d, expected %d", v.Code, conv.Major, result, conv.Minor)
				}
			}
		}
	})

	t.Run("ConversionVectorsRoundTrip", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found in registry", v.Code)
			}
			for _, conv := range v.Conversions {
				// "lossy" entries are rounding-boundary values not exactly
				// representable in integer minor units (e.g. USD 100.005
				// rounds to 10001, whose true inverse is 100.01, not the
				// original 100.005).
				if conv.Lossy {
					continue
				}
				back := c.FromMinor(conv.Minor)
				if back != conv.Major {
					t.Errorf("%s round-trip failed: %v -> %d -> %v", v.Code, conv.Major, conv.Minor, back)
				}
			}
		}
	})

	t.Run("ConversionVectorsHandleZero", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found", v.Code)
			}
			if c.ToMinor(0.0) != 0 {
				t.Errorf("%s.ToMinor(0.0) should be 0", v.Code)
			}
			if c.FromMinor(0) != 0.0 {
				t.Errorf("%s.FromMinor(0) should be 0.0", v.Code)
			}
		}
	})

	t.Run("FormattingVectors", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found in registry", v.Code)
			}
			for _, fmtVec := range v.Formatting {
				result := c.Format(fmtVec.Major)
				if result != fmtVec.Formatted {
					t.Errorf("%s.Format(%v) = %q, expected %q", v.Code, fmtVec.Major, result, fmtVec.Formatted)
				}
			}
		}
	})

	t.Run("MinorUnitsValues", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found", v.Code)
			}
			if c.MinorUnits != v.MinorUnits {
				t.Errorf("%s.MinorUnits = %d, expected %d", v.Code, c.MinorUnits, v.MinorUnits)
			}
		}
	})

	t.Run("PegProperties", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found", v.Code)
			}
			if v.IsIndependent != nil && c.IsIndependent != *v.IsIndependent {
				t.Errorf("%s.IsIndependent = %v, expected %v", v.Code, c.IsIndependent, *v.IsIndependent)
			}
			if v.IsPegged != nil && c.IsPegged() != *v.IsPegged {
				t.Errorf("%s.IsPegged() = %v, expected %v", v.Code, c.IsPegged(), *v.IsPegged)
			}
			if v.PeggedTo != nil {
				if c.PeggedTo == nil {
					t.Errorf("%s.PeggedTo is nil, expected %q", v.Code, *v.PeggedTo)
				} else if *c.PeggedTo != *v.PeggedTo {
					t.Errorf("%s.PeggedTo = %q, expected %q", v.Code, *c.PeggedTo, *v.PeggedTo)
				}
			}
			if v.PegType != nil {
				if c.PegType == nil {
					t.Errorf("%s.PegType is nil, expected %q", v.Code, *v.PegType)
				} else if *c.PegType != *v.PegType {
					t.Errorf("%s.PegType = %q, expected %q", v.Code, *c.PegType, *v.PegType)
				}
			}
			if v.PegRate != nil {
				if c.PegRate == nil {
					t.Errorf("%s.PegRate is nil, expected %v", v.Code, *v.PegRate)
				} else if *c.PegRate != *v.PegRate {
					t.Errorf("%s.PegRate = %v, expected %v", v.Code, *c.PegRate, *v.PegRate)
				}
			}
			if v.PegBandPct != nil {
				if c.PegBandPct == nil {
					t.Errorf("%s.PegBandPct is nil, expected %v", v.Code, *v.PegBandPct)
				} else if *c.PegBandPct != *v.PegBandPct {
					t.Errorf("%s.PegBandPct = %v, expected %v", v.Code, *c.PegBandPct, *v.PegBandPct)
				}
			}
		}
	})

	t.Run("WithdrawnProperties", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			if !v.Withdrawn {
				continue
			}
			c := r.Currency(v.Code)
			if c == nil {
				t.Fatalf("%s not found", v.Code)
			}
			if v.ReplacedBy != nil {
				if c.ReplacedBy == nil {
					t.Errorf("%s.ReplacedBy is nil, expected %q", v.Code, *v.ReplacedBy)
				} else if *c.ReplacedBy != *v.ReplacedBy {
					t.Errorf("%s.ReplacedBy = %q, expected %q", v.Code, *c.ReplacedBy, *v.ReplacedBy)
				}
			}
			if v.ConversionRate != nil {
				if c.ConversionRate == nil {
					t.Errorf("%s.ConversionRate is nil, expected %v", v.Code, *v.ConversionRate)
				} else if *c.ConversionRate != *v.ConversionRate {
					t.Errorf("%s.ConversionRate = %v, expected %v", v.Code, *c.ConversionRate, *v.ConversionRate)
				}
			}
		}
	})

	t.Run("CaseInsensitiveLookup", func(t *testing.T) {
		for _, test := range vectors.LookupTests {
			if test.ExpectedNull {
				for _, code := range test.Lookups {
					result := clcLookup(t, r, test.Method, code)
					if result != nil {
						t.Errorf("%s(%q) should return nil, got %v", test.Method, code, result.Code)
					}
				}
			} else {
				for _, code := range test.Lookups {
					result := clcLookup(t, r, test.Method, code)
					if result == nil {
						t.Errorf("%s(%q) returned nil", test.Method, code)
						continue
					}
					if result.Code != test.ExpectedCode {
						t.Errorf("%s(%q).Code = %q, expected %q", test.Method, code, result.Code, test.ExpectedCode)
					}
				}
			}
		}
	})

	t.Run("FilterVectors", func(t *testing.T) {
		for _, test := range vectors.FilterTests {
			results := clcFilter(t, r, test)
			resultCodes := make(map[string]bool, len(results))
			for _, c := range results {
				resultCodes[c.Code] = true
			}
			for _, expected := range test.ExpectedContains {
				if !resultCodes[expected] {
					t.Errorf("%s() should contain %s", test.Method, expected)
				}
			}
			for _, excluded := range test.ExpectedNotContains {
				if resultCodes[excluded] {
					t.Errorf("%s() should NOT contain %s", test.Method, excluded)
				}
			}
		}
	})

	t.Run("SummaryHasExpectedKeys", func(t *testing.T) {
		for _, test := range vectors.SummaryTests {
			for _, key := range test.ExpectedKeys {
				if !clcSummaryHasKey(key) {
					t.Errorf("RegistrySummary missing json key %q", key)
				}
			}
		}
	})

	t.Run("RegistryContainsAllTestVectorCodes", func(t *testing.T) {
		for _, v := range vectors.TestVectors {
			if r.Currency(v.Code) == nil {
				t.Errorf("%s from test vectors not found in registry", v.Code)
			}
		}
	})

	t.Run("ToMinorHandlesNegativeAmounts", func(t *testing.T) {
		usd := r.Currency("USD")
		if usd == nil {
			t.Fatal("USD not found")
		}
		if usd.ToMinor(-100.50) != -10050 {
			t.Errorf("USD.ToMinor(-100.50) = %d, expected -10050", usd.ToMinor(-100.50))
		}
		if usd.ToMinor(-0.01) != -1 {
			t.Errorf("USD.ToMinor(-0.01) = %d, expected -1", usd.ToMinor(-0.01))
		}
	})

	t.Run("FromMinorHandlesNegativeAmounts", func(t *testing.T) {
		usd := r.Currency("USD")
		if usd == nil {
			t.Fatal("USD not found")
		}
		if usd.FromMinor(-10050) != -100.5 {
			t.Errorf("USD.FromMinor(-10050) = %v, expected -100.5", usd.FromMinor(-10050))
		}
		if usd.FromMinor(-1) != -0.01 {
			t.Errorf("USD.FromMinor(-1) = %v, expected -0.01", usd.FromMinor(-1))
		}
	})
}