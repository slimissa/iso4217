# Release rules: the numbering authority

This file says which rule an ID means. It does not say what a rule requires: the text of every rule is in
[RELEASE_PATTERN.md](../RELEASE_PATTERN.md), and this file never restates it, so the two cannot disagree. `tools/check_rules_refs.py`
(a gate step and a CI job) keeps them honest: every row below must point at a heading that exists under the section it names,
every rule heading must have a row, and every qualified citation of a rule in a current document must resolve.

**IDs.** `E1` to `E8` are the essential eight (cited elsewhere as "invariant N"). `H1` to `H10`, with `H6b`, `H6c` and `H6d`, are the
operator-hygiene rules (cited as "hygiene rule N"). `R10` is an alias of `H10`.

**Citing.** Inside this repository a bare ID (`H7`) means this repository's rule. A citation that leaves it names the repository:
`4217/H7`, `3166/H7`, `10383/H7b`, `ec/H7`. A bare "rule 7" is ambiguous (inside this repository "rule 6" is both `E6` and `H6`),
so new text does not use it; the existing ones are frozen by the tool.

**What this is not.** It is not a merged pattern, not a shared document, and not a claim that the other registries agree. ADR 0016
records why. The adoption matrix below is documentation of what was read on the date shown; nothing checks it.

## Rules

| ID | Meaning | Section | Heading in RELEASE_PATTERN.md | Aliases |
|---|---|---|---|---|
| E1 | Refuse to start on an unclean state | The essential eight | 1. Refuse on unclean state |  |
| E2 | Refuse a version that collides or has no CHANGELOG section | The essential eight | 2. Refuse on version collision or missing CHANGELOG |  |
| E3 | Bump every version site, then verify them | The essential eight | 3. Bump all version sites, then verify |  |
| E4 | Verify after the rebuild | The essential eight | 4. Post-rebuild verify |  |
| E5 | Run the gate before the commit | The essential eight | 5. Gate before commit |  |
| E6 | Poll every workflow before tagging | The essential eight | 6. Poll every workflow |  |
| E7 | Tag only on green | The essential eight | 7. Tag only on green |  |
| E8 | Tags are immutable | The essential eight | 8. Immutable tags |  |
| H1 | No heredocs for multi-line scripts | Operator hygiene | 1. No heredocs for multi-line scripts |  |
| H2 | Read the diff before every add | Operator hygiene | 2. `git diff` before every `git add` |  |
| H3 | Read every CI status before the next step | Operator hygiene | 3. Read every CI status before the next step |  |
| H4 | Every multi-line construct goes into a file | Operator hygiene | 4. Every multi-line construct goes into a file |  |
| H5 | A pipeline's exit code is its last command's | Operator hygiene | 5. The exit code of a pipeline is the last command's exit |  |
| H6 | An artifact that quotes an implementation detail is coupled to it | Operator hygiene | 6. Every artifact that quotes an implementation detail is coupled to that implementation |  |
| H6b | The commit is not the working tree | Operator hygiene | 6b. The commit is not the working tree |  |
| H6c | Manifest claims describe state, not intent | Operator hygiene | 6c. Manifest claims describe state, not intent. |  |
| H6d | A check is only meaningful against the artifact it was designed for | Operator hygiene | 6d. A check is only meaningful against the artifact it was designed for |  |
| H7 | A check that cannot run must fail, not pass | Operator hygiene | 7. A check that cannot run must fail, not pass |  |
| H8 | Every tool proves its own reachability | Operator hygiene | 8. Every tool proves its own reachability |  |
| H9 | Every lockfile is audited on every push | Operator hygiene | 9. Every lockfile is audited on every push |  |
| H10 | A check that cannot fail is not a check | Operator hygiene | 10. A check that cannot fail is not a check | R10 |

## Adoption matrix

The criterion (ADR 0016, D3): a registry's pattern file refers to each canonical rule by ID, or documents an exception. Each sibling
column is **as of 2026-10-29, not verified by tooling**. ISO 4217 is this repository and is checked by `tools/check_rules_refs.py`. "P5-10, 2026-10-23" means what
the third-pass audit recorded from the raw files on `main` that day; "read 2026-10-29" means its pattern file was read in full that
day; "unknown" means neither.

| ID | ISO 4217 | ISO 3166 (as of 2026-10-29, not verified by tooling) | ISO 10383 (as of 2026-10-29, not verified by tooling) | Exchange Calendar (as of 2026-10-29, not verified by tooling) |
|---|---|---|---|---|
| E1 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E2 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E3 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E4 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E5 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E6 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E7 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| E8 | defines it | same number 1 to 8, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H1 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H2 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H3 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H4 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H5 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H6 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H6b | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H6c | defines it | no equivalent (P5-10, 2026-10-23) | unknown | unknown |
| H6d | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H7 | defines it | same number, no equivalent rule at it (P5-10, 2026-10-23) | same number, same meaning (P5-10, 2026-10-23) | same number, different meaning: "grep after every symbol removal" (P5-10, 2026-10-23) |
| H8 | defines it | no equivalent (P5-10, 2026-10-23) | unknown | unknown |
| H9 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |
| H10 | defines it | number exists in its hygiene 1 to 13, meaning not compared (its pattern file, read 2026-10-29) | unknown | unknown |

## Rules a sibling has that this repository lacks

- `3166`: dry-run rules numbered 9 to 19, further rules 24 to 28, and A10 and A11 (its pattern file, read 2026-10-29); no `H6c`, `H7` or `H8` equivalents (P5-10).
- `10383`: a `7b` this repository lacks (P5-10, 2026-10-23).
- `ec`: not read; its docs directory was blocked to automated access on 2026-10-29. Its meaning for number 7 differs (P5-10).

## What is deferred

Reading the Exchange Calendar and ISO 10383 pattern files, replacing every "unknown", verifying the matrix by tooling, and any
`--strict` mode are the fourth audit's work (ADR 0016). This repository does not change another repository.
