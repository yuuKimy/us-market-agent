---
name: ticker-deep-dive
description: >-
  Produces a comprehensive single-ticker analysis: price trend, rate and USD/JPY sensitivity,
  scored news sentiment, corporate actions, and option implied volatility, optionally as a
  Cursor Canvas dashboard. Use when the user asks to 詳しく分析, deep dive, 銘柄分析, or wants
  a dashboard for one or a few US tickers.
---

# Ticker deep dive

Combines the `macro-cross-asset` and `news-sentiment` skills. Read them for details on each step.

## Workflow

```
- [ ] 1. Refresh data
- [ ] 2. Price and snapshot
- [ ] 3. Macro sensitivity
- [ ] 4. News sentiment (last 30 days)
- [ ] 5. Events and options
- [ ] 6. Dashboard (if requested or 2+ tickers)
- [ ] 7. Answer
```

**1. Refresh** (project root)

```bash
uv run mkt fetch bars NVDA SPY
uv run mkt fetch macro DGS2 DGS10 DFII10 DEXJPUS VIXCLS
uv run mkt fetch news NVDA --start <30 days ago>
```

**2. Price** — `uv run mkt snapshot NVDA SPY` and
`uv run mkt plot prices NVDA SPY --series DGS10 DEXJPUS`. Compare with SPY (relative strength).

**3. Macro** — `uv run mkt analyze cross-asset NVDA --series DGS10 DEXJPUS --plot`. Add
`DFII10` for long-duration growth names, `DGS2` for financials.

**4. Sentiment** — score unscored articles per `news-sentiment`, then
`uv run mkt sentiment summary NVDA --start <30 days ago> --plot`.

**5. Events and options** (Alpaca MCP)

- `get_corporate_actions` for the symbol: splits, dividends, spin-offs in the past year and upcoming.
  A split or dividend after the last full fetch → `uv run mkt fetch bars NVDA --full`
- Earnings dates are not in Alpaca; use WebSearch and cite the source
- `get_option_chain` / `get_option_snapshot` for the nearest monthly expiry: at-the-money implied
  volatility and put/call skew. Keep it to a few strikes; do not dump the chain

**6. Dashboard** — write a Cursor Canvas. Pass the **current workspace's** canvases directory
(`~/.cursor/projects/<workspace-slug>/canvases`, the slug is the workspace path with `/` replaced by `-`):

```bash
uv run mkt export dashboard NVDA AMD SPY --series DGS10 DEXJPUS --start <1 year ago> \
  --canvas-dir ~/.cursor/projects/<workspace-slug>/canvases
```

The CLI writes `market-dashboard-<symbols>.canvas.tsx` from
`src/market_agent/templates/dashboard.canvas.tsx`; do not hand-copy the data. To change the
layout, edit the template and re-run. Link the canvas with its absolute path in the answer.

## Answer format (Japanese)

```markdown
## {TICKER} 総合分析（{as_of} 時点）

**要点**: 3 文以内

### 価格動向
### 金利・ドル円感応度
### ニュースとセンチメント
### イベント・オプション
### リスクと注意点

（図 PNG を埋め込み、Canvas があればリンク）

データ: ...（各ソースと as-of）
投資助言ではありません。
```
