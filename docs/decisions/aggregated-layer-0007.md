# ADR 0007 — Aggregated layer

**Status:** Accepted
**Date:** 2026-10-06
**Context:** v1.7.4 — first AGGREGATED artifacts

## Context

`docs/LAYERS.md` has described three layers since v1.5.2: RAW
(`iso4217.json`), CURATED (flat projections), and AGGREGATED (artifacts that
answer questions). The third layer was empty. Its rule was written before
anything lived in it:

> A layer may only assume what the layer below guarantees. The aggregated
> layer never parses `iso4217.json`. It reads CURATED artifacts.

The natural first artifact, `currencies_by_region.parquet`, is a join of
currency × country × region. It needs a currency→country mapping, and **no
CURATED artifact carries one.** `iso4217.parquet` has eleven columns and none
is `countries[]`; ADR 0002 left them out on purpose. The mapping exists only
in `iso4217.json`, which the aggregated layer must not read. Two shortcuts
were available — read the JSON from the aggregated tool, or stretch the
eleven-column file — and this ADR records why neither was taken.

## Decision

### 1. `iso4217.countries.parquet` is CURATED, not AGGREGATED

The file has one row per (currency, country) pair. Nothing is collapsed and
nothing is computed; it is a flattening of a nested field. By the decision
table in `docs/LAYERS.md`, "a projection of `iso4217.json`" is CURATED, and an
"aggregation of two or more CURATED artifacts" is AGGREGATED. This file is the
former. It is generated from RAW by `tools/export_countries_parquet.py`, has a
`--check` mode, and has its own CI gate (`check-countries-parquet`).

Putting it in AGGREGATED would have forced the aggregated tool to read RAW,
and the layer's only invariant would have been broken in its first artifact.

The file has six columns: `currency_code`, `country_code`, `country_name`,
`relationship`, `status`, and `classification`. The last is a denormalized
currency attribute (null for withdrawn entries). It is there because
`classification` is a required column of `currencies_by_region.parquet` and no
other CURATED artifact exposes it. Adding it to `iso4217.parquet` would have
broken the column parity with the CSV export that ADR 0002 establishes;
adding it to a new file breaks nothing.

### 2. ADR 0002 applies only to the flat eleven-column file

ADR 0002 decided that `iso4217.parquet` mirrors the CSV export's columns and
therefore carries no `countries[]`. The reasoning was about *that file's
shape*: a flat, one-row-per-currency table with CSV-compatible columns. It was
never a decision that country data must not exist in Parquet. A
one-row-per-currency table cannot hold a one-to-many relationship without
repeating rows or nesting a list, and ADR 0002 rejected both for the flat
file. `iso4217.countries.parquet` is the same data in the shape the
relationship actually has. The two decisions do not conflict; each governs its
own file.

### 3. `coverage_timeline.parquet` reads the changelog, and the changelog is not RAW

Every other aggregated file reads CURATED Parquet. `coverage_timeline.parquet`
reads `CHANGELOG.md`, because release history is recorded nowhere else in the
repository's data artifacts. This is the single exception, and it is
defensible for three reasons:

- **The changelog is not RAW.** RAW is the one file whose fields are the
  registry's contents. The changelog is a human-authored release record. No
  CURATED artifact is derived from it, and nothing about a currency can be
  learned from it.
- **The layering rule exists to give each artifact a single, auditable
  upstream.** `coverage_timeline.parquet`'s single upstream is the changelog
  itself; it does not mix a data layer with a document.
- **No lower layer can supply it.** Putting release history into a CURATED
  generator would mean writing it into RAW first, which is the wrong
  direction: history of the repository is not a fact about ISO 4217.

The tool reads the changelog by static parse. It does not shell out to `git`.
The first changelog heading is 1.0.0, the first release, so no released
version predates the heading format and no git fallback is needed. Counts come
from the changelog's `## Version History` table and are null where the table
has no row; they are never extrapolated.

### Enforcement

The aggregated tool enforces the rule in code rather than by convention. It
has no registry loader and no `--registry` flag. Every input passes an
allowlist by kind (`.parquet`, the snapshot's `.json`, `.md`), nothing under
`wrappers/` is accepted, and a JSON input with a top-level `currencies` key is
rejected as the RAW registry. The module opens with a comment stating the
rule, so a reader who greps for the RAW filename finds only that comment.

### Join and grain decisions

- **The region join resolves against the snapshot's `countries.active` list
  only.** The snapshot's `countries.withdrawn` list reuses `SK` (Sikkim) and
  `AI` (Afars and Issas), which are live codes for Slovakia and Anguilla. A
  merged index lets the withdrawn record win and files both countries in the
  wrong region. A code absent from `countries.active` is fatal (exit 2) and
  names the code and currency.
- **Grain is (region, currency).** `subregion` is therefore a property of the
  group: set when all the group's countries share one, null otherwise. It is
  informational, not a group-by key: a null means "several subregions or none
  known", and grouping on it would conflate the two.
- **`region` is nullable.** `XK` (Kosovo) and `TW` (Taiwan) are the two codes
  the ISO 3166 snapshot does not classify into a region. Those rows are kept
  with a null region, sorted last, rather than dropped or relabelled.
- **Input consistency.** The two CURATED Parquet inputs must carry the same
  `iso4217.version` and `iso4217.updated` footer values, or the tool stops.

## Consequences

### What consumers gain

- Questions that previously needed a three-way join and a nested-JSON parse
  are one file read: which currencies circulate in a region, which currencies
  hang off an anchor, how coverage grew by release.
- A consumer who wants the full currency→country relation, or the subregion
  breakdown, has `iso4217.countries.parquet` in a typed, joinable form.

### What changes in the repository

- New CURATED artifact `iso4217.countries.parquet` and generator.
- New AGGREGATED artifacts and one generator, `tools/export_aggregated.py`.
- Two CI gates: `check-countries-parquet` and `check-aggregated-export`.
- Every release that bumps `meta.version` must regenerate the countries
  Parquet first and the aggregated files second, because both embed the
  version in their footers and the aggregated tool refuses mismatched inputs.
  The order is the layer order.

### Version footers are not version-consistency sites

`tools/check_version_consistency.py` treats the footer of the flat
`iso4217.parquet` as a registry-version site. The four Parquet files added
here are deliberately not sites. Their `--check` modes already detect the same
failure: a regenerated footer says the new version, the committed file says
the old one, and `--check` exits 1. A fifth, sixth, seventh and eighth site
would add maintenance without adding detection. The aggregated tool also
refuses to run when its two CURATED inputs disagree on version.

### Limits to be aware of

- `coverage_timeline.parquet` has null counts for every version after 1.5.0,
  and a null date for 1.5.3, because the changelog states neither. Filling
  them is an edit to the changelog, not to the tool.
- `pegs_summary.parquet`'s median, minimum, and maximum are taken over
  per-currency exchange rates whose magnitudes differ widely within one
  anchor (EUR anchors both BAM and XOF). They are arithmetic summaries, not a
  "typical rate".

## Alternatives considered

**Option A — Read `iso4217.json` from the aggregated tool.**
Rejected. It is the shortcut the layering rule exists to prevent. The
artifact would have two upstreams, and its reproducibility chain would no
longer run through CURATED.

**Option B — Add `countries` (as a list column) to `iso4217.parquet`.**
Rejected. It breaks the CSV column parity ADR 0002 establishes, and a nested
column defeats the point of a flat analytical table.

**Option C — Put the currency→country projection inside the aggregated
tool.** Rejected. It is a denormalization, not an aggregate, and it would
require reading RAW.

**Option D — Parse git tags for `coverage_timeline.parquet`.**
Rejected. It would add a subprocess dependency to a tool whose output must be
deterministic from files alone, and every released version already has a
changelog heading.

**Option E — Drop unresolved country codes, or relabel null regions.**
Rejected. A silent drop undercounts and a relabel asserts something no source
says. An unresolvable code is a data error and stops the tool; a null region
is a fact about the snapshot and is carried through.

## References

- `docs/LAYERS.md` — the RAW / CURATED / AGGREGATED model
- `docs/decisions/parquet-schema.md` — ADR 0002, the flat Parquet schema
- `tools/export_countries_parquet.py` — the CURATED generator
- `tools/export_aggregated.py` — the AGGREGATED generator
- `tools/iso3166_snapshot.json`, `tools/iso3166_snapshot.meta.json` — the
  vendored ISO 3166 reference
