# Country-currency allow-list

Every place where ISO 4217's `countries[]` and ISO 3166's `currency_codes` legitimately disagree, one entry per
`(country, currency, side)`. The decisions and the reasoning are in
[ADR 0010](./decisions/country-currency-taxonomy.md). `tools/check_country_codes.py --membership` reads the JSON
block below and fails on any disagreement that is not listed, and on any entry that no longer matches a
disagreement, so this file cannot rot.

- `4217-only`: the registry lists the currency for the country; ISO 3166 does not.
- `3166-only`: ISO 3166 lists the currency for the country; the registry does not.
- Categories: `fix-in-3166`, `allow-list-with-reason`, `out-of-scope-historical`. A `fix-in-4217` decision is made
  in the registry and never appears here.
- When the vendored ISO 3166 snapshot moves, regenerate nothing by hand: run the check, read what it reports, and add
  a reasoned entry (or fix the registry) in the same commit as the re-vendor.

```json
{
  "snapshot_version": "1.8.0",
  "entries": [
    {
      "country": "BO",
      "currency": "BOV",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry BOV `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes BOV"
    },
    {
      "country": "BT",
      "currency": "INR",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry INR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes INR"
    },
    {
      "country": "CH",
      "currency": "CHE",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry CHE/CHW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[CHF]"
    },
    {
      "country": "CH",
      "currency": "CHW",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry CHE/CHW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[CHF]"
    },
    {
      "country": "CL",
      "currency": "CLF",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry CLF `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes CLF"
    },
    {
      "country": "CO",
      "currency": "COU",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry COU `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes COU"
    },
    {
      "country": "CU",
      "currency": "CUC",
      "side": "4217-only",
      "category": "out-of-scope-historical",
      "reason": "CUC was demonetized in January 2021. 3166 lists CUP only. The registry keeps CUC because its own `source_url` still points at the ISO 4217 entry.",
      "source": "registry CUC note ('Demonetized January 2021'); 3166 snapshot `currency_codes`=[CUP]; date 2021-01",
      "date": "2021-01"
    },
    {
      "country": "FK",
      "currency": "GBP",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP"
    },
    {
      "country": "GI",
      "currency": "GBP",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP"
    },
    {
      "country": "GS",
      "currency": "FKP",
      "side": "3166-only",
      "category": "fix-in-3166",
      "reason": "3166 says FKP, the registry says GBP. Secondary mirrors of ISO 4217 list one show 'No universal currency' for GS, so neither side is the standard's own statement. GBP matches the territory's de facto currency; FKP is the outlier.",
      "source": "3166 snapshot v1.8.0 `currency_codes`=[FKP]; registry GBP `territory`; secondary mirrors only (Thomson Reuters Tracker list, SBP Code List No. 2); OBP not read",
      "reference": "ISO 3166 issue not yet filed (owner action); ADR 0010 row GS"
    },
    {
      "country": "GS",
      "currency": "GBP",
      "side": "4217-only",
      "category": "fix-in-3166",
      "reason": "3166 says FKP, the registry says GBP. Secondary mirrors of ISO 4217 list one show 'No universal currency' for GS, so neither side is the standard's own statement. GBP matches the territory's de facto currency; FKP is the outlier.",
      "source": "3166 snapshot v1.8.0 `currency_codes`=[FKP]; registry GBP `territory`; secondary mirrors only (Thomson Reuters Tracker list, SBP Code List No. 2); OBP not read",
      "reference": "ISO 3166 issue not yet filed (owner action); ADR 0010 row GS"
    },
    {
      "country": "HT",
      "currency": "USD",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry USD `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes USD"
    },
    {
      "country": "LS",
      "currency": "ZAR",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR"
    },
    {
      "country": "MX",
      "currency": "MXV",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry MXV `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes MXV"
    },
    {
      "country": "NA",
      "currency": "ZAR",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR"
    },
    {
      "country": "SH",
      "currency": "GBP",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry GBP `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes GBP"
    },
    {
      "country": "SV",
      "currency": "SVC",
      "side": "4217-only",
      "category": "out-of-scope-historical",
      "reason": "El Salvador dollarized in 2001. 3166 lists USD only. The registry keeps SVC because ISO 4217 still lists it; the registry is a snapshot of ISO's list, not of circulation.",
      "source": "registry SVC note ('dollarized to USD in 2001', 'ISO 4217 continues to list as active'); 3166 snapshot `currency_codes`=[USD]; date 2001-01-01",
      "date": "2001-01-01"
    },
    {
      "country": "SZ",
      "currency": "ZAR",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry ZAR `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes ZAR"
    },
    {
      "country": "US",
      "currency": "USN",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry USN/USS `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[USD]"
    },
    {
      "country": "US",
      "currency": "USS",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry USN/USS `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[USD]"
    },
    {
      "country": "UY",
      "currency": "UYI",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry UYI/UYW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[UYU]"
    },
    {
      "country": "UY",
      "currency": "UYW",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry UYI/UYW `classification`=fund; 3166 snapshot v1.8.0 `currency_codes`=[UYU]"
    },
    {
      "country": "VE",
      "currency": "VED",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "3166 `currency_codes` lists the circulating currency only. The ISO 4217 code is a funds/indexation unit issued for the same country, not a currency of general circulation (registry `classification` = fund or indexation).",
      "source": "registry VED `classification` field; 3166 snapshot v1.8.0 `currency_codes` excludes VED"
    },
    {
      "country": "XK",
      "currency": "EUR",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "XK is a user-assigned code, not an officially assigned ISO 3166-1 code, so 3166 carries `currency_codes`=null. The registry records the unilateral euro adoption.",
      "source": "3166 snapshot v1.8.0 status `user-assigned`, `currency_codes`=null; registry EUR `adopting`"
    },
    {
      "country": "ZW",
      "currency": "USD",
      "side": "4217-only",
      "category": "allow-list-with-reason",
      "reason": "The registry's `relationship` field records a currency that circulates alongside the country's own currency (`parallel`/`adopting`). 3166 `currency_codes` lists only the territory's own ISO-assigned currency.",
      "source": "registry USD `countries[]` relationship; 3166 snapshot v1.8.0 `currency_codes` excludes USD"
    }
  ]
}
```
