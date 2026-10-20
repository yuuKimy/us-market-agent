---
name: market-snapshot
description: >-
  Summarizes current US market conditions: index ETFs, a watchlist's returns and volume, top
  gainers/losers, Treasury yields, USD/JPY, VIX, and notable headlines. Use when the user asks
  for 市場概況, 今日の相場, マーケットの様子, how the market did today/this week, or a quick
  overview of their watchlist.
---

# Market snapshot

## Workflow

**1. Market clock** — Alpaca MCP `get_clock`. State whether the US market is open, and the
latest session date (ET). During market hours, prices are intraday and SIP data on the free
plan is 15 minutes delayed.

**2. Index ETFs and watchlist** (project root). Default set: `SPY QQQ IWM DIA TLT` plus any
tickers the user named.

```bash
uv run mkt fetch bars SPY QQQ IWM DIA TLT NVDA
uv run mkt snapshot SPY QQQ IWM DIA TLT NVDA
```

During market hours, also call MCP `get_stock_snapshot` for the same symbols for intraday moves
(say they are intraday).

**3. Breadth** — MCP `get_market_movers` (top gainers/losers) and `get_most_active_stocks`.
Show at most 5 each; skip obvious penny stocks / warrants unless asked.

**4. Rates, FX, volatility**

```bash
uv run mkt fetch macro DGS2 DGS10 T10Y2Y DEXJPUS VIXCLS
uv run mkt query "SELECT series_id, date, value, value - lag(value, 5) OVER (PARTITION BY series_id ORDER BY date) AS chg_5obs FROM macro_series WHERE series_id IN ('DGS2','DGS10','T10Y2Y','DEXJPUS','VIXCLS') QUALIFY row_number() OVER (PARTITION BY series_id ORDER BY date DESC) = 1"
```

Yields: report level (%) and change in bp (`chg_5obs * 100`). `DEXJPUS` is up to a week old;
say so, and if the user needs today's USD/JPY, add a WebSearch figure with its source.

**5. Headlines** — MCP `get_news` with no symbol filter (or the watchlist), limit ~15.
Pick 3-5 market-moving items. For a scored view, use the `news-sentiment` skill instead.

**6. Optional dashboard** — if the user wants something to keep open, follow the dashboard
step in the `ticker-deep-dive` skill with the watchlist symbols.

## Answer format (Japanese)

```markdown
## 米国市場概況（{session} ET 時点 / 取引時間中なら「場中」と明記）

**要点**: 2〜3 文（株式の方向感、金利・ドル円、主なテーマ）

- 指数 ETF: SPY/QQQ/IWM/DIA の 1D・5D・YTD
- ウォッチリスト: 騰落率と出来高比（vol_vs_20d > 1.5 は注目）
- 値上がり/値下がり上位
- 金利: 2年・10年（水準と bp 変化）、2s10s
- ドル円・VIX（DEXJPUS の as-of を明記）
- 主なニュース 3〜5 件（出典リンク）

データ: Alpaca（日足 as-of ..., スナップショット取得 ... ET）, FRED（各系列 as-of）
投資助言ではありません。
```
