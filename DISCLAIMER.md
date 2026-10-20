# Disclaimer / 免責事項

## English

1. **Purpose.** This repository is a personal tool for gathering and analyzing information
   related to investing in US stocks. It is published for reference only.
2. **Not investment advice.** Nothing in this repository, including the code, rules, agent
   skills, charts and any output they produce, is investment advice or a recommendation or
   solicitation to buy, sell or hold any security. The author is not a registered investment
   adviser or a licensed financial services provider.
3. **Your own responsibility.** All investment decisions are made at your own discretion and
   risk. Do your own research and, if needed, consult a qualified professional.
4. **No liability.** The author accepts no liability whatsoever for any loss or damage, direct or
   indirect, arising from the use of, or reliance on, this repository or its output.
5. **No guarantee of accuracy.** Data may be delayed, incomplete or wrong, and outputs generated
   by AI agents may contain errors. No guarantee is made about the accuracy, completeness or
   timeliness of any data or analysis.
6. **Software.** The software is provided "as is" under the [MIT License](LICENSE), without
   warranty of any kind.

## 日本語

1. **目的**: 本リポジトリは、米国株式投資のための情報収集・分析を目的とした個人用ツールであり、参考情報として公開しています。
2. **投資助言ではありません**: 本リポジトリのコード・ルール・エージェントスキル・チャート、およびそれらが生成する出力は、いずれも投資助言ではなく、特定の有価証券の売買や保有を推奨・勧誘するものでもありません。本リポジトリの作成者は、投資助言・代理業等の金融商品取引業の登録を受けた者ではありません。
3. **投資は自己責任です**: 投資に関する最終的な判断は、ご自身の責任において行ってください。必要に応じて、専門家にご相談ください。
4. **作成者は一切の責任を負いません**: 本リポジトリおよびその出力の利用、またはそれらに依拠したことによって生じたいかなる損失・損害（直接・間接を問いません）についても、本リポジトリの作成者は一切の責任を負いません。
5. **正確性は保証しません**: データには遅延・欠損・誤りが含まれる可能性があり、AI エージェントが生成する出力にも誤りが含まれる可能性があります。データおよび分析結果の正確性・完全性・適時性は保証しません。
6. **ソフトウェア**: 本ソフトウェアは [MIT License](LICENSE) に基づき、「現状のまま」いかなる保証もなく提供されます。

## Data sources / データソース

- Market data and news: [Alpaca Market Data API](https://docs.alpaca.markets/) (news is provided by Benzinga via Alpaca)
- Treasury yields, USD/JPY, dollar index, VIX: [FRED, Federal Reserve Bank of St. Louis](https://fred.stlouisfed.org/)

Fetched data is stored locally under `data/` and is intentionally excluded from the repository.
Follow each provider's terms of use; this repository does not redistribute their data.

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.
By using this project, you agree to the [FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
and to [Alpaca's terms](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf) for your own account.
Use your own API keys. Fetched data is for your personal, non-commercial use only. Some FRED series are copyrighted by
third parties (for example, `VIXCLS` by Cboe); do not publish them without the owner's permission.

取得したデータはローカルの `data/` にのみ保存し、リポジトリには含めていません。各データ提供元の利用規約に従ってください。本リポジトリはそれらのデータを再配布しません。

本製品は FRED® API を利用していますが、セントルイス連邦準備銀行による承認・認定を受けたものではありません。本プロジェクトを利用する場合は、[FRED® API 利用規約](https://fred.stlouisfed.org/docs/api/terms_of_use.html) と、ご自身のアカウントに適用される [Alpaca の利用規約](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf) に同意したものとみなします。API キーはご自身のものを使い、取得したデータは個人的・非商用の利用にとどめてください。FRED の一部の系列（例: Cboe が著作権を持つ `VIXCLS`）は第三者の著作物のため、権利者の許可なく公開しないでください。
