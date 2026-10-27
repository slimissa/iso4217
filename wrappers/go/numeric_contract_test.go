package iso4217

// The wrapper numeric contract (ADR 0013, docs/decisions/wrapper-numeric-contract.md): every vector in the
// `numeric_contract` group of tests/cross_language_consistency.json must hold in this wrapper. The same file is read by
// the Python, JavaScript and Rust suites, so a wrapper that drifts fails its own tests.

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
	"testing"
)

type ncVector struct {
	Currency string          `json:"currency"`
	X        json.RawMessage `json:"x"`
	ToMinor  json.RawMessage `json:"to_minor"`
	Format   *string         `json:"format"`
}

type ncGroup struct {
	ID      string     `json:"id"`
	Vectors []ncVector `json:"vectors"`
}

type ncFile struct {
	NumericContract struct {
		VectorCount int       `json:"vector_count"`
		Groups      []ncGroup `json:"groups"`
	} `json:"numeric_contract"`
}

func ncDecodeX(t *testing.T, raw json.RawMessage) float64 {
	t.Helper()
	s := strings.TrimSpace(string(raw))
	switch s {
	case `"NaN"`:
		return math.NaN()
	case `"Infinity"`:
		return math.Inf(1)
	case `"-Infinity"`:
		return math.Inf(-1)
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		t.Fatalf("cannot decode amount %s: %v", s, err)
	}
	return f
}

// ncDigits reads a formatted amount back to its minor-unit magnitude: symbol, sign, commas and the point removed.
func ncDigits(s string) string {
	var b strings.Builder
	for _, r := range s {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return strings.TrimLeft(b.String(), "0")
}

func TestNumericContract(t *testing.T) {
	data, err := os.ReadFile("../../tests/cross_language_consistency.json")
	if err != nil {
		t.Fatalf("failed to read cross_language_consistency.json: %v", err)
	}
	var f ncFile
	if err := json.Unmarshal(data, &f); err != nil {
		t.Fatalf("failed to parse cross_language_consistency.json: %v", err)
	}
	reg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	count := 0
	for _, g := range f.NumericContract.Groups {
		for _, v := range g.Vectors {
			c := reg.Currency(v.Currency)
			if c == nil {
				c = reg.NonISO(v.Currency)
			}
			if c == nil {
				t.Fatalf("%s: currency %s not found", g.ID, v.Currency)
			}
			x := ncDecodeX(t, v.X)
			label := fmt.Sprintf("%s: %s %s", g.ID, v.Currency, strings.TrimSpace(string(v.X)))
			var wantMinor int64
			minorOK := false
			if v.ToMinor != nil {
				raw := strings.TrimSpace(string(v.ToMinor))
				got, err := c.ToMinorChecked(x)
				if strings.HasPrefix(raw, "{") {
					var e struct {
						Error string `json:"error"`
					}
					if err := json.Unmarshal(v.ToMinor, &e); err != nil {
						t.Fatalf("%s: bad expected %s", label, raw)
					}
					want := map[string]error{"non_finite": ErrNonFinite, "overflow": ErrOverflow}[e.Error]
					if err == nil || !errors.Is(err, want) {
						t.Errorf("%s: ToMinorChecked = (%d, %v), want error %s", label, got, err, e.Error)
					}
					if e.Error == "overflow" && (err == nil || !strings.Contains(err.Error(), "amount too large")) {
						t.Errorf("%s: overflow error must say \"amount too large\", got %v", label, err)
					}
					func() {
						defer func() {
							if recover() == nil {
								t.Errorf("%s: ToMinor must panic on %s", label, e.Error)
							}
						}()
						c.ToMinor(x)
					}()
				} else {
					wantMinor, err = strconv.ParseInt(raw, 10, 64)
					if err != nil {
						t.Fatalf("%s: bad expected %s", label, raw)
					}
					minorOK = true
					gotC, errC := c.ToMinorChecked(x)
					if errC != nil || gotC != wantMinor {
						t.Errorf("%s: ToMinorChecked = (%d, %v), want %d", label, gotC, errC, wantMinor)
					}
					if got := c.ToMinor(x); got != wantMinor {
						t.Errorf("%s: ToMinor = %d, want %d", label, got, wantMinor)
					}
				}
			}
			if v.Format != nil {
				got := c.Format(x)
				if got != *v.Format {
					t.Errorf("%s: Format = %q, want %q", label, got, *v.Format)
				}
				if minorOK {
					abs := wantMinor
					if abs < 0 {
						abs = -abs
					}
					want := strings.TrimLeft(strconv.FormatInt(abs, 10), "0")
					if ncDigits(got) != want {
						t.Errorf("%s: Format %q disagrees with ToMinor %d", label, got, wantMinor)
					}
				}
			}
			count++
		}
	}
	if count != f.NumericContract.VectorCount {
		t.Errorf("checked %d vectors, the fixture declares %d", count, f.NumericContract.VectorCount)
	}
	fmt.Printf("NUMERIC_CONTRACT go vectors=%d\n", count)
}
