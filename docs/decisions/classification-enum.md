# ADR 0003 — Classification enum for active currencies

**Status:** Accepted
**Date:** 2026-09-26
**Context:** v1.6.0 — separating circulating currencies from fund and indexation units

## Context

Since v1.2.0, the registry has carried 167 active ISO 4217 codes. Ten of
them are not circulating currencies:

- **Fund codes** (BOV, CHE, CHW, CLF, COU, MXV, USN, UYI, UYW): units
  of account, indexation bases, or complementary currencies defined by
  a monetary authority but not used as primary legal tender.
- **Indexation units** (VED): a recently-introduced rebase of the
  Venezuelan bolívar, denominated in a separate unit.

Today, the only way to know that a code is not a circulating currency
is to read the entry's `note` field. That is prose, not a queryable
fact. Consumers who want "every circulating currency" must either
maintain their own exclusion list or parse English notes.

## Decision

Add a `classification` field to every active entry. Four values:

| Value | Meaning | Example |
|-------|---------|---------|
| `circulating` | Primary legal tender. Default. | USD, EUR, JPY |
| `fund` | Fund, unit of account, or complementary currency | CLF, USN, CHE |
| `settlement` | Settlement unit — a companion to a circulating currency | reserved |
| `indexation` | Indexation unit | VED |

The field is required on every active entry, absent on withdrawn entries.
Non-ISO entries do not carry it — they have a `type` field already.

The ten fund and indexation codes are:

    BOV, CHE, CHW, CLF, COU, MXV, USN, UYI, UYW  →  fund
    VED                                          →  indexation

All other 157 active currencies are `circulating`.

## Consequences

- A consumer can filter `by_classification("circulating")` in one
  query, without parsing notes.
- The SQL and CSV exports remain seven- and eleven-column because they
  exclude this field. It lives in JSON and Parquet only — the exports
  are for joining, not for classification.
- The Parquet export gains the field. A consumer can write
  `WHERE classification = 'circulating'` against the Parquet file and
  get the expected result.

## Alternatives considered

**Option A — Reuse the existing `note` field.** Rejected. Notes are
prose and vary in wording. A consumer cannot filter on them.

**Option B — Boolean `is_circulating`.** Rejected. It loses the
distinction between fund, settlement, and indexation — three categories
that matter differently to different consumers.

**Option C — More granular enum (`fund`, `bond_unit`, `wage_index`,
`complementary`).** Rejected for v1.6.0. The ten codes fall cleanly
into two buckets. A finer taxonomy adds vocabulary without adding
information. Revisit if future fund codes need finer discrimination.

## References

- `docs/decisions/v1.6.0-candidates.md` — the deferred-items list
- `iso4217.json` — the ten fund and indexation codes
- `docs/PROVENANCE.md` — per-field sourcing