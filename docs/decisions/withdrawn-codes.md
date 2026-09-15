# ADR 0001 — Withdrawn currency codes and synthetic identifiers

**Status:** Accepted
**Date:** 2026-09-15
**Context:** v1.5.1 review — withdrawn code convention investigation

## Context

ISO 4217 assigns three-letter alphabetic codes to currencies. When a
currency is withdrawn, its code is retired and never reassigned. In
principle, every withdrawn currency has a unique, permanent, three-letter
identifier.

In practice, a small number of countries revalued their currency in a way
that leaves more than one entry competing for the same code stem. Mexico
is the canonical example:

- `MXN` — the current Mexican peso, in circulation since 1993.
- `MXP` — the withdrawn pre-1993 peso, numeric 484.
- `MXN_OLD` — a synthetic identifier for the same pre-1993 peso,
  distinguished by suffix.

`MXN_OLD` is 7 characters. It is not a valid ISO 4217 code. Consumers who
assumed `code` is always 3 characters — including several SQL schemas that
declared `CHAR(3)` — were surprised by it.

The registry needs an explicit rule, not an implicit convention buried in
a code comment.

## Decision

Withdrawn currency entries fall into two categories:

1. **ISO-assigned withdrawn codes.** Three letters, no suffix, no
   synthetic component. Example: `DEM`, `FRF`, `MXP`.

2. **Synthetic identifiers.** Used only when a withdrawn entry must be
   disambiguated from another entry with the same three-letter stem, and
   no distinct ISO-assigned code exists for the withdrawn version.
   Format: `<STEM>_<OLD>` where `<STEM>` is the 3-letter alphabetic stem.

The only synthetic identifier in v1.5.1 is `MXN_OLD`. Future entries may
add more, and each must carry a `note` field explaining the disambiguation.

**Consumers MUST treat `code` as an opaque string of length 3–7.** SQL
columns must be `VARCHAR(7)` (or equivalent), not `CHAR(3)`. Foreign-key
references to `currencies.code` must use the same width.

## Consequences

- The SQL `currencies.code` column is `VARCHAR(7)` in every dialect.
- The CHECK constraint `LENGTH(code) BETWEEN 3 AND 7` is required in all
  four SQL dialects and is already enforced.
- The JSON Schema pattern `^[A-Z][A-Z0-9_]{2,6}$` permits both forms.
- Wrappers expose `code` as a string with no length assumption. No
  wrapper may hardcode `len(code) == 3`.
- Any future synthetic identifier must have a `note` field that names
  the active entry it disambiguates from.

## Alternatives considered

**Option A — Reassign the withdrawn entry to a distinct ISO code.**
Use `MXP` for the pre-1993 peso and remove `MXN_OLD`. Rejected because
`MXP` and `MXN_OLD` are not entirely redundant: `MXP` is the ISO-assigned
code from the historical record, while `MXN_OLD` is the registry's own
disambiguator for consumers that read the numeric code 484 and need a
1:1 mapping from numeric to alphabetic. Removing either loses a real
detail. The right fix — consolidating the two — is a v1.6.0 data change.

**Option B — Drop the `code` field for synthetic entries.**
Store them under a separate `historical_id` key and keep `code` always
3 characters. Rejected because it splits a currency's identity across
two fields, forcing every consumer that iterates the withdrawn array to
switch on which field is populated.

**Option C — Merge the synthetic entry into the active entry.**
Add a `predecessor: "MXN_OLD"` field to `MXN`. Rejected because
withdrawn entries carry withdrawal dates, replacement codes, and
conversion rates that do not belong on an active currency's record.

## Notes

The Mexican situation is the only one in v1.5.1. Future withdrawal
chains — including any introduced by the forthcoming ISO 3166 country
registry — should follow the same rule: prefer the ISO-assigned code,
add a synthetic suffix only when disambiguation is genuinely impossible.

## References

- ISO 4217:2015, Table A.1
- `tools/validate.py` — `_row_from_entry` code-length check
- `tools/export_sql.py` — `_row_from_entry` and `chk_currencies_code_length`
- `schema.json` — `code` pattern `^[A-Z][A-Z0-9_]{2,6}$`
- README, "Coverage" section
