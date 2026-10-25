# Tool audit: reachability of every tool in `tools/`

`RELEASE_PATTERN.md` operator-hygiene rule 8 says a tool with no `--check` or smoke invocation in CI may have
unreachable code paths. This file is the table behind that rule: every tool in `tools/`, whether it declares a
`--check` mode, which workflow runs it, and whether `scripts/release.sh` runs it in the gate. A dash means none.

How to read the columns:

- **`--check`**: the tool declares a `--check` option (an `argparse` declaration, not a mention in prose).
- **CI**: the workflow file(s) under `.github/workflows/` with a `run:` line that invokes the tool.
- **Gate**: `run_gate()` in `scripts/release.sh` invokes the tool. "yes (N steps)" means N separate gate steps.

The table is written by hand and checked by machine: `tools/check_audit_table.py` derives each column from the tree and
fails the gate and CI when a row disagrees (v1.9.1). If a row and the tree disagree, the tree is right.

## Category A: committed-artifact producers

Tools whose output is a committed file. Rule 8 applies in full: each runs in CI and in the gate.

| Tool | `--check` | CI | Gate |
|------|-----------|----|------|
| `export_sql.py` | `--check` | validate.yml | yes |
| `export_csv.py` | `--check` | validate.yml | yes |
| `export_parquet.py` | `--check` | validate.yml | yes |
| `export_countries_parquet.py` | `--check` | version-and-hygiene.yml | yes |
| `export_aggregated.py` | `--check` | version-and-hygiene.yml | yes |
| `sync_wrappers.py` | `--check` | validate.yml, version-and-hygiene.yml | yes |
| `vendor_iso3166.py` | `--check` | version-and-hygiene.yml | yes |

## Category B: validators

Tools that read the tree and report. Rule 8 does not require them to have a `--check` mode (they are the check), but a
validator that runs nowhere validates nothing. One exception to "read and report": `check_country_codes.py
--refresh-from <path>` writes the vendored ISO 3166 snapshot; the plain invocation does not.

| Tool | `--check` | CI | Gate |
|------|-----------|----|------|
| `validate.py` | — | validate.yml | yes |
| `check_version_consistency.py` | — | version-and-hygiene.yml | yes |
| `check_mojibake.py` | — | version-and-hygiene.yml | yes |
| `check_snapshot_freshness.py` | — | version-and-hygiene.yml | yes |
| `check_registry_freshness.py` | — | version-and-hygiene.yml | yes |
| `check_country_codes.py` | — | version-and-hygiene.yml | yes |
| `check_readme_drift.py` | — | version-and-hygiene.yml | yes |
| `check_provenance.py` | — | version-and-hygiene.yml | yes |
| `check_verification_doc.py` | — | version-and-hygiene.yml | yes |
| `check_audit_table.py` | — | version-and-hygiene.yml | yes |
| `check_amendments.py` | — | monitor-amendments.yml | — |
| `check_cross_language.sh` | — | — | yes |
| `check_release_claims.py` | — | — | yes |

## Category C: enrichment

Tools that edit, or propose edits to, `iso4217.json` (RAW). They are run by hand; the generators in category A are
re-run afterwards.

| Tool | `--check` | CI | Gate |
|------|-----------|----|------|
| `enrich_field.py` | `--check` | version-and-hygiene.yml | yes (4 steps) |
| `update_from_iso.py` | `--check` | — | — |
| `refresh_market_caps.py` | `--check` | — | — |

Category C tools are manual and network-dependent. `update_from_iso.py` and `refresh_market_caps.py` are excluded from CI
and the gate by design, not by omission. `enrich_field.py` is the exception within the category: it runs in both.

## Outside the three categories

| Tool | `--check` | CI | Gate |
|------|-----------|----|------|
| `parse_source.py` | — | — | — |

`parse_source.py` is the source-table classifier, run by hand; unlike the category C tools, no decision records why it
runs nowhere.

## Gaps in this table as of v1.8.4

Producers and enrichment tools missing from CI or the gate (rule 8 scope):

- `update_from_iso.py`: not in CI and not in the gate (by design; see the note under category C)
- `refresh_market_caps.py`: not in CI and not in the gate (by design; see the note under category C)

Validators missing from CI or the gate:

- `check_amendments.py`: not in the gate
- `check_cross_language.sh`: not in CI
- `check_release_claims.py`: not in CI

Tools outside the three categories missing from CI or the gate:

- `parse_source.py`: not in CI and not in the gate

These are recorded, not fixed: v1.8.4 documents reachability, it does not change which tools run where.
