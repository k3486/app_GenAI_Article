# backend（FastAPI / Python 3.12 / uv）

## 置き場の決まり（必要になったら作る）
| 場所 | 内容 |
|---|---|
| `app/main.py` | `create_app()`。ルーター登録のみ |
| `app/config.py` | 設定。**環境変数のみ**から読む（`get_settings()` 経由で使う） |
| `app/db.py` | エンジンと `get_session()` |
| `app/api/<機能>.py` | ルーター。`app/api/__init__.py` で include。処理は薄く、ロジックは services へ |
| `app/services/<機能>.py` | ビジネスロジック |
| `app/models/<名前>.py` | DB テーブル（SQLModel, `table=True`） |
| `app/schemas/<機能>.py` | API の入出力型（ファイルが増えてきたら api から分離） |
| `app/workflows/<名前>.py` | LLM のワークフロー・エージェント。services から呼ぶ |
| `scripts/` | CLI・バッチ処理の入口 |
| `tests/` | `app/` と同じ構成で `test_*.py` |

依存方向: `api → services → models / db`。逆向きの import はしない。

## 規約
- PEP8 に従う（命名・書式とも ruff で検査。編集のたびに hook が整形と検査を行う）。
  ruff で判定できない点に迷ったら原文 https://peps.python.org/pep-0008/ を確認する
- 型ヒント必須（mypy strict が通ること）。ruff の設定は `pyproject.toml`
- エンドポイントは戻り値の型（Pydantic モデル）を明示する
- DB は `Depends(get_session)` で受け取る（直接 `engine` を触らない）
- パッケージ追加は `uv add <pkg>` ／ 開発用は `uv add --dev <pkg>`（pip は使わない）
- テーブルを初めて作るときに Alembic を導入する（それまでは入れない）

## LLM（ワークフロー・エージェント）
- 既定は LangChain（`create_agent`）。決まった手順と LLM の判断を組み合わせる独自の流れは LangGraph
- 入出力・状態の型は Pydantic で定義し、構造化出力で受け取る
- LLM を1回呼ぶだけなど、使わない方が簡単で良い場合は、理由を添えて別の方法を提案する
- 依存（`uv add langchain langgraph` など）は使い始めるときに追加する。最新の使い方は context7 で確認する
- API キーは `get_settings()` から渡す（LangChain に環境変数を直接読ませない）。
  提供元は `get_llm_provider()` で決める（空でないキーを使い、両方あれば Anthropic）
- キーの値はコード・`.env.example` に書かない（実際の値は `../.secrets/.env`）
- テストでは本物の LLM を呼ばず、LangChain のテスト用の偽モデルを使う

## テスト
- `tests/conftest.py` の `client` / `session` フィクスチャを使う（テストごとにメモリ上の SQLite）
- API を追加したら最低1本のテストを書く
- 実行: `uv run pytest -q`（またはルートで `make test`）
