# ADR 0006 — Schema version consistency belongs in check_version_consistency.py

**Status:** Accepted
**Date:** 2026-09-27
**Context:** v1.7.0 — removing a hardcoded schema version from validate.py

## Context

Through v1.6.x, `tools/validate.py` carried a hardcoded expectation
for `iso4217.json → meta.schema_version`:

    schema_version = meta.get("schema_version", "")
    if schema_version != "1.3.0":
        errors.append(...SCHEMA_VERSION_MISMATCH...)

The constant had been updated once, from `"1.0.0"` to `"1.3.0"`, and
was not updated when v1.6.0 bumped the schema to `1.4.0`. The
validator warned on every run for three releases.

The failure mode is structural: any constant that duplicates a value
already stored in a versioned file will drift. The question is not
"which value should the constant be?" — it is "should the constant
exist at all?".

## Decision

Remove the schema-version check from `validate.py`. Version agreement
is owned by `tools/check_version_consistency.py`, which checks
`iso4217.json → meta.schema_version == schema.json → $id` as part of
its two-axis consistency contract.

Division of concerns:

- `check_version_consistency.py` — verifies that every version site
  agrees with its axis. Owns the *agreement* question.
- `validate.py` — verifies data integrity. Reads the schema's shape
  from `schema.json` via `jsonschema`. Does not hardcode versions.
  Owns the *conformance* question.

## Consequences

- The warning count drops from 27 to 26 on every validation run.
- A schema bump requires no change to `validate.py`. The
  consistency check catches a mismatch automatically.
- If the consistency check ever stops running in CI, schema version
  agreement is no longer verified anywhere. The CI job
  `check-version` is the guard.
- Any future addition of a hardcoded version constant to
  `validate.py` is a regression. The ADR names this.

## Alternatives considered

**Option A — Update the constant to `"1.4.0"`.** Rejected. It fixes
the symptom and guarantees the same bug recurs on the next schema
bump. It is the fix the codebase already tried once.

**Option B — Read the schema version from `schema.json` at runtime.**
Rejected. `validate.py` would then check "does `meta.schema_version`
equal `schema.json → $id`?" — which is exactly what
`check_version_consistency.py` already does. Duplicate logic, same
drift risk if the two implementations ever diverge.

**Option C — Move the check to a new dedicated tool.**
Rejected. `check_version_consistency.py` is already the tool.

## References

- `tools/validate.py` — `validate_meta()`, where the check lived
- `tools/check_version_consistency.py` — the tool that owns version
  agreement
- `axes.json` — the declaration of which sites carry which version
- ADR 0005 — the complementary decision to keep 26 warnings as the
  steady state