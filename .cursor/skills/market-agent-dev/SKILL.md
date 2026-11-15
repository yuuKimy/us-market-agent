---
name: market-agent-dev
description: >-
  us-market-agent の Python CLI、DuckDB、テスト、Canvas テンプレの開発。
  src/market_agent/ や pyproject、.cursor/mcp.json の改修、新規 mkt サブコマンド、
  分析 skill の手順更新を触るときに使う。市場の質問・日常的な分析には使わない。
---

# us-market-agent 開発

> チャットでの市場分析 → **分析スキル**（`market-snapshot` 等）と [AGENTS.md](../../../AGENTS.md) の分析モード。本 skill はコード用。

## 最初に読む

1. [AGENTS.md](../../../AGENTS.md) — 絶対に守ること、ゲート
2. [README.md](../../../README.md) — Design principles、Security notes
3. `.cursor/rules/market-analysis.mdc` — 回答ルール（開発時も改修後に矛盾しないこと）

## 不変条件

- ニュースインジェクション: `src/market_agent/injection.py`（`SCANNER_VERSION`）と `news_safety`。ルール変更時はバージョンを上げて pytest を足す
- MCP は読取 toolset のみ。`trading` / `account` / `watchlists` を足さない
- 発注・口座変更のコードパスを入れない
- `.env` / API キーをログ・コミット・チャットに出さない
- テストは外部 API に接続しない
- `data/` `reports/` を git に含めない

## MCP 変更

`.cursor/mcp.json` を触る前は `design-reviewer` を起動する。`alpaca-mcp-server` のバージョンは README の Security notes に合わせて理由を残す。

## 検証

```bash
uv run pytest
uv run ruff check .
```

## オーケストレーション

- `verify-gate` skill（standard）
- 免責・データ源・MCP 表面の変更 → `design-reviewer`