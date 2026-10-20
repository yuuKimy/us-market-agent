import json

import numpy as np
import pandas as pd

EVENT_TYPES = {
    "earnings",
    "guidance",
    "analyst_rating",
    "product",
    "regulatory_legal",
    "m_and_a",
    "management",
    "capital_return",
    "supply_chain",
    "macro",
    "other",
}
SCORE_COLUMNS = ["news_id", "symbol", "score", "confidence", "event_type", "rationale", "scorer"]


def parse_scores(lines: list[str], known_ids: set[int]) -> pd.DataFrame:
    """Validate agent-produced JSONL scores; raises ValueError listing every bad line."""
    rows, errors = [], []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            row = {
                "news_id": int(r["news_id"]),
                "symbol": str(r["symbol"]).upper(),
                "score": float(r["score"]),
                "confidence": float(r.get("confidence", 1.0)),
                "event_type": r.get("event_type", "other"),
                "rationale": str(r.get("rationale", "")),
                "scorer": str(r.get("scorer", "cursor-agent")),
            }
        except (KeyError, ValueError, TypeError) as e:
            errors.append(f"line {n}: {e}")
            continue
        if not -1 <= row["score"] <= 1:
            errors.append(f"line {n}: score must be in [-1, 1]")
        elif not 0 <= row["confidence"] <= 1:
            errors.append(f"line {n}: confidence must be in [0, 1]")
        elif row["event_type"] not in EVENT_TYPES:
            errors.append(f"line {n}: unknown event_type {row['event_type']!r}")
        elif row["news_id"] not in known_ids:
            errors.append(f"line {n}: news_id {row['news_id']} is not in the news table")
        else:
            rows.append(row)
    if errors:
        raise ValueError("\n".join(errors))
    return pd.DataFrame(rows, columns=SCORE_COLUMNS)


def assign_session(created_at: pd.Series, trading_dates: pd.DatetimeIndex) -> pd.Series:
    """Map article timestamps to the first trading session whose close can reflect them.

    Articles published at or after 16:00 ET belong to the next session.
    """
    et = created_at.dt.tz_convert("America/New_York")
    day = et.dt.tz_localize(None).dt.normalize()
    day = day + pd.to_timedelta((et.dt.hour >= 16).astype(int), unit="D")
    idx = trading_dates.searchsorted(day.to_numpy(), side="left")
    sessions = pd.Series(pd.NaT, index=created_at.index, dtype="datetime64[ns]")
    valid = idx < len(trading_dates)
    sessions[valid] = trading_dates[idx[valid]]
    return sessions


def daily_sentiment(scored: pd.DataFrame, trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Confidence-weighted mean score per (symbol, session)."""
    df = scored.copy()
    df["session"] = assign_session(df["created_at"], trading_dates)
    df = df.dropna(subset=["session"])
    df["w"] = df["confidence"].fillna(1.0)
    df["ws"] = df["score"] * df["w"]
    g = df.groupby(["symbol", "session"])
    out = pd.DataFrame({"sentiment": (g["ws"].sum() / g["w"].sum()).round(4), "articles": g.size()})
    return out.reset_index()


def sentiment_vs_returns(daily: pd.DataFrame, closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join daily sentiment with same-session and next-session returns (%).

    Returns (joined rows, per-symbol summary).
    """
    rets = (closes / closes.shift(1) - 1) * 100
    long = rets.stack().rename("ret_same_pct").rename_axis(["session", "symbol"]).reset_index()
    nxt = rets.shift(-1).stack().rename("ret_next_pct").rename_axis(["session", "symbol"]).reset_index()
    joined = daily.merge(long, on=["session", "symbol"], how="left").merge(nxt, on=["session", "symbol"], how="left")

    def bucket(s: float) -> str:
        return "negative" if s < -0.2 else "positive" if s > 0.2 else "neutral"

    joined["bucket"] = joined["sentiment"].map(bucket)
    rows = {}
    for symbol, g in joined.groupby("symbol"):
        row = {
            "sessions": len(g),
            "articles": int(g["articles"].sum()),
            "avg_sentiment": g["sentiment"].mean(),
            "spearman_same": g["sentiment"].corr(g["ret_same_pct"], method="spearman"),
            "spearman_next": g["sentiment"].corr(g["ret_next_pct"], method="spearman"),
        }
        for b in ("negative", "neutral", "positive"):
            sub = g[g["bucket"] == b]
            row[f"n_{b}"] = len(sub)
            row[f"next_ret_{b}_pct"] = sub["ret_next_pct"].mean() if len(sub) else np.nan
        rows[symbol] = row
    return joined, pd.DataFrame.from_dict(rows, orient="index")
