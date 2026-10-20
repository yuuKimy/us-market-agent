import numpy as np
import pandas as pd
import pytest

from market_agent import indicators


def test_align_macro_does_not_carry_values_past_last_observation():
    days = pd.bdate_range("2026-01-05", periods=6)
    prices = pd.DataFrame({"SPY": range(6)}, index=days, dtype=float)
    macro = pd.DataFrame({"DGS10": [4.0, np.nan, 4.2, 4.3, np.nan, np.nan]}, index=days)
    macro = macro.drop(days[1])  # holiday gap inside the series

    aligned = indicators.align_macro(prices, macro)

    assert aligned.loc[days[1], "DGS10"] == 4.0
    assert aligned.loc[days[3], "DGS10"] == 4.3
    assert aligned.loc[days[4:], "DGS10"].isna().all()


def test_to_changes_uses_bp_for_yields_and_percent_otherwise():
    levels = pd.DataFrame({"SPY": [100.0, 110.0], "DGS10": [4.00, 4.25], "DEXJPUS": [150.0, 147.0]})

    changes = indicators.to_changes(levels)

    assert list(changes.columns) == ["SPY_pct", "DGS10_bp", "DEXJPUS_pct"]
    assert changes.iloc[1].to_dict() == pytest.approx({"SPY_pct": 10.0, "DGS10_bp": 25.0, "DEXJPUS_pct": -2.0})


def test_rotation_regimes_hold_until_opposite_threshold():
    rel = pd.Series([np.nan, 1.0, 5.0, 2.0, -3.0, -5.0, 0.0])

    regime = indicators.rotation_regimes(rel, threshold=4.0)

    assert list(regime) == [None, None, "AI lead", "AI lead", "AI lead", "non-AI lead", "non-AI lead"]


def test_regime_segments_measure_from_prior_close():
    days = pd.bdate_range("2026-01-05", periods=4)
    ai = pd.Series([100.0, 110.0, 121.0, 121.0], index=days)
    non_ai = pd.Series([100.0, 100.0, 100.0, 110.0], index=days)
    regime = pd.Series([None, "AI lead", "AI lead", "non-AI lead"], index=days, dtype=object)
    macro = pd.DataFrame({"DGS10": [4.0, 4.1, 4.2, np.nan]}, index=days)

    seg = indicators.regime_segments(regime, ai, non_ai, macro)

    assert list(seg["regime"]) == ["AI lead", "non-AI lead"]
    assert seg.loc[0, "ai_%"] == pytest.approx(21.0)
    assert seg.loc[0, "DGS10_bp"] == pytest.approx(20.0)
    assert seg.loc[1, "non_ai_%"] == pytest.approx(10.0)
    assert np.isnan(seg.loc[1, "DGS10_bp"])


def test_factor_regression_recovers_known_sensitivity():
    rng = np.random.default_rng(1)
    bp = rng.normal(0, 5, 500)
    changes = pd.DataFrame({"DGS10_bp": bp, "QQQ_pct": -0.1 * bp + rng.normal(0, 0.2, 500)})

    result = indicators.factor_regression(changes, "QQQ_pct", ["DGS10_bp"])

    assert result["nobs"] == 500
    assert result["table"].loc["DGS10_bp", "coef"] == pytest.approx(-0.1, abs=0.01)
