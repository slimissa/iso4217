# ADR 0015 - Wrapper lookup contract

**Status:** Proposed. It becomes Accepted when the lookup vectors pass on all four wrappers, every mutant is killed, and the owner commits it.
**Date:** 2026-10-29
**Context:** v1.9.5 - closing P5-09 of the third audit pass. Spine sentence: "The audit's documents are held to the same standard as its code."

## Context

P5-09 says the `currency()` docstring contradicts the code, `currency(None)` fails with an accidental exception, and duplicate
codes silently shrink `all_active`. It was Confirmed in Python and JavaScript and Likely in Go and Rust. Measured on the v1.9.4
tree (Python 3.12, Node 22, Go 1.27.3, Rust 1.99.1, linux/amd64), by loading three small registries through each wrapper's own
loader:

| Behavior | Python | JavaScript | Go | Rust |
|---|---|---|---|---|
| `currency("AAA")` when `AAA` is both active and non-ISO | the non-ISO entry | the non-ISO entry | the non-ISO entry | the non-ISO entry |
| `currency("DDD")` when `DDD` is both withdrawn and non-ISO | the non-ISO entry | the non-ISO entry | the non-ISO entry | the non-ISO entry |
| a code listed twice in `currencies.active` | loads; `all_active()` has one entry for it; the last one wins | same | same | same |
| `currency(None)` / `currency(null)` | `AttributeError` | `TypeError` | cannot occur (a `string`) | cannot occur (a `&str`) |
| `currency(123)` | `AttributeError` | `TypeError` | cannot occur | cannot occur |

[Confirmed] in all four by running real code, not by reading. The documented order ("active, then withdrawn, then non-ISO") is
in the docstring or comment of `currency()` in all four wrappers and in the wrapper READMEs. The code builds the index in that
order and lets each later section overwrite the earlier one, so the *last* section wins, which is the opposite of the words.

Two facts shape the decisions. `docs/WRAPPER_VALIDATION.md` already says "Duplicate codes within a registry are not checked by
the wrappers; the last one wins, as before", so duplicates are a documented decision, not a contradiction. And `validate.py`
rejects overlaps (`DUPLICATE_*`, `NON_ISO_OVERLAPS_ISO`), so no shipped data reaches any of this; the contract is about
behavior, not data.

## Decisions

### D1. Precedence: the documented order is the contract

**Decision:** `currency(code)` resolves in the order active, withdrawn, non-ISO, and **the earliest section wins**. The code is
changed to match the words, in all four wrappers: build each section's index first, then build the any-code index from the
non-ISO section, then the withdrawn, then the active, so a later `update` is the earlier-in-the-documented-order entry.
`active()`, `withdrawn()` and `non_iso()` do not change.
**Reason:** a consumer reads the docstring. The change is observable only on a registry that `validate.py` already rejects.
**Rejected:** changing the docs to say "last wins" (documents an accident, and puts the least authoritative section, the
non-ISO list, first); rejecting overlaps at load (D3).

### D2. A non-string code is a `TypeError` in Python and JavaScript

**Decision:** every method that takes a currency code (`currency`, `active`, `withdrawn`, `non_iso`, and the membership test:
`code in registry` in Python, `has()` in JavaScript) raises **`TypeError`** with the message
`<name> must be a string, got <type>` for any argument that is not a string, **including `None` / `null` / `undefined`**.
A string that is not a code (empty, unknown) still returns `None` / `null`, as today.
**Reason:** one named exception in both languages (Python's was `AttributeError`, JavaScript's was an incidental `TypeError`
from `.toUpperCase`), and a loud failure rather than a forgiving `None` that would hide a missing field upstream. It matches
ADR 0013's rule: one defined behavior.
**Go and Rust:** unchanged and documented as not applicable: the argument type cannot be null or a non-string.
**Rejected:** `None` for `None` input (silent; turns a crash into a wrong answer); `ValueError` (the value is not the
problem, the type is).

### D3. Duplicates stay tolerated and become specified

**Decision:** the wrappers do not reject duplicate codes (`docs/WRAPPER_VALIDATION.md` stands). The behavior is now written down
and tested: within one section the last entry for a code wins, and every collection accessor returns one entry per code.
Across sections, D1 applies.
**Reason:** the wrapper contract checks shape, not completeness; completeness is `validate.py`'s job. Rejecting duplicates at
load would make four wrappers re-implement the validator and would break any custom registry that loaded before.
**Rejected:** rejecting duplicates at load.

### D4. The vectors, and how they are held

**Decision:** one new fixture group, `lookup_contract`, in `tests/cross_language_consistency.json`, read by all four wrappers'
own suites and by one Python test that also runs the Python wrapper and the JavaScript suite directly (the v1.9.3 pattern). It
has three sub-groups: `precedence` (registries with overlaps and the entry each lookup must return), `duplicates` (the
registry with a repeated code, the expected count and the expected survivor) and `invalid_input` (the values that must raise
`TypeError`, marked `applies_to: ["python", "javascript"]`). Each wrapper reads the group by name and fails if a sub-group is
missing, so deleting a vector is itself a failure.

## Consequences

- **Behavior change, one line for consumers:** a code that exists in two sections of a hand-edited registry now resolves to the
  section the documentation names. `AttributeError` from `currency(None)` in Python becomes `TypeError`.
- **A new finding, not fixed here:** the same accidental `AttributeError` (Python) and `TypeError` from `.toUpperCase` (JavaScript)
  occur for `by_country(None)` and the registry's `pegged_to(None)`, which take a country code and an anchor code, not a
  currency code. [Confirmed by running `by_country(None)` and `pegged_to(None)` on the Python wrapper; JavaScript by reading.]
  They are outside the five lookups P5-09 names and go on the fourth-audit input list.
- **A second new finding, not fixed here:** Rust's collection accessors (`all_active()` and its siblings) return `HashMap` iteration
  order, which is not stable; Python, JavaScript and Go return file order. The cross-language fixture compares sets, so nothing
  fails today. [Confirmed by reading `rust/src/lib.rs`.] It goes on the fourth-audit input list.
- The wrapper READMEs and docstrings state the contract in the same words.

## Amendment 1 (v1.9.6): collection order

**Status:** Proposed, like the ADR it amends; accepted with it.

**Decision:** every collection accessor returns its entries in **file order** in all four languages: the order of the entries in
`iso4217.json`, section by section, one entry per code. `all_currencies()` is active, then withdrawn, then non-ISO
(cryptocurrencies, stablecoins, commodities, special purpose, in that order). A code listed more than once keeps the position of
its first entry and holds the entry D3 and D1 name (the last within a section, the earliest section across sections). Every
filter (`pegged_to`, `independent`, `with_minor_units`, `issued_by`, `used_in`, `by_classification`, Rust's `iter()`) keeps the
order of `all_active()`. Lookup by code stays O(1): Rust and Go keep their maps and walk an order index beside them.

**Correction to the Consequences above:** "Python, JavaScript and Go return file order" was wrong for Go. Its accessors ranged
over Go maps, whose iteration order is randomised on every call. [Confirmed by running v1.9.5: three calls of `AllActive()`
returned three different orders.] v1.9.6 fixed Go together with Rust.

**How it is held:** the `collection_order` group of `tests/cross_language_consistency.json` (the full ordered code lists for the
shipped registry and a synthetic registry with repeated and overlapping codes), read by `tests/test_wrapper_collection_order.py`,
`wrappers/javascript/collection_order.test.js`, `wrappers/go/collection_order_test.go` and the `collection_order_fixture` module
of `wrappers/rust/src/lib.rs`; mutants W01 to W12 of `tests/test_v196_mutations.py`.

## Verification owed

- Run `tools/check_cross_language.sh` on the maintainer's machine (Go 1.27.3, Rust 1.99.1, Node 22 were used here).
- Four mutants per behavior (one per wrapper) put the v1.9.4 behavior back; all must be killed.
