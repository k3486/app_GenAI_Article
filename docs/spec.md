# 仕様（現在）

> このファイルは**今の仕様だけ**を書く。変わったら書き換える（履歴は `.steering/history.md`）。
> 最終更新: 2026-11-04

## 概要
個人用 Web アプリの土台。現時点では API の稼働確認だけを行う。

## 画面
| パス | 内容 |
|---|---|
| `/` | API とDBの状態（`/api/health` の結果）をカードで表示 |

## API
| メソッド | パス | 応答 | 内容 |
|---|---|---|---|
| GET | `/api/health` | `{"status":"ok","database":"ok"}` | API と DB 接続の確認 |

## データ
テーブルなし。

## 設定（環境変数）
| 名前 | 既定値 | 内容 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<リポジトリ>/data/app.db` | DB の接続先 |
| `APP_NAME` | `app-template` | API のタイトル |
| `ANTHROPIC_API_KEY` | なし | Anthropic の API キー。空でなければこちらを優先して使う |
| `OPENAI_API_KEY` | なし | OpenAI の API キー。Anthropic のキーが空のときに使う |
