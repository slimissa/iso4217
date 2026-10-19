# Provenance

Where the data in `iso4217.json` comes from, how often each layer is refreshed, and how to audit a specific value.

This document exists because "canonical registry" is a claim, and claims about data need evidence. What follows is that evidence, stated plainly, including the limitations.

---

## 1. Sources by category

| Data category | Primary source | Cross-check | Refresh cadence |
|---------------|---------------|-------------|-----------------|
| Active ISO 4217 alphabetic codes | ISO 4217:2015 plus all published amendments through Amendment 180 | SIX Group amendment summary (`currency-iso.org`) | Per amendment (quarterly or slower) |
| Withdrawn ISO 4217 codes | ISO 4217 historical record, supplemented by national central bank archives | SIX Group revaluation tables and the ISO online browsing platform | Per amendment |
| Numeric codes | ISO 4217:2015 Table A.1 | SIX Group amendment PDFs | Per amendment |
| Minor units (decimal places) | ISO 4217:2015 | Central bank specification for the currency (e.g., Bank of Japan for JPY, Central Bank of Kuwait for KWD) | Annual spot-check |
| Currency symbols | Unicode CLDR currency data, plus central bank specification | Cross-checked against the currency's primary English-language Wikipedia entry | Annual spot-check |
| Central bank names | Central bank official website (the English-language "About" page) | Cross-checked against the Bank for International Settlements central bank directory | Annual spot-check |
| Peg information (anchor, type, rate, band, date) | Central bank official website and the IMF's Annual Report on Exchange Arrangements and Exchange Restrictions (AREAER) | Cross-checked against the currency's Wikipedia entry for the peg establishment date | Annual spot-check |
| Country relationships | ISO 3166-1 (country codes) and UN Statistics Division membership lists | Cross-checked against the currency's Wikipedia entry | Annual spot-check |
| Eurozone irrevocable conversion rates | ECB Council Regulation (EC) No 2866/98 and successor regulations | Cross-checked against each member state's central bank announcement | Never (historical fact) |
| Non-ISO cryptocurrencies | CoinGecko `/coins/markets` API endpoint | Manual review before commit | Weekly (manual, via `tools/refresh_market_caps.py`) |
| Non-ISO stablecoins | Issuer's transparency page plus CoinGecko market-cap rank | Manual review before commit | Weekly (manual) |
| Non-ISO commodities | London Bullion Market Association (LBMA) code conventions | Cross-checked against ISO 4217's X-code assignments | Annual spot-check |

Every active and withdrawn currency entry traces to one of the rows above. The row that applies depends on which field is being verified — a currency's numeric code and its peg rate come from different sources and are verified independently.

---

## 2. What `tools/check_amendments.py` actually checks

The weekly amendment monitor does one thing: it fetches the SIX Group amendment page, extracts the highest amendment number mentioned, and compares it to `source.last_amendment_applied` in the registry.

It does **not** diff the currency list itself. It does not parse the amendment PDF. It does not fetch a structured feed.

What this means in practice:

- If ISO publishes Amendment 180 and it only updates a currency name, the monitor fires. A human reads the amendment, updates the affected entry, bumps `source.last_amendment_applied` to 180, and commits.
- If ISO publishes Amendment 180 and it adds a new currency, the monitor fires the same way. The human work is heavier — a new entry needs a numeric code, minor units, symbol, entity, central bank, and country relationships — but the detection mechanism is identical.

The monitor is a **detection** tool, not an **ingestion** tool. It tells you that something changed; it does not tell you what.

It also tells you when it cannot see. A run that cannot read the SIX page, or finds no amendment number in it, exits 3: the workflow goes red and opens (or comments on) an issue titled "Amendment monitor cannot read the SIX page". Before v1.7.15 that case exited 0, so a change to the page made the monitor report success every week while detecting nothing.

This is deliberate. Automated ingestion of ISO amendments would require parsing PDFs published in a variety of formats, and the failure mode — silently ingesting a mis-parsed entry — is worse than the failure mode of a human doing the update slowly. The registry's correctness guarantee depends on human review, and the monitor's only job is to make sure the review happens.

---

## 3. What Wikipedia is used for

Wikipedia is used in three specific ways and no others:

1. **Initial ingestion.** `tools/parse_source.py` parses Wikipedia's ISO 4217 table to bootstrap the active, withdrawn, non-ISO, and commodity classification. Every entry that enters the registry through this path is verified against a primary source before it is committed.

2. **Cross-check during manual review.** When a primary source is ambiguous or unavailable, the currency's Wikipedia entry is consulted as a secondary source. This happens most often for peg establishment dates and for country relationships.

3. **Never as a sole source.** No value in `iso4217.json` exists in the registry because Wikipedia said so and nothing else did. Every field has a primary source in the table above.

The reason for this discipline is simple: Wikipedia is a compilation of primary sources, and the registry is also a compilation of primary sources. If the registry copied Wikipedia, it would inherit Wikipedia's edit-war risk, its uncited-revision risk, and its vandalism risk. If it copies primary sources directly, it inherits none of those.

---

## 4. How to audit a specific entry

For any currency code `XYZ` in `iso4217.json`, here is the audit trail:

**Step 1 — Locate the entry.**

```
python3 -c "
import json
d = json.load(open('iso4217.json'))
for status in ('active', 'withdrawn'):
    for c in d['currencies'][status]:
        if c['code'] == 'XYZ':
            print(json.dumps(c, indent=2, ensure_ascii=False))
"
```

Or, more simply:

```
iso4217 lookup XYZ
```

**Step 2 — Verify the ISO codes.**

Cross-check the `numeric` field against the ISO 4217 online browsing platform (`iso.org/iso-4217-currency-codes.html`). For withdrawn codes, cross-check against the SIX Group amendment history.

**Step 3 — Verify the peg information.**

If the entry has `pegged_to` set, visit the `central_bank` website and confirm:

- The anchor currency or basket composition
- The peg rate (or the band around it)
- The establishment date

The IMF's AREAER report for the relevant country is a secondary cross-check.

**Step 4 — Verify the country relationships.**

For each entry in the `countries` array, verify the `relationship` field:

- `issuing` — the sovereign issuer. The country's central bank is the monetary authority for that currency.
- `adopting` — uses the currency without being the issuer (e.g., Ecuador uses USD).
- `territory` — a dependent territory of the issuing country.
- `parallel` — circulates alongside a local currency at fixed parity.
- `local_issue` — issues local banknotes or coins denominated in this currency.

The UN Statistics Division's country membership lists and the currency's Wikipedia entry are both reasonable cross-checks for this field.

**Step 5 — File an issue if anything diverges.**

Open a GitHub issue with the title `Correction: XYZ <field>` and include:

- The current value in the registry
- The value you believe is correct
- A link to the primary source supporting your correction

Do not open a pull request directly. Data corrections go through review, and the review needs the source link before it can start.

---

## 5. Known gaps and limitations

These are the ways the registry's provenance story is incomplete. They are listed here so institutional adopters can make informed decisions, not so they can be glossed over.

**No per-entry `source` field.** The registry does not record which source each specific value came from. The sources are known at the *category* level (see section 1), not the *entry* level. A consumer who wants to know "where did AED's peg rate come from?" has to consult this document and infer.

**No automated refresh against primary ISO sources.** The `tools/check_amendments.py` monitor detects new amendments. It does not ingest them. Between detection and ingestion, there is a human-in-the-loop step. This is deliberate (see section 2), but it means the registry can lag behind an ISO amendment by the time it takes a maintainer to apply the change.

**No cryptographic signature.** The JSON file is not signed. A consumer who downloads `iso4217.json` from GitHub has no way to verify that the bytes they received are the bytes that were committed, short of checking the git tag's hash against a trusted local copy of the repository. If signed releases become a requirement, they will be added in a future version.

**No secondary source for some fields.** For a small number of obscure currencies, the central bank's website is the only source that mentions the currency's peg rate at all. There is no second source to cross-check against. These entries are marked in the CHANGELOG as "single-source verified" when they are added.

**Non-ISO entries have weaker provenance than ISO entries.** Cryptocurrency and stablecoin entries depend on CoinGecko's API for market-cap rank, which is a commercial aggregator, not a primary source. The issuer's transparency page is consulted for peg mechanism, but there is no ISO-equivalent for stablecoins. Consumers who need non-ISO entries at the same confidence level as ISO entries should not use this registry for that purpose.

**Wikipedia references in the CHANGELOG.** A small number of CHANGELOG entries from early versions cite Wikipedia. Those citations remain because the CHANGELOG is a historical record; they do not represent the current sourcing discipline.

---

## 6. Verification workflow for a new entry

When a new currency is added to the registry — whether from an ISO amendment or from a market-cap snapshot for a non-ISO instrument — the following verification steps are mandatory before merge.

For an **ISO 4217** entry:

1. The alphabetic code appears in the ISO amendment or in ISO 4217 Table A.1.
2. The numeric code is exactly three digits and matches ISO's assignment.
3. The minor units match the ISO specification.
4. The symbol matches the Unicode CLDR value or the central bank's specification.
5. The central bank name appears on the central bank's own website.
6. Every country in the `countries` array traces to a UN membership list or an ISO 3166-1 assignment.
7. If the currency is pegged, the anchor, rate, band, and establishment date each have a central bank or IMF source.

For a **non-ISO** entry:

1. The code (or synthetic identifier) does not collide with an existing code in the registry.
2. The market-cap rank is sourced from the current CoinGecko snapshot and is recorded in the entry's `note`.
3. The `type` field is one of the enumerated values.
4. The `note` field states explicitly that the entry is not an ISO 4217 code.

A pull request that adds an entry without these checks passing will fail CI or will fail review. The two failure modes are equivalent — a maintained registry depends on both.

---

## 7. Versioning of this document

This document describes the provenance discipline in effect as of v1.8.3. If the discipline changes — for example, if per-entry source fields are added, or if signed releases ship — this document will be updated alongside the change, and the CHANGELOG entry will reference it.

**Last updated:** 2026-10-19
**Applies to registry version:** 1.8.3 (data and documentation)
**Maintainer:** [github.com/slimissa](https://github.com/slimissa)

---

## 8. Snapshot freshness

`tools/check_registry_freshness.py` fails CI when `iso4217.json`'s
`meta.updated` field is more than **180 days** old.

Rationale: ISO 4217 amendments are published irregularly, and the
registry's `check_amendments.py` detects new amendments but does not
ingest them — a human applies each change. A single missed cycle,
roughly two quarterly windows, is a signal that the review loop has
stalled, not that the source is late. 180 days is one clearly-missed
cycle without being noisy on a healthy schedule.

The threshold can be overridden at the command line
(`--threshold 365`) but the CI job uses the default.

## 9. Per-field provenance

Section 1 describes sources by category. This table names every field of `iso4217.json`, one row each: where the value comes from, what makes it change, and what checks it. `tools/check_provenance.py` fails CI and the release gate when a field of the data has no row here, when a row names a field that no longer exists, when a cell is empty, or when "Checked by" names a file that is not in the repository.

How to read it:

- **Where** lists the kinds of object the field appears in: `meta`, `source`, `active` and `withdrawn` (currency entries), `countries[]` (the objects inside `countries`), `non_iso`. A field that appears in several kinds has one row.
- **Source** restates section 1's categories for the field. It is the primary source the value is verified against, not a record of where a specific entry came from (see "No per-entry `source` field" in section 5).
- **Checked by** names what can fail when the value is wrong in form. `schema.json` is enforced through `tools/validate.py`. A row that says "type only" is checked for its JSON type and nothing else; a value that is the right type and wrong is caught by review, not by a tool.
- Rows were assembled from `schema.json`, the ADRs, section 1 and the code of each checker. Refresh triggers for ISO-derived fields are the amendment; for the rest they are the annual spot-check or the release.

| Field | Where | Source | Refresh trigger | Checked by |
|---|---|---|---|---|
| `amendment` | meta | The amendment number printed on the SIX Group amendment PDF last applied; mirrors `source.last_amendment_applied` | Each amendment | `schema.json` (integer 1-999), `tools/validate.py` |
| `amendment_date` | meta | The date printed on that amendment's PDF (see "Amendment dates") | Each amendment | `schema.json` (date), `tools/validate.py` |
| `central_bank` | active | The central bank's own website, English "About" page (section 1) | Annual spot-check | `schema.json` (required), `tools/validate.py` |
| `classification` | active | ADR 0003: which ISO 4217 list the code sits on (circulating, fund, settlement, indexation) | When an amendment adds or reclassifies a code | `tools/enrich_field.py` (`--field classification --check`, CI and gate), `schema.json` (enum), `tools/validate.py` |
| `code` | active, withdrawn, non_iso, countries[] | ISO 4217 alphabetic code (Table A.1 and amendments) for currency entries; the instrument's ticker or convention for non-ISO entries; ISO 3166-1 alpha-2 for `countries[]` | Per amendment; per ISO 3166 release for `countries[]` | `schema.json` (patterns), `tools/validate.py`, `tools/check_country_codes.py` (`countries[].code` against the vendored ISO 3166 snapshot) |
| `code_lifetime` | withdrawn | ADR 0006: `from` is ISO's assignment date when documented, else null; `to` equals `withdrawn_date` | Each withdrawal | `tools/enrich_field.py` (`--field code_lifetime --check`), `tools/validate.py`, `tests/test_iso_codes.py` |
| `commodity_source` | source | Names the commodity code convention the non-ISO commodities follow (LBMA, section 1) | When that convention changes | `schema.json` (type only) |
| `conversion_rate` | withdrawn | Council Regulation (EC) No 2866/98 and successors for euro changeovers; the issuing authority's decree otherwise | Never (historical fact) | `schema.json` (number), `tools/validate.py`, `tests/test_iso_codes.py` |
| `countries` | active | ISO 3166-1 and the UN Statistics Division membership lists (section 1) | Annual spot-check | `schema.json` (array), `tools/validate.py` (at least one country), `tools/check_country_codes.py` |
| `crypto_source` | source | Names the CoinGecko `/coins/markets` endpoint (section 1) | Weekly (manual) | `schema.json` (type only) |
| `description` | meta | Written by the maintainer | Rarely | `schema.json` (type only) |
| `entity` | active, withdrawn, non_iso | The ISO 4217 table's Entity column for currency entries; the issuer or defining body for non-ISO entries | Per amendment; annual spot-check | `schema.json` (required), `tools/validate.py` |
| `introduced` | non_iso | The instrument's own launch documentation | When the entry is added | `schema.json` (date) |
| `is_independent` | active, non_iso | Peg information (section 1): central bank and AREAER; true when the currency floats or is a managed float, false when hard-pegged | Annual spot-check | `schema.json` (boolean), `tools/validate.py` |
| `iso_status` | non_iso | ISO 4217's own lists: whether the code is officially defined | When an amendment adds or withdraws a code | `schema.json` (enum), `tools/validate.py` |
| `last_amendment_applied` | source | The amendment number on the SIX Group amendment PDF | Each amendment | `tools/check_amendments.py` (weekly monitor compares it with the SIX page), `tools/validate.py`, `schema.json` |
| `last_amendment_date` | source | The date printed on that amendment's PDF (see "Amendment dates") | Each amendment | `schema.json` (date), `tools/validate.py` |
| `last_verified` | source | The UTC date the amendment PDF was last read (see "Amendment dates") | Each amendment or re-verification | `schema.json` (date), `tools/validate.py` |
| `license` | meta | The maintainer's choice (Apache-2.0) | Never expected | `schema.json` (enum) |
| `maintenance_agency` | source | ISO 4217 names SIX Group as its maintenance agency | Never expected | `schema.json` (enum) |
| `maintenance_agency_url` | source | The agency's published address | If the agency moves | `schema.json` (https pattern) |
| `market_cap_rank` | non_iso | CoinGecko `/coins/markets` rank (section 1) | Weekly (manual, `tools/refresh_market_caps.py`) | `schema.json` (integer, at least 1), `tests/test_refresh_market_caps.py` |
| `minor_units` | active, withdrawn, non_iso | ISO 4217:2015 for ISO codes, cross-checked against the central bank; a price-precision convention for non-ISO entries | Annual spot-check | `schema.json` (integer range), `tools/validate.py` |
| `name` | active, withdrawn, non_iso, countries[] | The ISO 4217 currency name for currency entries; the instrument's name for non-ISO entries; the country's English short name for `countries[]` | Per amendment; annual spot-check | `schema.json` (type only), `tools/validate.py` |
| `note` | active, withdrawn, non_iso | Written by the maintainer. ADR 0005: `note` explains, `source_url` links. A non-ISO note must say the entry is not an ISO 4217 code (section 6) | With the entry | `tools/validate.py` (non-ISO disclaimer), `schema.json`, `tests/test_iso_codes.py` |
| `numeric` | active, withdrawn, non_iso | ISO 4217:2015 Table A.1 and the SIX Group amendment PDFs; non-ISO entries carry one only where ISO assigned one | Per amendment | `schema.json` (three digits), `tools/validate.py`, `tools/enrich_field.py` (reuse derivation) |
| `numeric_reused` | active | ADR 0004 and ADR 0008: derived, true when the numeric code also appears on a withdrawn entry | Whenever a code is added or withdrawn | `tools/enrich_field.py` (`--field numeric_reused --check`, CI and gate), `tools/validate.py` |
| `peg_band_pct` | active | Central bank and the IMF AREAER (section 1) | Annual spot-check | `schema.json`, `tools/validate.py` |
| `peg_mechanism` | non_iso | The issuer's transparency page (section 1) | Weekly (manual) | `schema.json` (enum), `tools/validate.py` |
| `peg_rate` | active | Central bank and the IMF AREAER (section 1) | Annual spot-check | `schema.json`, `tests/test_iso_codes.py` |
| `peg_type` | active | The maintainer's reading of `pegged_to`: single anchor, basket or undisclosed | Annual spot-check | `schema.json`, `tools/validate.py` |
| `pegged_since` | active | The central bank, for the date the peg was established | Annual spot-check | `schema.json` (date), `tools/validate.py` |
| `pegged_to` | active, non_iso | Central bank and AREAER for currencies; the fiat currency the issuer tracks for stablecoins | Annual spot-check; weekly for stablecoins | `schema.json` (pattern for stablecoins), `tools/validate.py` (references resolve) |
| `project` | meta | The repository address, set by the maintainer | Never expected | `schema.json` (https://github.com/ pattern) |
| `relationship` | countries[] | UN Statistics Division and ISO 3166-1; the five values are defined in section 4, step 4 | Annual spot-check | `schema.json` (enum), `tools/validate.py` |
| `replaced_by` | withdrawn | The ISO 4217 amendment or national decree that names the replacement | Each withdrawal | `schema.json` (pattern), `tools/validate.py`, `tests/test_iso_codes.py` |
| `schema_version` | meta | `schema.json`'s `$id`: the format-contract axis, separate from the data version | When the schema changes | `tools/check_version_consistency.py`, `schema.json` |
| `source_url` | active, withdrawn | ADR 0005: the entry's primary source address | With the entry | `tools/enrich_field.py` (`--field source_url --check`, CI and gate), `schema.json`, `tools/validate.py` |
| `stablecoin_source` | source | Names the issuer transparency pages and CoinGecko (section 1) | Weekly (manual) | `schema.json` (type only) |
| `standard` | source | The edition of ISO 4217 the data follows | When ISO publishes a new edition | `schema.json` (enum) |
| `symbol` | active, withdrawn, non_iso | Unicode CLDR currency data and the central bank (section 1) | Annual spot-check | `schema.json` (type only), `tools/validate.py`, `tests/test_export_csv.py` |
| `type` | non_iso | The maintainer's classification of the instrument; an enumerated value for special-purpose entries | When the entry is added | `schema.json` (enum for special-purpose), `tools/validate.py` |
| `updated` | meta | The UTC date of the release that last changed the data, set by `scripts/release.sh` | Every release | `tools/check_registry_freshness.py` (180 days), `tools/validate.py`, `schema.json` |
| `verified_against` | source | The maintainer's list of sources consulted in the last verification | Each verification | `schema.json` (array only) |
| `version` | meta | The `VERSION` file, bumped by `scripts/release.sh` | Every release | `tools/check_version_consistency.py`, `schema.json` |
| `withdrawn_date` | withdrawn | The date the currency ceased to be legal tender: the ISO 4217 amendment's effective date or the national legislation | Each withdrawal | `schema.json` (date), `tools/validate.py`, `tools/enrich_field.py` (`code_lifetime.to` must equal it), `tests/test_iso_codes.py` |

## Amendment dates

`meta.amendment_date` and `source.last_amendment_date` hold the date printed on the amendment's PDF at
`currency-iso.org` (amendment 180: 2025-09-22). They are not effective dates: one amendment has one issue
date and can carry several effective dates (180: 2026-01-01, with BGN and EUR in parallel circulation until
2026-01-31). `source.last_verified` is the UTC date the PDF was last read. Before v1.8.0 these fields read
`2025-06-15` for amendment 179, which matches neither that PDF's date (2025-05-02) nor its effective date
(2025-05-12).
