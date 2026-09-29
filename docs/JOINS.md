# Cross-registry joins

ISO 4217's `code` field is the primary key that four other registries
reference, and one foreign key that 4217 itself references. This
document names every edge, its direction, and its current status.

The venue side of the same graph is at
[`iso10383/docs/JOINS.md`](https://github.com/slimissa/iso10383/blob/main/docs/JOINS.md).
This document covers the currency side. Together they describe the
complete FK surface of the QuantOS registry layer.

---

## Outgoing edges (ISO 4217 → other registries)

### `currencies.active[].countries[].code` → ISO 3166 `alpha_2`

**Status:** shipped, validated in CI.

Every entry in a currency's `countries[]` array carries an ISO 3166-1
alpha-2 code. The set is validated against a byte-for-byte vendored
snapshot of ISO 3166 at
[`tools/iso3166_snapshot.json`](../tools/iso3166_snapshot.json).

The check is `tools/check_country_codes.py`. It runs in the release
gate and in CI. 245 unique codes across 268 references, all
resolving in the snapshot at ISO 3166 v1.5.2.

The snapshot's freshness is tracked by
`tools/check_snapshot_freshness.py` reading
`tools/iso3166_snapshot.meta.json`. When ISO 3166 ships a new
release, the notification rule fires and the snapshot refreshes in
the same PR.

**Planned:** none. The edge is complete.

### `currencies.*[].numeric` → Asset Identifiers `numeric`

**Status:** planned. No consumer yet.

The numeric code is a 3-digit string. Asset Identifiers carries a
`numeric` field on every entry that maps a currency to a currency code.
If Asset Identifiers adds currency records — currently it holds
instruments, not currencies — the join would be
`currencies.active[].numeric == asset_identifiers.*.numeric`.

The link is documented here so the shape is stable when the consumer
exists. Nothing to check until then.

---

## Incoming edges (other registries → ISO 4217)

### ISO 3166 `currency_codes[]` → `currencies.active[].code`

**Status:** shipped, validated on the ISO 3166 side.

Every country in ISO 3166 carries a `currency_codes[]` array listing
the currencies in circulation there. Each code resolves to an entry
in `currencies.active[].code`.

The check runs in ISO 3166's release gate. Reference:
`slimissa/iso3166/tools/validate.py`, layer 4 (cross-reference).
The join is one-directional in this document — ISO 3166 validates
against 4217, not the reverse — because a 4217 entry can reference
a country with no currency of its own (dependency, territory), but
an ISO 3166 entry cannot reference a currency that is not in 4217's
active set without failing validation.

### Asset Identifiers `currency` → `currencies.active[].code`

**Status:** planned. Asset Identifiers ships schema-only.

Asset Identifiers' instrument entries carry a `currency` field naming
the currency the instrument is denominated in. When that registry
reaches full coverage, the field will reference
`currencies.active[].code`.

The check, when it exists, would live in Asset Identifiers' release
gate. 4217 has nothing to validate until then.

### Corporate Actions `currency` → `currencies.active[].code`

**Status:** planned. Corporate Actions currently references only USD
instruments.

Corporate Actions' dividend entries carry a `currency` field for the
dividend amount. It will reference `currencies.active[].code` when
non-USD instruments are added.

---

## What ISO 4217 does not answer

Four common queries that look like 4217 concerns and aren't:

| Query | Answered by |
|-------|-------------|
| What exchange trades a currency? | Not a currency property. Use Exchange Calendar and ISO 10383. |
| What are the trading hours for a market? | Exchange Calendar. |
| What's the legal entity that issues a currency? | Partially. `central_bank` names the monetary authority; the LEI of that authority is in ISO 10383 for exchanges, not for central banks. |
| What's the tick size for a symbol? | Not a registry concern. |

The rule: if the question is about *where* or *when* a currency
trades, it belongs to Exchange Calendar or ISO 10383. If it's about
*what* the currency is, it's here.

---

## Reverse lookups

Common traversals from a currency code:

- **Currency → countries** — `currencies.active[].countries[]` on the
  entry itself.
- **Currency → MIC venues** — via ISO 10383's `mic` field if a
  currency-to-venue edge ever exists. Currently none.
- **Currency → ISIN instruments** — via Asset Identifiers' `currency`
  field, planned.
- **Currency → corporate actions** — via Corporate Actions'
  `currency` field, planned.

The direct edges are the ones this document checks. The traversals
through other registries are their responsibility.

---

## Adding an edge

When a new cross-registry reference lands:

1. Add the edge to the appropriate section above.
2. If the reference validates against a vendored snapshot, add the
   snapshot and the check in the same commit.
3. If the reference is on the other side, note it in that registry's
   `Consumed by` section and in the JOIN doc at the reference point.

The document is not a contract until the edge exists. Planned edges
belong here as much as shipped ones — the shape should be visible
before the code is.