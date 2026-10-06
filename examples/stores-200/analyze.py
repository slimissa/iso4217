#!/usr/bin/env python3
"""
The six business questions of the stores-200 demo.

Reads facts.parquet and stores.json (made by generate_facts.py) and joins
them to the registry's CURATED and AGGREGATED artifacts with DuckDB. Prints
six sections, each with a heading, a one-line explanation, and a table.

Inputs
------
    facts.parquet                   this directory (synthetic)
    stores.json                     this directory (synthetic)
    iso4217.parquet                 CURATED     (real registry data)
    iso4217.countries.parquet       CURATED     (real registry data)
    currencies_by_region.parquet    AGGREGATED  (real registry data)
    pegs_summary.parquet            AGGREGATED  (real registry data)
    coverage_timeline.parquet       AGGREGATED  (real registry data)
    tools/iso3166_snapshot.json     vendored ISO 3166 reference (real)

Like the registry's own AGGREGATED layer, this script never reads the RAW
registry file. The only non-registry numbers are the demo's round-number
exchange rates for floating currencies (FLOATING_UNITS_PER_USD in
generate_facts.py), which are labelled synthetic wherever they matter.

How money is converted
----------------------
Every store's revenue is stored in minor units of its own currency. To get
USD equivalents this script divides by 10^minor_units (from the registry)
and then by the currency's units-per-USD rate:

    base         USD, rate 1.
    peg          single peg to USD: the registry's own peg_rate.
    peg+float    single peg to another anchor: the registry's peg_rate
                 times the demo's rate for the anchor.
    float        anything else, including basket pegs (the registry says
                 "pegged" but has no numeric rate): the demo's rate.

Two rules the queries follow
----------------------------
1. A store's region is its *country's* region (ISO 3166 snapshot,
   `countries.active` only). Joining a fact table to
   currencies_by_region on currency alone is wrong: USD circulates in
   several regions, so every USD store would be counted in each of them.
   Q1 shows the size of that error. The correct join key is the
   (region, currency) pair, which is the table's grain.

2. A missing region is NULL, and NULL does not equal NULL. Joins on region
   use IS NOT DISTINCT FROM so that Kosovo and Taiwan are kept. Q4 shows
   what an ordinary `=` join does to them.

Usage
-----
    python3 analyze.py

Exit codes
----------
    0  all six sections printed
    2  fatal (missing input, failed integrity check, failed cross-check)

Dependencies
------------
pyarrow and duckdb (see requirements.txt).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    import duckdb
except ImportError as e:
    print(f"FATAL: duckdb is required for this demo: {e}", file=sys.stderr)
    print("Install with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(2)

import generate_facts as gf

EXIT_OK: int = 0
EXIT_FATAL: int = 2

REPO_ROOT: Path = gf.REPO_ROOT
BY_REGION_PARQUET: Path = REPO_ROOT / "currencies_by_region.parquet"
PEGS_PARQUET: Path = REPO_ROOT / "pegs_summary.parquet"
TIMELINE_PARQUET: Path = REPO_ROOT / "coverage_timeline.parquet"

UNCLASSIFIED: str = "(unclassified)"

PATH_LABELS: Dict[str, str] = {
    "base": "USD itself (rate 1)",
    "peg": "registry peg rate (anchor USD)",
    "peg+float": "registry peg rate x demo anchor rate",
    "float": "demo floating rate",
}
PATH_ORDER: Sequence[str] = ("base", "peg", "peg+float", "float")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(EXIT_FATAL)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.0f}"
    return str(value)


def render_table(headers: Sequence[str], rows: Sequence[Sequence[Any]], indent: str = "  ") -> str:
    """Fixed-width terminal table; numbers right-aligned, text left-aligned."""
    body = [[_cell(v) for v in row] for row in rows]
    widths = [
        max(len(h), *(len(r[i]) for r in body)) if body else len(h)
        for i, h in enumerate(headers)
    ]
    numeric = [
        bool(rows) and all(isinstance(r[i], (int, float)) and not isinstance(r[i], bool)
                           for r in rows if r[i] is not None)
        for i in range(len(headers))
    ]

    def line(cells: Sequence[str]) -> str:
        parts = [c.rjust(w) if numeric[i] else c.ljust(w) for i, (c, w) in enumerate(zip(cells, widths))]
        return indent + "  ".join(parts).rstrip()

    rule = indent + "  ".join("-" * w for w in widths)
    return "\n".join([line(list(headers)), rule] + [line(r) for r in body])


def section(code: str, title: str, explanation: str) -> None:
    print(f"\n=== {code}: {title} ===\n")
    print(explanation + "\n")


def pct(part: float, whole: float) -> float:
    return 100.0 * part / whole if whole else 0.0


def pct_cell(part: float, whole: float) -> str:
    return f"{pct(part, whole):.1f}%"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _q(path: Path) -> str:
    """Quote a path for a SQL string literal."""
    return str(path).replace("'", "''")


def connect() -> "duckdb.DuckDBPyConnection":
    """
    Open an in-memory DuckDB with every input exposed as a view or table.

    Views over files: facts, stores, flat (iso4217.parquet), countries,
    by_region, pegs, timeline. Tables built in Python: store_region (the
    snapshot, active list only) and fx (units per USD and rate path for
    every currency a store uses).
    """
    for path in (
        gf.FACTS_PATH, gf.STORES_PATH, gf.CURRENCIES_PARQUET, gf.COUNTRIES_PARQUET,
        BY_REGION_PARQUET, PEGS_PARQUET, TIMELINE_PARQUET, gf.SNAPSHOT_PATH,
    ):
        if not path.exists():
            hint = " Run 'python3 generate_facts.py' first." if path in (gf.FACTS_PATH, gf.STORES_PATH) else ""
            _fatal(f"Input not found: {path}.{hint}")

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW facts AS SELECT * FROM read_parquet('{_q(gf.FACTS_PATH)}')")
    con.execute(
        "CREATE VIEW stores AS SELECT store_id, name, country, currency, "
        f"CAST(tax_rate AS DOUBLE) AS tax_rate, CAST(opened AS DATE) AS opened "
        f"FROM read_json_auto('{_q(gf.STORES_PATH)}')"
    )
    con.execute(f"CREATE VIEW flat AS SELECT * FROM read_parquet('{_q(gf.CURRENCIES_PARQUET)}') WHERE status = 'active'")
    con.execute(f"CREATE VIEW countries AS SELECT * FROM read_parquet('{_q(gf.COUNTRIES_PARQUET)}')")
    con.execute(f"CREATE VIEW by_region AS SELECT * FROM read_parquet('{_q(BY_REGION_PARQUET)}')")
    con.execute(f"CREATE VIEW pegs AS SELECT * FROM read_parquet('{_q(PEGS_PARQUET)}')")
    con.execute(
        "CREATE VIEW timeline AS SELECT version, TRY_CAST(date AS DATE) AS d, "
        "active_count, withdrawn_count, non_iso_count "
        f"FROM read_parquet('{_q(TIMELINE_PARQUET)}')"
    )

    # Region per country: the snapshot's active list only (see module docstring).
    snapshot = gf.load_snapshot_active()
    store_countries = sorted(
        {row[0] for row in con.execute("SELECT DISTINCT country FROM stores").fetchall()}
    )
    for country in store_countries:
        if country not in snapshot:
            _fatal(f"store country {country!r} not found in ISO 3166 snapshot countries.active")
    con.execute("CREATE TABLE store_region (country VARCHAR, region VARCHAR, subregion VARCHAR)")
    con.executemany(
        "INSERT INTO store_region VALUES (?, ?, ?)",
        [(c, snapshot[c]["region"], snapshot[c]["subregion"]) for c in store_countries],
    )

    # Exchange rates for every currency a store reports in.
    currencies = gf.load_currencies()
    store_currencies = sorted(
        {row[0] for row in con.execute("SELECT DISTINCT currency FROM stores").fetchall()}
    )
    con.execute("CREATE TABLE fx (currency VARCHAR, units_per_usd DOUBLE, path VARCHAR)")
    fx_rows = []
    for code in store_currencies:
        rate, path = gf.units_per_usd(code, currencies)
        fx_rows.append((code, rate, path))
    con.executemany("INSERT INTO fx VALUES (?, ?, ?)", fx_rows)

    # One row per store: its revenue in minor units and in USD equivalents.
    con.execute(
        """
        CREATE VIEW store_rev AS
        SELECT s.store_id, s.country, s.currency, s.opened,
               sr.region, f.minor_units, fx.path AS rate_path,
               t.rev_minor,
               CAST(t.rev_minor AS DOUBLE) / POW(10, f.minor_units) / fx.units_per_usd AS rev_usd
        FROM stores s
        JOIN (SELECT store_id, SUM(revenue_local) AS rev_minor FROM facts GROUP BY store_id) t
          ON t.store_id = s.store_id
        JOIN store_region sr ON sr.country = s.country
        JOIN flat f ON f.code = s.currency
        JOIN fx ON fx.currency = s.currency
        """
    )
    return con


def check_integrity(con: "duckdb.DuckDBPyConnection") -> None:
    """Fail loudly if the inputs are not the shape the queries assume."""
    n_stores = con.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
    n_rev = con.execute("SELECT COUNT(*) FROM store_rev").fetchone()[0]
    if n_rev != n_stores:
        _fatal(f"{n_stores - n_rev} store(s) failed to join to the registry (country or currency unresolved)")
    n_facts, n_keys = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT (store_id, date)) FROM facts"
    ).fetchone()
    if n_facts != n_keys:
        _fatal(f"facts.parquet has {n_facts - n_keys} duplicate (store_id, date) rows")
    orphans = con.execute(
        "SELECT COUNT(DISTINCT store_id) FROM facts WHERE store_id NOT IN (SELECT store_id FROM stores)"
    ).fetchone()[0]
    if orphans:
        _fatal(f"facts.parquet references {orphans} store_id value(s) missing from stores.json")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def q1(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q1", "Revenue by region",
        "A fact table has a country and a currency; the registry supplies the region and the rate path, "
        "and a careless join on currency alone overcounts.",
    )
    total = con.execute("SELECT SUM(rev_usd) FROM store_rev").fetchone()[0]

    rows = con.execute(
        """
        SELECT COALESCE(region, ?) AS label, COUNT(*) AS stores, SUM(rev_usd) AS usd
        FROM store_rev
        GROUP BY 1
        ORDER BY (label = ?), usd DESC, label
        """,
        [UNCLASSIFIED, UNCLASSIFIED],
    ).fetchall()
    print(render_table(
        ["region", "stores", "revenue (USD eq.)", "share"],
        [(r, n, usd, pct_cell(usd, total)) for r, n, usd in rows],
    ))
    print(f"\n  Total: {total:,.0f} USD equivalents across {sum(r[1] for r in rows)} stores.")

    print("\n  How each store's revenue was converted to USD:\n")
    path_counts = dict(con.execute("SELECT rate_path, COUNT(*) FROM store_rev GROUP BY 1").fetchall())
    print(render_table(
        ["rate path", "stores"],
        [(PATH_LABELS[p], path_counts.get(p, 0)) for p in PATH_ORDER if path_counts.get(p, 0)],
    ))
    pegged = path_counts.get("peg", 0) + path_counts.get("peg+float", 0)
    print(
        f"\n  {pegged} stores used a registry peg rate, {path_counts.get('float', 0)} used a demo floating rate, "
        f"{path_counts.get('base', 0)} reported in USD already."
    )
    print("  The demo rates are synthetic round numbers; the registry has no market rates, by design.")

    # Referential check on the correct key, and the cost of the wrong one.
    matched = con.execute(
        """
        SELECT COUNT(*) FROM store_rev sr
        WHERE EXISTS (SELECT 1 FROM by_region br
                      WHERE br.currency_code = sr.currency
                        AND br.region IS NOT DISTINCT FROM sr.region)
        """
    ).fetchone()[0]
    n_stores = con.execute("SELECT COUNT(*) FROM store_rev").fetchone()[0]
    naive_rows, naive_total = con.execute(
        """
        SELECT COUNT(*), SUM(sr.rev_usd)
        FROM store_rev sr JOIN by_region br ON br.currency_code = sr.currency
        """
    ).fetchone()
    print(
        f"\n  Check: {matched} of {n_stores} stores have their (region, currency) pair in currencies_by_region."
        f"\n  Trap:  joining stores to currencies_by_region on currency alone yields {naive_rows} rows for "
        f"{n_stores} stores and\n         {naive_total:,.0f} USD equivalents, {pct(naive_total, total) - 100:.0f}% "
        f"more than the true total. USD and EUR circulate in several regions."
    )


def q2(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q2", "Currency exposure",
        "Per currency: how many stores, how much revenue in local minor units, and what the registry says it is "
        "(classification from the countries file, pegged flag and minor units from iso4217.parquet).",
    )
    rows = con.execute(
        """
        SELECT sr.currency, COUNT(*) AS stores, SUM(sr.rev_minor) AS minor_total, f.minor_units,
               c.classification, f.pegged_to IS NOT NULL AS is_pegged, COALESCE(f.peg_type, '-') AS peg_type
        FROM store_rev sr
        JOIN flat f ON f.code = sr.currency
        JOIN (SELECT DISTINCT currency_code, classification FROM countries WHERE status = 'active') c
          ON c.currency_code = sr.currency
        GROUP BY sr.currency, f.minor_units, c.classification, f.pegged_to, f.peg_type
        ORDER BY stores DESC, sr.currency
        """
    ).fetchall()
    n_currencies = con.execute("SELECT COUNT(DISTINCT currency) FROM store_rev").fetchone()[0]
    if len(rows) != n_currencies:
        _fatal("a currency maps to more than one classification in iso4217.countries.parquet")
    print(render_table(
        ["currency", "stores", "revenue (minor units)", "minor_units", "classification", "pegged", "peg_type"],
        [(r[0], r[1], int(r[2]), r[3], r[4], bool(r[5]), r[6]) for r in rows],
    ))
    classes = sorted({r[4] for r in rows})
    print(f"\n  {n_currencies} currencies; classifications present: {', '.join(classes)}.")
    print("  Minor-unit totals are not comparable across rows: JPY has 0 decimals, USD 2, BHD 3.")


def q3(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q3", "Peg concentration",
        "Revenue (USD equivalents) of every store whose currency is pegged to each anchor, "
        "joined through pegs_summary.parquet's member lists.",
    )
    total = con.execute("SELECT SUM(rev_usd) FROM store_rev").fetchone()[0]
    rows = con.execute(
        """
        WITH members AS (
            SELECT anchor_code, anchor_name, currency_count, UNNEST(currencies) AS member FROM pegs
        )
        SELECT m.anchor_code, m.anchor_name, m.currency_count, COUNT(DISTINCT sr.currency),
               COUNT(*), SUM(sr.rev_usd)
        FROM members m JOIN store_rev sr ON sr.currency = m.member
        GROUP BY m.anchor_code, m.anchor_name, m.currency_count
        ORDER BY SUM(sr.rev_usd) DESC, m.anchor_code
        """
    ).fetchall()
    print(render_table(
        ["anchor", "anchor name", "members in registry", "members in chain", "stores", "revenue (USD eq.)", "share of chain"],
        [(a, n, mc, cc, s, usd, pct_cell(usd, total)) for a, n, mc, cc, s, usd in rows],
    ))
    n_anchors = con.execute("SELECT COUNT(*) FROM pegs").fetchone()[0]
    print(f"\n  The chain touches {len(rows)} of the registry's {n_anchors} single-peg anchors.")

    # What pegs_summary does not cover: pegs without a single anchor.
    other = con.execute(
        """
        SELECT sr.currency, f.peg_type, COUNT(*), SUM(sr.rev_usd)
        FROM store_rev sr JOIN flat f ON f.code = sr.currency
        WHERE f.peg_type IS NOT NULL AND f.peg_type <> 'single'
        GROUP BY sr.currency, f.peg_type ORDER BY sr.currency
        """
    ).fetchall()
    for code, peg_type, n, usd in other:
        print(
            f"  Not in pegs_summary: {code} is pegged by a {peg_type}, not to one anchor "
            f"({n} stores, {usd:,.0f} USD eq., {pct_cell(usd, total)})."
        )

    # Honest cross-check: the same totals fall out of the flat file's pegged_to.
    flat_totals = dict(con.execute(
        """
        SELECT f.pegged_to, SUM(sr.rev_usd) FROM store_rev sr JOIN flat f ON f.code = sr.currency
        WHERE f.peg_type = 'single' GROUP BY 1
        """
    ).fetchall())
    for anchor, _, _, _, _, usd in rows:
        if abs(flat_totals[anchor] - usd) > 1e-6 * max(1.0, usd):
            _fatal(f"pegs_summary and iso4217.parquet disagree on {anchor} revenue")
    print(
        "  Cross-check passed: GROUP BY pegged_to on iso4217.parquet gives the same anchor totals. "
        "pegs_summary adds\n  the anchor's name, its full member list (including members the chain does not use), "
        "and the anchor count."
    )


def q4(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q4", "Countries the registry has no region for",
        "XK and TW are real, valid country codes that the ISO 3166 snapshot does not place in a region; "
        "the registry keeps them with a NULL region instead of inventing one.",
    )
    total = con.execute("SELECT SUM(rev_usd) FROM store_rev").fetchone()[0]
    rows = con.execute(
        """
        SELECT country, currency, COUNT(*), SUM(rev_usd)
        FROM store_rev WHERE country IN ('XK', 'TW') GROUP BY 1, 2 ORDER BY 1
        """
    ).fetchall()
    print(render_table(
        ["country", "currency", "stores", "revenue (USD eq.)"], rows
    ))
    n = sum(r[2] for r in rows)
    usd = sum(r[3] for r in rows)
    print(f"\n  {n} stores, {usd:,.0f} USD equivalents ({pct_cell(usd, total)} of the chain).")

    null_rows = con.execute(
        "SELECT currency_code, country_count FROM by_region WHERE region IS NULL ORDER BY 1"
    ).fetchall()
    print("\n  currencies_by_region rows with a NULL region (the registry's side of the same gap):\n")
    print(render_table(["currency", "countries"], null_rows))

    eq_matched = con.execute(
        """
        SELECT COUNT(*) FROM store_rev sr
        WHERE EXISTS (SELECT 1 FROM by_region br
                      WHERE br.currency_code = sr.currency AND br.region = sr.region)
        """
    ).fetchone()[0]
    keep_matched = con.execute(
        """
        SELECT COUNT(*) FROM store_rev sr
        WHERE EXISTS (SELECT 1 FROM by_region br
                      WHERE br.currency_code = sr.currency AND br.region IS NOT DISTINCT FROM sr.region)
        """
    ).fetchone()[0]
    n_stores = con.execute("SELECT COUNT(*) FROM store_rev").fetchone()[0]
    print(
        f"\n  Joining on (region, currency) with '=' matches {eq_matched} of {n_stores} stores: NULL = NULL is not true, "
        f"so the {n_stores - eq_matched} unclassified\n  stores vanish without an error. "
        f"IS NOT DISTINCT FROM matches {keep_matched}. The gap is visible only if the join is written for it."
    )


def q5(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q5", "Coverage over time",
        "A proof of concept, and a negative result: coverage_timeline.parquet counts currencies per release; "
        "it cannot say when one currency began.",
    )
    first_version, first_date = con.execute(
        "SELECT version, d FROM timeline WHERE d IS NOT NULL ORDER BY d LIMIT 1"
    ).fetchone()
    n_releases, n_counted = con.execute(
        "SELECT COUNT(*), COUNT(active_count) FROM timeline"
    ).fetchone()
    earliest, latest = con.execute("SELECT MIN(opened), MAX(opened) FROM stores").fetchone()
    total, found = con.execute(
        """
        SELECT COUNT(*), COUNT(release) FROM (
            SELECT s.store_id,
                   (SELECT t.version FROM timeline t WHERE t.d <= s.opened ORDER BY t.d DESC LIMIT 1) AS release
            FROM stores s
        )
        """
    ).fetchone()
    active_now = con.execute(
        "SELECT COUNT(*) FROM store_rev sr JOIN flat f ON f.code = sr.currency"
    ).fetchone()[0]

    print(render_table(
        ["measure", "value"],
        [
            ("stores opened", f"{earliest} .. {latest}"),
            ("first registry release in the timeline", f"{first_version} on {first_date}"),
            ("stores with a registry release in force when they opened", f"{found} of {total}"),
            ("stores whose currency is active in the current registry", f"{active_now} of {total}"),
            ("releases in the timeline / with known counts", f"{n_releases} / {n_counted}"),
        ],
    ))
    print(
        f"\n  The as-of join (latest release on or before the opening date) finds nothing: all {total - found} stores "
        f"opened before\n  the registry's first release. The registry is a versioned snapshot, not a history of "
        f"currencies."
    )
    print(
        "  'Opened after its currency's most recent registry appearance' is not computable here: the timeline has "
        "counts\n  per version, not per currency, and no CURATED artifact carries per-currency start dates. "
        "The query would need one."
    )


def q6(con: "duckdb.DuckDBPyConnection") -> None:
    section(
        "Q6", "Pegged versus not pegged",
        "Distinct currencies and revenue share by peg status, then by region. Region comes from the country, "
        "peg status from the registry; the fact table has neither.",
    )
    total = con.execute("SELECT SUM(rev_usd) FROM store_rev").fetchone()[0]
    rows = con.execute(
        """
        SELECT CASE WHEN f.peg_type = 'single' THEN 'pegged: single anchor'
                    WHEN f.peg_type IS NOT NULL THEN 'pegged: basket or undisclosed'
                    ELSE 'not pegged' END AS grp,
               COUNT(DISTINCT sr.currency), COUNT(*), SUM(sr.rev_usd)
        FROM store_rev sr JOIN flat f ON f.code = sr.currency
        GROUP BY 1 ORDER BY (grp = 'not pegged'), grp
        """
    ).fetchall()
    print(render_table(
        ["group", "currencies", "stores", "revenue (USD eq.)", "share"],
        [(g, c, s, usd, pct_cell(usd, total)) for g, c, s, usd in rows],
    ))
    pegged_usd = sum(r[3] for r in rows if r[0].startswith("pegged"))
    pegged_cur = sum(r[1] for r in rows if r[0].startswith("pegged"))
    n_cur = con.execute("SELECT COUNT(DISTINCT currency) FROM store_rev").fetchone()[0]
    print(
        f"\n  {pegged_cur} of {n_cur} currencies are pegged; they carry {pct(pegged_usd, total):.1f}% of revenue."
    )

    mismatch = con.execute(
        """
        SELECT COUNT(*) FROM store_rev sr
        JOIN by_region br ON br.currency_code = sr.currency AND br.region IS NOT DISTINCT FROM sr.region
        JOIN flat f ON f.code = sr.currency
        WHERE br.is_pegged <> (f.pegged_to IS NOT NULL)
        """
    ).fetchone()[0]
    if mismatch:
        _fatal("currencies_by_region.is_pegged disagrees with iso4217.parquet pegged_to")

    by_region = con.execute(
        """
        SELECT COALESCE(sr.region, ?) AS label,
               SUM(sr.rev_usd) FILTER (WHERE br.is_pegged) AS pegged_usd,
               SUM(sr.rev_usd) AS total_usd
        FROM store_rev sr
        JOIN by_region br ON br.currency_code = sr.currency AND br.region IS NOT DISTINCT FROM sr.region
        GROUP BY 1 ORDER BY (label = ?), total_usd DESC, label
        """,
        [UNCLASSIFIED, UNCLASSIFIED],
    ).fetchall()
    print("\n  By region (store's region joined to currencies_by_region on the (region, currency) pair):\n")
    print(render_table(
        ["region", "revenue (USD eq.)", "pegged share"],
        [(r, t, pct_cell(p or 0.0, t)) for r, p, t in by_region],
    ))
    print(
        "\n  'Not pegged' is the registry's word for 'no peg recorded'. It does not mean freely floating."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    con = connect()
    check_integrity(con)
    for query in (q1, q2, q3, q4, q5, q6):
        query(con)
    print()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
