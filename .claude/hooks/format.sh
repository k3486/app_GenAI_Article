#!/usr/bin/env bash
# Edit/Write 後に、編集されたファイルだけを自動整形する。
# Python は ruff check も行い、直しきれない違反を Claude に知らせる（exit 2）。
# ツールが未インストール（make setup 前）なら何もせず終了する。整形の失敗では作業を止めない。
set -u
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
file="$(jq -r '.tool_input.file_path // empty' 2>/dev/null)"
[ -n "$file" ] && [ -f "$file" ] || exit 0

case "$file" in
  "$root"/backend/*.py)
    if command -v uv >/dev/null 2>&1 && [ -d "$root/backend/.venv" ]; then
      uv run --directory "$root/backend" ruff format --quiet "$file" >/dev/null 2>&1 || true
      # 自動で直せる違反は直し、残った PEP8 などの違反は終了コード 2 で Claude に知らせる
      if ! out="$(uv run --directory "$root/backend" ruff check --fix --quiet "$file" 2>&1)"; then
        printf 'ruff check の違反があります。直してください:\n%s\n' "$out" >&2
        exit 2
      fi
    fi
    ;;
  "$root"/frontend/*.ts | "$root"/frontend/*.tsx | "$root"/frontend/*.css | "$root"/frontend/*.json)
    if [ -x "$root/frontend/node_modules/.bin/prettier" ]; then
      (cd "$root/frontend" && ./node_modules/.bin/prettier --write --log-level silent "$file") || true
    fi
    ;;
esac
exit 0
