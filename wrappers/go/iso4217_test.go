package iso4217

import (
	"math"
	"testing"
)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

func registry(t *testing.T) *CurrencyRegistry {
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
	r := registry(t)

	if r.Version() == "" || r.Version() == "unknown" {
		t.Error("Version is empty or unknown")
	}
	if r.Updated() == "" || r.Updated() == "unknown" {
		t.Error("Updated is empty or unknown")
	}
}

func TestLoadHasCurrencies(t *testing.T) {
	r := registry(t)

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
	r := registry(t)
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
	r := registry(t)

	tests := []string{"usd", "Usd", "USD", "uSd"}
	for _, code := range tests {
		if r.Active(code) == nil {
			t.Errorf("Active(%q) returned nil — lookup should be case-insensitive", code)
		}
	}
}

func TestActiveNotFound(t *testing.T) {
	r := registry(t)

	if c := r.Active("XXX"); c != nil {
		t.Errorf("Expected nil for 'XXX', got %v", c)
	}
}

func TestCurrencyFindsActive(t *testing.T) {
	r := registry(t)

	usd := r.Currency("USD")
	if usd == nil {
		t.Fatal("Currency('USD') returned nil")
	}
}

func TestCurrencyFindsWithdrawn(t *testing.T) {
	r := registry(t)

	dem := r.Currency("DEM")
	if dem == nil {
		t.Fatal("Currency('DEM') returned nil")
	}
}

func TestCurrencyFindsNonISO(t *testing.T) {
	r := registry(t)

	btc := r.Currency("BTC")
	if btc == nil {
		t.Fatal("Currency('BTC') returned nil")
	}
}

func TestCurrencyNotFound(t *testing.T) {
	r := registry(t)

	if c := r.Currency("XXX"); c != nil {
		t.Errorf("Expected nil for 'XXX', got %v", c)
	}
}

func TestContains(t *testing.T) {
	r := registry(t)

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
	r := registry(t)
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
	r := registry(t)
	kwd := r.Active("KWD")
	if kwd == nil {
		t.Fatal("KWD not found")
	}

	if kwd.MinorUnits != 3 {
		t.Errorf("KWD MinorUnits = %d, want 3", kwd.MinorUnits)
	}
}

func TestCHFProperties(t *testing.T) {
	r := registry(t)
	chf := r.Active("CHF")
	if chf == nil {
		t.Fatal("CHF not found")
	}

	if chf.Entity != "Switzerland" {
		t.Errorf("CHF Entity = %q, want 'Switzerland'", chf.Entity)
	}
}

func TestBGNProperties(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	jpy := r.Active("JPY")

	if got := jpy.ToMinor(500.0); got != 500 {
		t.Errorf("JPY.ToMinor(500.0) = %d, want 500", got)
	}
}

func TestFromMinorJPY(t *testing.T) {
	r := registry(t)
	jpy := r.Active("JPY")

	if got := jpy.FromMinor(500); got != 500.0 {
		t.Errorf("JPY.FromMinor(500) = %v, want 500.0", got)
	}
}

func TestToMinorKWD(t *testing.T) {
	r := registry(t)
	kwd := r.Active("KWD")

	if got := kwd.ToMinor(1.500); got != 1500 {
		t.Errorf("KWD.ToMinor(1.500) = %d, want 1500", got)
	}
}

func TestFromMinorKWD(t *testing.T) {
	r := registry(t)
	kwd := r.Active("KWD")

	if got := kwd.FromMinor(1500); got != 1.5 {
		t.Errorf("KWD.FromMinor(1500) = %v, want 1.5", got)
	}
}

func TestToMinorBTC(t *testing.T) {
	r := registry(t)
	btc := r.Currency("BTC")
	if btc == nil {
		t.Fatal("BTC not found")
	}

	if got := btc.ToMinor(0.000_000_01); got != 1 {
		t.Errorf("BTC.ToMinor(0.000_000_01) = %d, want 1", got)
	}
}

func TestToMinorRoundTrip(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
	usd := r.Active("USD")

	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic for NaN, but did not panic")
		}
	}()

	usd.ToMinor(math.NaN())
}

func TestToMinorInfPanics(t *testing.T) {
	r := registry(t)
	usd := r.Active("USD")

	defer func() {
		if r := recover(); r == nil {
			t.Error("Expected panic for +Inf, but did not panic")
		}
	}()

	usd.ToMinor(math.Inf(1))
}

func TestToMinorNegInfPanics(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
	usd := r.Active("USD")

	tests := []struct {
		amount   float64
		expected string
	}{
		{100.50, "$100.50"},
		{0.99, "$0.99"},
		{1000.00, "$1000.00"},
		{0.00, "$0.00"},
	}

	for _, tt := range tests {
		if got := usd.Format(tt.amount); got != tt.expected {
			t.Errorf("USD.Format(%v) = %q, want %q", tt.amount, got, tt.expected)
		}
	}
}

func TestFormatJPY(t *testing.T) {
	r := registry(t)
	jpy := r.Active("JPY")

	if got := jpy.Format(500.0); got != "¥500" {
		t.Errorf("JPY.Format(500.0) = %q, want '¥500'", got)
	}
}

func TestFormatEUR(t *testing.T) {
	r := registry(t)
	eur := r.Active("EUR")

	if got := eur.Format(1234.56); got != "€1234.56" {
		t.Errorf("EUR.Format(1234.56) = %q, want '€1234.56'", got)
	}
}

// ---------------------------------------------------------------------------
// Peg tests
// ---------------------------------------------------------------------------

func TestAEDPeg(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	usd := r.Active("USD")

	if usd.IsPegged() {
		t.Error("USD should not be pegged")
	}
	if !usd.IsIndependent {
		t.Error("USD should be independent")
	}
}

func TestHKDIsPegged(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	frf := r.Withdrawn("FRF")
	if frf == nil {
		t.Fatal("FRF not found in withdrawn")
	}

	if frf.Name != "French Franc" {
		t.Errorf("FRF Name = %q, want 'French Franc'", frf.Name)
	}
}

func TestWithdrawnITL(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	eth := r.NonISO("ETH")
	if eth == nil {
		t.Fatal("ETH not found in non-ISO")
	}

	if eth.MinorUnits != 18 {
		t.Errorf("ETH MinorUnits = %d, want 18", eth.MinorUnits)
	}
}

func TestNonISOXAU(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	all := r.AllActive()

	if len(all) != r.ActiveCount() {
		t.Errorf("AllActive() len = %d, ActiveCount() = %d", len(all), r.ActiveCount())
	}
}

func TestAllWithdrawn(t *testing.T) {
	r := registry(t)
	all := r.AllWithdrawn()

	if len(all) != r.WithdrawnCount() {
		t.Errorf("AllWithdrawn() len = %d, WithdrawnCount() = %d", len(all), r.WithdrawnCount())
	}
}

func TestAllCurrencies(t *testing.T) {
	r := registry(t)
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
	r := registry(t)
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
	r := registry(t)
	usd := r.Active("USD")

	s := usd.String()
	if s == "" {
		t.Error("String() returned empty string")
	}
}

func TestRegistryString(t *testing.T) {
	r := registry(t)

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