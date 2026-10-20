import numpy as np
import pandas as pd
import statsmodels.api as sm

from market_agent.config import FRED_SERIES


def align_macro(prices: pd.DataFrame, macro: pd.DataFrame, max_gap: int = 5) -> pd.DataFrame:
    """Join macro levels onto stock trading dates.

    Holiday gaps are forward-filled, but never past a series' last observation,
    so a lagging series (e.g. DEXJPUS) shows NaN instead of a stale value.
    """
    macro = macro.reindex(macro.index.union(prices.index)).sort_index()
    filled = macro.ffill(limit=max_gap)
    for col in macro.columns:
        last = macro[col].last_valid_index()
        if last is not None:
            filled.loc[filled.index > last, col] = np.nan
    return prices.join(filled.reindex(prices.index))


def resample(levels: pd.DataFrame, freq: str) -> pd.DataFrame:
    return levels if freq == "D" else levels.resample("W-FRI").last()


def to_changes(levels: pd.DataFrame) -> pd.DataFrame:
    """Stocks/FX/indices -> percent change (`_pct`); yields -> basis-point change (`_bp`)."""
    out = {}
    for col in levels.columns:
        if FRED_SERIES.get(col, (None, None))[1] == "yield":
            out[f"{col}_bp"] = levels[col].diff() * 100
        else:
            out[f"{col}_pct"] = (levels[col] / levels[col].shift(1) - 1) * 100
    return pd.DataFrame(out, index=levels.index)


def change_column(name: str) -> str:
    return f"{name}_bp" if FRED_SERIES.get(name, (None, None))[1] == "yield" else f"{name}_pct"


def rolling_corr(changes: pd.DataFrame, target: str, factors: list[str], window: int) -> pd.DataFrame:
    min_periods = max(int(window * 0.8), 3)
    return changes[factors].rolling(window, min_periods=min_periods).corr(changes[target])


def factor_regression(changes: pd.DataFrame, target: str, factors: list[str], hac_lags: int = 5) -> dict:
    data = changes[[target, *factors]].dropna()
    if len(data) <= len(factors) + 2:
        raise ValueError(f"Not enough overlapping observations for regression ({len(data)})")
    model = sm.OLS(data[target], sm.add_constant(data[factors])).fit(
        cov_type="HAC", cov_kwds={"maxlags": hac_lags}
    )
    table = pd.DataFrame({"coef": model.params, "t": model.tvalues, "p": model.pvalues})
    return {
        "table": table,
        "nobs": int(model.nobs),
        "r2": model.rsquared,
        "start": data.index.min(),
        "end": data.index.max(),
    }


def regime_stats(
    changes: pd.DataFrame, levels: pd.DataFrame, target: str, factors: list[str], regime_series: str, lookback: int
) -> pd.DataFrame:
    trend = levels[regime_series].diff(lookback)
    regime = pd.Series(np.where(trend > 0, f"{regime_series} rising", f"{regime_series} falling"), index=trend.index)
    regime[trend.isna()] = None
    rows = {}
    for name, group in changes.groupby(regime):
        row = {
            "n": int(group[target].notna().sum()),
            "mean": group[target].mean(),
            "std": group[target].std(),
        }
        for f in factors:
            row[f"corr_{f}"] = group[target].corr(group[f])
        rows[name] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def basket_index(prices: pd.DataFrame, members: list[str]) -> pd.Series:
    """Equal-weight, daily-rebalanced basket rebased to 100 (members join when their data starts)."""
    daily = (prices[members] / prices[members].shift(1) - 1).mean(axis=1, skipna=True)
    return 100 * (1 + daily.fillna(0)).cumprod()


def rotation_regimes(rel_return: pd.Series, threshold: float) -> pd.Series:
    """Label each day by which side leads, with hysteresis: the label only flips once the
    rolling relative return crosses the opposite threshold."""
    state, labels = None, []
    for v in rel_return:
        if pd.notna(v):
            if v > threshold:
                state = "AI lead"
            elif v < -threshold:
                state = "non-AI lead"
        labels.append(state)
    return pd.Series(labels, index=rel_return.index, dtype=object)


def regime_segments(
    regime: pd.Series, ai_index: pd.Series, non_ai_index: pd.Series, macro: pd.DataFrame
) -> pd.DataFrame:
    """One row per contiguous regime: returns from the prior close to the segment's last close,
    plus macro changes over the same span (yields in bp, others in %)."""
    labeled = regime.dropna()
    rows = []
    for _, seg in labeled.groupby((labeled != labeled.shift()).cumsum()):
        start, end = seg.index[0], seg.index[-1]
        loc = ai_index.index.get_loc(start)
        base = ai_index.index[loc - 1] if loc > 0 else start
        ai_ret = (ai_index[end] / ai_index[base] - 1) * 100
        non_ret = (non_ai_index[end] / non_ai_index[base] - 1) * 100
        row = {
            "regime": seg.iloc[0],
            "start": start.date(),
            "end": end.date(),
            "days": len(seg),
            "ai_%": ai_ret,
            "non_ai_%": non_ret,
            "spread_pt": ai_ret - non_ret,
        }
        for col in macro.columns:
            before, after = macro[col].loc[:base].dropna(), macro[col].loc[:end].dropna()
            if before.empty or after.empty or after.index[-1] <= base:
                row[change_column(col)] = np.nan
            elif FRED_SERIES.get(col, (None, None))[1] == "yield":
                row[change_column(col)] = (after.iloc[-1] - before.iloc[-1]) * 100
            else:
                row[change_column(col)] = (after.iloc[-1] / before.iloc[-1] - 1) * 100
        rows.append(row)
    return pd.DataFrame(rows)


def snapshot(bars: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for symbol, g in bars.groupby("symbol"):
        g = g.set_index("date").sort_index()
        close, volume = g["close"], g["volume"]
        last = close.iloc[-1]
        ret = {n: (last / close.iloc[-1 - n] - 1) * 100 if len(close) > n else np.nan for n in (1, 5, 21, 63)}
        this_year = close[close.index.year == close.index[-1].year]
        prior = close[close.index < this_year.index[0]]
        ytd_base = prior.iloc[-1] if len(prior) else this_year.iloc[0]
        high_52w = close.iloc[-252:].max()
        rows[symbol] = {
            "as_of": close.index[-1].date(),
            "close": last,
            "1d_%": ret[1],
            "5d_%": ret[5],
            "1m_%": ret[21],
            "3m_%": ret[63],
            "ytd_%": (last / ytd_base - 1) * 100,
            "from_52w_high_%": (last / high_52w - 1) * 100,
            "vol_vs_20d": volume.iloc[-1] / volume.iloc[-21:-1].mean() if len(volume) > 20 else np.nan,
        }
    return pd.DataFrame.from_dict(rows, orient="index")
