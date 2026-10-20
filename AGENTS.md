# US Market Analysis Agent

個人用の米国株分析環境。米国株・ETF、米国債利回り、ドル円、ニュースセンチメントを日足〜週足で分析する。
出力は投資助言ではない（[DISCLAIMER.md](DISCLAIMER.md)）。

## 絶対に守ること

- ユーザーへの出力（作業中の進捗報告、最終回答、図や Canvas の説明）は常に自然な日本語で書く。スキルや参照資料が英語でも出力は日本語にする。ティッカー、系列 ID、コマンド、固有名詞は原文のままでよい
- 発注・ポジション変更・口座設定変更は一切行わない。Alpaca MCP は読み取り専用の toolset のみ有効化している。もし発注系ツールが見えても使わない
- `.env` の中身や API キーを表示・出力・コミットしない
- `data/` と `reports/` は公開しない（git 管理外）

## データソースと使い分け

| 用途 | 手段 |
| --- | --- |
| 最新スナップショット、値上がり/値下がり上位、個別ニュースの閲覧、オプション IV | Alpaca MCP（`get_stock_snapshot`, `get_market_movers`, `get_news`, `get_option_snapshot` など） |
| 日足の時系列、ニュースの蓄積、指標計算、作図 | Python CLI `uv run mkt ...`（alpaca-py → DuckDB） |
| 米国債利回り、ドル円、ドル指数、VIX | Python CLI `uv run mkt fetch macro`（FRED → DuckDB） |
| 決算日程・マクロイベントなどの背景 | WebSearch（出典 URL を明記） |

計算は LLM の暗算ではなくコードで行う。MCP で大量の時系列を取得してチャットに展開しない（数十行を超えるなら CLI を使う）。

Alpaca には FX データも米国債利回りの時系列もない。ドル円と利回りは必ず FRED（`macro_series` テーブル）を使う。
`DEXJPUS`（ドル円）は週次更新のため最大約 1 週間遅れる。直近のドル円が必要な場合は遅延を明記したうえで WebSearch で補足する。

## Python CLI

すべてプロジェクトルートで `uv run mkt <command>` として実行する。結果は標準出力にテキストで出る。図は `reports/` に PNG で保存され、パスが表示される。

```
mkt init                                   # DuckDB スキーマ作成（初回のみ。他コマンドも自動で作成する）
mkt status                                 # 保存済みデータの件数と as-of
mkt fetch bars [SYMBOL ...] [--start D] [--full]   # 日足（調整済み）を差分取得。SYMBOL 省略時は保存済み全銘柄
mkt fetch macro [SERIES ...] [--start D]   # FRED 系列。省略時はカタログ全系列
mkt fetch news SYMBOL ... [--start D] [--end D] [--limit N]
mkt query "SELECT ..."                     # DuckDB への読み取り専用 SQL
mkt snapshot SYMBOL ...                    # 保存済み日足から騰落率・出来高比
mkt analyze cross-asset SYMBOL ... [--series DGS10 DEXJPUS] [--start D] [--window 60] [--freq D|W] [--market SPY] [--plot]
mkt analyze rotation [--ai ...] [--non-ai ...] [--series ...] [--window 20] [--threshold 4] [--plot]
mkt plot prices SYMBOL ... [--series DGS10] [--start D]
mkt news unscored [--symbols S ...] [--start D] [--limit N]   # 未採点ニュースを JSONL で出力
mkt sentiment import FILE|-                # 採点結果 JSONL を保存
mkt sentiment summary SYMBOL ... [--start D] [--plot]
mkt export dashboard SYMBOL ... [--series ...] [--start D] [--canvas-dir DIR]   # JSON と Canvas を出力
```

Canvas は `--canvas-dir` に現在のワークスペースの `~/.cursor/projects/<workspace-slug>/canvases` を渡すと、
`src/market_agent/templates/dashboard.canvas.tsx` にデータを埋め込んで書き出される。データを手でコピーしない。

FRED カタログ: `DGS3MO`, `DGS2`, `DGS10`, `DGS30`, `T10Y2Y`, `DFII10`, `DEXJPUS`, `DTWEXBGS`, `VIXCLS`（定義は `src/market_agent/config.py`）。

DuckDB テーブル: `bars_daily`, `macro_series`, `news`, `news_sentiment`（定義は `src/market_agent/store.py`）。

## スキル

定型分析は `.cursor/skills/` のスキルに従う。

- `market-snapshot`: 市場概況
- `macro-cross-asset`: 株式と利回り・ドル円の関係
- `news-sentiment`: ニュースセンチメントの採点と集計
- `ticker-deep-dive`: 1 銘柄の総合分析
- `ai-rotation`: AI 関連とそれ以外の主導権の入れ替わり（ETF バスケットの相対強度と局面判定）
- `article-briefing`: ユーザーが渡した外部記事（URL・本文）の要約、市場データとの照合、材料の方向感・シナリオ・注意点

## 開発

- Python 3.12 / uv。依存追加は `uv add`
- テスト: `uv run pytest`、lint: `uv run ruff check .`
- 外部 API を叩くテストは書かない（指標計算などの純粋関数のみテストする）
