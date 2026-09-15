# Provenance

Where the data in `iso4217.json` comes from, how often each layer is refreshed, and how to audit a specific value.

This document exists because "canonical registry" is a claim, and claims about data need evidence. What follows is that evidence, stated plainly, including the limitations.

---

## 1. Sources by category

| Data category | Primary source | Cross-check | Refresh cadence |
|---------------|---------------|-------------|-----------------|
| Active ISO 4217 alphabetic codes | ISO 4217:2015 plus all published amendments through Amendment 179 | SIX Group amendment summary (`currency-iso.org`) | Per amendment (quarterly or slower) |
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

This document describes the provenance discipline in effect as of v1.5.1. If the discipline changes — for example, if per-entry source fields are added, or if signed releases ship — this document will be updated alongside the change, and the CHANGELOG entry will reference it.

**Last updated:** 2026-09-15
**Applies to registry version:** 1.5.0 (data), 1.5.1 (documentation)
**Maintainer:** [github.com/slimissa](https://github.com/slimissa)


