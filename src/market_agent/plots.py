import math
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import AutoMinorLocator, MaxNLocator

from market_agent.config import FRED_SERIES, REPORTS_DIR

WIDTH = 11


def _save(fig: plt.Figure, name: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{date.today():%Y%m%d}_{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _guides(ax: plt.Axes, y_ticks: int = 8) -> None:
    ax.yaxis.set_major_locator(MaxNLocator(nbins=y_ticks, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.grid(which="major", linewidth=0.6, alpha=0.4)
    ax.grid(which="minor", axis="y", linestyle=":", linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)


def _baseline(ax: plt.Axes, value: float) -> None:
    ax.axhline(value, color="black", linestyle="--", linewidth=0.9, alpha=0.6)


def _symmetric_ylim(ax: plt.Axes, values: pd.Series | pd.DataFrame, floor: float, cap: float = 1.0) -> None:
    """Zoom a bounded score (correlation, sentiment) around 0 in 0.25 steps instead of always ±1."""
    peak = float(pd.DataFrame(values).abs().max().max()) if len(values) else 0.0
    limit = min(cap, max(floor, math.ceil(peak * 1.15 / 0.25) * 0.25))
    ax.set_ylim(-limit, limit)


def rolling_corr(rc: pd.DataFrame, target: str, window: int, name: str) -> Path:
    fig, ax = plt.subplots(figsize=(WIDTH, 5.5))
    rc.plot(ax=ax)
    _symmetric_ylim(ax, rc, floor=0.5)
    _guides(ax)
    _baseline(ax, 0)
    ax.set_title(f"Rolling {window}-period correlation with {target}")
    ax.set_ylabel("correlation")
    ax.set_xlabel("")
    return _save(fig, name)


def prices_and_macro(levels: pd.DataFrame, symbols: list[str], series: list[str], name: str) -> Path:
    fig, axes = plt.subplots(
        1 + len(series),
        1,
        figsize=(WIDTH, 4.8 + 2.8 * len(series)),
        sharex=True,
        squeeze=False,
        height_ratios=[1.7] + [1] * len(series),
    )
    axes = axes[:, 0]
    prices = levels[symbols].dropna(how="all")
    (prices / prices.bfill().iloc[0] * 100).plot(ax=axes[0])
    axes[0].set_title("Adjusted close, rebased to 100")
    axes[0].set_ylabel("index (start = 100)")
    _baseline(axes[0], 100)
    for ax, s in zip(axes[1:], series):
        levels[s].dropna().plot(ax=ax, color="tab:red")
        ax.set_title(f"{s}: {FRED_SERIES.get(s, (s,))[0]}")
        ax.set_ylabel("%" if FRED_SERIES.get(s, (None, None))[1] == "yield" else "level")
    for ax in axes:
        _guides(ax)
    axes[-1].set_xlabel("")
    return _save(fig, name)


def rotation(
    ai_index: pd.Series,
    non_ai_index: pd.Series,
    rel_return: pd.Series,
    segments: pd.DataFrame,
    window: int,
    threshold: float,
    name: str,
) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(WIDTH, 9), sharex=True, height_ratios=[2, 2, 1.4])
    ai_index.plot(ax=axes[0], label="AI basket", color="tab:blue")
    non_ai_index.plot(ax=axes[0], label="non-AI basket", color="tab:gray")
    axes[0].set_title("Equal-weight baskets, rebased to 100")
    axes[0].legend(loc="upper left")
    _baseline(axes[0], 100)
    (ai_index / non_ai_index * 100).plot(ax=axes[1], color="black", linewidth=1.2)
    axes[1].set_title("Relative strength: AI / non-AI (100 = start)")
    _baseline(axes[1], 100)
    rel_return.plot(ax=axes[2], color="tab:purple", linewidth=1)
    for level in (threshold, -threshold):
        axes[2].axhline(level, color="grey", linestyle="--", linewidth=0.8)
    axes[2].axhline(0, color="grey", linewidth=0.8)
    axes[2].set_title(f"{window}-day relative return (%), regime threshold ±{threshold}%")
    for ax in axes:
        _guides(ax)
    for seg in segments.itertuples():
        color = "tab:blue" if seg.regime == "AI lead" else "tab:orange"
        for ax in axes:
            ax.axvspan(pd.Timestamp(seg.start), pd.Timestamp(seg.end), color=color, alpha=0.08, linewidth=0)
    axes[-1].set_xlabel("shaded: blue = AI lead, orange = non-AI lead")
    return _save(fig, name)


def sentiment(joined: pd.DataFrame, closes: pd.DataFrame, name: str) -> Path:
    symbols = sorted(joined["symbol"].unique())
    fig, axes = plt.subplots(len(symbols), 1, figsize=(WIDTH, 4.8 * len(symbols)), squeeze=False)
    for ax, symbol in zip(axes[:, 0], symbols):
        g = joined[joined["symbol"] == symbol]
        colors = ["tab:green" if s > 0 else "tab:red" for s in g["sentiment"]]
        ax.bar(g["session"], g["sentiment"], color=colors, width=0.8)
        _symmetric_ylim(ax, g["sentiment"], floor=0.25)
        _guides(ax)
        _baseline(ax, 0)
        ax.set_ylabel("sentiment")
        ax.set_title(f"{symbol}: daily news sentiment vs close")
        price = closes[symbol].loc[g["session"].min() : g["session"].max()]
        ax2 = ax.twinx()
        ax2.plot(price.index, price.values, color="black", linewidth=1)
        ax2.set_ylabel("close")
        locator = mdates.AutoDateLocator(maxticks=10)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    return _save(fig, name)
