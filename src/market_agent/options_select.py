"""Pick monthly option expiry and ATM strike (pure functions for tests)."""

from __future__ import annotations

from datetime import date, timedelta


def is_third_friday(d: date) -> bool:
    return d.weekday() == 4 and 15 <= d.day <= 21


def is_friday(d: date) -> bool:
    return d.weekday() == 4


def monthly_expiries_in_dte_window(as_of: date, dte_min: int = 7, dte_max: int = 45) -> list[date]:
    """Third-Friday monthly expirations with DTE in [dte_min, dte_max]."""
    out: list[date] = []
    for dte in range(dte_min, dte_max + 1):
        exp = as_of + timedelta(days=dte)
        if is_third_friday(exp):
            out.append(exp)
    return sorted(set(out))


def pick_expiry(as_of: date, dte_min: int = 7, dte_max: int = 45) -> date | None:
    """Shortest monthly expiry in the DTE window; fallback to any Friday in window."""
    monthlies = monthly_expiries_in_dte_window(as_of, dte_min, dte_max)
    if monthlies:
        return monthlies[0]
    for dte in range(dte_min, dte_max + 1):
        exp = as_of + timedelta(days=dte)
        if is_friday(exp):
            return exp
    return None


def pick_atm_strike(underlying_close: float, strikes: list[float]) -> float | None:
    if not strikes:
        return None
    target = float(underlying_close)
    unique = sorted({float(s) for s in strikes})
    best = min(unique, key=lambda s: (abs(s - target), -s))
    return best


def strikes_in_band(atm_strike: float, strikes: list[float], steps: int = 10) -> list[float]:
    """Return up to 2*steps+1 strikes centered on atm_strike (must exist in chain)."""
    unique = sorted({float(s) for s in strikes})
    if not unique or steps < 0:
        return []
    if atm_strike not in unique:
        atm = pick_atm_strike(atm_strike, unique)
        if atm is None:
            return []
        atm_strike = atm
    idx = unique.index(float(atm_strike))
    lo = max(0, idx - steps)
    hi = min(len(unique), idx + steps + 1)
    return unique[lo:hi]