# ADR 0016 - One numbering for the release rules

**Status:** Proposed. It becomes Accepted when `tools/check_rules_refs.py` passes on the tree with every mutant killed and the owner commits it.
**Date:** 2026-10-29
**Context:** v1.9.5 - closing P5-10 and EC of the third audit pass.

## Context

P5-10 says "the same pattern across registries" is false at the rule level: numbers collide, so a bare rule number is ambiguous when it
crosses a repository boundary. Read on 2026-10-29:

- **This repo (`RELEASE_PATTERN.md`, 894 lines).** The essential eight are numbered 1 to 8 and cited as "invariant N" (14 times
  for invariant 5 alone). The operator-hygiene rules are numbered 1 to 10, with 6b, 6c and 6d, and cited as "hygiene rule N"
  or "operator-hygiene rule N". Bare "rule N" is also used (about 30 times) and "R10" is used 9 times for hygiene rule 10.
  [Confirmed] **The collision is inside this repo too:** the number 6 is both E6 (poll every workflow) and H6 (an
  artifact that quotes an implementation detail). The heading of the hygiene section still says "Four rules that emerged",
  above thirteen headings, and its "Reviewed by" list says Exchange Calendar's review is "pending".
- **ISO 3166 (`docs/RELEASE_PATTERN.md`, read in full).** It presents itself as the adopted, shared pattern, reviewed by all <!-- doc-path: example -->
  four registries. Its numbering: the essential eight 1 to 8 with 6b and 6d; operator hygiene 1 to 13 and 16 to 23; further
  its numbers 24 to 28; A10 and A11. Its README describes a fail-fast gate (the first failure stops the release); this repo's gate
  now runs every step and reports every failure. [Confirmed] So two documents that call themselves the shared pattern have
  diverged in numbering, in length and in reviewers.
- **ISO 10383 and Exchange Calendar.** I read ISO 10383's README (its gate is described as fail-fast; its preconditions
  include "tag free locally and on origin") but not its pattern file. Exchange Calendar's `docs` directory was blocked to
  automated access (`robots`), so its pattern file was not read. For both, this ADR relies on what P5-10 recorded from the raw
  files on 2026-10-23: hygiene 7 means "grep after every symbol removal" in Exchange Calendar, and ISO 10383 has a 7b this repo
  lacks. [Likely] that is still true; it is not re-verified.
- **EC.** The audit's own text never defines "EC": it appears only in the list "P5-09, P5-10, P5-11, EC" and in the phrase
  "docs and pattern alignment". [Guess] It is the Exchange Calendar alignment, a part of P5-10, and this ADR treats it so:
  its acceptance test is the Exchange Calendar column of the adoption matrix below. If the owner meant something else, this is
  the one line to correct.

## Decisions

### D1. `docs/rules.md` is a numbering authority, not a fifth copy of the rules

**Decision:** one table, one row per rule, with an ID, a one-line meaning, the section and heading it comes from in
`RELEASE_PATTERN.md`, and a status. IDs: `E1` to `E8` for the essential eight, `H1` to `H10` for operator hygiene with `H6b`,
`H6c` and `H6d`. `R10` is recorded as an alias of `H10`; "invariant N" is an alias of `EN`; "hygiene rule N" of `HN`. The rule
text stays in `RELEASE_PATTERN.md`; `rules.md` never restates it, so it cannot disagree with it.
**Reason:** a second copy of the text is the failure this finding describes. A table of IDs can be checked against the one
document it indexes.
**Rejected:** renumbering this repo's rules to 3166's scheme (a rewrite of every historical citation, for a scheme this repo
has not reviewed); a merged shared document (a cross-repo change, not in this release).

### D2. Cross-repo citations are prefixed

**Decision:** a citation that leaves this repository names the repository: `4217/H7`, `3166/H7`, `10383/H7b`, `ec/H7`. Inside
this repo a bare ID (`H7`) means this repo's rule. The prefix removes the ambiguity without any sibling changing anything.

### D3. The adoption matrix is documentation, labelled as unverified

**Decision:** `docs/rules.md` carries a matrix with one row per rule and one column per registry (ISO 4217, ISO 3166, ISO
10383, Exchange Calendar). Each cell says "uses the ID", "uses a different ID for the same meaning", "documented exception" or
"unknown". Every sibling column carries the label **"as of 2026-10-29, not verified by tooling"** and cites what it was read
from (the file, or "P5-10, 2026-10-23"). The adoption criterion is the one the owner proposed: a sibling's pattern file refers
to each canonical rule by ID, or documents an exception.
**Reason:** a hand-written table that nothing keeps true is the `docs/AUDIT.md` failure (P5-04's neighbor, fixed in v1.9.1).
The matrix does not claim to be more than it is; the fourth audit verifies it.
**Not in v1.9.5:** fetching the siblings from a checker, and any `--strict` mode. Both are cross-repo work.

### D4. `tools/check_rules_refs.py` keeps this repo's side true

**Decision:** the tool fails when (a) an ID in `rules.md` is duplicated or malformed; (b) an ID's heading is not found in
`RELEASE_PATTERN.md` under the section it names, or a rule heading in `RELEASE_PATTERN.md` has no row (the table and the
document index each other); (c) a *qualified* citation in a current document (`invariant N`, `hygiene rule N`,
`operator-hygiene rule N`, `R<n>`, or a prefixed ID) names a rule that does not exist; (d) a bare "rule N" citation appears in
a file that is not in the tool's legacy list, or appears more often in a listed file than recorded (an entry is also stale
when its count is lower, the same "every entry is current" mechanism as the country-currency allow-list).
Only Markdown documents are scanned (comments in code are not). Historical records are not scanned: `CHANGELOG.md` and
`docs/v*-verification.md`. The frozen bare-citation counts live in `docs/rules-legacy-bare.json`, read from the root being
checked (an absent file means none), so no other repository root and no test fixture inherits this repository's history.
**Reason:** bare citations already exist in about thirty places and cannot be rewritten without editing history; the legacy
list freezes them and makes a new ambiguous citation a failure. Qualified citations are the ones that can be checked for truth.

## Consequences

- `RELEASE_PATTERN.md` gets two small corrections (the stale "Four rules" sentence and a pointer to `docs/rules.md`) and a
  review-history entry in the format the document prescribes, naming this repo as the source.
- The gate and CI grow by one step; `docs/AUDIT.md` gets a row (`check_audit_table.py` requires it).
- **New findings, not fixed here:** the intra-repo collision (the number 6 is two rules) is solved for qualified citations only;
  the fail-fast versus accumulating gate difference between siblings is recorded, not decided; Exchange Calendar's pattern file
  and ISO 10383's were not read.

## Verification owed

- The fourth audit reads the Exchange Calendar and ISO 10383 pattern files and replaces "unknown" cells.
- The owner confirms the EC reading above.
