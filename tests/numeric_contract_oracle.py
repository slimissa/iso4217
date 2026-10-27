"""
Reference implementation of the wrapper numeric contract (ADR 0013, docs/decisions/wrapper-numeric-contract.md).

It shares no code with any wrapper: the half-away-from-zero round is done on the exact rational value of the double
(Fractions), and the digits come from Python ints. tests/test_wrapper_numeric_contract.py checks that every expected
value in tests/cross_language_consistency.json's `numeric_contract` group equals this oracle's answer, so a vector
cannot be edited to match a wrapper's bug.
"""

from __future__ import annotations

import math
from fractions import Fraction

INT64_LIMIT = 2**63  # |r| must be strictly below this (ADR 0013, D3)
MAX_SCALE = 22       # 10^n is an exact double for n <= 22 (ADR 0013, "Verification still owed")
NON_FINITE_TOKENS = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}


def decode_x(raw):
    """Fixture amounts are JSON numbers, or the strings NaN / Infinity / -Infinity (JSON has no non-finite literals)."""
    if isinstance(raw, str):
        return NON_FINITE_TOKENS[raw]
    return float(raw)


def signbit(x: float) -> bool:
    return math.copysign(1.0, x) < 0


def scaled(x: float, n: int):
    """('non_finite', None) | ('overflow', None) | ('ok', r) with r an exact Python int."""
    if not math.isfinite(x):
        return ("non_finite", None)
    assert 0 <= n <= MAX_SCALE
    p = x * float(10**n)  # one IEEE-double product, as in every wrapper
    if not math.isfinite(p):
        return ("overflow", None)
    q = Fraction(p)
    r = math.floor(q + Fraction(1, 2)) if q >= 0 else -math.floor(-q + Fraction(1, 2))
    if abs(r) >= INT64_LIMIT:
        return ("overflow", None)
    return ("ok", r)


def to_minor(x: float, n: int):
    kind, r = scaled(x, n)
    return r if kind == "ok" else {"error": kind}


def format_amount(x: float, n: int, symbol: str) -> str:
    if x != x:
        return symbol + "nan"
    if math.isinf(x):
        return symbol + ("-" if x < 0 else "") + "inf"
    kind, r = scaled(x, n)
    if kind == "overflow" and not math.isfinite(x * float(10**n)):
        return symbol + ("-" if x < 0 else "") + "inf"
    # A finite product that only exceeds int64 is still formatted: format prints the digits of r (ADR 0013, D5).
    if kind == "overflow":
        q = Fraction(x * float(10**n))
        r = math.floor(q + Fraction(1, 2)) if q >= 0 else -math.floor(-q + Fraction(1, 2))
    negative = (signbit(x) and (n > 0 or r != 0)) or (n == 0 and r < 0)
    digits = str(abs(r)).rjust(n + 1, "0")
    int_part, frac = (digits[:-n], digits[-n:]) if n else (digits, "")
    # 0-decimal currencies print ungrouped in all four wrappers today (\u00a51234567); that is preserved (ADR 0013, D5).
    body = (f"{int(int_part):,}" + f".{frac}") if n else int_part
    return symbol + ("-" if negative else "") + body
