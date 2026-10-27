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
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Union,
)


# ---------------------------------------------------------------------------
# Registry data validation (v1.9.0, F13)
# ---------------------------------------------------------------------------
# One strict pass over the parsed JSON, before any Currency is built. The same contract is implemented in the
# JavaScript, Go and Rust wrappers and tested against tests/cross_language_consistency.json
# ("malformed_registry_tests"). The rules are in docs/WRAPPER_VALIDATION.md.

MAX_MINOR_UNITS = 36

_STRING_FIELDS = ("numeric", "symbol", "entity", "central_bank", "pegged_to", "peg_type", "pegged_since", "note",
                  "withdrawn_date", "replaced_by", "type", "peg_mechanism", "classification", "source_url")
_NUMBER_FIELDS = ("peg_rate", "peg_band_pct", "conversion_rate")
_INTEGER_FIELDS = ("market_cap_rank",)
_BOOLEAN_FIELDS = ("is_independent", "numeric_reused")
_ENTRY_LISTS = (
    ("currencies", ("active", "withdrawn")),
    ("non_iso", ("cryptocurrencies", "stablecoins", "commodities", "special_purpose")),
)


class RegistryDataError(ValueError):
    """
    The registry data is malformed.

    Raised by CurrencyRegistry() for a file that is not valid JSON, is not valid UTF-8, or breaks the contract in
    docs/WRAPPER_VALIDATION.md. The message is "malformed registry data: <JSON path>: <reason>". A missing file is
    still FileNotFoundError: that is I/O, not data.
    """


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _fail(path: str, reason: str) -> None:
    raise RegistryDataError(f"malformed registry data: {path}: {reason}")


def _check_kind(value: Any, kind: str, path: str) -> None:
    ok = {
        "string": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }[kind](value)
    if not ok:
        _fail(path, f"expected {kind}, got {_json_kind(value)}")


def _check_optional(obj: Dict[str, Any], key: str, kind: str, path: str) -> None:
    if obj.get(key) is not None:
        _check_kind(obj[key], kind, f"{path}.{key}")


def _validate_entry(entry: Any, path: str) -> None:
    _check_kind(entry, "object", path)
    for key, kind in (("code", "string"), ("name", "string"), ("minor_units", "integer")):
        if key not in entry:
            _fail(f"{path}.{key}", "required field is missing")
        _check_kind(entry[key], kind, f"{path}.{key}")
    if entry["code"] == "":
        _fail(f"{path}.code", "must not be empty")
    if not 0 <= entry["minor_units"] <= MAX_MINOR_UNITS:
        _fail(f"{path}.minor_units", f"expected an integer from 0 to {MAX_MINOR_UNITS}, got {entry['minor_units']}")
    for key in _STRING_FIELDS:
        _check_optional(entry, key, "string", path)
    for key in _NUMBER_FIELDS:
        _check_optional(entry, key, "number", path)
    for key in _INTEGER_FIELDS:
        _check_optional(entry, key, "integer", path)
    for key in _BOOLEAN_FIELDS:
        _check_optional(entry, key, "boolean", path)
    _check_optional(entry, "countries", "array", path)
    for i, country in enumerate(entry.get("countries") or []):
        cpath = f"{path}.countries[{i}]"
        _check_kind(country, "object", cpath)
        if "code" not in country:
            _fail(f"{cpath}.code", "required field is missing")
        _check_kind(country["code"], "string", f"{cpath}.code")
        _check_optional(country, "name", "string", cpath)
        _check_optional(country, "relationship", "string", cpath)
    _check_optional(entry, "code_lifetime", "object", path)
    life = entry.get("code_lifetime")
    if life is not None:
        lpath = f"{path}.code_lifetime"
        if "to" not in life:
            _fail(f"{lpath}.to", "required field is missing")
        _check_kind(life["to"], "string", f"{lpath}.to")
        _check_optional(life, "from", "string", lpath)


def _validate_registry_data(data: Any) -> None:
    """Raise RegistryDataError unless `data` satisfies the contract in docs/WRAPPER_VALIDATION.md."""
    _check_kind(data, "object", "$")
    for section in ("meta", "source", "currencies", "non_iso"):
        if section in data:
            _check_kind(data[section], "object", f"$.{section}")
    meta, source = data.get("meta", {}), data.get("source", {})
    _check_optional(meta, "version", "string", "$.meta")
    _check_optional(meta, "updated", "string", "$.meta")
    _check_optional(source, "last_amendment_applied", "integer", "$.source")
    _check_optional(source, "last_amendment_date", "string", "$.source")
    for section, keys in _ENTRY_LISTS:
        group = data.get(section, {})
        for key in keys:
            if key not in group:
                continue
            _check_kind(group[key], "array", f"$.{section}.{key}")
            for i, entry in enumerate(group[key]):
                _validate_entry(entry, f"$.{section}.{key}[{i}]")


def _reject_constant(name: str) -> None:
    raise RegistryDataError(f"malformed registry data: $: non-standard JSON constant {name}")


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Numeric contract (ADR 0013, docs/decisions/wrapper-numeric-contract.md)
# ---------------------------------------------------------------------------
# One IEEE-double multiplication by an exact power of ten, then an exact round half away from zero; int64 bound on
# the rounded value. The same algorithm runs in the Go, JavaScript and Rust wrappers.

# 10^n is an exact double for n <= 22 (the registry maximum is 18); every wrapper takes it from the same exact table.
_POW10_EXACT = tuple(float(10 ** _n) for _n in range(23))
_INT64_LIMIT = 2 ** 63  # a rounded amount whose magnitude is at or above this does not fit in an int64


def _round_half_away_from_zero(p: float) -> int:
    """Round a finite double to an int, ties away from zero, exactly.

    No ``floor(p + 0.5)``: in doubles ``0.49999999999999994 + 0.5`` is 1.0, and above 2**52 the addition loses the
    half. ``p - trunc(p)`` is exact for doubles, so the comparison with 0.5 is exact.
    """
    t = math.trunc(p)
    if abs(p - t) >= 0.5:
        return t + (1 if p > 0 else -1)
    return t


def _non_finite(x: Any) -> Optional[str]:
    """``'nan'``, ``'inf'`` or ``'-inf'`` for a non-finite int/float/Decimal, else None."""
    if isinstance(x, Decimal):
        if x.is_nan():
            return "nan"
        if x.is_infinite():
            return "-inf" if x.is_signed() else "inf"
        return None
    if isinstance(x, float):
        if math.isnan(x):
            return "nan"
        if math.isinf(x):
            return "-inf" if x < 0 else "inf"
    return None


def _sign_bit(x: Any) -> bool:
    """True for a negative amount and for -0.0 (a float's sign bit, a Decimal's sign)."""
    if isinstance(x, Decimal):
        return x.is_signed()
    if isinstance(x, float):
        return math.copysign(1.0, x) < 0
    return x < 0


def _as_amount(x: Any) -> Any:
    """int, float and Decimal are used as they are; any other numeric type is converted with float(); str is refused."""
    if isinstance(x, (str, bytes)):
        raise TypeError(f"Cannot convert {x!r} to minor units: expected a number")
    if isinstance(x, (int, float, Decimal)):
        return x
    return float(x)


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

        Defaults to False when the field is absent — the conservative
        choice, matching the CSV export's rendering. Reporting a pegged
        currency as independent is a silent correctness bug no downstream
        consumer would notice; reporting an independent currency as
        not-independent is visible in any filter and easy to correct.
        """
        return self._data.get("is_independent", False)

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

    # -- v1.6.0 properties --------------------------------------------------

    @property
    def classification(self) -> Optional[str]:
        """
        Classification of an active currency: "circulating", "fund",
        "settlement", or "indexation". None for withdrawn and non-ISO
        entries, and for v1.5.x registries that predate this field.

        See the README's Enums section for the meaning of each value.
        """
        return self._data.get("classification")

    @property
    def numeric_reused(self) -> Optional[bool]:
        """
        True if this active currency's numeric code also appears on a
        withdrawn entry. False if not. None for withdrawn and non-ISO
        entries, and for v1.5.x registries.

        A consumer who uses numeric codes as foreign keys should filter
        on `numeric_reused is not True` to avoid the reuse case.
        """
        return self._data.get("numeric_reused")

    @property
    def source_url(self) -> Optional[str]:
        """
        URL of the entry's primary source. Present on every active and
        withdrawn entry as of v1.6.0. None for v1.5.x registries and
        for non-ISO entries.
        """
        return self._data.get("source_url")

    @property
    def code_lifetime(self) -> Optional[Dict[str, Any]]:
        """
        The withdrawn code's full valid range: ``{"from": str | None,
        "to": str}``. None for active and non-ISO entries, and for
        v1.5.x registries.

        ``from`` is None when the ISO assignment date is undocumented —
        which is the case for every withdrawn entry in v1.6.0.
        """
        return self._data.get("code_lifetime")

    # -- Conversion ---------------------------------------------------------

    def _round_scaled(self, x: Any) -> Optional[int]:
        """The amount scaled to minor units and rounded half away from zero, as an exact int.

        ``x`` is finite. A Decimal and an int are exact; a float is one double multiplication followed by an exact
        round. Returns None when the float product overflows a double (the amount is beyond any int64).
        """
        n = self.minor_units
        if isinstance(x, Decimal):
            with localcontext() as ctx:
                ctx.prec = len(x.as_tuple().digits) + 10
                return int(x.scaleb(n).to_integral_value(rounding=ROUND_HALF_UP))
        if isinstance(x, int):
            return int(x) * 10 ** n
        p = x * _POW10_EXACT[n]
        if math.isinf(p):
            return None
        return _round_half_away_from_zero(p)

    def to_minor(self, major_amount: Union[int, float, Decimal]) -> int:
        """
        Convert a major currency amount to minor units.

        Rounds half away from zero (2.5 -> 3, -2.5 -> -3), identically in the Go, JavaScript and Rust wrappers
        (ADR 0013). A float is multiplied by 10**minor_units as one IEEE double, then rounded exactly, so
        ``to_minor(1.005)`` for USD is 100: 1.005 * 100 is 100.49999999999999. An int is exact; a Decimal is converted
        exactly (no binary float is involved); any other numeric type is converted with ``float()``.

        Args:
            major_amount: Amount in major units (e.g., 100.50 for $100.50).

        Returns:
            Integer amount in minor units (e.g., 10050 for 10050 cents).

        Raises:
            ValueError: If major_amount is NaN or infinite (float or Decimal).
            OverflowError: If a float or int amount rounds to a result that does not fit in an int64
                (``|result| >= 2**63``); the message says "amount too large". The four wrappers return the same numbers
                or the same errors; Python and JavaScript used to return the larger value, which Go and Rust could
                not. A Decimal is exempt: it is exact and unbounded (v1.9.0), and no other wrapper takes one.
            TypeError: If major_amount is a str or bytes.

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
        major_amount = _as_amount(major_amount)
        kind = _non_finite(major_amount)
        if kind == "nan":
            raise ValueError("Cannot convert NaN to minor units")
        if kind is not None:
            raise ValueError("Cannot convert infinity to minor units")
        r = self._round_scaled(major_amount)
        if r is None or (not isinstance(major_amount, Decimal) and abs(r) >= _INT64_LIMIT):
            raise OverflowError(
                f"Cannot convert {major_amount!r} to minor units: amount too large for int64 minor units"
            )
        return r

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

    def format(self, major_amount: Union[int, float, Decimal]) -> str:
        """
        Format a major currency amount with the currency symbol.

        The amount is rounded exactly as :meth:`to_minor` rounds it (half away from zero) and its digits are printed
        from that rounded value, so ``format`` and ``to_minor`` cannot disagree (ADR 0013). It does not raise for a
        number: NaN is ``nan``, infinity (or a float amount whose scaled value overflows a double) is ``inf`` or
        ``-inf``, each after the symbol. Fractional currencies get comma thousands separators; 0-decimal currencies
        print ungrouped.

        Args:
            major_amount: Amount in major units. A Decimal is formatted exactly.

        Returns:
            Formatted string like "$100.50" or "¥500".

        Examples:
            >>> usd.format(100.50)
            '$100.50'
            >>> jpy.format(500)
            '¥500'
            >>> usd.format(float("nan"))
            '$nan'
        """
        major_amount = _as_amount(major_amount)
        kind = _non_finite(major_amount)
        if kind is not None:
            return f"{self.symbol}{kind}"
        r = self._round_scaled(major_amount)
        if r is None:  # a finite float whose scaled value overflows a double
            return f"{self.symbol}{'-' if major_amount < 0 else ''}inf"
        n = self.minor_units
        # Sign comes from the sign bit of the amount when there are decimals, and from the rounded value when there
        # are none: a negative amount that rounds to zero prints "$-0.00" but "¥0" (today's behavior in all four).
        negative = (_sign_bit(major_amount) and (n > 0 or r != 0)) or (n == 0 and r < 0)
        digits = str(abs(r))
        if n > 0:
            digits = digits.rjust(n + 1, "0")
            digits = f"{int(digits[:-n]):,}.{digits[-n:]}"
        return f"{self.symbol}{'-' if negative else ''}{digits}"

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

        Raises:
            FileNotFoundError: If the registry file cannot be found.
            RegistryDataError: If the data is malformed (not JSON, not UTF-8, or
                               outside the contract in docs/WRAPPER_VALIDATION.md).
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
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                data = json.load(f, parse_constant=_reject_constant)
        except UnicodeDecodeError as e:
            raise RegistryDataError(f"malformed registry data: $: not valid UTF-8 ({e.reason})") from e
        except json.JSONDecodeError as e:
            raise RegistryDataError(f"malformed registry data: $: invalid JSON: {e}") from e
        except RecursionError as e:
            raise RegistryDataError("malformed registry data: $: nested too deeply") from e
        _validate_registry_data(data)
        return data

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

    def by_classification(self, cls: str) -> List[Currency]:
        """
        Find all active currencies with the given classification.

        Args:
            cls: One of "circulating", "fund", "settlement", "indexation".

        Returns:
            List of active Currency objects whose classification matches.
            Empty list if none match, or if the registry predates v1.6.0
            and no entry carries a classification field.

        Examples:
            >>> len(registry.by_classification("circulating"))
            157
            >>> [c.code for c in registry.by_classification("indexation")]
            ['VED']
        """
        return [c for c in self._active.values() if c.classification == cls]


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
    "RegistryDataError",
    "Currency",
    "CurrencyRegistry",
    "currency",
    "active",
    "pegged_to",
    "all_active",
]