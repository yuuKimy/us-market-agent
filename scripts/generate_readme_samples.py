"""Regenerate the README sample charts from deterministic synthetic data.

    uv run python scripts/generate_readme_samples.py

No API keys are needed and nothing touches data/ or reports/. The prices, yields,
FX, VIX and news below are random but structured (an AI-vs-broad-market spread
that switches regimes, rate sensitivity, a VIX link) so the charts look realistic.
They are not real market data.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="mkt-samples-"))
os.environ["MARKET_AGENT_DB"] = str(WORK / "samples.duckdb")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from market_agent import cli, plots, store
from market_agent.config import ROOT

OUT = ROOT / "docs" / "images"
START, END = "2024-10-01", "2026-09-30"
SEED = 7


def synthetic_market(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.bdate_range(START, END)
    n = len(days)

    def mean_reverting(center: float, speed: float, sd: float) -> np.ndarray:
        level = np.empty(n)
        level[0] = center
        for i in range(1, n):
            level[i] = level[i - 1] + speed * (center - level[i - 1]) + rng.normal(0, sd)
        return level

    dgs10 = mean_reverting(4.2, 0.015, 0.05)
    d10_bp = np.diff(dgs10, prepend=dgs10[0]) * 100
    mkt = rng.normal(0.045, 0.9, n) - 0.02 * d10_bp
    vix = np.empty(n)
    vix[0] = 16.0
    for i in range(1, n):
        vix[i] = max(10.0, vix[i - 1] + 0.08 * (17 - vix[i - 1]) - 0.9 * (mkt[i] - 0.045) + rng.normal(0, 0.6))

    # AI-vs-broad spread: alternating regimes of 30-90 sessions
    spread = np.empty(n)
    i, sign = 0, 1
    while i < n:
        length = int(rng.integers(30, 90))
        spread[i : i + length] = sign * rng.uniform(0.12, 0.35)
        i, sign = i + length, -sign
    spread += rng.normal(0, 0.6, n)

    def path(daily_pct: np.ndarray, start: float) -> np.ndarray:
        return start * np.cumprod(1 + daily_pct / 100)

    def noise(sd: float) -> np.ndarray:
        return rng.normal(0, sd, n)

    returns = {
        "SPY": mkt,
        "SMH": 1.4 * mkt + spread - 0.05 * d10_bp + noise(0.8),
        "QQQ": 1.15 * mkt + 0.45 * spread - 0.03 * d10_bp + noise(0.4),
        "NVDA": 1.7 * mkt + 1.2 * spread - 0.08 * d10_bp + noise(1.6),
        "RSP": 0.95 * mkt + noise(0.35),
        "IWM": 1.15 * mkt - 0.02 * d10_bp + noise(0.7),
        "XLV": 0.6 * mkt + 0.01 + noise(0.6),
        "XLP": 0.5 * mkt + 0.01 + noise(0.5),
        "XLU": 0.55 * mkt + 0.02 * d10_bp * -1 + noise(0.7),
    }
    starts = {"SPY": 570, "SMH": 240, "QQQ": 480, "NVDA": 120, "RSP": 175, "IWM": 220, "XLV": 145, "XLP": 80, "XLU": 75}
    bars = []
    for symbol, r in returns.items():
        px = path(r, starts[symbol])
        bars.append(pd.DataFrame({
            "symbol": symbol, "date": days, "open": px, "high": px * 1.006, "low": px * 0.994, "close": px,
            "volume": rng.integers(2_000_000, 6_000_000, n).astype(float), "trade_count": 1.0, "vwap": px,
        }))

    usdjpy = 150 * np.exp(mean_reverting(0.0, 0.01, 0.0045) + 0.0004 * (dgs10 - 4.2) * 100)
    macro = pd.concat([
        pd.DataFrame({"series_id": "DGS10", "date": days, "value": dgs10}),
        # DEXJPUS is published weekly, so the synthetic series stops a few sessions early too
        pd.DataFrame({"series_id": "DEXJPUS", "date": days[:-4], "value": usdjpy[:-4]}),
        pd.DataFrame({"series_id": "VIXCLS", "date": days, "value": vix}),
    ])
    return pd.concat(bars), macro


def synthetic_news(rng: np.random.Generator, bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    nvda = bars[bars["symbol"] == "NVDA"].set_index("date")["close"]
    ret = (nvda / nvda.shift(1) - 1).iloc[-25:]
    events = ["earnings", "analyst_rating", "product", "supply_chain", "regulatory_legal", "macro", "other"]
    news, scores, next_id = [], [], 1
    for day, r in ret.items():
        for _ in range(int(rng.integers(1, 4))):
            hour = int(rng.choice([8, 11, 14, 17]))
            news.append({
                "id": next_id,
                "created_at": pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=hour),
                "updated_at": None, "headline": f"Synthetic headline {next_id}", "summary": "synthetic",
                "source": "synthetic", "author": "synthetic", "url": None, "symbols": ["NVDA"],
            })
            score = float(np.clip(np.tanh(r * 25) * 0.6 + rng.normal(0, 0.25), -1, 1))
            scores.append({
                "news_id": next_id, "symbol": "NVDA", "score": round(score, 2),
                "confidence": round(float(rng.uniform(0.5, 0.9)), 2), "event_type": str(rng.choice(events)),
                "rationale": "synthetic", "scorer": "synthetic",
            })
            next_id += 1
    return pd.DataFrame(news), pd.DataFrame(scores)


def run(argv: list[str]) -> str:
    args = cli.build_parser().parse_args(argv)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        args.func(args)
    return buf.getvalue()


def watermark(path: Path) -> None:
    img = plt.imread(path)
    h, w = img.shape[:2]
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.imshow(img)
    ax.axis("off")
    ax.text(0.995, 0.005, "Synthetic data, for illustration only", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=11, color="dimgray", bbox={"facecolor": "white", "edgecolor": "lightgray", "pad": 3})
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main() -> None:
    rng = np.random.default_rng(SEED)
    bars, macro = synthetic_market(rng)
    news, scores = synthetic_news(rng, bars)
    con = store.connect()
    store.upsert(con, "bars_daily", bars)
    store.upsert(con, "macro_series", macro)
    store.upsert(con, "news", news)
    store.upsert(con, "news_sentiment", scores, "scored_at")
    con.close()

    plots.REPORTS_DIR = WORK / "reports"
    outputs = {
        "cross_asset": run(["analyze", "cross-asset", "NVDA", "--series", "DGS10", "DEXJPUS",
                            "--start", "2024-11-01", "--plot"]),
        "rotation": run(["analyze", "rotation", "--start", "2024-11-01", "--plot"]),
        "sentiment": run(["sentiment", "summary", "NVDA", "--start", "2026-08-01", "--plot"]),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    names = {"prices_macro_NVDA": "cross_asset_prices.png", "rollcorr_NVDA": "cross_asset_rollcorr.png",
             "rotation_ai": "rotation.png", "sentiment_NVDA": "sentiment.png"}
    for png in sorted((WORK / "reports").glob("*.png")):
        key = png.stem.split("_", 1)[1]
        if key in names:
            target = OUT / names[key]
            shutil.copy(png, target)
            watermark(target)
            print(f"wrote {target.relative_to(ROOT)}")

    if "-v" in sys.argv:
        for name, text in outputs.items():
            print(f"\n===== {name} =====\n{text}")
    shutil.rmtree(WORK)


if __name__ == "__main__":
    main()
