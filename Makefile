# よく使うコマンドはすべてここから実行する（Claude Code もこれを使う）
.PHONY: setup dev dev-api dev-web test lint format typecheck types migrate seed backup

UV := uv
NPM := npm --prefix frontend

setup: ## 依存関係のインストール
	cd backend && $(UV) sync
	$(NPM) ci

dev: ## バックエンド(8000)とフロントエンド(5173)を同時に起動。Ctrl-C で両方止まる
	$(MAKE) -j2 dev-api dev-web

dev-api: migrate
	cd backend && $(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	$(NPM) run dev

test: ## テスト
	cd backend && $(UV) run pytest -q
	$(NPM) test

lint: ## lint ＋ 型チェック ＋ 整形チェック
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy app tests scripts
	$(NPM) run lint
	$(NPM) run typecheck

migrate: ## DB の表を最新の形にする（Alembic）。make dev で自動的に実行される
	cd backend && $(UV) run alembic upgrade head

seed: migrate ## 画面確認用の試しのデータを DB に入れる（入れ直しは `cd backend && uv run python -m scripts.seed_sample --reset`）
	cd backend && $(UV) run python -m scripts.seed_sample

backup: ## DB のバックアップを作る（data/backups/ に7世代）
	cd backend && $(UV) run python -m scripts.backup

types: ## API の仕様(OpenAPI)から frontend の型(src/lib/api-types.ts)を作り直す。API を変えたら実行
	cd backend && $(UV) run python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../data/openapi.json
	$(NPM) run gen:api

format: ## 自動整形
	cd backend && $(UV) run ruff check --fix . && $(UV) run ruff format .
	$(NPM) run format
