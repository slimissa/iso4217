# ADR 0013 - Wrapper numeric contract

**Status:** Proposed. It becomes Accepted when the contract tests pass on all four wrappers and the owner commits it.
**Date:** 2026-10-27
**Context:** v1.9.3 - closing P5-04. Spine sentence: "The four wrappers produce identical numbers for every input."

## Context

The brief for v1.9.3 listed the rounding mode as one of five disagreements. The audit's own finding (`docs/audits/fifth-pass.md`,
P5-04) says something narrower: `to_minor` rounds ties identically in all four wrappers and `format` does not. Measured on
the v1.9.2 tree (Python 3.12, Node 22, Go 1.27 linux/amd64, Rust 1.99), the audit is right and the brief's framing is not:
**the rounding mode is not changing**:

- **`to_minor` already agrees on every rounding vector in the fixture.** All four round half away from zero. The
  Python docstring, the JS and Rust code comments and `tests/cross_language_consistency.json` say so, and the fixture's
  `100.005 -> 10001` vector is the regression test for issue #5 (Python's banker's rounding gave 10000). USD 0.005,
  0.015, 0.025, 0.125, 1.005, -0.005 and -0.125 give 1, 2, 3, 13, 100, -1, -13 in all four.
- **The divergences are in `format`, in overflow, in non-finite input, and in one rounding edge.** Each is listed below
  with what each wrapper does today.

### 1. `format` disagrees with `to_minor`, and with itself across wrappers

Python, Go and Rust format USD from the exact binary value of the double (ties to even on an exact tie). JavaScript
formats through ICU, which rounds half away from zero on the shortest decimal representation.

| Call | Python | JavaScript | Go | Rust | `to_minor` (all four) |
|---|---|---|---|---|---|
| `format(0.125, USD)` | `$0.12` | `$0.13` | `$0.12` | `$0.12` | 13 |
| `format(0.015, USD)` | `$0.01` | `$0.02` | `$0.01` | `$0.01` | 2 |
| `format(1.005, USD)` | `$1.00` | `$1.01` | `$1.00` | `$1.00` | 100 |

So `format` disagrees with `to_minor` inside Python, Go and Rust on ties, and inside JavaScript on 1.005.

### 2. JPY (0 minor units) formats by three different rules

| Call | Python | JavaScript | Go | Rust |
|---|---|---|---|---|
| `format(-2.5, JPY)` | `¥-2` | `¥-2` | `¥-3` | `¥-3` |
| `format(2.5, JPY)` | `¥2` | `¥3` | `¥3` | `¥3` |
| `format(2.9, JPY)` | `¥2` | `¥3` | `¥3` | `¥3` |
| `format(-0.5, JPY)` | `¥0` | `¥0` | `¥-1` | `¥-1` |

Python truncates (`int(x)`), so `format(2.9, JPY)` is `¥2`: a wrong amount under any rounding mode. JavaScript uses
`Math.round`, which rounds ties toward +infinity. `-2` for -2.5 looks like banker's rounding in both and is not. The
brief said JavaScript gives `-3`; it gives `-2`.

### 3. Overflow

`to_minor(1e17, USD)` (the product is 1e19, above int64):

| Python | JavaScript | Go | Rust |
|---|---|---|---|
| 10000000000000000000 (no error) | 1e19 (a Number, no error) | `-9223372036854775808` (amd64) | `9223372036854775807` (saturates) |

Python does not raise, contrary to the brief. Go's wrong-signed `INT64_MIN` comes from `int64(float64)` on an
out-of-range value, which the Go spec leaves implementation-defined; arm64 saturates instead of wrapping.

### 4. Non-finite input

| Call | Python | JavaScript | Go | Rust |
|---|---|---|---|---|
| `format(NaN, USD)` | `$nan` | `$NaN` | `$NaN` | `$NaN` |
| `format(+inf, USD)` | `$inf` | `$∞` | `$+,Inf` (malformed) | `$inf` |
| `format(-inf, USD)` | `$-inf` | `$-∞` | `$-Inf` | `$-inf` |
| `format(NaN, JPY)` | raises `ValueError` | `¥NaN` | `¥-9223372036854775808` | `¥0` |
| `format(+inf, JPY)` | raises `OverflowError` | `¥Infinity` | `¥-9223372036854775808` | `¥9223372036854775807` |

`to_minor(NaN)` and `to_minor(inf)` raise in Python and JS and panic in Go and Rust.

### 5. A rounding edge that is not in the brief

Python and JS round with `floor(x + 0.5)`; Go and Rust use an exact round. In doubles `0.49999999999999994 + 0.5` is
`1.0` (the exact sum is a tie between 1 - 2^-53 and 1, and ties-to-even picks 1), so:

- `to_minor(0.49999999999999994, JPY)` is 1 in Python and JS, 0 in Go and Rust.
- `to_minor(0.004999999999999999, USD)` reaches the same case (its product is 0.49999999999999994): Python and JS give 1
  (and format `$0.00`, disagreeing with themselves). Go and Rust are expected to give 0 [Likely]; that USD input was not
  run in Go or Rust.
- Above 2^52 the addition itself loses the half: `to_minor(4503599627370497.0, JPY)` is `4503599627370498` in Python and
  JS and `4503599627370497` in Rust (Go not run, [Likely] as Rust). An exact integer input comes back off by one.

### 6. Eighteen-decimal assets exist in the registry

ETH, BNB, DAI, USDP, FRAX and TUSD have 18 minor units and are reachable through `non_iso()` and `currency()`. Today
`to_minor(1.0, ETH)` is `1000000000000000000` in all four. `to_minor(10.0, ETH)` is 10^19 in Python and JS, `INT64_MIN` in
Go and `i64::MAX` in Rust. `format(10.0, ETH)` is `Ξ10.000000000000000000` in all four. Any overflow rule has to leave
these working, so the bound cannot be 2^53 (one ETH is 1e18 minor units).

### 7. Zero sign is consistent today

All four print `$-0.00` for USD -0.004, -1e-7 and -0.0, and `¥0` for JPY -0.4 and -0.0.

## Decision

**D1. Rounding mode: half away from zero, unchanged.** Because the contract is already half away from zero in all four
`to_minor` implementations, documented in the code, and pinned by the issue #5 regression vector. Half-even was
considered and rejected (below). Nothing about `to_minor` results on in-range, non-edge inputs changes.

**D2. Float semantics: one IEEE-double operation, then an exact round.** For a finite float `x` and a currency with `n`
minor units, `p = x * 10^n` is computed once as a double, with `10^n` taken from an exact table (n <= 22; the registry
maximum is 18). `r = round_half_away(p)` is computed exactly: `t = trunc(p)`, `r = t + sign(p)` when `|p - t| >= 0.5`,
else `t`. `p - t` is exact for doubles, so there is no `floor(x + 0.5)`. This fixes section 5 in Python and JS and keeps
every vector that passes today. The known limitation stays and is documented: `1.005 * 100` is `100.49999999999999`, so
`to_minor(1.005, USD)` is 100, not 101. Python `int` input is exact (`x * 10^n`); Python `Decimal` input is exact half
away from zero (already the case); any other numeric type is converted with `float()`.

**D3. Overflow: an error when `|r| >= 2^63` or when `p` is not finite for a finite `x`, for float and int input.** Because int64 is the widest
integer Go and Rust return, the rounded value is itself a double that Python and JavaScript hold exactly, and the 18-decimal
assets need the whole range. The bound is symmetric, so `INT64_MIN` is never a valid result. The error text contains
"amount too large". JavaScript's `toMinor` also normalizes `-0` to `0`. Python `Decimal` input is **exempt**: it has no
counterpart in the other three wrappers, v1.9.0 (F28) made it exact and unbounded on purpose, and the CLI's `minor`
command depends on that (a 100-digit amount converts exactly). The cross-language claim covers the inputs all four
wrappers accept, which are floats (and integers, which are floats in JavaScript).

**D4. Error shape: checked variants, additive.** Python raises `OverflowError` (overflow) and keeps `ValueError`
(non-finite). JavaScript throws `RangeError` (overflow) and keeps `Error` (non-finite). Go gains
`ToMinorChecked(x) (int64, error)` with exported `ErrNonFinite` and `ErrOverflow`; Rust gains
`try_to_minor(x) -> Result<i64, MinorError>`. The existing Go `ToMinor` and Rust `to_minor` keep their signatures and
panic on both errors, as they already do for NaN. `format` never calls the panicking variants.

**D5. `format` is derived from the same rounded value as `to_minor`, and prints it exactly.**

```
format(x, ccy):
  n = ccy.minor_units
  if x is NaN:               symbol + "nan"                      (never signed)
  if x is +-inf, or p is +-inf:  symbol + ("-" if x < 0) + "inf"
  r = round_half_away(x * 10^n)           # finite, integer-valued double
  digits = exact decimal digits of |r|, left-padded to n+1 digits
  body   = n > 0 ? comma-grouped(digits[:-n]) + "." + digits[-n:]  :  digits      # n == 0: no grouping, as today
  symbol + sign + body
```

Sign is written after the symbol, as today (`$-5.00`). Because `format` takes its digits from `r` and never narrows to
int64, `format` and `to_minor` cannot disagree on the rounded value, and `format(10.0, ETH)` keeps working. Non-finite
values use the lowercase spelling `nan`, `inf`, `-inf`, which Python and Rust already print for USD.

**D6. Zero sign: preserved as it is today, with an explicit rule.** `negative = (signbit(x) and (n > 0 or r != 0)) or
(n == 0 and r < 0)`. `signbit` is true for -0.0. So `format(-0.004, USD)` is `$-0.00`, `format(-0.4, JPY)` is `¥0` and
`format(-2.5, JPY)` is `¥-3`. This is a legacy rule and is not endorsed; see "Verification still owed".

## Alternatives rejected

- **D1, half-even** (the brief's recommendation). IEEE-754's default tie rule governs binary arithmetic and is not a
  financial standard. Reversing it changes `to_minor` in every wrapper, contradicts the issue #5 regression and the
  documented contract, and is a numeric break. [Likely] Council Regulation (EC) 1103/97 Art. 5 requires an exact half to
  round up for euro conversions (cited from memory, not read this session).
- **D2, decimal-string arithmetic on the shortest representation.** It makes `to_minor(1.005, USD)` 101 in all four,
  which is arguably what a human meant, but flips a result every consumer has today. Rejected for v1.9.3; it is the
  natural basis for a future `Decimal`-input API.
- **D3, a 2^53 - 1 bound.** One ETH is 1e18 minor units, so it would turn working calls on six shipped assets into errors.
  An int64-only rule for `format`, which was also considered, would break `format(10.0, ETH)`.
- **D3, bounding Python `Decimal` too.** It would break the exact-Decimal feature of v1.9.0 and the CLI's `minor` command
  for no cross-language gain, since no other wrapper takes a Decimal.
- **D3, unbounded Python and JS.** Honest for those two, but it leaves "identical numbers" false: Go and Rust cannot return
  these values.
- **D4, changing `ToMinor` and `to_minor` to return errors.** A signature change that breaks every Go and Rust caller; the
  additive variant gives the same recoverability.
- **D5, a `$overflow` token.** There is no case left for it: a finite `x` whose product is infinite is spelled `inf`.
- **D5, `format` calling `to_minor`.** It would make `format` fail wherever `to_minor` errors, including 10 ETH.
- **D6, dropping the minus when `r == 0`.** The right display but a visible change in all four wrappers, deferred.

## Consequences

Changes a consumer can see (the CHANGELOG consumer line says them in user terms):

- **Python:** `format` for 0-decimal currencies rounds (was truncation); `format` ties agree with `to_minor`;
  `format(Decimal)` uses half away from zero (was half-even); `to_minor` of a float or an int raises `OverflowError`
  above int64 where it returned a correct big integer (a `Decimal` is unaffected); `to_minor(inf product)` raises `OverflowError` from the library, not from `math.floor`.
- **JavaScript:** `format` no longer uses `Intl`/`toLocaleString`; JPY ties follow half away from zero; `$∞` becomes
  `$inf`; `toMinor` throws `RangeError` above int64 where it returned an imprecise Number; `-0` becomes `0`.
- **Go:** `ToMinor` panics with "amount too large" instead of returning `INT64_MIN`; `Format(+Inf)` is `$inf`; ties
  follow D5. New: `ToMinorChecked`, `ErrNonFinite`, `ErrOverflow`.
- **Rust:** `to_minor` panics instead of saturating; ties follow D5. New: `try_to_minor`, `MinorError`.
- **All four:** `format` digits for large or high-precision amounts are the exact digits of the rounded double, identical
  across wrappers. For 1.15 ETH that is `Ξ1.149999999999999872`. Python, Go and Rust printed `...911` and JavaScript
  `...000` before; neither was the amount typed. This is the float limitation made visible, not fixed.
- Python and JavaScript consumers of 18-decimal assets lose `to_minor` results above about 9.22 units. A bignum API is
  planned, not part of v1.9.3.
- The CLI's exact conversion (`iso4217 minor 1.005 USD` is 101) and the float API (`to_minor(1.005)` is 100) still differ, as
  the audit noted. D2 keeps that, and a Decimal-string input in every wrapper is the way to close it.
- Every wrapper's `to_minor` and `format` are now tested against one fixture group, `numeric_contract`, in every
  wrapper's own suite.
- Unchanged: `from_minor`, lookups, the rounding mode, every existing fixture vector.

Versioning: the Go and Rust additions are minor for those wrappers. The numeric changes above are behavior changes that
a consumer can observe; whether that is a patch or a minor for the registry release is the owner's call and is not
decided here.

## Verification still owed

- **[Guess]** Council Regulation 1103/97 Art. 5 as the source for half-up on exact halves. Not read this session.
- **No thousands separator for 0-decimal currencies:** all four wrappers print `¥1234567` today, while 2-decimal currencies
  group (`$1,234.56`). D5 preserves that; it looks like an inconsistency, not a design, and should be decided on its own.
- **Zero sign (v1.9.4):** `$-0.00` for a negative amount that rounds to zero is the existing behavior in all four and is
  preserved by D6, not endorsed. D6 should be revisited with its own decision.
- **Decimal-string input and a bignum API (v1.9.4+):** 18-decimal assets are IEEE doubles here, so amounts above about
  9.22 units cannot be converted, and trailing digits reflect the double, not the typed decimal.
- **Go on arm64 not run.** The new code does not convert an out-of-range float to `int64`, so the amd64/arm64 difference
  cannot be reached, but it was not executed on arm64.
- **Scale table:** `10^n` is exact in a double for n <= 22; the registry maximum is 18. A test pins that tripwire.
