# 構成（現在）

> **今の構成だけ**を書く。変わったら書き換える。最終更新: 2026-11-07

## 全体
```
ブラウザ ──> Vite dev server :5173 ──(/api/* を転送)──> FastAPI :8000 ──> SQLite (data/app.db)
```
- 開発中は Vite のプロキシで同一オリジンになるため CORS は設定していない
- 本番（将来・AWS）は静的ファイル（frontend/dist）と API を同一オリジンで配信する想定（段階②で決める）
- 記事の収集は、API とは別のプロセス（`scripts/collect.py`）で動かす。Haiku の処理も同様に別プロセスで動かす設計（未実装）

## バックエンド（backend/）
- `app/main.py` の `create_app()` が `app/api` のルーターを登録
- 依存方向: `api → services → models / db`（逆向きの import はしない）
- `app/api/` 受付係（薄い）／`app/services/` 処理本体／`app/models/` 表／`app/schemas/` API の入出力の型
- 主な services: `topics`（一覧・詳細・操作）、`scoring`（点数と選定の判定）、`insights`（分析の集計）、
  `collect/`（収集: urls・fetcher・extract・browser・collectors・pipeline・run）、
  `runs`（実行履歴・費用・失敗判定）、`sources`、`app_settings`、`search`（全文検索の窓口）、`backup`
- 設定は `app/config.py`（環境変数のみ）。DB セッションは `Depends(get_session)`
- `scripts/`: `collect.py`（収集）、`seed_sample.py`（試しのデータ）、`backup.py`。`sample_data.py` は試しのデータの定義
- `config/sources.yaml`（情報源）、`config/scoring.yaml`（AI 関連語）
- `config/interest_profile.default.md`: 興味プロファイルの初期値（アプリ起動後は DB の設定が正）

### DB
- SQLite は WAL モード＋待ち時間（5秒）＋外部キー有効（`app/db.py`）。API と更新処理の2つのプロセスが同時に使える
- 表の形の変更は Alembic。移行ファイルはアプリのコードに依存しない（標準の型で書き出す）
- 日時は UTC で保存（`app/models/types.py`）。配列などは JSON 型。状態は文字列（DB 固有の型を使わない）
- SQLite 専用の機能は全文検索（FTS5・trigram）だけで、`app/services/search.py` に隔離している。PostgreSQL へ移すときはここを差し替える
- 本文は別表（`article_texts`）。バックアップは SQLite の標準機能で作る（書き込み中でも安全）

## フロントエンド（frontend/）
- `src/lib/api.ts` 経由で `/api/*` を呼ぶ（GET は `apiGet`、更新は `apiSend`）。データの取得・更新は `src/lib/queries.ts`（TanStack Query）
- 型は `src/lib/api-types.ts`（`make types` で API の仕様から自動生成。手で直さない）。別名は `src/lib/types.ts`
- `src/features/<シート>/` に画面、`src/components/` に共通部品、`src/components/charts/` にグラフ（Recharts）
- 一覧の表は TanStack Table 9（サーバー側で並べ替え・ページ分け）
- UI は Tailwind v4 ＋ shadcn/ui。色は `src/index.css` のテーマ変数（ライト／ダーク）。グラフの色は検証済みのパレット
- 開発サーバーは、Windows 側のフォルダ（9p）でも変更を検知できるよう、ポーリングで監視する（`vite.config.ts`）

## 決めた理由
| 決定 | 理由 |
|---|---|
| FastAPI | 非同期 I/O（スクレイピング等）と相性がよく、型から OpenAPI を生成できる |
| uv | 高速・lockfile で再現性が高い |
| SQLite（WAL） | 個人用には十分。SQLModel 経由なので将来 PostgreSQL へ移行しやすい。9p のフォルダでも、3プロセスの同時書き込みでエラーが出ないことを確認済み |
| Alembic | 表の形の変更を、本番でも同じ手順で行うため。移行ファイルと表の定義のずれはテストで検知する |
| 画面と API の型を自動生成 | API を変えたときに、画面側の食い違いをコンパイルの段階で見つけるため |
| 話題を一覧の単位にする | 同じ話題の報道が重複して並ばないようにするため（代表記事に関連記事がぶら下がる） |
| Vite + React + TS | 静的ファイルとして出力でき、AWS 無料枠（S3 等）で公開しやすい |
| oxlint | Vite の標準。ESLint より高速で設定が少ない |
| 秘密情報は環境変数 | ローカル（.secrets/.env）と AWS（SSM Parameter Store）でコードを変えずに済む |
