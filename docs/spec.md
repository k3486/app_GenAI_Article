# 仕様（現在）

> このファイルは**今の仕様だけ**を書く。変わったら書き換える（履歴は `.steering/history.md`）。
> 最終更新: 2026-11-07（段階① 画面・DB・API まで。収集と Haiku は未実装）

## 概要
生成AIの記事を集め、好みで選定し、関心に沿って整理した日本語の記事を、ダッシュボードで見る個人用アプリ。
設計の全体は `.steering/20261107-local-dashboard/design.md`。

**実装済み**: 7シートの画面、DB（表・移行・全文検索・バックアップ）、API、点数の計算と選定の判定。
**未実装**: 記事の収集、Haiku による採点・整理記事、更新ボタン、壁打ち、好みメモ・プロファイルの修正案。
いまは `make seed`（試しの架空のデータ）で画面を確認できる。

## 画面
| パス | シート | 内容 |
|---|---|---|
| `/` | 最新トピック | 直近7日の選定記事を、更新の回ごとに点数順で並べたカード。重大ニュースは別枠。絞り込み・検索 |
| `/favorites` | お気に入り記事 | ★ を付けた記事と、好みの傾向 |
| `/backlog` | バックログ | 未読の選定記事（自動で入る）と「後で読む」。残数の推移。未読30日で自動的に「見送り」（「後で読む」は除く） |
| `/articles` | 全記事 | 選定された記事の表（並べ替え・絞り込み・検索・ページ送り） |
| `/rejected` | 落選記事 | 落選した記事の表。「実はよかった」を付けられる |
| `/insights` | 分析 | トピックの内訳・話題の推移・効き具合（👍率など）・バックログ推移・情報源の成績。表でも見られる |
| `/settings` | 設定・運用 | 興味プロファイル・重み・しきい値・件数・費用の上限・情報源の切り替え・実行履歴 |

どのシートでも、記事を開くと詳細（整理記事・点数の内訳・URL 一覧）が出る（URL の `?topic=ID`）。
ライト／ダーク（端末に追従、手動で切り替え可）、スマホ幅にも対応。

## 点数と選定
- 5観点（関心との一致・実用性・新しさ・信頼性・内容の深さ）を 1〜5 で評価する。初期の重みは 20/25/25/15/15
- 合計 = Σ 重み × (点数−1)÷4。公式の情報源の記事は +10 点
- 論文・発表・リリースは、「実用性」の代わりに「実務・事業への示唆の大きさ」で評価する
- 60点以上かつ関心が3以上なら選定。選定に入らず「新しさ・重要度」が5なら重大ニュース。それ以外は落選
- 採点時の重みを記事ごとに保存する。実装は `backend/app/services/scoring.py`

## API
| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/health` | API と DB 接続の確認 |
| GET | `/api/topics` | 話題の一覧。`view`（latest／favorites／backlog／all／rejected）、`q`、`type`、`category`、`source`、`sort`、`order`、`page`、`page_size` |
| GET | `/api/topics/{id}` | 話題の詳細（整理記事・点数の内訳・URL 一覧） |
| PATCH | `/api/topics/{id}/state` | ★・👍👎・読了・後で読む・「実はよかった」を、送った項目だけ更新 |
| GET | `/api/status` | 前回の更新結果・今月の費用と上限・試しのデータかどうか |
| POST | `/api/runs` | 更新の開始。**未実装（501）** |
| GET | `/api/runs` | 実行履歴（失敗の理由・Haiku が作った検索語つき） |
| GET | `/api/insights` | 分析シートの集計 |
| GET / PUT | `/api/settings` | 画面から変える設定 |
| GET | `/api/sources` | 情報源と成績 |
| PATCH | `/api/sources/{key}` | 情報源を使う／使わない |

入出力の型は `backend/app/schemas/`。画面の型は `make types` で自動生成する（`frontend/src/lib/api-types.ts`）。

## データ（DB）
`sources`・`topics`（話題。あなたの操作の状態も持つ）・`articles`・`article_texts`（本文）・`scores`（5観点・そのときの重み）・
`digests`（整理記事）・`runs`・`run_issues`・`search_queries`・`llm_usage`（Haiku の費用）・`settings`。
日時は UTC で保存し、表示のときだけ日本時間にする。全文検索は SQLite の FTS5（`topic_search`）。
表の形の変更は Alembic（`backend/alembic/`）。

## コマンド
| コマンド | 内容 |
|---|---|
| `make migrate` | DB の表を最新の形にする（`make dev` で自動実行） |
| `make seed` | 試しのデータを入れる（`--reset` で入れ直し、`--clear` で全部消す） |
| `make backup` | DB のバックアップ（`data/backups/` に7世代） |
| `make types` | API の仕様から画面の型を作り直す（API を変えたら実行） |

## 設定（環境変数）
| 名前 | 既定値 | 内容 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<リポジトリ>/data/app.db` | DB の接続先 |
| `APP_NAME` | `ai-news-dashboard` | API のタイトル |
| `ANTHROPIC_API_KEY` | なし | Haiku 用の API キー（収集・採点の段階で使う） |
| `OPENAI_API_KEY` | なし | 雛形の名残。この作業では使わない（Haiku 固定） |
