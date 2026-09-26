# ADR 0005 — Split note into source_url and note

**Status:** Accepted
**Date:** 2026-09-26
**Context:** v1.6.0 — separating provenance from commentary

## Context

The `note` field currently does two jobs:

1. Records the URL of the entry's primary source.
2. Adds free-text context a reader needs to interpret the entry.

A consumer who wants the source URL has to parse English prose. A
consumer who wants the commentary has to strip the URL. Neither task is
what a well-structured field is for.

The registry has 302 entries — 167 active, 135 withdrawn. Every one
has some form of `note`. Some are just a URL. Some are just prose. Some
are both.

## Decision

Introduce `source_url` as a scalar string field. Every active and
withdrawn entry carries it. Rule:

- If `note` begins with `source: <url>` (or similar), the URL moves to
  `source_url`, and the remaining text stays in `note`.
- If `note` contains a URL elsewhere, that URL moves to `source_url`,
  and the remaining text stays in `note`.
- If `note` has no URL, `source_url` is set to the ISO OBP page for
  the currency.
- If `note` is empty, `source_url` is set, and `note` becomes null.

After this change, `note` never contains a URL. The validator enforces
this.

## Consequences

- A consumer reads the source URL as a URL. No prose parsing.
- A consumer reads the note as commentary. No stripping.
- `source_url` is a scalar, not a list, because every entry has exactly
  one primary source. Secondary sources belong in `docs/PROVENANCE.md`,
  not on the entry.
- The SQL and CSV exports do not carry `source_url` — they are for
  joining, not for provenance.

## Alternatives considered

**Option A — `sources[]` array.** Rejected. Every current entry has one
primary source. An array for a single value is over-structured, and it
would immediately raise the question "which one is primary?"

**Option B — Structured `provenance` object.** Rejected. Overkill for
one field. The complexity budget belongs in `docs/PROVENANCE.md`, not
in a per-entry object.

**Option C — Keep note as-is and add `source_url` without moving
anything.** Rejected. The two jobs would still overlap and the note
would still contain a URL.

## References

- `docs/PROVENANCE.md` — per-category sourcing
- ADR 0004 — the other `v1.6.0` schema change