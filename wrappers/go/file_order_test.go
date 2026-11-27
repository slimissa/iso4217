package iso4217

// Collection order (v1.9.6): every collection is in file order, the order of the entries in iso4217.json, section by
// section, one entry per code (ADR 0015). The expected orders are read from the embedded JSON itself, not from the wrapper.

import (
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"
)

type orderEntry struct {
	Code     string  `json:"code"`
	PegType  *string `json:"peg_type"`
	PeggedTo *string `json:"pegged_to"`
}

type orderJSON struct {
	Currencies struct {
		Active    []orderEntry `json:"active"`
		Withdrawn []orderEntry `json:"withdrawn"`
	} `json:"currencies"`
	NonISO map[string][]orderEntry `json:"non_iso"`
}

func readOrderJSON(t *testing.T) orderJSON {
	t.Helper()
	raw, err := os.ReadFile("iso4217.json")
	if err != nil {
		t.Fatal(err)
	}
	var j orderJSON
	if err := json.Unmarshal(raw, &j); err != nil {
		t.Fatal(err)
	}
	return j
}

// firstSeen keeps one entry per code, at the position of its first entry.
func firstSeen(codes []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, c := range codes {
		if !seen[c] {
			seen[c] = true
			out = append(out, c)
		}
	}
	return out
}

func entryCodes(list []orderEntry) []string {
	out := []string{}
	for _, e := range list {
		out = append(out, strings.ToUpper(e.Code))
	}
	return out
}

func gotCodes(list []*Currency) []string {
	out := []string{}
	for _, c := range list {
		out = append(out, c.Code)
	}
	return out
}

func assertFirstLastAndAll(t *testing.T, name string, got, want []string) {
	t.Helper()
	if len(want) == 0 {
		t.Fatalf("%s: the JSON gives an empty expectation", name)
	}
	if len(got) == 0 || got[0] != want[0] || got[len(got)-1] != want[len(want)-1] {
		t.Fatalf("%s: first/last are %v, want %s ... %s", name, got, want[0], want[len(want)-1])
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%s: order differs from the file:\n got  %v\n want %v", name, got, want)
	}
}

func TestCollectionsAreInFileOrder(t *testing.T) {
	j := readOrderJSON(t)
	r, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	active := firstSeen(entryCodes(j.Currencies.Active))
	withdrawn := firstSeen(entryCodes(j.Currencies.Withdrawn))
	var nonISOAll []string
	for _, cat := range []string{"cryptocurrencies", "stablecoins", "commodities", "special_purpose"} {
		nonISOAll = append(nonISOAll, entryCodes(j.NonISO[cat])...)
	}
	nonISO := firstSeen(nonISOAll)
	all := firstSeen(append(append(append([]string{}, active...), withdrawn...), nonISO...))

	// Twice: a map-ordered accessor can pass once by luck, not every time.
	for i := 0; i < 2; i++ {
		assertFirstLastAndAll(t, "AllActive", gotCodes(r.AllActive()), active)
		assertFirstLastAndAll(t, "AllWithdrawn", gotCodes(r.AllWithdrawn()), withdrawn)
		assertFirstLastAndAll(t, "AllNonISO", gotCodes(r.AllNonISO()), nonISO)
		assertFirstLastAndAll(t, "AllCurrencies", gotCodes(r.AllCurrencies()), all)
		for _, anchor := range []string{"USD", "EUR", "XAF"} {
			want := []string{}
			for _, e := range j.Currencies.Active {
				if e.PegType != nil && *e.PegType == "single" && e.PeggedTo != nil && strings.ToUpper(*e.PeggedTo) == anchor {
					want = append(want, strings.ToUpper(e.Code))
				}
			}
			want = firstSeen(want)
			if len(want) == 0 {
				if len(r.PeggedTo(anchor)) != 0 {
					t.Fatalf("PeggedTo(%s) should be empty", anchor)
				}
				continue
			}
			assertFirstLastAndAll(t, "PeggedTo("+anchor+")", gotCodes(r.PeggedTo(anchor)), want)
		}
	}
}

func TestEveryFilterKeepsFileOrder(t *testing.T) {
	r, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	position := map[string]int{}
	for i, c := range r.AllActive() {
		position[c.Code] = i
	}
	for name, list := range map[string][]*Currency{
		"Independent":                   r.Independent(),
		"WithMinorUnits(2)":             r.WithMinorUnits(2),
		"IssuedBy(FR)":                  r.IssuedBy("FR"),
		"UsedIn(FR)":                    r.UsedIn("FR"),
		"ByClassification(circulating)": r.ByClassification("circulating"),
	} {
		if len(list) == 0 {
			t.Fatalf("%s: empty", name)
		}
		for i := 1; i < len(list); i++ {
			if position[list[i-1].Code] >= position[list[i].Code] {
				t.Fatalf("%s: not in file order: %v", name, gotCodes(list))
			}
		}
	}
}

func TestARepeatedCodeKeepsItsFirstPositionAndItsLastEntry(t *testing.T) {
	r, err := loadRegistryFrom([]byte(`{"currencies": {"active": [
		{"code": "FFF", "name": "first", "minor_units": 2},
		{"code": "GGG", "name": "g", "minor_units": 2},
		{"code": "FFF", "name": "second", "minor_units": 2}],
	  "withdrawn": [{"code": "GGG", "name": "w", "minor_units": 2}, {"code": "WWW", "name": "w2", "minor_units": 2}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	if got := gotCodes(r.AllActive()); !reflect.DeepEqual(got, []string{"FFF", "GGG"}) || r.AllActive()[0].Name != "second" {
		t.Fatalf("AllActive: %v", got)
	}
	if got := gotCodes(r.AllCurrencies()); !reflect.DeepEqual(got, []string{"FFF", "GGG", "WWW"}) || r.AllCurrencies()[1].Name != "g" {
		t.Fatalf("AllCurrencies: %v (the earliest section wins)", got)
	}
}
