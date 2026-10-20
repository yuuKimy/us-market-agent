import os
from datetime import UTC, datetime, timedelta

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from market_agent.config import require_env

BAR_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
NEWS_COLUMNS = ["id", "created_at", "updated_at", "headline", "summary", "source", "author", "url", "symbols"]


def _keys() -> tuple[str, str]:
    return require_env("ALPACA_API_KEY"), require_env("ALPACA_SECRET_KEY")


def fetch_daily_bars(symbols: list[str], start: datetime, end: datetime | None = None) -> pd.DataFrame:
    feed = DataFeed(os.environ.get("ALPACA_DATA_FEED", "sip"))
    if end is None and feed == DataFeed.SIP:
        # The free plan rejects SIP queries that touch the latest 15 minutes.
        end = datetime.now(UTC) - timedelta(minutes=16)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment=Adjustment.ALL,
        feed=feed,
    )
    df = StockHistoricalDataClient(*_keys()).get_stock_bars(request).df
    if df.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)
    df = df.reset_index()
    df["date"] = df["timestamp"].dt.tz_convert("America/New_York").dt.date
    return df[BAR_COLUMNS]


def fetch_news(symbols: list[str], start: datetime, end: datetime | None, limit: int) -> pd.DataFrame:
    request = NewsRequest(
        symbols=",".join(symbols),
        start=start,
        end=end,
        limit=limit,
        sort="desc",
        include_content=False,
    )
    articles = NewsClient(*_keys()).get_news(request).data.get("news", [])
    if not articles:
        return pd.DataFrame(columns=NEWS_COLUMNS)
    return pd.DataFrame([a.model_dump() for a in articles])[NEWS_COLUMNS]
