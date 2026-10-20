---
name: news-sentiment
description: >-
  Fetches Alpaca (Benzinga) news for US tickers, scores each article's price impact with a fixed
  rubric, stores the scores in DuckDB, and compares daily sentiment with same-day and next-day
  returns. Use when the user asks about news sentiment, ニュースセンチメント, 材料の良し悪し,
  or how news relates to a ticker's price moves.
---

# News sentiment

## Workflow

```
- [ ] 1. Fetch news and bars
- [ ] 2. Score unscored articles in batches (repeat until none left)
- [ ] 3. Summarize and compare with returns
- [ ] 4. Answer in the standard format
```

**1. Fetch** (project root)

```bash
uv run mkt fetch news NVDA AMD --start 2026-09-01
uv run mkt fetch bars NVDA AMD
```

If the output says it hit `--limit`, narrow the date range or raise `--limit`.

**2. Score in batches of up to 30**

```bash
uv run mkt news unscored --symbols NVDA AMD --start 2026-09-01 --limit 30
```

Each JSONL line has `news_id`, `target_symbols`, `headline`, `summary`. For every
(`news_id`, symbol in `target_symbols`) pair, write one line using the rubric below to
`reports/scores_<YYYYMMDD_HHMM>.jsonl` (use the Write tool), then import:

```bash
uv run mkt sentiment import reports/scores_20261017_1030.jsonl
```

Line format:

```json
{"news_id": 123, "symbol": "NVDA", "score": 0.6, "confidence": 0.8, "event_type": "analyst_rating", "rationale": "大手証券が目標株価を引き上げ", "scorer": "cursor-agent"}
```

Import is all-or-nothing: if it reports invalid lines, fix them and re-import the whole file.
Repeat step 2 until `# 0 unscored articles`. For more than ~150 articles, confirm with the user first.

**3. Summarize**

```bash
uv run mkt sentiment summary NVDA AMD --start 2026-09-01 --plot
```

For the latest headlines without storing them, the Alpaca MCP `get_news` tool is fine for reading,
but scores must go through the CLI so they are reproducible.

## Scoring rubric

`score` (-1..+1) = expected impact **on the target symbol's stock price** at publication time,
judged from the headline and summary only. Not the article's general tone.

| Score | Meaning | Examples |
| --- | --- | --- |
| ±0.8〜1.0 | Material, company-specific, surprising | Beat-and-raise or guidance cut, acquisition at a premium, fraud, product ban |
| ±0.4〜0.7 | Clear directional news | Major-broker upgrade/downgrade, large contract won/lost, key product launch/delay |
| ±0.1〜0.3 | Mild | Small price-target changes, minor partnerships, generic commentary |
| 0 | Neutral or not really about the symbol | Listicles, sector roundups, peripheral mentions |

Rules:

- **No lookahead**: never use knowledge of what the price did after publication
- Articles that only report a price move ("shares are trading lower") → `score: 0`, `event_type: "other"`,
  `confidence` ≤ 0.3 (they describe returns rather than cause them)
- Multi-symbol articles: score each target separately; a passing mention → 0 with low confidence
- `confidence` (0..1): how clearly the text supports the score
- `event_type`: one of `earnings`, `guidance`, `analyst_rating`, `product`, `regulatory_legal`,
  `m_and_a`, `management`, `capital_return`, `supply_chain`, `macro`, `other`
- `rationale`: one short Japanese sentence

## Interpreting the summary

- Sessions are ET trading days; articles at or after 16:00 ET count toward the next session
- `spearman_same` mostly reflects news *reacting to* or *coinciding with* the move;
  `spearman_next` is the (weak) predictive check. With fewer than ~30 sessions, call it anecdotal
- `next_ret_<bucket>_pct` compares average next-day returns by sentiment bucket (±0.2 thresholds)
- Scores are LLM judgments; mention this and the sample size

## Answer format (Japanese)

```markdown
## {TICKER} ニュースセンチメント（{start}〜{end}、{articles} 記事 / {sessions} 営業日）

**要点**: センチメントの傾向と、主なポジティブ/ネガティブ材料

- 主な材料: 日付・見出し要約・スコア（上位 3〜5 件）
- イベント種別の内訳
- リターンとの関係: spearman_same / spearman_next と解釈

![センチメントと株価](/abs/path/to/reports/..._sentiment_TICKER.png)

データ: Alpaca News（Benzinga）, 採点: cursor-agent（ルーブリック v1）, 株価 as-of ...
投資助言ではありません。
```
