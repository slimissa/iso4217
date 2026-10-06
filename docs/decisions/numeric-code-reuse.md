# ADR 0008 — Numeric code reuse is expected

**Status:** Accepted
**Date:** 2026-09-27
**Context:** v1.6.2 — documenting the 26 warnings that fire on every validation

## Context

`tools/validate.py` emits 26 warnings on every run. Each names a
numeric code shared by two or more entries:

- 25 `REVALUATION_CHAIN_NUMERIC_REUSE` warnings — one per chain
  where two or more withdrawn currencies share a numeric code
  (Brazil's BRB/BRC/BRN/BRE share 076; Yugoslavia's
  YUD/YUG/YUN/YUO/YUR share 890; Mexico's MXN_OLD/MXP share 484;
  twenty-two others).
- 1 `NUMERIC_CODE_REUSE` warning — the active/withdrawn counterpart
  (MXN shares 484 with MXN_OLD and MXP; eighteen other pairs follow
  the same pattern).

A maintainer seeing 26 warnings on every validation has a reasonable
question: are these bugs? The answer is no. ISO 4217 reassigns
numeric codes on currency revaluation, and the registry records
both sides of each reassignment.

## Decision

The 26 warnings are permanent, expected, and correct. They fire on
every validation. They are not to be silenced, suppressed, or
reclassified as info-level.

The `numeric_reused` field on every active entry (added in v1.6.0)
records the same fact queryably. The warning is the validator's way
of surfacing it on every run; the field is the registry's way of
exposing it for downstream consumption.

## Consequences

- The validator's exit code is 0 with 26 warnings. That is the
  steady state.
- A PR that changes the warning count requires review: a
  revaluation chain added or removed is a data change, and the
  corresponding warning changes with it.
- Consumers who use numeric codes as foreign keys should filter on
  `numeric_reused = false` in the Parquet export. The warning is
  for maintainers; the field is for consumers.

## Alternatives considered

**Option A — Silence the warnings.** Rejected. The warning is the
only signal that a numeric code reuse exists. Silencing it would
hide the fact from maintainers who have not read this ADR.

**Option B — Downgrade to info level.** Rejected. Python's
`logging` has levels; this validator does not. Every non-error
issue is a warning. Adding levels would be a larger change than
the problem warrants.

**Option C — Fold the warnings into a single summary line.**
Rejected. Each revaluation chain is a distinct historical event
with a specific set of affected codes. A summary line loses that.

## References

- `iso4217.json` — the entries that trigger each warning
- ADR 0004 — `numeric_reused` field rationale
- `tools/validate.py` — `REVALUATION_CHAIN_NUMERIC_REUSE` and
  `NUMERIC_CODE_REUSE` check functions
- `tests/test_iso_codes.py` — the ground-truth tests that verify
  each chain is correct