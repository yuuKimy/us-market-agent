import json

import pandas as pd
import pytest

from market_agent import sentiment


def test_assign_session_rolls_after_close_and_over_holidays():
    trading = pd.DatetimeIndex(["2026-07-02", "2026-07-06", "2026-07-07"])  # 2026-07-03 is a market holiday
    created = pd.Series(pd.to_datetime([
        "2026-07-02 15:59",
        "2026-07-02 16:00",
        "2026-07-04 10:00",
        "2026-07-07 17:00",
    ]).tz_localize("America/New_York").tz_convert("UTC"))

    sessions = sentiment.assign_session(created, trading)

    assert list(sessions[:3].dt.strftime("%Y-%m-%d")) == ["2026-07-02", "2026-07-06", "2026-07-06"]
    assert pd.isna(sessions[3])


def test_parse_scores_reports_all_invalid_lines():
    lines = [
        json.dumps({"news_id": 1, "symbol": "nvda", "score": 0.5, "event_type": "earnings"}),
        json.dumps({"news_id": 1, "symbol": "NVDA", "score": 1.5}),
        json.dumps({"news_id": 2, "symbol": "NVDA", "score": 0.1}),
    ]

    with pytest.raises(ValueError) as err:
        sentiment.parse_scores(lines, known_ids={1})

    assert "line 2" in str(err.value) and "line 3" in str(err.value)
    assert sentiment.parse_scores(lines[:1], known_ids={1}).loc[0, "symbol"] == "NVDA"
