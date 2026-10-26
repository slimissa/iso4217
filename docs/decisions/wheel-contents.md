# ADR 0011 - What the Python wheel ships

**Status:** Accepted.
**Date:** 2026-10-25
**Context:** v1.9.2 - closing P5-01.

## Context

[Confirmed] The wheel built from `wrappers/python` ships `iso4217.json` and `schema.json` (a custom `build_py` copies
both, and `MANIFEST.in` lists both). Measured on the v1.9.1 tree:

| File | `$id` | Errors validating the shipped `iso4217.json` |
|---|---|---|
| root `schema.json` | v1.4.0 | 0 |
| `wrappers/python/schema.json` (what the wheel ships) | v1.3.0 | 314 |

`sync_wrappers.py` copies `iso4217.json` into four wrappers and has never copied the schema. Nothing in `iso4217.py`
or `iso4217_cli.py` reads the schema, so the copy is inert in code and wrong for any consumer who validates with it.

## Decision

**The wheel and the sdist ship the registry data and the wrapper code. They do not ship `schema.json`.**

- `setup.py`: `DATA_FILES = ("iso4217.json",)`.
- `MANIFEST.in`: drop `include schema.json`.
- `wrappers/python/schema.json` is deleted from the tree.
- The schema is the contract and lives at the tag. The registry names its schema by version
  (`meta.schema_version`), and the schema names itself by `$id`. A consumer who wants to validate takes the schema
  from the matching tag.

## Alternatives rejected

- **Sync the schema** (add it to `WRAPPER_COPIES`). Works, and the check would hold. It also keeps a second copy of a
  contract inside every future wheel, so the class of bug that P5-01 is stays possible with one more file to
  forget. A copy needs a reason to exist, and none of the code uses it.
- **Ship a hash of the schema and fetch the schema at the tag.** [Likely] Wrong tool. The wheel has zero runtime
  dependencies and works offline; a fetch adds a network step to a package that has none. A hash proves the schema
  is the expected bytes. It does not prove the registry is valid. The brief offered this as the way to let the wheel
  validate itself; I disagree, and `pip install iso4217-registry[dev]` already brings `jsonschema` for those who validate.

## Consequences

- A consumer who validated with the wheel's bundled schema (it rejected valid data, so none could have succeeded)
  now fetches the schema from the tag. This goes in the CHANGELOG in consumer terms.
- The wheel's registry must validate against the repo schema at the same checkout. A test builds the real wheel,
  installs it in a clean virtualenv, loads the installed JSON and validates it against root `schema.json`. It also
  asserts that the wheel's file list contains no `schema.json`, so the two halves of the decision are tested
  separately.
- Not audited here: the Go, Rust and JavaScript packages. Nothing in the tree suggests they ship a schema, but no
  package build was run for them.
