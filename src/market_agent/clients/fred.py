import pandas as pd
from fredapi import Fred

from market_agent.config import require_env


def fetch_series(series_id: str, start: str) -> pd.DataFrame:
    values = Fred(api_key=require_env("FRED_API_KEY")).get_series(series_id, observation_start=start)
    df = values.dropna().rename("value").rename_axis("date").reset_index()
    df["date"] = df["date"].dt.date
    df.insert(0, "series_id", series_id)
    return df
