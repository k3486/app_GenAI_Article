# 生成AIニュースダッシュボード

状態: 検討中（このテンプレートから `ai-news-dashboard` として作る予定）

## 背景
Web 検索・クローリング・スクレイピングで生成AIの最新情報を集め、優先順位を付けて表示する個人用ダッシュボード。
まずローカルで公開、将来は AWS 無料枠で個人向けに公開。

## 案（2026-11-03 の会話より）
- 収集方法: RSS/Atom、公開API（arXiv / Hacker News / GitHub / Hugging Face 等）、Web検索API、HTMLスクレイピング（robots.txt 遵守）
- 優先順位: 情報源ごとの重み ＋ 記事ごとのスコア（新しさ・キーワード一致など）の両方。設定ファイルで調整
- 構成案（backend/app 配下）:
  - `collectors/`（base, rss, apis/, search, scraper, registry）
  - `pipeline/`（正規化 → 重複排除 → スコアリング → 保存）
  - `scoring/`（rules, scorer）、`config/sources.yaml`・`config/scoring.yaml`
  - `summarizers/`（LLM 要約の置き場。今は何もしない）
  - `api/`（articles, sources, collect=手動更新）、`scripts/collect.py`
- frontend: `features/articles`（一覧・フィルタ・スコア順）、`features/sources`

## 未決事項
- LLM による要約・分類・翻訳を入れるか
- 収集の実行タイミング（バッチ／アプリ内スケジューラ／手動）
- Web 検索 API の選定（Brave / Tavily 等）
