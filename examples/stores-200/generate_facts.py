#!/usr/bin/env python3
"""
Synthetic fact-table generator for the stores-200 demo.

Writes two files next to this script:

    stores.json      200 store definitions (committed; regenerated here)
    facts.parquet    one row per (store, day) for 2024-01-01..2024-12-31
                     (73,200 rows; git-ignored; regenerated here)

What is real and what is synthetic
----------------------------------
Real, read from the registry (never typed in here):
  - which ISO 3166 alpha-2 codes exist (tools/iso3166_snapshot.json,
    `countries.active` only);
  - which currency a country issues, and that it is `circulating`
    (iso4217.countries.parquet);
  - each currency's minor units, peg anchor, peg type, and peg rate
    (iso4217.parquet).

Synthetic, defined in this file and labelled as such wherever shown:
  - the country plan (which 25 countries, how many stores each);
  - store names, tax rates, opening dates;
  - daily transaction counts, baskets, and revenue;
  - FLOATING_UNITS_PER_USD, round-number exchange rates for currencies
    the registry does not peg. The registry has no market rates, by
    design: a rate for a floating currency is a fact about a day, not
    about the currency. These numbers are not market data.

Design choices
--------------
- **Minor units, as integers.** `revenue_local` and `avg_basket_local` are
  int64 counts of the currency's minor unit (cents, fils, yen). The scale
  comes from the registry: JPY has 0, USD 2, BHD 3. A fact table that
  stored floats would have to guess; this one cannot.

- **Deterministic by construction.** Every random draw comes from
  `random.Random(seed)` with a fixed seed, using only `random()` and
  integer/float arithmetic (no libm functions), so two runs produce
  byte-identical files. Neither file carries a timestamp.

- **The fact table does not know about regions or pegs.** It holds a
  store id, a date, and money in the store's own currency. Everything else
  is the registry's job; that is the point of the demo.

- **Country to currency is looked up, not typed.** A country's currency
  is the one `circulating` currency the registry lists for it. A country
  with zero or several candidates stops the generator. Fund codes (CLF,
  CHE, USN) are therefore never chosen: a store in Chile prices in CLP.

Usage
-----
    python3 generate_facts.py

Exit codes
----------
    0  both files written
    2  fatal (registry file missing, unresolved country or currency,
       ambiguous or missing currency for a country)

Dependency
----------
pyarrow only.
"""

from __future__ import annotations

import io
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as e:
    print(f"FATAL: pyarrow is required for this demo: {e}", file=sys.stderr)
    print("Install with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEMO_DIR: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = DEMO_DIR.parent.parent

STORES_PATH: Path = DEMO_DIR / "stores.json"
FACTS_PATH: Path = DEMO_DIR / "facts.parquet"

# Registry inputs: CURATED and AGGREGATED artifacts plus the vendored ISO
# 3166 snapshot. The demo never reads the RAW registry file.
CURRENCIES_PARQUET: Path = REPO_ROOT / "iso4217.parquet"
COUNTRIES_PARQUET: Path = REPO_ROOT / "iso4217.countries.parquet"
SNAPSHOT_PATH: Path = REPO_ROOT / "tools" / "iso3166_snapshot.json"

EXIT_OK: int = 0
EXIT_FATAL: int = 2


# ---------------------------------------------------------------------------
# Synthetic parameters
# ---------------------------------------------------------------------------

STORES_SEED: int = 4217
FACTS_SEED: int = 2024

WINDOW_START: date = date(2024, 1, 1)
WINDOW_DAYS: int = 366  # 2024 is a leap year

OPENED_FIRST: date = date(2010, 1, 1)
OPENED_LAST: date = date(2023, 12, 31)

# (alpha-2, stores, tax_low, tax_high). SYNTHETIC. Weights are rough GDP
# shares for the six head countries; the 19 tail countries are chosen to
# cover the cases the queries need: pegged to USD (AE, SA, BH), pegged to
# EUR (DK, SN), basket-pegged (MA), unpegged (US, GB, DE, ...), a
# three-decimal currency (BH), zero-decimal currencies (JP, KR, CL, SN),
# a code ISO 3166 shares with a withdrawn entry (SK), and the two codes
# the ISO 3166 snapshot does not place in a region (TW, XK).
# Tax ranges are plausible, not authoritative.
COUNTRY_PLAN: Tuple[Tuple[str, int, float, float], ...] = (
    ("US", 40, 0.0000, 0.1025),
    ("GB", 20, 0.2000, 0.2000),
    ("DE", 15, 0.0700, 0.1900),
    ("FR", 15, 0.0550, 0.2000),
    ("JP", 10, 0.0800, 0.1000),
    ("CN", 10, 0.0600, 0.1300),
    ("IN", 8, 0.0500, 0.2800),
    ("BR", 7, 0.1700, 0.2500),
    ("CA", 7, 0.0500, 0.1500),
    ("KR", 6, 0.1000, 0.1000),
    ("AU", 6, 0.1000, 0.1000),
    ("MX", 6, 0.1600, 0.1600),
    ("CH", 5, 0.0260, 0.0810),
    ("TW", 5, 0.0500, 0.0500),
    ("ZA", 5, 0.1500, 0.1500),
    ("AE", 5, 0.0500, 0.0500),
    ("SA", 4, 0.1500, 0.1500),
    ("DK", 4, 0.2500, 0.2500),
    ("SK", 4, 0.1000, 0.2000),
    ("MA", 4, 0.1000, 0.2000),
    ("SN", 3, 0.1800, 0.1800),
    ("BH", 3, 0.1000, 0.1000),
    ("CL", 3, 0.1900, 0.1900),
    ("NG", 3, 0.0750, 0.0750),
    ("XK", 2, 0.1800, 0.1800),
)

# Local units per 1 USD for currencies the registry does not give a usable
# rate for. SYNTHETIC ROUND NUMBERS, not market data. MAD is here because
# its peg is a basket: the registry records that it is pegged but has no
# numeric rate to offer.
FLOATING_UNITS_PER_USD: Dict[str, float] = {
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 150.0,
    "CNY": 7.2,
    "INR": 83.0,
    "BRL": 5.0,
    "CAD": 1.35,
    "AUD": 1.5,
    "KRW": 1330.0,
    "MXN": 17.0,
    "CHF": 0.88,
    "TWD": 32.0,
    "ZAR": 18.5,
    "NGN": 1000.0,
    "CLP": 940.0,
    "MAD": 10.0,
}

# Demand shape. SYNTHETIC. Monday..Sunday, and January..December.
DAY_OF_WEEK_FACTOR: Tuple[float, ...] = (0.85, 0.90, 0.92, 0.95, 1.10, 1.30, 1.20)
MONTH_FACTOR: Tuple[float, ...] = (
    0.90, 0.90, 0.95, 1.00, 1.00, 1.00, 0.95, 0.95, 1.00, 1.05, 1.15, 1.35,
)


# ---------------------------------------------------------------------------
# Registry access (CURATED artifacts and the vendored snapshot only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrencyInfo:
    """The registry facts about one active currency that the demo needs."""

    code: str
    minor_units: int
    pegged_to: Optional[str]
    peg_type: Optional[str]
    peg_rate: Optional[float]


def _fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(EXIT_FATAL)


def _read_table(path: Path) -> pa.Table:
    if not path.exists():
        _fatal(f"Registry artifact not found: {path}. Run the demo from inside the registry repository.")
    return pq.read_table(path)


def load_currencies(path: Path = CURRENCIES_PARQUET) -> Dict[str, CurrencyInfo]:
    """Active currencies from iso4217.parquet, keyed by code."""
    out: Dict[str, CurrencyInfo] = {}
    for row in _read_table(path).to_pylist():
        if row["status"] != "active":
            continue
        out[row["code"]] = CurrencyInfo(
            code=row["code"],
            minor_units=row["minor_units"],
            pegged_to=row["pegged_to"],
            peg_type=row["peg_type"],
            peg_rate=row["peg_rate"],
        )
    return out


def load_circulating_by_country(path: Path = COUNTRIES_PARQUET) -> Dict[str, List[str]]:
    """Circulating currency codes per country, from iso4217.countries.parquet."""
    out: Dict[str, List[str]] = {}
    for row in _read_table(path).to_pylist():
        if row["status"] == "active" and row["classification"] == "circulating":
            out.setdefault(row["country_code"], []).append(row["currency_code"])
    return {k: sorted(v) for k, v in out.items()}


def load_snapshot_active(path: Path = SNAPSHOT_PATH) -> Dict[str, dict]:
    """
    ISO 3166 `countries.active`, keyed by alpha-2.

    The snapshot's `countries.withdrawn` list reuses two live codes (SK,
    AI) for historical entities. Only the active list is ever consulted.
    """
    if not path.exists():
        _fatal(f"ISO 3166 snapshot not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["alpha_2"]: c for c in data["countries"]["active"]}


def units_per_usd(
    code: str, currencies: Dict[str, CurrencyInfo], _depth: int = 0
) -> Tuple[float, str]:
    """
    Return (local units per 1 USD, rate path) for a currency.

    Rate paths:
      base        USD itself; the rate is 1 by definition.
      peg         single peg to USD; the registry's own peg_rate.
      peg+float   single peg to another anchor; the registry's peg_rate
                  times the anchor's demo floating rate.
      float       no usable registry rate (unpegged, or a basket or
                  undisclosed peg); the demo's round-number rate.
    """
    if code == "USD":
        return 1.0, "base"
    info = currencies.get(code)
    if info is None:
        _fatal(f"currency {code!r} not found among active rows of iso4217.parquet")
    if info.peg_type == "single" and info.peg_rate is not None and info.pegged_to:
        if info.pegged_to == "USD":
            return float(info.peg_rate), "peg"
        if _depth >= 2:
            _fatal(f"peg chain for {code} is deeper than the demo supports")
        anchor_rate, _ = units_per_usd(info.pegged_to, currencies, _depth + 1)
        return float(info.peg_rate) * anchor_rate, "peg+float"
    rate = FLOATING_UNITS_PER_USD.get(code)
    if rate is None:
        _fatal(f"no demo exchange rate for currency {code!r}; add it to FLOATING_UNITS_PER_USD")
    return rate, "float"


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

def build_stores(
    currencies: Dict[str, CurrencyInfo],
    circulating: Dict[str, List[str]],
    snapshot: Dict[str, dict],
) -> List[dict]:
    """
    Build the 200 store records from COUNTRY_PLAN.

    Draw order is fixed: per country in plan order, per store: tax rate,
    then opening date. A final pass shuffles stores across countries (so
    store ids do not cluster by country) using one more draw per store.
    """
    if len(COUNTRY_PLAN) != 25:
        _fatal(f"COUNTRY_PLAN has {len(COUNTRY_PLAN)} countries, expected 25")
    if sum(n for _, n, _, _ in COUNTRY_PLAN) != 200:
        _fatal("COUNTRY_PLAN store counts do not sum to 200")

    rng = random.Random(STORES_SEED)
    span = (OPENED_LAST - OPENED_FIRST).days + 1
    pending: List[Tuple[str, str, float, str]] = []

    for alpha2, count, tax_lo, tax_hi in COUNTRY_PLAN:
        if alpha2 not in snapshot:
            _fatal(f"country {alpha2!r} not found in ISO 3166 snapshot countries.active")
        candidates = circulating.get(alpha2, [])
        if len(candidates) != 1:
            _fatal(
                f"country {alpha2!r}: expected exactly one circulating currency in "
                f"iso4217.countries.parquet, found {candidates!r}"
            )
        currency = candidates[0]
        if currency not in currencies:
            _fatal(f"currency {currency!r} (country {alpha2!r}) not found in iso4217.parquet")
        for _ in range(count):
            tax = round(tax_lo + (tax_hi - tax_lo) * rng.random(), 4)
            opened = OPENED_FIRST + timedelta(days=int(rng.random() * span))
            pending.append((alpha2, currency, tax, opened.isoformat()))

    keys = [rng.random() for _ in pending]
    order = sorted(range(len(pending)), key=lambda i: (keys[i], i))

    stores: List[dict] = []
    for n, i in enumerate(order, start=1):
        alpha2, currency, tax, opened = pending[i]
        stores.append(
            {
                "store_id": f"ST-{n:04d}",
                "name": f"Store {n:04d}",
                "country": alpha2,
                "currency": currency,
                "tax_rate": tax,
                "opened": opened,
            }
        )
    return stores


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

FACT_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("store_id", pa.string(), nullable=False),
        pa.field("date", pa.date32(), nullable=False),
        pa.field("revenue_local", pa.int64(), nullable=False),
        pa.field("transactions", pa.int32(), nullable=False),
        pa.field("avg_basket_local", pa.int64(), nullable=False),
    ]
)


def build_facts(stores: List[dict], currencies: Dict[str, CurrencyInfo]) -> pa.Table:
    """
    One row per (store, day). Money is in the store's currency, in minor
    units.

    Per store, drawn once: a size (USD-equivalent daily revenue) and a
    basket size (USD-equivalent). Per day, drawn three times: a demand
    noise factor, a basket noise factor, and a remainder that stops
    revenue being an exact multiple of the basket. `avg_basket_local` is
    then *derived* as revenue // transactions, as the column's contract
    says.
    """
    rng = random.Random(FACTS_SEED)
    days = [WINDOW_START + timedelta(days=i) for i in range(WINDOW_DAYS)]

    store_ids: List[str] = []
    dates: List[date] = []
    revenue: List[int] = []
    transactions: List[int] = []
    avg_basket: List[int] = []

    for store in sorted(stores, key=lambda s: s["store_id"]):
        info = currencies[store["currency"]]
        rate, _ = units_per_usd(store["currency"], currencies)

        u = rng.random()
        size_usd = 6000 + int(u * u * 24000)
        basket_usd = 18 + int(rng.random() * 42)
        base_transactions = size_usd / basket_usd
        base_basket = max(1, int(round(basket_usd * rate * (10 ** info.minor_units))))

        for day in days:
            demand = DAY_OF_WEEK_FACTOR[day.weekday()] * MONTH_FACTOR[day.month - 1]
            n_tx = max(1, int(base_transactions * demand * (0.85 + 0.30 * rng.random())))
            basket = max(1, int(base_basket * (0.95 + 0.10 * rng.random())))
            total = n_tx * basket + int(rng.random() * basket)

            store_ids.append(store["store_id"])
            dates.append(day)
            revenue.append(total)
            transactions.append(n_tx)
            avg_basket.append(total // n_tx)

    return pa.Table.from_arrays(
        [
            pa.array(store_ids, type=pa.string()),
            pa.array(dates, type=pa.date32()),
            pa.array(revenue, type=pa.int64()),
            pa.array(transactions, type=pa.int32()),
            pa.array(avg_basket, type=pa.int64()),
        ],
        schema=FACT_SCHEMA,
    )


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: bytes) -> None:
    """Write via a temporary sibling and rename, so no partial file survives."""
    tmp = path.parent / (path.name + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(content)
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        _fatal(f"Failed to write {path}: {e}")


def render_stores(stores: List[dict]) -> bytes:
    return (json.dumps(stores, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def render_facts(table: pa.Table) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def main() -> int:
    currencies = load_currencies()
    circulating = load_circulating_by_country()
    snapshot = load_snapshot_active()

    stores = build_stores(currencies, circulating, snapshot)
    table = build_facts(stores, currencies)

    _atomic_write(STORES_PATH, render_stores(stores))
    content = render_facts(table)
    _atomic_write(FACTS_PATH, content)

    countries = len({s["country"] for s in stores})
    print(f"Wrote {STORES_PATH.name} ({len(stores)} stores, {countries} countries)")
    print(f"Wrote {FACTS_PATH.name} ({table.num_rows:,} rows, {len(content):,} bytes)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
