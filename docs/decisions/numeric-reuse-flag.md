# ADR 0004 — Numeric code reuse flag

**Status:** Accepted
**Date:** 2026-09-26
**Context:** v1.6.0 — making MXN/MXN_OLD-style reuse queryable

## Context

ISO 4217 assigns each currency a numeric code in addition to its
alphabetic code. Revaluations sometimes reuse a numeric code: MXN and
MXN_OLD both carry 484 because Mexico kept the numeric assignment
through the 1993 rebase.

The validator already warns on this (see `tools/validate.py`,
`NUMERIC_CODE_REUSE`). The warning is useful for maintainers but not
queryable by consumers — the fact lives in a validation run, not in the
registry data.

A consumer who uses numeric codes as foreign keys can silently join a
transaction on the wrong row if the numeric code is reused. The failure
is rare but real, and only happens in revaluation cases.

## Decision

Add a `numeric_reused` boolean to every active entry. `true` when the
entry's numeric code also appears on a withdrawn entry. `false`
otherwise.

Every active entry carries the field. No ambiguity about absence.

The current registry has one such entry: MXN (numeric 484, shared with
MXN_OLD and MXP).

## Consequences

- A consumer can filter `WHERE numeric_reused` on the Parquet file and
  see every affected code in one query.
- The `false` value is uniform. No active entry omits the field, so a
  query `WHERE numeric_reused = false` returns every unaffected
  active currency without a null-handling clause.
- The validator's existing warning continues to fire for maintainer
  visibility. The new field complements it.

## Alternatives considered

**Option A — `numeric_reuse[]` array of affected codes.** Rejected.
Every current case has at most two codes on the withdrawn side. An
array implies multiple, which the data does not support.

**Option B — Numeric-only flag, no field.** Rejected. The warning is
not part of the data contract. Consumers cannot read it.

**Option C — Deprecate numeric codes entirely.** Rejected. ISO 4217
still publishes them, and some downstream systems still key on them.

## References

- `tools/validate.py` — `NUMERIC_CODE_REUSE` warning
- `iso4217.json` — MXN entry
- ADR 0001 — withdrawn code conventions