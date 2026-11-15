import json
from datetime import date

import duckdb
import pandas as pd

from market_agent import injection
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
CREATE TABLE IF NOT EXISTS news_safety (
    news_id BIGINT PRIMARY KEY,
    scanned_at TIMESTAMPTZ NOT NULL,
    max_severity VARCHAR NOT NULL,
    rules_json VARCHAR NOT NULL,
    scanner_version VARCHAR NOT NULL
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


def upsert_news_safety(con: duckdb.DuckDBPyConnection, news_id: int, result: injection.ScanResult) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO news_safety (news_id, scanned_at, max_severity, rules_json, scanner_version)
        VALUES (?, current_timestamp, ?, ?, ?)
        """,
        [news_id, result.max_severity, json.dumps(list(result.rules), ensure_ascii=False), injection.SCANNER_VERSION],
    )


def scan_news_frame(con: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> int:
    """Scan headline/summary for each row with id; return count updated."""
    if frame.empty or "id" not in frame.columns:
        return 0
    n = 0
    for row in frame.itertuples(index=False):
        result = injection.scan_article(getattr(row, "headline", None), getattr(row, "summary", None))
        upsert_news_safety(con, int(row.id), result)
        n += 1
    return n


def load_news_safety(con: duckdb.DuckDBPyConnection, news_id: int) -> injection.ScanResult | None:
    row = con.execute(
        "SELECT max_severity, rules_json, scanner_version FROM news_safety WHERE news_id = ?",
        [news_id],
    ).fetchone()
    if not row:
        return None
    max_severity, rules_json, version = row
    if version != injection.SCANNER_VERSION:
        return None
    rules = tuple(json.loads(rules_json))
    return injection.ScanResult(max_severity, rules)


def safety_for_article(
    con: duckdb.DuckDBPyConnection,
    news_id: int,
    headline: str | None,
    summary: str | None,
) -> injection.ScanResult:
    cached = load_news_safety(con, news_id)
    if cached is not None:
        return cached
    result = injection.scan_article(headline, summary)
    upsert_news_safety(con, news_id, result)
    return result


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
