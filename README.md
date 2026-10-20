# US Market Agent

A personal setup that turns [Cursor](https://cursor.com) into a US equity research assistant.
Ask questions in chat, such as "How sensitive is NVDA to the 10-year yield lately?" or
"Are AI stocks leading or lagging the rest of the market?", and the agent fetches data,
runs the numbers in code, and answers with charts and stated data freshness.

It combines:

- **[Alpaca's official MCP server](https://github.com/alpacahq/alpaca-mcp-server)**, read-only,
  for snapshots, market movers, news and option data
- **A Python CLI (`mkt`)** that stores Alpaca daily bars and news plus [FRED](https://fred.stlouisfed.org/)
  series (Treasury yields, USD/JPY, dollar index, VIX) in DuckDB, and runs the analysis and charts
- **Cursor rules and skills** that define repeatable analysis workflows and answer formats

> This project is shared for reference only. Nothing it produces is investment advice.
> See [DISCLAIMER.md](DISCLAIMER.md).

## Design principles

- **Code does the math, not the LLM.** MCP is used for small, exploratory lookups; anything
  quantitative goes through the CLI so results are reproducible.
- **Read-only by construction.** The MCP server only exposes data toolsets (`ALPACA_TOOLSETS`);
  trading, account and watchlist tools are not loaded, and the rules forbid placing orders.
- **Always state freshness.** Answers include sources, as-of dates and known lags.
- **Secrets stay local.** Keys live only in `.env`, which is git-ignored and read by both the
  MCP server and the CLI.

## What it can do

| Area | Command / skill |
| --- | --- |
| Market overview (indices, movers, rates, USD/JPY, VIX) | `market-snapshot` |
| Stock sensitivity to yields and USD/JPY (rolling correlation, HAC regression, rate regimes) | `mkt analyze cross-asset`, `macro-cross-asset` |
| AI vs non-AI leadership rotation (ETF baskets, relative strength, regime detection) | `mkt analyze rotation`, `ai-rotation` |
| News sentiment scored by the agent with a fixed rubric, compared with returns | `mkt sentiment ...`, `news-sentiment` |
| Briefing on articles you paste or link, checked against market data | `article-briefing` |
| Single-ticker deep dive and a Cursor Canvas dashboard | `mkt export dashboard`, `ticker-deep-dive` |

## Requirements

- macOS or Linux, [uv](https://docs.astral.sh/uv/), Python 3.12
- [Cursor](https://cursor.com)
- An [Alpaca](https://app.alpaca.markets/signup) paper trading account (free) and API keys
- A [FRED API key](https://fredaccount.stlouisfed.org/apikeys) (free)

## Setup

```bash
git clone https://github.com/yuuKimy/us-market-agent.git
cd us-market-agent
uv sync
cp .env.example .env   # then fill in the keys
```

`.env`:

```bash
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_DATA_FEED=iex   # paper-only accounts get IEX data
FRED_API_KEY=...
```

Check that both data sources work:

```bash
uv run mkt fetch macro
uv run mkt fetch bars SPY QQQ
uv run mkt status
```

Then open this folder as the Cursor workspace. The project-level `.cursor/mcp.json` starts the
Alpaca MCP server with `uvx`; in Cursor's MCP settings, `alpaca` should show 35 read-only tools.

## CLI overview

```bash
uv run mkt fetch bars NVDA SPY               # adjusted daily bars (incremental; --full to rebuild)
uv run mkt fetch macro                       # FRED catalog: DGS3MO DGS2 DGS10 DGS30 T10Y2Y DFII10 DEXJPUS DTWEXBGS VIXCLS
uv run mkt fetch news NVDA --start 2026-10-01
uv run mkt snapshot NVDA SPY
uv run mkt analyze cross-asset NVDA --series DGS10 DEXJPUS --plot
uv run mkt analyze rotation --plot
uv run mkt sentiment summary NVDA --plot
uv run mkt export dashboard NVDA SPY --canvas-dir ~/.cursor/projects/<workspace-slug>/canvases
uv run mkt query "SELECT * FROM bars_daily LIMIT 5"
```

Charts are written to `reports/` as PNG. Run `uv run mkt --help` for all options.

## Project layout

```
AGENTS.md                      # instructions for the agent (Japanese)
.cursor/mcp.json               # Alpaca MCP, read-only toolsets, keys from .env
.cursor/rules/                 # answer rules: sources, as-of, no buy/sell calls
.cursor/skills/                # analysis workflows
src/market_agent/
  clients/{alpaca,fred}.py     # data fetchers
  store.py                     # DuckDB schema and queries
  indicators.py                # returns, correlation, regression, regimes, rotation
  sentiment.py                 # score validation, session mapping, aggregation
  plots.py                     # matplotlib charts
  templates/                   # Cursor Canvas dashboard template
  cli.py                       # `mkt` entry point
tests/
```

`data/` (DuckDB) and `reports/` (charts, score files) are local only and git-ignored.

## Data notes and limitations

- **IEX feed.** Alpaca paper-only accounts receive IEX data: history starts on 2020-07-27, and
  volume covers only IEX, so volume is used in relative terms.
- **USD/JPY lag.** FRED's `DEXJPUS` is released weekly, so it can be up to a week behind.
  Lagging series are never forward-filled past their last observation.
- **No FX or yield history on Alpaca.** Yields and USD/JPY come from FRED.
- **Sentiment scores are LLM judgments** made with the rubric in `news-sentiment`; treat small
  samples as anecdotal.
- **Data is not redistributed.** Follow the Alpaca and FRED terms of use; fetched data stays local.

## Development

```bash
uv run pytest
uv run ruff check .
```

Tests cover pure calculation logic only; no test calls external APIs.

## License

[MIT](LICENSE)
