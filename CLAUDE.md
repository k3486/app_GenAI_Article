# ai-news-dashboard

FastAPI（backend/）＋ React（frontend/）＋ SQLite の個人用 Web アプリ。

> 役割・作業の進め方・ドキュメント運用などの共通ルールは `~/.claude/CLAUDE.md`。
> このファイルにはこのプロジェクト固有のことだけを書く。

## 最初に読む
1. `.steering/history.md` と最新の `.steering/*/tasklist.md` → 続きから再開する
2. 現在の仕様は `docs/spec.md`、構成は `docs/architecture.md`
3. 詳細規約は `backend/CLAUDE.md`、`frontend/CLAUDE.md`

## 技術スタック
| 層 | 技術 |
|---|---|
| backend | Python 3.12, FastAPI, SQLModel(SQLite), pydantic-settings, uv, ruff, mypy, pytest |
| frontend | Vite, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, oxlint, Prettier, Vitest |
| 開発環境 | Dev Container（Node 26 / Claude Code）、Playwright 用 Chrome |

## コマンド（必ず Makefile 経由）
| コマンド | 内容 |
|---|---|
| `make setup` | 依存関係のインストール |
| `make dev` | API(8000) と画面(5173) を同時起動 |
| `make lint` | lint・整形チェック・型チェック（Python/TS 両方） |
| `make test` | pytest ＋ Vitest |
| `make format` | 自動整形 |

完了条件: `make lint && make test` が通ること（画面の変更は `make dev` 中に Playwright MCP でも確認）。

## ディレクトリ構造
```
backend/        FastAPI。層は api → services → models/db（逆向きの import 禁止）
frontend/       React。API は /api/*（Vite が :8000 へ転送）
data/           SQLite の置き場（git 管理外）
docs/           現在の仕様
ideas/          実装案
.steering/      作業記録
scripts/        補助スクリプト
.claude/        Claude Code の設定・hook・スキル
.devcontainer/  開発コンテナ
```
各フォルダの中の決まりは `backend/CLAUDE.md`・`frontend/CLAUDE.md`。

## このプロジェクト固有の注意
- API キーは `../.secrets/.env`（コンテナに環境変数として渡される）。必要なキーは `.env.example`
- MCP: context7・playwright・brave-search・github が有効（github は `GITHUB_MCP_PAT` が必要。未設定だと接続失敗になるだけで他には影響しない）
- aws-docs はコンテキスト節約のため AWS の作業まで止めている。使うときは `.claude/settings.json` の
  `disabledMcpjsonServers` から `enabledMcpjsonServers` へ移す
- ファイル編集後は hook で ruff format / prettier が自動で走る
