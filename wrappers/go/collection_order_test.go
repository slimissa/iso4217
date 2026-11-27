package iso4217

// Collection order (v1.9.6, ADR 0015): every list in the `collection_order` group of tests/cross_language_consistency.json
// must be returned by this wrapper in exactly that order. The same group is read by the Python, JavaScript and Rust suites,
// so the four outputs are identical.

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

type coCase struct {
	ID          string              `json:"id"`
	Registry    json.RawMessage     `json:"registry"`
	Collections map[string][]string `json:"collections"`
	PeggedTo    map[string][]string `json:"pegged_to"`
}

type coGroup struct {
	VectorCount int      `json:"vector_count"`
	Shipped     *coCase  `json:"shipped"`
	Synthetic   []coCase `json:"synthetic"`
}

func TestCollectionOrderFixture(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "tests", "cross_language_consistency.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		CollectionOrder *coGroup `json:"collection_order"`
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	co := fixture.CollectionOrder
	if co == nil || co.Shipped == nil || len(co.Synthetic) == 0 {
		t.Fatal("tests/cross_language_consistency.json has no collection_order group with shipped and synthetic cases")
	}

	shipped := *co.Shipped
	shipped.ID = "shipped"
	vectors := 0
	for _, c := range append([]coCase{shipped}, co.Synthetic...) {
		var r *CurrencyRegistry
		if string(c.Registry) == `"shipped"` {
			r, err = Load()
		} else {
			r, err = loadRegistryFrom([]byte(c.Registry))
		}
		if err != nil {
			t.Fatalf("%s: registry did not load: %v", c.ID, err)
		}
		for method, want := range c.Collections {
			vectors++
			var list []*Currency
			switch method {
			case "all_active":
				list = r.AllActive()
			case "all_withdrawn":
				list = r.AllWithdrawn()
			case "all_non_iso":
				list = r.AllNonISO()
			case "all_currencies":
				list = r.AllCurrencies()
			default:
				t.Fatalf("%s: unknown collection %q", c.ID, method)
			}
			if got := codesOf(list); !reflect.DeepEqual(got, want) {
				t.Errorf("%s: %s\n got  %v\n want %v", c.ID, method, got, want)
			}
		}
		for anchor, want := range c.PeggedTo {
			vectors++
			if got := codesOf(r.PeggedTo(anchor)); !reflect.DeepEqual(got, want) {
				t.Errorf("%s: pegged_to(%s)\n got  %v\n want %v", c.ID, anchor, got, want)
			}
		}
	}
	if vectors != co.VectorCount {
		t.Errorf("the fixture declares vector_count=%d but this suite ran %d", co.VectorCount, vectors)
	}
	fmt.Printf("COLLECTION_ORDER go vectors=%d\n", vectors)
}

// codesOf returns the codes in order; an empty result is an empty slice, never nil, so it compares equal to the
// fixture's [].
func codesOf(list []*Currency) []string {
	out := []string{}
	for _, c := range list {
		out = append(out, c.Code)
	}
	return out
}
