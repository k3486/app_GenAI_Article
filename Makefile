# よく使うコマンドはすべてここから実行する（Claude Code もこれを使う）
.PHONY: setup dev dev-api dev-web test lint format typecheck

UV := uv
NPM := npm --prefix frontend

setup: ## 依存関係のインストール
	cd backend && $(UV) sync
	$(NPM) ci

dev: ## バックエンド(8000)とフロントエンド(5173)を同時に起動。Ctrl-C で両方止まる
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd backend && $(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	$(NPM) run dev

test: ## テスト
	cd backend && $(UV) run pytest -q
	$(NPM) test

lint: ## lint ＋ 型チェック ＋ 整形チェック
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy app tests
	$(NPM) run lint
	$(NPM) run typecheck

format: ## 自動整形
	cd backend && $(UV) run ruff check --fix . && $(UV) run ruff format .
	$(NPM) run format
