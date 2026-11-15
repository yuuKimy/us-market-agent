from datetime import date

from market_agent.options_select import is_third_friday, pick_atm_strike, pick_expiry, strikes_in_band


def test_third_friday():
    assert is_third_friday(date(2026, 11, 20))
    assert not is_third_friday(date(2026, 11, 13))


def test_pick_expiry_prefers_nearest_monthly():
    # 2026-11-10: DTE 10 -> 2026-11-20 (3rd Friday)
    exp = pick_expiry(date(2026, 11, 10), dte_min=7, dte_max=45)
    assert exp == date(2026, 11, 20)


def test_pick_atm_strike_tie_break_higher():
    assert pick_atm_strike(100.0, [97.5, 100.0, 102.5]) == 100.0
    assert pick_atm_strike(100.5, [100.0, 101.0]) == 101.0


def test_strikes_in_band_centered():
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    band = strikes_in_band(100.0, strikes, steps=1)
    assert band == [95.0, 100.0, 105.0]
    band2 = strikes_in_band(100.0, strikes, steps=10)
    assert band2 == strikes