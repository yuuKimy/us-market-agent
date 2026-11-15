"""Alpaca options data: ATM monthly metrics per session day."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.enums import OptionsFeed
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, OptionSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest

from market_agent.clients.alpaca import _keys
from market_agent.options_select import pick_atm_strike, pick_expiry, strikes_in_band

OPTIONS_STRIKE_COLUMNS = [
    "underlying",
    "date",
    "expiry",
    "strike",
    "option_type",
    "contract_symbol",
    "volume",
    "close",
    "vwap",
    "iv",
    "underlying_close",
    "atm_strike",
    "feed",
]

ET = ZoneInfo("America/New_York")

OPTIONS_METRICS_COLUMNS = [
    "underlying",
    "date",
    "expiry",
    "atm_strike",
    "call_symbol",
    "put_symbol",
    "iv_call",
    "iv_put",
    "iv_atm",
    "volume_call",
    "volume_put",
    "open_interest_call",
    "open_interest_put",
    "underlying_close",
    "feed",
]


def _options_feed() -> OptionsFeed:
    raw = os.environ.get("ALPACA_OPTIONS_FEED", "indicative").lower()
    return OptionsFeed.OPRA if raw == "opra" else OptionsFeed.INDICATIVE


def _trading_client() -> TradingClient:
    paper = os.environ.get("ALPACA_PAPER_TRADE", "true").lower() in ("1", "true", "yes")
    return TradingClient(*_keys(), paper=paper)


def _option_data_client() -> OptionHistoricalDataClient:
    return OptionHistoricalDataClient(*_keys())


def _contracts_for_expiry(underlying: str, expiry: date) -> pd.DataFrame:
    client = _trading_client()
    rows: list[dict] = []
    token: str | None = None
    while True:
        req = GetOptionContractsRequest(
            underlying_symbols=[underlying],
            expiration_date=expiry,
            limit=1000,
            page_token=token,
        )
        page = client.get_option_contracts(req)
        for c in page.option_contracts or []:
            raw_type = c.type.value if hasattr(c.type, "value") else str(c.type)
            oi = c.open_interest
            rows.append(
                {
                    "symbol": c.symbol,
                    "strike": float(c.strike_price),
                    "type": str(raw_type).lower(),
                    "open_interest": float(oi) if oi is not None else None,
                }
            )
        token = page.next_page_token
        if not token:
            break
    return pd.DataFrame(rows)


def _session_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=ET)
    return start, start + timedelta(days=1)


def _daily_option_bars(symbols: list[str], day: date) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame(columns=["symbol", "volume", "close", "vwap"])
    start, end = _session_bounds(day)
    frames: list[pd.DataFrame] = []
    chunk = 50
    client = _option_data_client()
    feed = _options_feed()
    for i in range(0, len(symbols), chunk):
        batch = symbols[i : i + chunk]
        request = OptionBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=feed,
        )
        df = client.get_option_bars(request).df
        if df.empty:
            continue
        df = df.reset_index()
        df["date"] = df["timestamp"].dt.tz_convert(ET).dt.date
        df = df.loc[df["date"] == day, ["symbol", "volume", "close", "vwap"]]
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["symbol", "volume", "close", "vwap"])
    return pd.concat(frames, ignore_index=True)


def _snapshot_iv(symbols: list[str]) -> dict[str, float | None]:
    if not symbols:
        return {}
    request = OptionSnapshotRequest(symbol_or_symbols=symbols, feed=_options_feed())
    snaps = _option_data_client().get_option_snapshot(request)
    out: dict[str, float | None] = {}
    for sym in symbols:
        snap = snaps.get(sym)
        if snap is None:
            continue
        iv = snap.implied_volatility
        out[sym] = float(iv) if iv is not None else None
    return out


def _contract_open_interest(contracts: pd.DataFrame, symbol: str | None) -> float | None:
    if not symbol or contracts.empty or "open_interest" not in contracts.columns:
        return None
    val = contracts.loc[contracts["symbol"] == symbol, "open_interest"]
    if val.empty or pd.isna(val.iloc[0]):
        return None
    return float(val.iloc[0])


def _pair_symbols(contracts: pd.DataFrame, strike: float) -> tuple[str | None, str | None]:
    sub = contracts.loc[contracts["strike"] == strike]
    call = sub.loc[sub["type"] == "call", "symbol"]
    put = sub.loc[sub["type"] == "put", "symbol"]
    call_sym = call.iloc[0] if len(call) else None
    put_sym = put.iloc[0] if len(put) else None
    return call_sym, put_sym


def fetch_options_data(
    underlying: str,
    schedule: pd.DataFrame,
    *,
    dte_min: int = 7,
    dte_max: int = 45,
    strike_steps: int = 10,
    fill_iv_for_latest: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build daily ATM monthly option metrics.

    schedule: columns date (datetime or date), close (underlying close).
    IV snapshots and open interest are only filled for the latest session (historical IV/OI
    are usually unavailable from these APIs; OI comes from the contract listing at fetch time).
    """
    empty_m = pd.DataFrame(columns=OPTIONS_METRICS_COLUMNS)
    empty_s = pd.DataFrame(columns=OPTIONS_STRIKE_COLUMNS)
    if schedule.empty:
        return empty_m, empty_s

    schedule = schedule.copy()
    schedule["date"] = pd.to_datetime(schedule["date"]).dt.date
    schedule = schedule.sort_values("date")
    latest_day = schedule["date"].iloc[-1]
    feed = _options_feed().value
    metric_rows: list[dict] = []
    strike_rows: list[dict] = []
    contract_cache: dict[date, pd.DataFrame] = {}

    for _, row in schedule.iterrows():
        day: date = row["date"]
        close = float(row["close"])
        expiry = pick_expiry(day, dte_min, dte_max)
        if expiry is None:
            continue
        if expiry not in contract_cache:
            contracts = _contracts_for_expiry(underlying, expiry)
            contract_cache[expiry] = contracts
        else:
            contracts = contract_cache[expiry]
        if contracts.empty:
            continue
        atm = pick_atm_strike(close, contracts["strike"].tolist())
        if atm is None:
            continue
        band = strikes_in_band(atm, contracts["strike"].tolist(), strike_steps) if strike_steps >= 0 else []
        symbol_map: list[tuple[float, str, str]] = []
        for k in band:
            call_sym, put_sym = _pair_symbols(contracts, k)
            if call_sym:
                symbol_map.append((k, "call", call_sym))
            if put_sym:
                symbol_map.append((k, "put", put_sym))
        all_symbols = [s for _, _, s in symbol_map]
        bar_df = _daily_option_bars(all_symbols, day) if all_symbols else pd.DataFrame()
        bar_by_sym = bar_df.set_index("symbol") if not bar_df.empty else pd.DataFrame()

        snap_iv: dict[str, float | None] = {}
        if fill_iv_for_latest and day == latest_day and all_symbols:
            snap_iv = _snapshot_iv(all_symbols)

        for strike, opt_type, sym in symbol_map:
            bar = bar_by_sym.loc[sym] if sym in bar_by_sym.index else None
            strike_rows.append(
                {
                    "underlying": underlying,
                    "date": day,
                    "expiry": expiry,
                    "strike": strike,
                    "option_type": opt_type,
                    "contract_symbol": sym,
                    "volume": float(bar["volume"]) if bar is not None and pd.notna(bar["volume"]) else None,
                    "close": float(bar["close"]) if bar is not None and pd.notna(bar["close"]) else None,
                    "vwap": float(bar["vwap"]) if bar is not None and pd.notna(bar["vwap"]) else None,
                    "iv": snap_iv.get(sym),
                    "underlying_close": close,
                    "atm_strike": atm,
                    "feed": feed,
                }
            )

        call_sym, put_sym = _pair_symbols(contracts, atm)
        vol_c = vol_p = None
        iv_call = iv_put = oi_call = oi_put = None
        if call_sym and call_sym in bar_by_sym.index:
            vol_c = bar_by_sym.loc[call_sym, "volume"]
        if put_sym and put_sym in bar_by_sym.index:
            vol_p = bar_by_sym.loc[put_sym, "volume"]
        if fill_iv_for_latest and day == latest_day:
            if call_sym and call_sym in snap_iv:
                iv_call = snap_iv[call_sym]
            if put_sym and put_sym in snap_iv:
                iv_put = snap_iv[put_sym]
            oi_call = _contract_open_interest(contracts, call_sym)
            oi_put = _contract_open_interest(contracts, put_sym)

        iv_vals = [v for v in (iv_call, iv_put) if v is not None]
        iv_atm = sum(iv_vals) / len(iv_vals) if iv_vals else None
        metric_rows.append(
            {
                "underlying": underlying,
                "date": day,
                "expiry": expiry,
                "atm_strike": atm,
                "call_symbol": call_sym,
                "put_symbol": put_sym,
                "iv_call": iv_call,
                "iv_put": iv_put,
                "iv_atm": iv_atm,
                "volume_call": float(vol_c) if vol_c is not None and pd.notna(vol_c) else None,
                "volume_put": float(vol_p) if vol_p is not None and pd.notna(vol_p) else None,
                "open_interest_call": oi_call,
                "open_interest_put": oi_put,
                "underlying_close": close,
                "feed": feed,
            }
        )

    return (
        pd.DataFrame(metric_rows, columns=OPTIONS_METRICS_COLUMNS),
        pd.DataFrame(strike_rows, columns=OPTIONS_STRIKE_COLUMNS),
    )


def fetch_options_metrics(
    underlying: str,
    schedule: pd.DataFrame,
    *,
    dte_min: int = 7,
    dte_max: int = 45,
    strike_steps: int = 10,
    fill_iv_for_latest: bool = True,
) -> pd.DataFrame:
    metrics, _ = fetch_options_data(
        underlying,
        schedule,
        dte_min=dte_min,
        dte_max=dte_max,
        strike_steps=strike_steps,
        fill_iv_for_latest=fill_iv_for_latest,
    )
    return metrics