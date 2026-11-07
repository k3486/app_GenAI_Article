# 構成（現在）

> **今の構成だけ**を書く。変わったら書き換える。最終更新: 2026-11-03

## 全体
```
ブラウザ ──> Vite dev server :5173 ──(/api/* を転送)──> FastAPI :8000 ──> SQLite (data/app.db)
```
- 開発中は Vite のプロキシで同一オリジンになるため CORS は設定していない
- 本番（将来・AWS）は静的ファイル（frontend/dist）と API を同一オリジンで配信する想定

## バックエンド
- `app/main.py` の `create_app()` が `app/api` のルーターを登録
- 依存方向: `api → services → models / db`
- 設定は `app/config.py`（環境変数のみ）。DB セッションは `Depends(get_session)`
- テストはメモリ上の SQLite に差し替えて実行

## フロントエンド
- `src/lib/api.ts` 経由で `/api/*` を呼ぶ
- UI は Tailwind v4 ＋ shadcn/ui（`src/components/ui/`）

## 決めた理由
| 決定 | 理由 |
|---|---|
| FastAPI | 非同期 I/O（スクレイピング等）と相性がよく、型から OpenAPI を生成できる |
| uv | 高速・lockfile で再現性が高い |
| SQLite | 個人用には十分。SQLModel 経由なので将来 PostgreSQL へ移行しやすい |
| Vite + React + TS | 静的ファイルとして出力でき、AWS 無料枠（S3 等）で公開しやすい |
| oxlint | Vite の標準。ESLint より高速で設定が少ない |
| 秘密情報は環境変数 | ローカル（.secrets/.env）と AWS（SSM Parameter Store）でコードを変えずに済む |
| Alembic は未導入 | テーブルを初めて作るときに導入する |
