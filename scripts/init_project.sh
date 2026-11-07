#!/usr/bin/env bash
# テンプレートから作った新しいリポジトリを初期化する。
#   使い方: ./scripts/init_project.sh <new-name>   （kebab-case: 小文字・数字・ハイフン）
# やること:
#   1. "app-template" という名前を <new-name> に一括置換
#   2. README のテンプレート専用の節を削除
#   3. .steering/ と ideas/ のテンプレート自身の記録を空にする（README・書き方の見本は残す）
#   4. このスクリプト自身を削除
set -euo pipefail

OLD="app-template"
NEW="${1:-}"

if [[ ! "$NEW" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]]; then
  echo "usage: $0 <new-name>   (kebab-case 例: ai-news-dashboard)" >&2
  exit 1
fi
if [[ "$NEW" == "$OLD" ]]; then
  echo "error: 新しい名前を指定してください（$OLD 以外）" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SELF="scripts/init_project.sh"

# 1. 名前の置換（生成物・依存・記録フォルダ・自分自身は対象外）
grep -rlI --null "$OLD" . \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=dist \
  --exclude-dir=.steering --exclude-dir=ideas --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache \
  --exclude-dir=.pytest_cache \
  | while IFS= read -r -d '' f; do
      [[ "$f" == "./$SELF" ]] && continue
      sed -i "s/$OLD/$NEW/g" "$f"
      echo "replaced: $f"
    done

# 2. README のテンプレート専用の節を削除
sed -i '/<!-- TEMPLATE-ONLY:START -->/,/<!-- TEMPLATE-ONLY:END -->/d' README.md

# 3. 記録のリセット
find .steering -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +
cat > .steering/history.md <<'EOF'
# 開発履歴（追記のみ）

| 日付 | 内容 | 記録 |
|---|---|---|
EOF
find ideas -mindepth 1 -maxdepth 1 -type f ! -name README.md -delete

# 4. 自分自身を削除
rm -f "$SELF"
rmdir scripts 2>/dev/null || true

echo
echo "done: $OLD -> $NEW"
echo "次: make setup && make lint && make test"
