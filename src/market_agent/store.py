from datetime import date

import duckdb
import pandas as pd

from market_agent.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars_daily (
    symbol VARCHAR NOT NULL,
    date DATE NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume DOUBLE, trade_count DOUBLE, vwap DOUBLE,
    fetched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS macro_series (
    series_id VARCHAR NOT NULL,
    date DATE NOT NULL,
    value DOUBLE,
    fetched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (series_id, date)
);
CREATE TABLE IF NOT EXISTS news (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    headline VARCHAR,
    summary VARCHAR,
    source VARCHAR,
    author VARCHAR,
    url VARCHAR,
    symbols VARCHAR[],
    fetched_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS news_sentiment (
    news_id BIGINT NOT NULL,
    symbol VARCHAR NOT NULL,
    score DOUBLE NOT NULL,
    confidence DOUBLE,
    event_type VARCHAR,
    rationale VARCHAR,
    scorer VARCHAR,
    scored_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (news_id, symbol)
);
"""


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    if read_only and DB_PATH.exists():
        return duckdb.connect(str(DB_PATH), read_only=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA)
    return con


def upsert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame, timestamp_column: str = "fetched_at") -> int:
    if df.empty:
        return 0
    columns = ", ".join(df.columns)
    con.register("incoming", df)
    con.execute(
        f"INSERT OR REPLACE INTO {table} ({columns}, {timestamp_column}) "
        f"SELECT {columns}, current_timestamp FROM incoming"
    )
    con.unregister("incoming")
    return len(df)


def last_dates(con: duckdb.DuckDBPyConnection, table: str, key: str) -> dict[str, date]:
    rows = con.execute(f"SELECT {key}, max(date) FROM {table} GROUP BY {key}").fetchall()
    return dict(rows)


def load_closes(con: duckdb.DuckDBPyConnection, symbols: list[str], start: str | None = None) -> pd.DataFrame:
    df = con.execute(
        "SELECT date, symbol, close FROM bars_daily WHERE list_contains(?, symbol) AND date >= coalesce(?::DATE, DATE '1900-01-01')",
        [symbols, start],
    ).df()
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot(index="date", columns="symbol", values="close").sort_index()


def load_bars(con: duckdb.DuckDBPyConnection, symbols: list[str], start: str | None = None) -> pd.DataFrame:
    df = con.execute(
        "SELECT * FROM bars_daily WHERE list_contains(?, symbol) AND date >= coalesce(?::DATE, DATE '1900-01-01') ORDER BY symbol, date",
        [symbols, start],
    ).df()
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_macro(con: duckdb.DuckDBPyConnection, series: list[str], start: str | None = None) -> pd.DataFrame:
    df = con.execute(
        "SELECT date, series_id, value FROM macro_series WHERE list_contains(?, series_id) AND date >= coalesce(?::DATE, DATE '1900-01-01')",
        [series, start],
    ).df()
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot(index="date", columns="series_id", values="value").sort_index()


def status(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    return {
        "bars_daily": con.execute(
            "SELECT symbol, count(*) AS rows, min(date) AS first, max(date) AS as_of FROM bars_daily GROUP BY 1 ORDER BY 1"
        ).df(),
        "macro_series": con.execute(
            "SELECT series_id, count(*) AS rows, min(date) AS first, max(date) AS as_of FROM macro_series GROUP BY 1 ORDER BY 1"
        ).df(),
        "news": con.execute(
            "SELECT count(*) AS articles, min(created_at) AS first, max(created_at) AS latest FROM news"
        ).df(),
        "news_sentiment": con.execute(
            "SELECT symbol, count(*) AS scored, round(avg(score), 3) AS avg_score FROM news_sentiment GROUP BY 1 ORDER BY 1"
        ).df(),
    }
