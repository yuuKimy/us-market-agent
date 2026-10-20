---
name: macro-cross-asset
description: >-
  Analyzes how US stocks/ETFs move with Treasury yields and USD/JPY (rolling correlation,
  regression betas, rising/falling-rate regimes) using FRED and Alpaca data stored in DuckDB.
  Use when the user asks about rate sensitivity, 金利感応度, 米国債利回りと株価の関係, ドル円と株価,
  or cross-asset correlation for specific tickers.
---

# Macro cross-asset analysis

## Workflow

```
- [ ] 1. Refresh data
- [ ] 2. Run the analysis
- [ ] 3. Interpret with caveats
- [ ] 4. Answer in the standard format
```

**1. Refresh data** (project root). Always include `SPY` as the market factor.

```bash
uv run mkt fetch bars NVDA SPY
uv run mkt fetch macro DGS10 DGS2 DEXJPUS
```

**2. Run the analysis**

```bash
uv run mkt analyze cross-asset NVDA --series DGS10 DEXJPUS --start 2023-01-01 --plot
```

Options: `--freq W` for weekly (less noise, good for 1y+ horizons), `--window 60` rolling window,
`--market none` to drop the SPY factor. Choose the series to match the question:

| Question | Series |
| --- | --- |
| Long-rate sensitivity (growth / tech) | `DGS10`, `DFII10` (real yield) |
| Policy-rate sensitivity | `DGS2`, `DGS3MO` |
| Curve steepening / flattening | `T10Y2Y` |
| Yen / dollar | `DEXJPUS`, `DTWEXBGS` |
| Risk-off | `VIXCLS` |

For a quick visual only: `uv run mkt plot prices NVDA SPY --series DGS10 DEXJPUS`.

**3. Interpret**

- Units: stock/FX changes are %, yield changes are bp. A `DGS10_bp` coefficient of -0.05 means
  about -0.5% for a +10bp move, holding SPY constant (i.e. sensitivity beyond the market beta)
- With `--market SPY`, macro coefficients are *incremental* to the market. Also report the
  full-period correlation, which includes the market channel
- Treat |t| < 2 as "no clear relationship". Report n and the period
- Rolling correlation ranges show stability; a sign flip means the relationship is regime-dependent
- `DEXJPUS` lags up to a week; the regression end date shows the effective cutoff
- Correlation is not causation; mention confounders (earnings, Fed events) when relevant

**4. Answer format** (Japanese)

```markdown
## {TICKER} の金利・ドル円感応度（{start}〜{end}、日次 n={n}）

**要点**: 1〜2 文で結論（例: 10年債利回り +10bp あたり市場要因を除いて約 -0.5%、統計的に有意）

- 回帰（HAC 標準誤差）: 係数・t 値の要約
- 相関: 全期間と直近ローリング（範囲）
- レジーム: 金利上昇局面と低下局面の違い

![ローリング相関](/abs/path/to/reports/..._rollcorr_TICKER.png)

データ: Alpaca（調整済み日足, as-of ...）, FRED（DGS10 as-of ..., DEXJPUS as-of ...）
注意点: ...
投資助言ではありません。
```
