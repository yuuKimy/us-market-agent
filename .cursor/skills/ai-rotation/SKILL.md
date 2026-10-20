---
name: ai-rotation
description: >-
  Visualizes and summarizes leadership rotation between AI-related equities and the rest of the
  US market (equal-weight ETF baskets, relative strength, detected regimes, macro and news context).
  Use when the user asks about AI vs non-AI trends, AI 相場とそれ以外の入れ替わり, ローテーション,
  セクターローテーション, or whether AI stocks are leading or lagging the market.
---

# AI vs non-AI rotation

Baskets (defaults in `src/market_agent/config.py`): AI = `SMH QQQ`, non-AI = `RSP IWM XLV XLP XLU`.
Override with `--ai` / `--non-ai` only when the user asks; state the baskets in the answer.

## Workflow

```
- [ ] 1. Refresh data
- [ ] 2. Run the analysis
- [ ] 3. Add context for recent turns
- [ ] 4. Answer
```

**1. Refresh** (project root)

```bash
uv run mkt fetch bars SMH QQQ RSP IWM XLV XLP XLU
uv run mkt fetch macro DGS10 DEXJPUS VIXCLS
```

If `mkt status` shows a basket member starting later than the analysis start, backfill it with
`uv run mkt fetch bars <SYMBOL> --full --start 2020-07-27` (IEX history begins 2020-07-27).

**2. Analyze**

```bash
uv run mkt analyze rotation --plot
```

Options: `--start` (default 2 years), `--window 20`, `--threshold 4` (relative return in % needed
to flip the regime). Lower threshold = more, shorter regimes. Keep defaults unless asked.

**3. Context for the latest one or two switches**

- Drivers: the `members` table shows which ETFs moved most over the window
- Macro: segment columns `DGS10_bp`, `DEXJPUS_pct`, `VIXCLS_pct`, and the correlation table.
  A strongly negative VIX correlation means AI leadership tends to fade on risk-off days
- News: `uv run mkt fetch news NVDA AVGO MSFT --start <switch date - 5 days>` and scan headlines
  with `mkt query`, or WebSearch for events around the switch date (earnings, Fed, policy). Cite URLs

## Interpreting

- Regimes are **detected with a lag** (the 20-day relative return must cross the threshold).
  The segment's `spread_pt` is performance *after* detection; a non-AI-lead segment with a
  positive spread means the move reversed soon after it was detected (whipsaw)
- A regime that is only a few days old is unconfirmed; say so
- `ai_lead_share_%` and the number of switches describe how persistent leadership has been
- The baskets are proxies: `SMH` is semiconductors, `QQQ` includes non-AI names, `RSP` holds
  some AI stocks at small weight

## Answer format (Japanese)

```markdown
## AI 関連とそれ以外のローテーション（{start}〜{as_of}）

**要点**: 現在の局面（いつから、確定度）、直近の入れ替わりの特徴、2〜3 文

![AI vs non-AI](/abs/path/to/reports/..._rotation_ai.png)

- 現在: 20 日相対リターン、相対強度の 5 日・1 か月・3 か月変化
- 期間全体: 切り替え回数、AI 主導の割合、局面の中央日数
- 直近の局面: 期間・両バスケットの騰落・金利/ドル円/VIX の変化
- けん引役: 動きの大きい ETF
- 背景: 入れ替わり前後のニュース・イベント（出典 URL）
- 注意点: 判定の遅れ、代理指標の限界、データ as-of（DEXJPUS の遅れ）

バスケット: AI = SMH, QQQ / 非 AI = RSP, IWM, XLV, XLP, XLU（均等加重・日次リバランス）
データ: Alpaca（IEX 日足 as-of ...）, FRED（as-of ...）
投資助言ではありません。
```
