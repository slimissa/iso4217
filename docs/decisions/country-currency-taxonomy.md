# ADR 0010 - Country-currency taxonomy

**Status:** Proposed. It becomes Accepted when the owner commits it after checking the rows marked [Likely] or [Guess] against the ISO 4217 OBP page (see "Verification still owed").
**Date:** 2026-10-25
**Context:** v1.9.2 - closing P5-03. Spine sentence: "A consumer who downloads the wheel gets a valid registry."

## Context

`check_country_codes.py` asks whether every `countries[].code` in `iso4217.json` resolves in the vendored ISO 3166
snapshot. It never asks whether the currency agrees. Comparing 4217 `countries[]` with the snapshot's
`currency_codes` (v1.8.0) gives **25 countries and 29 country-currency pairs** that differ. Every
one of them is classified below. The set was recomputed from the tree, not copied from the audit.

Two corrections to the brief that opened this release:

- Panama and Ecuador are not among the disagreements. Both sides already agree for PA (PAB and USD) and EC (USD). Only
  Zimbabwe from that list is in the set (ZW: USD is `adopting` in 4217, absent from 3166, while 3166 does list USD
  for PA; that inconsistency is upstream's).
- EU and UK have `currency_codes` null in 3166 (status `exceptionally-reserved`) and no currency in 4217. That is
  agreement, not a disagreement. The naive diff shows 27 rows; the real count is 25.

## Decision

### The comparison

For each country code, let `S4217` be the set of currency codes of **active** registry currencies whose `countries[]`
list it (withdrawn currencies are excluded: 3166 carries current currencies only), and `S3166` the snapshot's
`currency_codes` (null counts as empty). A **disagreement atom** is `(country, currency, side)`:

- `4217-only`: the currency is in `S4217` and not in `S3166`.
- `3166-only`: the currency is in `S3166` and not in `S4217`.

Both directions are checked. Funds and indexation codes are not skipped by rule; they are allow-listed explicitly,
so a new fund code on a country is a visible decision.

### The allow-list

`docs/COUNTRY_CURRENCY_ALLOWLIST.md` holds one fenced JSON block. Each entry is
`{country, currency, side, category, reason, source}` (plus `date` for `out-of-scope-historical`). The check fails on:

1. any atom not in the allow-list;
2. any allow-list entry that matches no current atom (**stale entry**), so the list cannot rot;
3. an entry with an empty reason or source, an unknown category, or a country absent from the snapshot;
4. a `fix-in-4217` entry. That category means "change the registry", so once the registry is fixed no entry may
   remain.

### The four categories

| Category | Meaning | Action |
|---|---|---|
| `fix-in-4217` | The registry's `countries[]` is wrong | Change `iso4217.json`. No allow-list entry. |
| `fix-in-3166` | ISO 3166's `currency_codes` is wrong | File an issue upstream; allow-list with the reference until the vendored snapshot moves. |
| `allow-list-with-reason` | The two standards describe different things, legitimately | Allow-list with the reason. |
| `out-of-scope-historical` | The currency changed on a date; the registry mirrors ISO's list | Allow-list with the date. |

### The 25 rows

Counts: `fix-in-4217` 4, `fix-in-3166` 1, `allow-list-with-reason` 18, `out-of-scope-historical` 2.

| # | Country | Disagreement | Category | Reason | Source | Action | Confidence |
|---|---|---|---|---|---|---|---|
| 1 | AS American Samoa | USD (3166-only) | `fix-in-4217` | 3166 assigns USD; 4217 `countries[]` omits the territory although USD is its legal tender. | 3166 snapshot v1.8.0 `currency_codes`=[USD]; ISO 4217 list one (OBP) - OBP page not read this session | Add AS to USD `countries[]` as `territory`. | [Likely] |
| 2 | AX Aland Islands | EUR (3166-only) | `fix-in-4217` | 3166 assigns EUR; 4217 `countries[]` omits the territory. | 3166 snapshot v1.8.0 `currency_codes`=[EUR]; ISO 4217 list one (OBP) - OBP page not read this session | Add AX to EUR `countries[]` as `territory`. | [Likely] |
| 3 | TF French Southern Territories | EUR (3166-only) | `fix-in-4217` | 3166 assigns EUR; 4217 `countries[]` omits the territory. | 3166 snapshot v1.8.0 `currency_codes`=[EUR]; ISO 4217 list one (OBP) - OBP page not read this session | Add TF to EUR `countries[]` as `territory`. | [Likely] |
| 4 | UM United States Minor Outlying Islands | USD (3166-only) | `fix-in-4217` | 3166 assigns USD; 4217 `countries[]` omits the territory. | 3166 snapshot v1.8.0 `currency_codes`=[USD]; ISO 4217 list one (OBP) - OBP page not read this session | Add UM to USD `countries[]` as `territory`. | [Likely] |
| 5 | GS South Georgia and the South Sandwich Islands | FKP (3166-only); GBP (4217-only) | `fix-in-3166` | 3166 says FKP, the registry says GBP. Secondary mirrors of ISO 4217 list one show 'No universal currency' for GS, so neither side is the standard's own statement. GBP matches the territory's de facto currency; FKP is the outlier. | 3166 snapshot v1.8.0 `currency_codes`=[FKP]; registry GBP `territory`; secondary mirrors only (Thomson Reuters Tracker list, SBP Code List No. 2); OBP not read | File an issue in the ISO 3166 repo to change GS to GBP; keep both atoms allowed until it ships, then the stale-entry check forces their removal. | [Guess] |
| 6 | BO Bolivia | BOV (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry BOV `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes BOV | Allow-list. | [Confirmed] |
| 7 | BT Bhutan | INR (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry INR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes INR | Allow-list. | [Confirmed] |
| 8 | CH Switzerland | CHE (4217-only); CHW (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry CHE/CHW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[CHF] | Allow-list. | [Confirmed] |
| 9 | CL Chile | CLF (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry CLF `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes CLF | Allow-list. | [Confirmed] |
| 10 | CO Colombia | COU (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry COU `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes COU | Allow-list. | [Confirmed] |
| 11 | FK Falkland Islands | GBP (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP | Allow-list. | [Confirmed] |
| 12 | GI Gibraltar | GBP (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP | Allow-list. | [Confirmed] |
| 13 | HT Haiti | USD (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry USD `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes USD | Allow-list. | [Confirmed] |
| 14 | LS Lesotho | ZAR (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR | Allow-list. | [Confirmed] |
| 15 | MX Mexico | MXV (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry MXV `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes MXV | Allow-list. | [Confirmed] |
| 16 | NA Namibia | ZAR (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR | Allow-list. | [Confirmed] |
| 17 | SH Saint Helena | GBP (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP | Allow-list. | [Confirmed] |
| 18 | SZ Eswatini | ZAR (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR | Allow-list. | [Confirmed] |
| 19 | US United States | USN (4217-only); USS (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry USN/USS `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[USD] | Allow-list. | [Confirmed] |
| 20 | UY Uruguay | UYI (4217-only); UYW (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry UYI/UYW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[UYU] | Allow-list. | [Confirmed] |
| 21 | VE Venezuela | VED (4217-only) | `allow-list-with-reason` | 3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation). | registry VED `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes VED | Allow-list. | [Confirmed] |
| 22 | XK Kosovo | EUR (4217-only) | `allow-list-with-reason` | XK is a user-assigned code, not an officially assigned ISO 3166-1 code, so 3166 carries `currency_codes`=null. The registry records the unilateral euro adoption. | 3166 snapshot v1.8.0 status `user-assigned`, `currency_codes`=null; registry EUR `adopting` | Allow-list; revisit only if ISO assigns the code. | [Likely] |
| 23 | ZW Zimbabwe | USD (4217-only) | `allow-list-with-reason` | The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency. | registry USD `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes USD | Allow-list. | [Confirmed] |
| 24 | CU Cuba | CUC (4217-only) | `out-of-scope-historical` | CUC was demonetized in January 2021. 3166 lists CUP only. The registry keeps CUC because its own `source_url` still points at the ISO 4217 entry. | registry CUC note ('Demonetized January 2021'); 3166 snapshot `currency_codes`=[CUP]; date 2021-01 | Allow-list with date 2021-01. Open question for the owner: whether CUC should move to `withdrawn`; not decided here. | [Likely] |
| 25 | SV El Salvador | SVC (4217-only) | `out-of-scope-historical` | El Salvador dollarized in 2001. 3166 lists USD only. The registry keeps SVC because ISO 4217 still lists it; the registry is a snapshot of ISO's list, not of circulation. | registry SVC note ('dollarized to USD in 2001', 'ISO 4217 continues to list as active'); 3166 snapshot `currency_codes`=[USD]; date 2001-01-01 | Allow-list with date 2001-01-01. | [Likely] |

## Rationale

Twenty-one of the 25 countries need no change to the data. They disagree because ISO 3166 lists one currency per
territory while ISO 4217 also lists funds and indexation codes (8 rows), the registry records circulating-alongside
currencies (9 rows), and two rows are superseded currencies (CU, SV). Treating those as errors would delete information. The four `fix-in-4217` rows are different in kind: 3166
names a currency for a territory and the registry says nothing, so a consumer joining 3166 to 4217 loses the row.

## Verification still owed

- **[Guess]** The "Source" column cites the 3166 snapshot and registry fields, which were read in this session. For
  AS, UM, AX, TF, GS and XK it also names the ISO 4217 OBP entry, which was **not** read (the page needs a browser).
  For GS the only evidence found is secondary mirrors showing "No universal currency". The owner confirms these six
  against OBP before this ADR is Accepted.
- **Open question, not decided here:** whether CUC (demonetized January 2021) belongs in `withdrawn`. It is
  allow-listed as historical; moving it is a registry decision with its own release.

## Consequences

- 4 countries gain a `countries[]` entry on USD or EUR. This is a data change, hence a minor for the data and a
  patch for the registry.
- Allow-list entries: 25 after the four fixes
  (the 4 `fix-in-4217` atoms disappear when the data is fixed).
- When the vendored 3166 snapshot moves (F31 currently reports upstream v1.8.1), new disagreements fail the check
  and need a row here before the re-vendor lands.
- The 3-to-4 direction is now enforced on the 4217 side. The 3166 repo's own side is not audited here.
