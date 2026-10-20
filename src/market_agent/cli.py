import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from market_agent import indicators, plots, sentiment, store
from market_agent.config import (
    DEFAULT_HISTORY_START,
    FRED_SERIES,
    REPORTS_DIR,
    ROTATION_AI,
    ROTATION_NON_AI,
)

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 300)


def _print(title: str, df: pd.DataFrame, digits: int = 3) -> None:
    print(f"\n## {title}")
    if df.empty:
        print("(no rows)")
        return
    print(df.round({c: digits for c in df.select_dtypes("number").columns}).to_string())


def _utc(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def _upper(symbols: list[str] | None) -> list[str]:
    return [s.upper() for s in symbols or []]


def _require_columns(frame: pd.DataFrame, names: list[str], hint: str) -> None:
    missing = [n for n in names if n not in frame.columns]
    if missing:
        raise SystemExit(f"No stored data for {', '.join(missing)}. Run: {hint} {' '.join(missing)}")


def _as_of(levels: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {"first": levels.apply(lambda c: c.first_valid_index()), "as_of": levels.apply(lambda c: c.last_valid_index())}
    )


# --- fetch ---------------------------------------------------------------


def cmd_fetch_bars(args: argparse.Namespace) -> None:
    from market_agent.clients import alpaca

    con = store.connect()
    last = store.last_dates(con, "bars_daily", "symbol")
    symbols = _upper(args.symbols) or sorted(last)
    if not symbols:
        raise SystemExit("No symbols given and none stored yet.")

    groups: dict[str, list[str]] = {}
    if args.full:
        groups[args.start or DEFAULT_HISTORY_START] = symbols
    else:
        new = [s for s in symbols if s not in last]
        existing = [s for s in symbols if s in last]
        if new:
            groups.setdefault(args.start or DEFAULT_HISTORY_START, []).extend(new)
        if existing:
            overlap_start = str(min(last[s] for s in existing) - timedelta(days=7))
            groups.setdefault(args.start or overlap_start, []).extend(existing)

    for start, group in groups.items():
        df = alpaca.fetch_daily_bars(group, _utc(start))
        df["date"] = pd.to_datetime(df["date"])
        if args.full:
            con.execute("DELETE FROM bars_daily WHERE list_contains(?, symbol)", [group])
        else:
            old = store.load_bars(con, group, start)[["symbol", "date", "close"]]
            merged = df.merge(old, on=["symbol", "date"], suffixes=("", "_old"))
            drift = merged.loc[(merged["close"] / merged["close_old"] - 1).abs() > 1e-3, "symbol"].unique()
            if len(drift):
                print(f"WARNING: adjusted history changed for {', '.join(drift)} (split/dividend). "
                      f"Run: mkt fetch bars {' '.join(drift)} --full")
        print(f"fetched {store.upsert(con, 'bars_daily', df)} bars for {', '.join(group)} from {start}")

    status = store.status(con)["bars_daily"]
    _print("bars_daily", status[status["symbol"].isin(symbols)])


def cmd_fetch_macro(args: argparse.Namespace) -> None:
    from market_agent.clients import fred

    con = store.connect()
    last = store.last_dates(con, "macro_series", "series_id")
    series = _upper(args.series) or list(FRED_SERIES)
    for s in series:
        if s not in FRED_SERIES:
            print(f"WARNING: {s} is not in the catalog; it will be treated as a level series.")
        # Re-fetch a 30-day overlap because FRED revises recent observations.
        start = args.start or (str(last[s] - timedelta(days=30)) if s in last else DEFAULT_HISTORY_START)
        print(f"{s}: {store.upsert(con, 'macro_series', fred.fetch_series(s, start))} rows from {start}")
    status = store.status(con)["macro_series"]
    _print("macro_series", status[status["series_id"].isin(series)])


def cmd_fetch_news(args: argparse.Namespace) -> None:
    from market_agent.clients import alpaca

    con = store.connect()
    start = _utc(args.start) if args.start else datetime.now(UTC) - timedelta(days=7)
    end = _utc(args.end) + timedelta(days=1) if args.end else None
    df = alpaca.fetch_news(_upper(args.symbols), start, end, args.limit)
    n = store.upsert(con, "news", df)
    print(f"fetched {n} articles for {', '.join(_upper(args.symbols))} since {start:%Y-%m-%d}")
    if n == args.limit:
        print(f"NOTE: hit --limit {args.limit}; older articles in the range may be missing.")
    _print("news", store.status(con)["news"])


# --- inspect -------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    store.connect().close()
    print(f"schema ready: {store.DB_PATH}")


def cmd_status(args: argparse.Namespace) -> None:
    for name, df in store.status(store.connect(read_only=True)).items():
        _print(name, df)


def cmd_query(args: argparse.Namespace) -> None:
    df = store.connect(read_only=True).execute(args.sql).df()
    print(df.to_string(max_rows=args.max_rows))


def cmd_snapshot(args: argparse.Namespace) -> None:
    symbols = _upper(args.symbols)
    bars = store.load_bars(store.connect(read_only=True), symbols, str(date.today() - timedelta(days=400)))
    missing = sorted(set(symbols) - set(bars["symbol"]))
    if missing:
        raise SystemExit(f"No stored bars for {', '.join(missing)}. Run: mkt fetch bars {' '.join(missing)}")
    _print("snapshot (adjusted close, % change)", indicators.snapshot(bars), digits=2)


# --- analysis ------------------------------------------------------------


def _levels(con, symbols: list[str], series: list[str], start: str | None) -> pd.DataFrame:
    prices = store.load_closes(con, symbols, start)
    _require_columns(prices, symbols, "mkt fetch bars")
    macro = store.load_macro(con, series, start)
    _require_columns(macro, series, "mkt fetch macro")
    return indicators.align_macro(prices, macro)


def cmd_cross_asset(args: argparse.Namespace) -> None:
    symbols, series = _upper(args.symbols), _upper(args.series)
    market = None if args.market.lower() == "none" else args.market.upper()
    con = store.connect(read_only=True)
    columns = symbols + ([market] if market and market not in symbols else [])
    levels = indicators.resample(_levels(con, columns, series, args.start), args.freq)
    changes = indicators.to_changes(levels)
    factors = [indicators.change_column(s) for s in series]
    lookback = 20 if args.freq == "D" else 4

    print(f"# Cross-asset analysis ({'daily' if args.freq == 'D' else 'weekly'}, stock/FX in %, yields in bp)")
    if args.freq == "W":
        print("Weekly rows are labeled by the week-ending Friday and use the last available value in each week.")
    _print("data coverage", _as_of(levels))

    for symbol in symbols:
        target = indicators.change_column(symbol)
        fac = factors + ([indicators.change_column(market)] if market and symbol != market else [])
        reg = indicators.factor_regression(changes, target, fac)
        print(f"\n# {symbol}")
        _print(
            f"OLS {target} ~ {' + '.join(fac)} (HAC SE) | n={reg['nobs']} R2={reg['r2']:.3f} "
            f"| {reg['start']:%Y-%m-%d}..{reg['end']:%Y-%m-%d}",
            reg["table"],
            digits=4,
        )
        _print("full-period correlation", changes[[target, *fac]].corr()[[target]].drop(target))
        rc = indicators.rolling_corr(changes, target, factors, args.window)
        _print(
            f"rolling {args.window}-period correlation",
            pd.DataFrame({"latest": rc.ffill().iloc[-1], "min": rc.min(), "max": rc.max(), "median": rc.median()}),
        )
        _print(
            f"regimes by {lookback}-period change in {series[0]}",
            indicators.regime_stats(changes, levels, target, fac, series[0], lookback),
        )
        if args.plot:
            print(f"plot: {plots.rolling_corr(rc, symbol, args.window, f'rollcorr_{symbol}')}")

    if args.plot:
        name = f"prices_macro_{'_'.join(symbols)}"
        print(f"plot: {plots.prices_and_macro(levels, symbols, series, name)}")


def cmd_rotation(args: argparse.Namespace) -> None:
    ai, non_ai, series = _upper(args.ai), _upper(args.non_ai), _upper(args.series)
    levels = _levels(store.connect(read_only=True), ai + non_ai, series, args.start)
    prices = levels[ai + non_ai]
    ai_idx, non_idx = indicators.basket_index(prices, ai), indicators.basket_index(prices, non_ai)
    rs = ai_idx / non_idx * 100
    rel = (rs / rs.shift(args.window) - 1) * 100
    regime = indicators.rotation_regimes(rel, args.threshold)
    segments = indicators.regime_segments(regime, ai_idx, non_idx, levels[series])

    print(f"# AI vs non-AI rotation | AI: {' '.join(ai)} | non-AI: {' '.join(non_ai)}")
    print(f"Equal-weight daily-rebalanced baskets. Regime = sign of {args.window}-day relative return "
          f"beyond ±{args.threshold}% (hysteresis), so turns are detected with a lag.")
    _print("data coverage", _as_of(levels))

    labeled = regime.dropna()
    if labeled.empty:
        raise SystemExit("Not enough history to label regimes; use an earlier --start.")
    current = segments.iloc[-1]
    rs_change = {f"rs_{n}d_%": (rs.iloc[-1] / rs.iloc[-1 - n] - 1) * 100 for n in (5, 21, 63) if len(rs) > n}
    _print("current", pd.DataFrame([{
        "regime": current["regime"],
        "since": current["start"],
        "days": current["days"],
        f"rel_{args.window}d_%": rel.iloc[-1],
        **rs_change,
    }]))
    _print("summary", pd.DataFrame([{
        "period": f"{labeled.index[0]:%Y-%m-%d}..{labeled.index[-1]:%Y-%m-%d}",
        "switches": len(segments) - 1,
        "ai_lead_share_%": (labeled == "AI lead").mean() * 100,
        "median_segment_days": segments["days"].median(),
    }]))
    _print(f"regime segments (last {args.segments})", segments.tail(args.segments), digits=2)

    member_ret = {
        f"{n}d_%": (prices.iloc[-1] / prices.iloc[-1 - n] - 1) * 100 for n in (args.window, 63) if len(prices) > n
    }
    members = pd.DataFrame(member_ret)
    members.insert(0, "side", ["AI" if s in ai else "non-AI" for s in members.index])
    _print("members (who is driving)", members)

    if series:
        daily_rel = ((ai_idx / ai_idx.shift(1)) - (non_idx / non_idx.shift(1))) * 100
        macro_changes = indicators.to_changes(levels[series])
        recent = macro_changes.index[-60:]
        _print("correlation of daily AI-minus-non-AI return with macro changes", pd.DataFrame({
            "full": macro_changes.corrwith(daily_rel),
            "last_60d": macro_changes.loc[recent].corrwith(daily_rel.loc[recent]),
        }))

    if args.plot:
        print(f"plot: {plots.rotation(ai_idx, non_idx, rel, segments, args.window, args.threshold, 'rotation_ai')}")


def cmd_plot_prices(args: argparse.Namespace) -> None:
    symbols, series = _upper(args.symbols), _upper(args.series)
    levels = _levels(store.connect(read_only=True), symbols, series, args.start)
    print(f"plot: {plots.prices_and_macro(levels, symbols, series, 'prices_' + '_'.join(symbols))}")


# --- sentiment -----------------------------------------------------------


def cmd_news_unscored(args: argparse.Namespace) -> None:
    con = store.connect(read_only=True)
    start = args.start or str(date.today() - timedelta(days=7))
    news = con.execute(
        "SELECT id, created_at, symbols, headline, summary, source FROM news WHERE created_at >= ?::DATE ORDER BY created_at DESC",
        [start],
    ).df()
    scored = set(con.execute("SELECT news_id, symbol FROM news_sentiment").fetchall())
    wanted = set(_upper(args.symbols))
    emitted = 0
    for row in news.itertuples():
        targets = [s for s in row.symbols if (not wanted or s in wanted) and (row.id, s) not in scored]
        if not targets:
            continue
        print(json.dumps({
            "news_id": int(row.id),
            "created_at": row.created_at.isoformat(),
            "target_symbols": targets,
            "all_symbols": list(row.symbols),
            "headline": row.headline,
            "summary": (row.summary or "")[: args.max_summary],
            "source": row.source,
        }, ensure_ascii=False))
        emitted += 1
        if emitted >= args.limit:
            break
    print(f"# {emitted} unscored articles", file=sys.stderr)


def cmd_sentiment_import(args: argparse.Namespace) -> None:
    if args.file == "-":
        lines = sys.stdin.read().splitlines()
    else:
        with open(args.file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    con = store.connect()
    known = {r[0] for r in con.execute("SELECT id FROM news").fetchall()}
    try:
        df = sentiment.parse_scores(lines, known)
    except ValueError as e:
        raise SystemExit(f"Nothing imported. Fix these lines and retry:\n{e}")
    print(f"imported {store.upsert(con, 'news_sentiment', df, 'scored_at')} scores")
    _print("news_sentiment", store.status(con)["news_sentiment"])


def _sentiment_frames(con, symbols: list[str], start: str):
    scored = con.execute(
        "SELECT s.symbol, s.score, s.confidence, s.event_type, n.created_at "
        "FROM news_sentiment s JOIN news n ON n.id = s.news_id "
        "WHERE list_contains(?, s.symbol) AND n.created_at >= ?::DATE",
        [symbols, start],
    ).df()
    closes = store.load_closes(con, symbols, str(date.fromisoformat(start) - timedelta(days=10)))
    return scored, closes


def cmd_sentiment_summary(args: argparse.Namespace) -> None:
    symbols = _upper(args.symbols)
    start = args.start or str(date.today() - timedelta(days=30))
    con = store.connect(read_only=True)
    scored, closes = _sentiment_frames(con, symbols, start)
    if scored.empty:
        raise SystemExit("No scored articles in range. Use the news-sentiment skill to score articles first.")
    _require_columns(closes, sorted(scored["symbol"].unique()), "mkt fetch bars")

    daily = sentiment.daily_sentiment(scored, closes.index)
    unmapped = len(scored) - int(daily["articles"].sum())
    joined, summary = sentiment.sentiment_vs_returns(daily, closes)

    print(f"# News sentiment since {start} (returns in %, sessions in ET; articles >= 16:00 ET go to next session)")
    if unmapped:
        print(f"NOTE: {unmapped} articles fall after the latest stored bar. Run: mkt fetch bars {' '.join(symbols)}")
    _print("per-symbol summary", summary)
    _print(
        "by event type",
        scored.groupby(["symbol", "event_type"])["score"].agg(["count", "mean"]).reset_index(),
    )
    _print("recent sessions", joined.sort_values("session").groupby("symbol").tail(args.recent))
    if args.plot:
        print(f"plot: {plots.sentiment(joined, closes, 'sentiment_' + '_'.join(symbols))}")


# --- export --------------------------------------------------------------


def _records(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].map(lambda v: v.strftime("%Y-%m-%d") if hasattr(v, "strftime") and pd.notna(v) else v)
    return json.loads(df.to_json(orient="records", double_precision=4))


def _with_daily_close(daily: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    """Every trading session from the first scored one, with close; sentiment is null on days without news."""
    parts = []
    for symbol, g in daily.groupby("symbol"):
        if symbol not in closes:
            continue
        px = closes[symbol].loc[g["session"].min() :].dropna()
        frame = pd.DataFrame({"symbol": symbol, "session": px.index, "close": px.to_numpy()})
        parts.append(frame.merge(g, on=["symbol", "session"], how="left"))
    return pd.concat(parts, ignore_index=True) if parts else daily


def cmd_export_dashboard(args: argparse.Namespace) -> None:
    symbols, series = _upper(args.symbols), _upper(args.series)
    start = args.start or str(date.today() - timedelta(days=365))
    con = store.connect(read_only=True)
    levels = _levels(con, symbols, series, start)
    daily_changes = indicators.to_changes(levels)
    factors = [indicators.change_column(s) for s in series]

    rebased = levels[symbols] / levels[symbols].bfill().iloc[0] * 100
    chart = pd.concat([rebased, levels[series]], axis=1)
    if len(chart) > 300:
        chart = chart.resample("W-FRI").last()

    rolling, regressions = {}, {}
    for symbol in symbols:
        target = indicators.change_column(symbol)
        rc = indicators.rolling_corr(daily_changes, target, factors, args.window).dropna(how="all")
        rolling[symbol] = _records(rc.resample("W-FRI").last().reset_index(names="date"))
        reg = indicators.factor_regression(daily_changes, target, factors)
        regressions[symbol] = {
            "nobs": reg["nobs"],
            "r2": round(reg["r2"], 4),
            "coefficients": _records(reg["table"].reset_index(names="term")),
        }

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "start": start,
        "symbols": symbols,
        "series": {s: FRED_SERIES.get(s, (s,))[0] for s in series},
        "series_kind": {s: FRED_SERIES.get(s, (s, "level"))[1] for s in series},
        "units": {"prices": "adjusted close rebased to 100", "yields": "%", "changes": "stock/FX %, yields bp"},
        "rolling_window": args.window,
        "coverage": _records(_as_of(levels).reset_index(names="column")),
        "snapshot": _records(
            indicators.snapshot(store.load_bars(con, symbols, str(date.today() - timedelta(days=400))))
            .reset_index(names="symbol")
        ),
        "levels": _records(chart.reset_index(names="date")),
        "rolling_corr": rolling,
        "regressions": regressions,
    }

    scored, closes = _sentiment_frames(con, symbols, start)
    if not scored.empty:
        daily = sentiment.daily_sentiment(scored, closes.index)
        payload["sentiment_daily"] = _records(_with_daily_close(daily, closes))

    out = args.out or REPORTS_DIR / f"{date.today():%Y%m%d}_dashboard.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"dashboard data: {out}")

    if args.canvas_dir:
        template = (Path(__file__).parent / "templates" / "dashboard.canvas.tsx").read_text(encoding="utf-8")
        canvas = Path(args.canvas_dir).expanduser() / f"market-dashboard-{'-'.join(symbols).lower()}.canvas.tsx"
        canvas.parent.mkdir(parents=True, exist_ok=True)
        canvas.write_text(template.replace("__DASHBOARD_DATA__", json.dumps(payload, ensure_ascii=False)), "utf-8")
        print(f"canvas: {canvas}")


# --- entry point ---------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mkt", description="US market analysis CLI (Alpaca + FRED + DuckDB)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the DuckDB schema").set_defaults(func=cmd_init)
    sub.add_parser("status", help="stored data coverage").set_defaults(func=cmd_status)

    q = sub.add_parser("query", help="read-only SQL against DuckDB")
    q.add_argument("sql")
    q.add_argument("--max-rows", type=int, default=200)
    q.set_defaults(func=cmd_query)

    fetch = sub.add_parser("fetch", help="fetch data into DuckDB").add_subparsers(dest="target", required=True)
    fb = fetch.add_parser("bars", help="adjusted daily bars from Alpaca")
    fb.add_argument("symbols", nargs="*")
    fb.add_argument("--start")
    fb.add_argument("--full", action="store_true", help="replace stored history (after splits/dividends)")
    fb.set_defaults(func=cmd_fetch_bars)
    fm = fetch.add_parser("macro", help="FRED series")
    fm.add_argument("series", nargs="*")
    fm.add_argument("--start")
    fm.set_defaults(func=cmd_fetch_macro)
    fn = fetch.add_parser("news", help="Alpaca (Benzinga) news")
    fn.add_argument("symbols", nargs="+")
    fn.add_argument("--start")
    fn.add_argument("--end")
    fn.add_argument("--limit", type=int, default=200)
    fn.set_defaults(func=cmd_fetch_news)

    s = sub.add_parser("snapshot", help="returns and volume from stored bars")
    s.add_argument("symbols", nargs="+")
    s.set_defaults(func=cmd_snapshot)

    analyze = sub.add_parser("analyze").add_subparsers(dest="analysis", required=True)
    ca = analyze.add_parser("cross-asset", help="stocks vs yields / USDJPY")
    ca.add_argument("symbols", nargs="+")
    ca.add_argument("--series", nargs="+", default=["DGS10", "DEXJPUS"])
    ca.add_argument("--start", default=str(date.today() - timedelta(days=3 * 365)))
    ca.add_argument("--window", type=int, default=60)
    ca.add_argument("--freq", choices=["D", "W"], default="D")
    ca.add_argument("--market", default="SPY", help="market factor symbol, or 'none'")
    ca.add_argument("--plot", action="store_true")
    ca.set_defaults(func=cmd_cross_asset)
    ro = analyze.add_parser("rotation", help="AI vs non-AI leadership regimes")
    ro.add_argument("--ai", nargs="+", default=ROTATION_AI)
    ro.add_argument("--non-ai", nargs="+", default=ROTATION_NON_AI)
    ro.add_argument("--series", nargs="*", default=["DGS10", "DEXJPUS", "VIXCLS"])
    ro.add_argument("--start", default=str(date.today() - timedelta(days=2 * 365)))
    ro.add_argument("--window", type=int, default=20)
    ro.add_argument("--threshold", type=float, default=4.0, help="relative return (%%) needed to flip regime")
    ro.add_argument("--segments", type=int, default=12, help="number of recent segments to list")
    ro.add_argument("--plot", action="store_true")
    ro.set_defaults(func=cmd_rotation)

    plot = sub.add_parser("plot").add_subparsers(dest="chart", required=True)
    pp = plot.add_parser("prices", help="rebased prices with macro series")
    pp.add_argument("symbols", nargs="+")
    pp.add_argument("--series", nargs="*", default=["DGS10"])
    pp.add_argument("--start", default=str(date.today() - timedelta(days=365)))
    pp.set_defaults(func=cmd_plot_prices)

    news = sub.add_parser("news").add_subparsers(dest="news_cmd", required=True)
    nu = news.add_parser("unscored", help="emit unscored articles as JSONL")
    nu.add_argument("--symbols", nargs="*")
    nu.add_argument("--start")
    nu.add_argument("--limit", type=int, default=30)
    nu.add_argument("--max-summary", type=int, default=600)
    nu.set_defaults(func=cmd_news_unscored)

    sent = sub.add_parser("sentiment").add_subparsers(dest="sent_cmd", required=True)
    si = sent.add_parser("import", help="store agent-produced scores (JSONL file or '-')")
    si.add_argument("file")
    si.set_defaults(func=cmd_sentiment_import)
    ss = sent.add_parser("summary", help="aggregate sentiment and compare with returns")
    ss.add_argument("symbols", nargs="+")
    ss.add_argument("--start")
    ss.add_argument("--recent", type=int, default=10)
    ss.add_argument("--plot", action="store_true")
    ss.set_defaults(func=cmd_sentiment_summary)

    export = sub.add_parser("export").add_subparsers(dest="export_cmd", required=True)
    ed = export.add_parser("dashboard", help="JSON payload for a Cursor Canvas dashboard")
    ed.add_argument("symbols", nargs="+")
    ed.add_argument("--series", nargs="+", default=["DGS10", "DEXJPUS"])
    ed.add_argument("--start")
    ed.add_argument("--window", type=int, default=60)
    ed.add_argument("--out")
    ed.add_argument("--canvas-dir", help="also write a .canvas.tsx here (the workspace's ~/.cursor/projects/<slug>/canvases)")
    ed.set_defaults(func=cmd_export_dashboard)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
