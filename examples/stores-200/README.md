# stores-200 - a fact table, a registry, and six questions

## 1. What this is

A fictional chain of 200 stores in 25 countries, one year of daily revenue (73,200 rows), and six business questions answered by joining that fact table to the ISO 4217 registry's CURATED and AGGREGATED Parquet files. The stores are invented. The countries, currencies, minor units, peg anchors, and peg rates are the registry's. The demo is a companion to the registry, not part of its release pipeline.

## 2. Run it

The demo needs two packages the registry itself does not: `pyarrow` and `duckdb`. Install them once with `pip install -r requirements.txt`. Then:

```bash
cd examples/stores-200
python3 generate_facts.py
python3 analyze.py
```

No Docker, no virtual environment, no services. Both scripts finish in a few seconds (under one second of CPU time each in testing). `generate_facts.py` is deterministic: two runs write byte-identical files. `facts.parquet` is git-ignored; `stores.json` is committed and regenerated identically on every run.

DuckDB is the choice for the queries because it reads Parquet natively and keeps the SQL legible. It was tested only on DuckDB 1.5.6. `requirements.txt` sets 0.9 as the floor, but versions below 1.5 were not tried.

## 3. Why this demo exists

A fact table records what happened: this store, this day, this much money, in this currency. It should not also record which region that currency belongs to, what it is pegged to, how many decimals it has, or whether it is a circulating currency or a fund code. Those are facts about currencies, they change on a different schedule from sales, and every fact table that stores its own copy gets them subtly wrong in its own way.

The registry is the join dimension: one versioned place that answers those questions, so the fact table carries only a currency code. A store in Morocco reports in MAD. Finance wants EUR, a regulator wants USD, a chart wants "Africa". None of those is the fact table's problem.

## 4. The 200 stores

`generate_facts.py` builds the stores from a 25-country plan and a fixed seed. Nothing about the 200 rows is typed by hand.

What the registry decides, not the script:

- The country must resolve in `tools/iso3166_snapshot.json`, in its `countries.active` list.
- The currency is the one `circulating` currency `iso4217.countries.parquet` lists for the country. A country with none or several stops the generator. This is why a store in Chile prices in CLP and never in CLF, and a store in Switzerland never in CHE or CHW.
- Minor units come from `iso4217.parquet`: the JPY store counts yen, the USD store cents, the BHD store fils (three decimals).

The ten largest countries by store count:

| Country | Currency | Stores |
|---------|----------|--------|
| US | USD | 40 |
| GB | GBP | 20 |
| DE | EUR | 15 |
| FR | EUR | 15 |
| JP | JPY | 10 |
| CN | CNY | 10 |
| IN | INR | 8 |
| BR | BRL | 7 |
| CA | CAD | 7 |
| KR | KRW | 6 |

AU and MX also have 6. The remaining countries have 2 to 5 stores each. The 19 countries after the head six were chosen for coverage, not for GDP: pegged to USD (AE, SA, BH), pegged to EUR (DK, SN), pegged to a basket (MA), unpegged (US, GB, DE and most others), a three-decimal currency (BH), zero-decimal currencies (JP, KR, CL, SN), a code that ISO 3166 also assigns to a withdrawn entry (SK), and the two codes the ISO 3166 snapshot does not place in a region (TW, XK).

| Real (from the registry or ISO 3166) | Synthetic (defined in `generate_facts.py`) |
|--------------------------------------|--------------------------------------------|
| Country codes and which ones exist | Which 25 countries, and how many stores each |
| Each country's circulating currency | Store names, tax rates, opening dates |
| Minor units, peg anchors, peg types, peg rates | Daily transactions, baskets, revenue |
| Regions and subregions (ISO 3166 snapshot) | Exchange rates for currencies the registry does not peg |

The synthetic exchange rates are round numbers (EUR 0.92 per USD, JPY 150, and so on). They are not market data. The registry has no market rates, by design: a rate for a floating currency is a fact about a day, not about the currency. Wherever a query depends on one, the output says so.

## 5. The six queries

Every query prints a heading, a one-line explanation, and a table. All of them read only registry artifacts below RAW; none opens the registry's JSON file.

**Q1 - Revenue by region.** Sums revenue per region and converts it to USD, using the registry's peg rate where the registry has one and a demo rate where it does not. It reports how many stores used each rate path. A store's region is its country's region from the ISO 3166 snapshot. `currencies_by_region.parquet` is then used for what its grain makes it good at: checking that each store's (region, currency) pair exists. The output also shows the trap: joining stores to `currencies_by_region.parquet` on currency alone returns several rows per store, because USD and EUR circulate in several regions, and overcounts revenue by a large factor. The table's grain is (region, currency) and the join key has to be too. This differs from a plain "join on currency to get the region"; that join does not work for any currency used in more than one region.

**Q2 - Currency exposure.** Per currency: stores, revenue in local minor units, minor units, classification, pegged flag, peg type. Classification comes from `iso4217.countries.parquet`, which carries it as a denormalized currency attribute; `iso4217.parquet` does not have that column. The pegged flag is `pegged_to IS NOT NULL` on `iso4217.parquet`. The point of the table: minor-unit totals are not comparable across rows, and the registry is what says how many decimals each currency has.

**Q3 - Peg concentration.** For each anchor currency, the revenue of every store whose currency is pegged to it, joined through `pegs_summary.parquet`'s member lists. The output also names what `pegs_summary.parquet` does not cover: a basket peg such as MAD has no single anchor. The query includes a cross-check, and the honest result of it is that `GROUP BY pegged_to` on the flat `iso4217.parquet` gives the same totals. What `pegs_summary.parquet` adds is the anchor's name, the full member list (including members the chain has no store in), and the count of anchors, so the chain's exposure can be read against the registry's whole peg universe.

**Q4 - Countries the registry has no region for.** Stores in XK (Kosovo) and TW (Taiwan): how many, and how much revenue. The ISO 3166 snapshot does not place either in a region, so the registry keeps them with a NULL region instead of inventing one, and `currencies_by_region.parquet` has rows for them with a NULL `region`. The query also shows the cost of not writing for the gap: an ordinary `=` join on region silently drops those stores, because NULL does not equal NULL. `IS NOT DISTINCT FROM` keeps them. The absence is information, and the join has to be written to preserve it.

**Q5 - Coverage over time.** A proof of concept, and a negative result. The question as posed was whether each store's currency existed in the registry when the store opened. `coverage_timeline.parquet` has one row per release with currency counts; it has no per-currency rows, so it cannot say when a currency began. What it can do is an as-of join on release dates. Every store opened between 2010 and 2023, and the registry's first release is dated 2026-07-29, so the as-of join finds no release for any store. That is the finding: the registry is a versioned snapshot, not a history of currencies, and "opened after its currency's most recent registry appearance" cannot be computed from any shipped artifact. It would need per-currency start dates. This query is contrived to make that point; the demo's date range is too narrow for the interesting case to fire.

**Q6 - Pegged versus not pegged.** Distinct currencies and revenue share for pegged-to-one-anchor, pegged-to-a-basket, and not pegged, then the same split by region. The region comes from the store's country, the peg status from the registry, and the fact table has neither. Be careful what the result is evidence of: the pegged versus not-pegged split alone can be read off the flat `iso4217.parquet`; the by-region split uses `currencies_by_region.parquet`'s `is_pegged` on the (region, currency) pair, and the script checks that it agrees with the flat file. "Not pegged" means no peg is recorded. It does not mean freely floating.

## 6. What this demo is not

It is not a real company, real revenue, or a real analytics pipeline. Store names, tax rates, opening dates, and every revenue number are synthetic. The demo exchange rates are round numbers, not market data. Revenue is not corrected for taxes, returns, or anything else. Do not use this as a template for production: a real pipeline would take exchange rates from a dated rate source and would keep the fact table's currency code as the only link to the registry.

## 7. Related

- [`docs/LAYERS.md`](../../docs/LAYERS.md) - the RAW / CURATED / AGGREGATED model this demo respects.
- [`docs/JOINS.md`](../../docs/JOINS.md) - the registry's cross-registry edges; this demo uses the country edge to ISO 3166.
- [`README.md`](../../README.md) - the registry itself.
