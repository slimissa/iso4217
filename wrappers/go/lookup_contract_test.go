package iso4217

// The wrapper lookup contract (ADR 0015, docs/decisions/wrapper-lookup-contract.md): every vector in the `lookup_contract`
// group of tests/cross_language_consistency.json must hold in this wrapper. The same file is read by the Python, JavaScript
// and Rust suites. A Go string cannot be nil and has no non-string form, so the group's invalid_input vectors do not apply
// here; the test asserts the group says so.

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

type lcLookup struct {
	Method       string `json:"method"`
	Code         string `json:"code"`
	ExpectedName string `json:"expected_name"`
}

type lcCase struct {
	ID                  string          `json:"id"`
	Registry            json.RawMessage `json:"registry"`
	Lookups             []lcLookup      `json:"lookups"`
	ExpectedActiveCount *int            `json:"expected_active_count"`
}

type lcGroup struct {
	VectorCount       int      `json:"vector_count"`
	InvalidInputCount int      `json:"invalid_input_count"`
	Precedence        []lcCase `json:"precedence"`
	Duplicates        []lcCase `json:"duplicates"`
	InvalidInput      struct {
		AppliesTo []string `json:"applies_to"`
	} `json:"invalid_input"`
}

func TestLookupContract(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "tests", "cross_language_consistency.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		LookupContract *lcGroup `json:"lookup_contract"`
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	lc := fixture.LookupContract
	if lc == nil {
		t.Fatal("tests/cross_language_consistency.json has no lookup_contract group")
	}
	for _, lang := range lc.InvalidInput.AppliesTo {
		if lang == "go" {
			t.Fatal("invalid_input cannot apply to Go: a string argument is never nil or a non-string")
		}
	}

	vectors := 0
	for _, c := range append(append([]lcCase{}, lc.Precedence...), lc.Duplicates...) {
		r, err := loadRegistryFrom([]byte(c.Registry))
		if err != nil {
			t.Fatalf("%s: registry did not load: %v", c.ID, err)
		}
		for _, lk := range c.Lookups {
			vectors++
			var found *Currency
			switch lk.Method {
			case "currency":
				found = r.Currency(lk.Code)
			case "active":
				found = r.Active(lk.Code)
			case "withdrawn":
				found = r.Withdrawn(lk.Code)
			case "non_iso":
				found = r.NonISO(lk.Code)
			default:
				t.Fatalf("%s: unknown method %q", c.ID, lk.Method)
			}
			if found == nil || found.Name != lk.ExpectedName {
				got := "<nil>"
				if found != nil {
					got = found.Name
				}
				t.Errorf("%s: %s(%s) expected %q, got %q", c.ID, lk.Method, lk.Code, lk.ExpectedName, got)
			}
		}
		if c.ExpectedActiveCount != nil {
			vectors++
			if n := len(r.AllActive()); n != *c.ExpectedActiveCount {
				t.Errorf("%s: AllActive() has %d entries, expected %d", c.ID, n, *c.ExpectedActiveCount)
			}
		}
	}
	if vectors != lc.VectorCount {
		t.Errorf("the fixture declares vector_count=%d but this suite ran %d", lc.VectorCount, vectors)
	}
	fmt.Printf("LOOKUP_CONTRACT go vectors=%d\n", vectors)
}
