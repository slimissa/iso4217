"""
ISO 4217 Currency Registry — Python Wrapper

A minimal, zero-dependency Python interface to the canonical ISO 4217 currency
registry. Provides Currency and CurrencyRegistry classes with full type hints,
minor/major unit conversion, peg information access, and country relationship
lookup.

Usage:
    from iso4217 import CurrencyRegistry

    registry = CurrencyRegistry()
    usd = registry.currency("USD")
    print(usd.minor_units)          # 2
    print(usd.to_minor(100.50))     # 10050
    print(usd.from_minor(10050))    # 100.5

    # Filter pegged currencies
    pegged = [c for c in registry.all_active() if not c.is_independent]

    # Get all countries using a currency
    for country in usd.countries:
        print(f"{country['name']}: {country['relationship']}")

License: Apache 2.0
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Union,
    overload,
)


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

class Currency:
    """
    Represents a single currency from the ISO 4217 registry.

    Provides read-only access to all currency properties plus convenience
    methods for converting between major and minor currency units.

    Attributes:
        code: ISO 4217 alphabetic code (e.g., "USD").
        numeric: ISO 4217 numeric code as string (e.g., "840").
        name: Official English name (e.g., "US Dollar").
        minor_units: Number of decimal places for the minor unit.
        symbol: Display symbol (e.g., "$").
        entity: Issuing entity or monetary authority.
        central_bank: Official name of the central bank.
        pegged_to: Anchor currency code, basket description, or None.
        peg_type: Classification of peg ("single", "basket", "undisclosed").
        pegged_since: Date the peg was established, or None.
        peg_rate: Official peg rate, or None.
        peg_band_pct: Allowed deviation from peg as percentage, or None.
        peg_mechanism: Peg mechanism for stablecoins (e.g., "Fiat-collateralized").
        is_independent: True if currency floats independently.
        note: Optional note for special cases.
        countries: List of country references with code, name, and relationship.
        withdrawn_date: Withdrawal date for withdrawn currencies, or None.
        replaced_by: Replacement currency code for withdrawn currencies, or None.
        conversion_rate: Official conversion rate for withdrawn currencies, or None.
        market_cap_rank: Market cap rank for crypto/stablecoins, or None.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    # -- Basic properties ---------------------------------------------------

    @property
    def code(self) -> str:
        """ISO 4217 alphabetic currency code."""
        return self._data["code"]

    @property
    def numeric(self) -> str:
        """ISO 4217 numeric currency code as a 3-digit string."""
        return self._data.get("numeric", "")

    @property
    def name(self) -> str:
        """Official English name of the currency."""
        return self._data["name"]

    @property
    def minor_units(self) -> int:
        """
        Number of decimal places for the minor currency unit.

        0 = no subdivision (JPY, KRW, VND).
        2 = standard cents/pence (USD, EUR, GBP).
        3 = dinar subdivisions (KWD, BHD, OMR, JOD, TND, LYD, IQD).
        8 = Bitcoin.
        18 = Ethereum.
        """
        return self._data["minor_units"]

    @property
    def symbol(self) -> str:
        """Primary display symbol. May be empty string if none exists."""
        return self._data.get("symbol", "")

    @property
    def entity(self) -> str:
        """Issuing entity or monetary authority."""
        return self._data.get("entity", "")

    @property
    def central_bank(self) -> str:
        """Official name of the central bank."""
        return self._data.get("central_bank", "")

    # -- Peg properties -----------------------------------------------------

    @property
    def pegged_to(self) -> Optional[str]:
        """
        The currency or basket this currency is pegged to.

        Returns:
            ISO 4217 code of the anchor currency, a basket description
            (e.g., "EUR+USD basket"), or None if freely floating.
        """
        return self._data.get("pegged_to")

    @property
    def peg_type(self) -> Optional[str]:
        """
        How to interpret `pegged_to`.

        Returns:
            "single" if pegged_to is a parseable ISO 4217 code (e.g. AED -> "USD").
            "basket" if pegged_to is a free-text description of a weighted
                basket peg (e.g. MAD -> "EUR+USD basket").
            "undisclosed" if pegged, but the peg mechanism/composition is not
                public (e.g. KWD -> "Currency basket").
            None if not pegged.

        Do not assume `pegged_to` is a parseable currency code without
        checking `peg_type == "single"` first — MAD and KWD are pegged
        with free-text `pegged_to` values that will not match a currency code.
        """
        return self._data.get("peg_type")

    @property
    def pegged_since(self) -> Optional[str]:
        """Date the peg was established in ISO 8601 format, or None."""
        return self._data.get("pegged_since")

    @property
    def peg_rate(self) -> Optional[float]:
        """
        Official peg rate (units of this currency per 1 unit of anchor).

        None for basket pegs or undisclosed pegs.
        """
        return self._data.get("peg_rate")

    @property
    def peg_band_pct(self) -> Optional[float]:
        """
        Allowed deviation from the peg as a percentage.

        0.0 = fixed peg. None = not applicable or undisclosed.
        """
        return self._data.get("peg_band_pct")

    @property
    def peg_mechanism(self) -> Optional[str]:
        """Peg mechanism for stablecoins (e.g., "Fiat-collateralized")."""
        return self._data.get("peg_mechanism")

    @property
    def is_independent(self) -> bool:
        """
        True if the currency floats independently or is a managed float
        without a fixed anchor. False if hard-pegged or currency board.
        """
        return self._data.get("is_independent", True)

    @property
    def is_pegged(self) -> bool:
        """Convenience property: True if this currency is pegged to something."""
        return self.pegged_to is not None

    # -- Note ---------------------------------------------------------------

    @property
    def note(self) -> Optional[str]:
        """Optional note for special cases or market conventions."""
        return self._data.get("note")

    # -- Countries ----------------------------------------------------------

    @property
    def countries(self) -> List[Dict[str, str]]:
        """
        Countries and territories where this currency is primary legal tender.

        Each entry has:
            code: ISO 3166-1 alpha-2 country code.
            name: Human-readable country or territory name.
            relationship: One of "issuing", "adopting", "territory",
                          "parallel", "local_issue".
        """
        return self._data.get("countries", [])

    def issuing_countries(self) -> List[Dict[str, str]]:
        """Countries that are the sovereign issuer of this currency."""
        return [c for c in self.countries if c.get("relationship") == "issuing"]

    def adopting_countries(self) -> List[Dict[str, str]]:
        """Countries that use this currency without being the issuer."""
        return [c for c in self.countries if c.get("relationship") == "adopting"]

    # -- Withdrawn properties -----------------------------------------------

    @property
    def withdrawn_date(self) -> Optional[str]:
        """Withdrawal date in ISO 8601 format, or None for active currencies."""
        return self._data.get("withdrawn_date")

    @property
    def replaced_by(self) -> Optional[str]:
        """ISO 4217 code of the replacement currency, or None."""
        return self._data.get("replaced_by")

    @property
    def conversion_rate(self) -> Optional[float]:
        """Official conversion rate (units of this currency per 1 unit of replacement)."""
        return self._data.get("conversion_rate")

    # -- Non-ISO properties -------------------------------------------------

    @property
    def market_cap_rank(self) -> Optional[int]:
        """Market cap rank for crypto/stablecoins, or None for fiat currencies."""
        return self._data.get("market_cap_rank")

    # -- Conversion ---------------------------------------------------------

    def to_minor(self, major_amount: Union[int, float]) -> int:
        """
        Convert a major currency amount to minor units.

        Uses round-half-away-from-zero semantics, matching Go (math.Round),
        Rust (f64::round()), and JavaScript (Math.round for positives).

        Args:
            major_amount: Amount in major units (e.g., 100.50 for $100.50).

        Returns:
            Integer amount in minor units (e.g., 10050 for 10050 cents).

        Raises:
            ValueError: If major_amount is NaN or infinite.

        Examples:
            >>> usd.to_minor(100.50)
            10050
            >>> jpy.to_minor(500)
            500
            >>> kwd.to_minor(1.500)
            1500
            >>> btc.to_minor(0.00000001)
            1
        """
        if isinstance(major_amount, float):
            if math.isnan(major_amount):
                raise ValueError("Cannot convert NaN to minor units")
            if math.isinf(major_amount):
                raise ValueError("Cannot convert infinity to minor units")

        factor = 10 ** self.minor_units
        # Round half away from zero: 2.5 -> 3, -2.5 -> -3
        product = major_amount * factor
        if product >= 0:
            return math.floor(product + 0.5)
        else:
            return math.ceil(product - 0.5)

    def from_minor(self, minor_amount: int) -> float:
        """
        Convert minor units to a major currency amount.

        Args:
            minor_amount: Integer amount in minor units (e.g., 10050 for 10050 cents).

        Returns:
            Float amount in major units (e.g., 100.5 for $100.50).

        Examples:
            >>> usd.from_minor(10050)
            100.5
            >>> jpy.from_minor(500)
            500.0
        """
        factor = 10 ** self.minor_units
        return minor_amount / factor

    # -- Display ------------------------------------------------------------

    def format(self, major_amount: Union[int, float]) -> str:
        """
        Format a major currency amount with the currency symbol.

        Args:
            major_amount: Amount in major units.

        Returns:
            Formatted string like "$100.50" or "¥500".

        Examples:
            >>> usd.format(100.50)
            '$100.50'
            >>> jpy.format(500)
            '¥500'
        """
        if self.minor_units == 0:
            return f"{self.symbol}{int(major_amount)}"
        return f"{self.symbol}{major_amount:,.{self.minor_units}f}"

    # -- Magic methods ------------------------------------------------------

    def __repr__(self) -> str:
        peg = f", pegged to {self.pegged_to}" if self.pegged_to else ""
        return (
            f"Currency(code='{self.code}', name='{self.name}', "
            f"minor_units={self.minor_units}{peg})"
        )

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Currency):
            return NotImplemented
        return self.code == other.code

    def __hash__(self) -> int:
        return hash(self.code)

    def to_dict(self) -> Dict[str, Any]:
        """Return the raw dictionary for this currency."""
        return dict(self._data)


# ---------------------------------------------------------------------------
# CurrencyRegistry
# ---------------------------------------------------------------------------

class CurrencyRegistry:
    """
    The main registry interface for looking up ISO 4217 currencies.

    Loads the canonical iso4217.json file and provides lookup methods
    for active, withdrawn, and non-ISO currencies.

    Usage:
        registry = CurrencyRegistry()
        usd = registry.currency("USD")
        all_pegged = [c for c in registry.all_active() if c.is_pegged]
    """

    def __init__(self, data_path: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize the registry from a JSON file.

        Args:
            data_path: Path to iso4217.json. If None, looks for the file
                       relative to this module's location, then in the
                       current working directory.
        """
        self._data = self._load_data(data_path)
        self._active: Dict[str, Currency] = {}
        self._withdrawn: Dict[str, Currency] = {}
        self._non_iso: Dict[str, Currency] = {}
        self._all_codes: Dict[str, Currency] = {}
        self._build_indexes()

    # -- Loading ------------------------------------------------------------

    @staticmethod
    def _find_data_path(explicit_path: Optional[Union[str, Path]] = None) -> Path:
        """Resolve the path to iso4217.json."""
        if explicit_path is not None:
            path = Path(explicit_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Registry file not found: {path}")

        # Try relative to this module
        module_dir = Path(__file__).resolve().parent
        candidate = module_dir / "iso4217.json"
        if candidate.exists():
            return candidate

        # Try two levels up (wrappers/python -> project root)
        candidate = module_dir.parent.parent / "iso4217.json"
        if candidate.exists():
            return candidate

        # Try current working directory
        candidate = Path.cwd() / "iso4217.json"
        if candidate.exists():
            return candidate

        raise FileNotFoundError(
            "Cannot find iso4217.json. "
            "Place it next to iso4217.py, in the project root, "
            "or pass an explicit path to CurrencyRegistry()."
        )

    @staticmethod
    def _load_data(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Load and parse the registry JSON."""
        resolved = CurrencyRegistry._find_data_path(path)
        with open(resolved, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_indexes(self) -> None:
        """Build lookup indexes from the raw data."""
        currencies = self._data.get("currencies", {})

        # Active currencies
        for c in currencies.get("active", []):
            currency = Currency(c)
            self._active[c["code"]] = currency
            self._all_codes[c["code"]] = currency

        # Withdrawn currencies
        for c in currencies.get("withdrawn", []):
            currency = Currency(c)
            self._withdrawn[c["code"]] = currency
            self._all_codes[c["code"]] = currency

        # Non-ISO currencies
        non_iso = self._data.get("non_iso", {})
        for category in ["cryptocurrencies", "stablecoins", "commodities", "special_purpose"]:
            for c in non_iso.get(category, []):
                currency = Currency(c)
                self._non_iso[c["code"]] = currency
                self._all_codes[c["code"]] = currency

    # -- Metadata -----------------------------------------------------------

    @property
    def version(self) -> str:
        """Semantic version of the registry data."""
        return self._data.get("meta", {}).get("version", "unknown")

    @property
    def updated(self) -> str:
        """Date the registry was last updated (ISO 8601)."""
        return self._data.get("meta", {}).get("updated", "unknown")

    @property
    def amendment(self) -> int:
        """Most recent ISO 4217 amendment applied."""
        return self._data.get("source", {}).get("last_amendment_applied", 0)

    @property
    def amendment_date(self) -> str:
        """Date of the most recent amendment applied."""
        return self._data.get("source", {}).get("last_amendment_date", "unknown")

    # -- Lookup methods -----------------------------------------------------

    def currency(self, code: str) -> Optional[Currency]:
        """
        Look up any currency by code (case-insensitive).

        Searches active, withdrawn, and non-ISO currencies in that order.

        Args:
            code: Currency code (e.g., "USD", "usd", "Btc").

        Returns:
            Currency object or None if not found.
        """
        return self._all_codes.get(code.upper())

    def active(self, code: str) -> Optional[Currency]:
        """
        Look up an active ISO 4217 currency by code (case-insensitive).

        Args:
            code: Currency code (e.g., "USD", "eur").

        Returns:
            Currency object or None if not found or not active.
        """
        return self._active.get(code.upper())

    def withdrawn(self, code: str) -> Optional[Currency]:
        """
        Look up a withdrawn ISO 4217 currency by code (case-insensitive).

        Args:
            code: Currency code (e.g., "DEM", "frf").

        Returns:
            Currency object or None if not found or not withdrawn.
        """
        return self._withdrawn.get(code.upper())

    def non_iso(self, code: str) -> Optional[Currency]:
        """
        Look up a non-ISO currency by code (case-insensitive).

        Args:
            code: Currency code (e.g., "BTC", "xau").

        Returns:
            Currency object or None if not found.
        """
        return self._non_iso.get(code.upper())

    # -- Collection accessors -----------------------------------------------

    def all_active(self) -> List[Currency]:
        """Return all active ISO 4217 currencies."""
        return list(self._active.values())

    def all_withdrawn(self) -> List[Currency]:
        """Return all withdrawn ISO 4217 currencies."""
        return list(self._withdrawn.values())

    def all_non_iso(self) -> List[Currency]:
        """Return all non-ISO currencies (crypto, stablecoins, commodities)."""
        return list(self._non_iso.values())

    def all_currencies(self) -> List[Currency]:
        """Return all currencies across all categories."""
        return list(self._all_codes.values())

    # -- Filtering ----------------------------------------------------------

    def pegged_to(self, anchor_code: str) -> List[Currency]:
        """
        Find all active currencies pegged to a specific anchor currency.

        Args:
            anchor_code: ISO 4217 code of the anchor currency (e.g., "USD", "EUR").

        Returns:
            List of Currency objects with peg_type == "single" and
            pegged_to exactly matching the given anchor.

        Only currencies with peg_type == "single" are considered — a
        currency pegged to a basket or an undisclosed mix (e.g. MAD's
        "EUR+USD basket") is not "pegged to USD" just because "USD"
        appears in its pegged_to description, even though the anchor
        is a component of the basket. Use `all_active()` and inspect
        `peg_type` / `pegged_to` directly if you need basket-aware search.

        Examples:
            >>> registry.pegged_to("USD")
            [Currency(code='AED', ...), Currency(code='SAR', ...), ...]
        """
        anchor = anchor_code.upper()
        return [
            c for c in self._active.values()
            if c.peg_type == "single"
            and c.pegged_to is not None
            and c.pegged_to.upper() == anchor
        ]

    def independent(self) -> List[Currency]:
        """Return all active currencies that are independently floating."""
        return [c for c in self._active.values() if c.is_independent]

    def with_minor_units(self, n: int) -> List[Currency]:
        """
        Find all active currencies with a specific number of minor units.

        Args:
            n: Number of minor units (0, 2, 3, etc.).

        Examples:
            >>> registry.with_minor_units(3)
            [Currency(code='BHD', ...), Currency(code='JOD', ...), ...]
        """
        return [c for c in self._active.values() if c.minor_units == n]

    def issued_by(self, country_code: str) -> List[Currency]:
        """
        Find all active currencies where a country is the issuer.

        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., "GB", "CH").

        Returns:
            List of Currency objects issued by that country.
        """
        code = country_code.upper()
        return [
            c for c in self._active.values()
            if any(
                country.get("code") == code and country.get("relationship") == "issuing"
                for country in c.countries
            )
        ]

    def used_in(self, country_code: str) -> List[Currency]:
        """
        Find all active currencies used in a country (any relationship).

        Args:
            country_code: ISO 3166-1 alpha-2 country code.

        Returns:
            List of Currency objects used in that country.
        """
        code = country_code.upper()
        return [
            c for c in self._active.values()
            if any(country.get("code") == code for country in c.countries)
        ]

    # -- Iteration ----------------------------------------------------------

    def __iter__(self) -> Iterator[Currency]:
        """Iterate over all active currencies."""
        return iter(self._active.values())

    def __len__(self) -> int:
        """Number of active currencies in the registry."""
        return len(self._active)

    def __contains__(self, code: str) -> bool:
        """Check if a currency code exists in the registry (any category)."""
        return code.upper() in self._all_codes

    # -- Statistics ---------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of active ISO 4217 currencies."""
        return len(self._active)

    @property
    def withdrawn_count(self) -> int:
        """Number of withdrawn ISO 4217 currencies."""
        return len(self._withdrawn)

    @property
    def non_iso_count(self) -> int:
        """Number of non-ISO currencies."""
        return len(self._non_iso)

    @property
    def pegged_count(self) -> int:
        """Number of active currencies that are pegged."""
        return sum(1 for c in self._active.values() if c.is_pegged)

    @property
    def independent_count(self) -> int:
        """Number of active currencies that float independently."""
        return sum(1 for c in self._active.values() if c.is_independent)

    def summary(self) -> Dict[str, Any]:
        """
        Return a summary dictionary with registry statistics.

        Useful for logging, monitoring, and sanity checks.
        """
        mu_dist: Dict[int, int] = {}
        for c in self._active.values():
            mu_dist[c.minor_units] = mu_dist.get(c.minor_units, 0) + 1

        return {
            "version": self.version,
            "updated": self.updated,
            "amendment": self.amendment,
            "active_currencies": self.active_count,
            "withdrawn_currencies": self.withdrawn_count,
            "non_iso_currencies": self.non_iso_count,
            "pegged_currencies": self.pegged_count,
            "independent_currencies": self.independent_count,
            "minor_units_distribution": dict(sorted(mu_dist.items())),
        }

    # -- Display ------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CurrencyRegistry(version={self.version!r}, "
            f"active={self.active_count}, "
            f"withdrawn={self.withdrawn_count}, "
            f"non_iso={self.non_iso_count})"
        )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

# Singleton instance — created lazily on first access
_registry: Optional[CurrencyRegistry] = None


def _get_registry() -> CurrencyRegistry:
    """Get or create the module-level singleton registry."""
    global _registry
    if _registry is None:
        _registry = CurrencyRegistry()
    return _registry


def currency(code: str) -> Optional[Currency]:
    """
    Convenience function to look up any currency by code.

    Uses a module-level singleton registry.

    Args:
        code: Currency code (case-insensitive).

    Returns:
        Currency object or None if not found.

    Examples:
        >>> currency("USD")
        Currency(code='USD', name='US Dollar', minor_units=2)
        >>> currency("btc")
        Currency(code='BTC', name='Bitcoin', minor_units=8)
    """
    return _get_registry().currency(code)


def active(code: str) -> Optional[Currency]:
    """Convenience function to look up an active currency."""
    return _get_registry().active(code)


def pegged_to(anchor: str) -> List[Currency]:
    """Convenience function to find currencies pegged to an anchor."""
    return _get_registry().pegged_to(anchor)


def all_active() -> List[Currency]:
    """Convenience function to get all active currencies."""
    return _get_registry().all_active()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "Currency",
    "CurrencyRegistry",
    "currency",
    "active",
    "pegged_to",
    "all_active",
]