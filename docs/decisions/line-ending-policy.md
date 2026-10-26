# ADR 0012 - Line-ending policy

**Status:** Accepted.
**Date:** 2026-10-25
**Context:** v1.9.2 - closing P5-06.

## Context

[Confirmed] `.gitattributes` pins `eol=lf` for `*.csv`, `*.tsv` and `VERSION`. The fifth pass simulated a CRLF copy of
the tree: `vendor_iso3166.py --check` failed (it hashes the snapshot bytes) and `release.sh` stopped parsing in bash.
No tracked file in the v1.9.1 archive contains a CR byte, so the problem is a Windows checkout with
`core.autocrlf=true`, not the repository content.

[Confirmed] The brief said the Excel CSV needs CRLF "or BOM, depending on Excel version". The Excel CSV already
carries the BOM (`EF BB BF`, the only tracked file that does) and uses LF; `export_csv.py` documents LF as deliberate
for all four flat files. Changing it to CRLF would change its bytes for no consumer benefit.

## Decision

**Every text file in the repository is LF, in the repository and in every working tree. There is no CRLF carve-out.**

- `.gitattributes` gains a default rule `* text=auto eol=lf`, plus explicit `eol=lf` for `*.sh`, `*.py`, `*.json`,
  `*.sql` (as the brief asked) so the rule survives someone deleting the default, and `binary` for `*.parquet`.
  The default rule is the part that matters: listing extensions again would leave the next new extension
  (`.yml`, `.md`, `.go`, `.rs`, `.js`, `.toml`) unpinned, which is the P5-06 gap.
- The Excel CSV keeps its BOM and LF. The BOM is the Excel-on-Windows signal; Excel 2016+ reads LF.
- A gate step, `tools/check_line_endings.py`, fails on any CR byte in a tracked text file and on a `.gitattributes`
  that drops the default rule. The gate does not rely on git's normalization, because normalization runs at `git add`
  and the gate runs before it.
- A Windows CI job runs `vendor_iso3166.py --check`, `check_release_claims.py` and `check_line_endings.py` on
  `windows-latest` with `core.autocrlf=true` forced, so the job exercises the checkout that broke.
- `windows-verify-manifest.txt` (v1.5.1 hashes, nothing reads it) is deleted. It was the v1.5.1 stand-in for a CI job.

## Consequences

- [Confirmed] The gate count goes to 28, not the 27 the brief assumed: the country-currency membership check is one
  new step and `check_line_endings.py` is a second. The brief's own R10 requirement (add a CRLF file, assert the gate
  fails) needs a step that detects CR, and none of the 26 does.
- [Guess] The Windows job has not been run: this session had no Windows runner. It is a CI definition tested for shape
  (`tests/test_ci_*.py` style), not for behaviour on Windows.
