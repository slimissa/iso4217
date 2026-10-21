# Wrapper validation contract

Every wrapper (Python, JavaScript, Go, Rust) runs one strict validation pass over the parsed registry JSON before it
builds a single currency. A registry that breaks the contract fails at load, with one documented error type per
language, instead of failing later and differently (a `TypeError` in Python, `NaN` in JavaScript, whatever serde or
`encoding/json` happened to type in Rust and Go).

| Wrapper | Error | How to catch it |
|---|---|---|
| Python | `RegistryDataError`, a subclass of `ValueError` | `except RegistryDataError` |
| JavaScript | `RegistryDataError`, a subclass of `Error` | `catch (e) { if (e instanceof RegistryDataError) ... }` |
| Go | an error wrapping `ErrMalformedRegistry` | `errors.Is(err, iso4217.ErrMalformedRegistry)` |
| Rust | `Err(String)` whose text starts `malformed registry data: ` | `Err(msg) if msg.starts_with("malformed registry data: ")` |

In all four the message is `malformed registry data: <JSON path>: <reason>`, for example
`malformed registry data: $.currencies.active[3].minor_units: expected integer, got string`. A missing file is not a data
error: Python and JavaScript keep `FileNotFoundError` and `Error`; Go and Rust embed the data at compile time.

## The contract

`$` is the root. Unknown fields are ignored. `null` counts as absent for an optional entry field, never for a section.

1. The root is an object.
2. `meta`, `source`, `currencies` and `non_iso` are each absent or an object.
3. `currencies.active`, `currencies.withdrawn` and `non_iso.cryptocurrencies`, `.stablecoins`, `.commodities`,
   `.special_purpose` are each absent or an array, and every element is an object.
4. Every entry has `code` (a non-empty string), `name` (a string) and `minor_units` (an integer from 0 to 36).
5. When present and not null, these entry fields have these types. Strings: `numeric`, `symbol`, `entity`,
   `central_bank`, `pegged_to`, `peg_type`, `pegged_since`, `note`, `withdrawn_date`, `replaced_by`, `type`,
   `peg_mechanism`, `classification`, `source_url`. Numbers: `peg_rate`, `peg_band_pct`, `conversion_rate`. Integer:
   `market_cap_rank`. Booleans: `is_independent`, `numeric_reused`.
6. `countries`, when present, is an array of objects, each with a string `code`; `name` and `relationship` are strings
   when present. `code_lifetime`, when present, is an object with a string `to`; `from` is a string or null.
7. `meta.version`, `meta.updated` and `source.last_amendment_date` are strings, and `source.last_amendment_applied` is an
   integer, when present and not null.

Files that are not valid JSON, not valid UTF-8, or that contain `NaN` or `Infinity` (Python and JavaScript only: Go and
Rust reject them in the parser) are malformed too.

## Known differences

- JavaScript cannot distinguish `2.0` from `2`, so it accepts an integral float for an integer field. Python, Go and Rust
  reject it. No fixture case relies on that.
- A registry with no currencies at all (`{}`) is valid. The contract checks shape, not completeness; completeness is
  `tools/validate.py`'s job.
- Duplicate codes within a registry are not checked by the wrappers; the last one wins, as before.

## Where it is tested

`tests/cross_language_consistency.json`, key `malformed_registry_tests`: registries every wrapper must reject, each
with the JSON path its message must name, and registries every wrapper must accept. Each wrapper's suite reads it, so
`tools/check_cross_language.sh` exercises all four.
