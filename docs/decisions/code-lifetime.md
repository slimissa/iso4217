# ADR 0006 — code_lifetime for withdrawn entries

**Status:** Accepted
**Date:** 2026-09-26
**Context:** v1.6.0 — recording the full lifespan of withdrawn codes

## Context

Every withdrawn entry has a `withdrawn_date`. None has an assignment
date — the date the code was first published in ISO 4217.

For a consumer reconstructing a historical join — "was code XYZ valid
on date D?" — the withdrawn date alone is insufficient. The consumer
must know when the code *started* being valid, and today must consult
the ISO amendment history for that.

## Decision

Add `code_lifetime` to every withdrawn entry. An object:

    { "from": "YYYY-MM-DD" | null, "to": "YYYY-MM-DD" }

- `from` — the assignment date, if documented. `null` otherwise.
- `to` — identical to the existing `withdrawn_date`.

The registry does not have an assignment date for every entry. Some
codes were assigned before ISO began publishing per-amendment dates.
Fabricating a date would be worse than leaving it null. The rule:

> If a primary source documents the assignment date, record it. If no
> primary source exists, `from` is `null`. Do not infer, extrapolate,
> or approximate.

The count of null `from` values is published in `docs/PROVENANCE.md`.
It is a fact about the registry's coverage, not a gap to hide.

## Consequences

- A consumer can reconstruct a code's lifetime, when both ends are
  known.
- When `from` is null, the consumer knows the registry does not know —
  rather than being told a wrong date.
- The SQL and CSV exports do not carry `code_lifetime` — they carry
  `status` and nothing finer.

## Alternatives considered

**Option A — A flat pair of columns (`valid_from`, `valid_to`).**
Rejected. The `{from, to}` object groups the concept and makes the
"both or neither" relationship obvious in the JSON.

**Option B — Approximate `from` values where no source exists.**
Rejected. An approximation that looks like a fact is worse than a null
that looks like a gap. A consumer who needs the exact assignment date
can consult the ISO amendment log; the registry does not pretend to
know what it does not.

**Option C — Derive `from` from ISO amendment numbers.** Rejected.
Amendment numbers are published, but the effective dates vary by
currency within a single amendment. There is no reliable mapping.

## References

- `iso4217.json` — the 135 withdrawn entries
- `docs/PROVENANCE.md` — where assignment dates come from when known
- ADR 0001 — withdrawn code conventions