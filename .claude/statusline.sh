#!/usr/bin/env bash
# Claude Code のステータスライン。標準入力のセッション情報（JSON）から1行を組み立てて出力する。
#   表示: モデル·思考の深さ │ フォルダ ブランチ(*=未コミットあり) │ ctx バー 使用率 │ 5h 利用上限の消費率
# 値がない項目は省く。JSON が壊れていても止まらず、出せる部分だけを出す。
set -u

input="$(cat)"

# 1回の jq で必要な値を取り出す（空の値でもずれないよう、区切りは空白ではなく \x1f）
IFS=$'\x1f' read -r model effort dir ctx five_hour < <(
  jq -r '[
    (.model.display_name // ""),
    (.effort.level // ""),
    (.workspace.current_dir // .cwd // ""),
    (.context_window.used_percentage // "" | tostring),
    (.rate_limits.five_hour.used_percentage // "" | tostring)
  ] | join("\u001f")' <<<"$input" 2>/dev/null
) || true

reset=$'\033[0m'
dim=$'\033[2m'

# 使用率に応じた色: 50% 未満は緑、80% 未満は黄、それ以上は赤
color_for() {
  local p=$1
  if ((p < 50)); then printf '\033[32m'
  elif ((p < 80)); then printf '\033[33m'
  else printf '\033[31m'
  fi
}

# 小数を切り捨てて 0〜100 の整数にする。数値でなければ空を返す
to_pct() {
  local v=${1%%.*}
  [[ "$v" =~ ^[0-9]+$ ]] || return 0
  ((v > 100)) && v=100
  printf '%s' "$v"
}

parts=()

if [[ -n "${model:-}" ]]; then
  parts+=("${model}${effort:+·$effort}")
fi

if [[ -n "${dir:-}" ]]; then
  where="$(basename "$dir")"
  branch="$(git -C "$dir" --no-optional-locks branch --show-current 2>/dev/null)"
  if [[ -n "$branch" ]]; then
    if [[ -n "$(git -C "$dir" --no-optional-locks status --porcelain 2>/dev/null | head -1)" ]]; then
      branch+="*"
    fi
    where+=" $branch"
  fi
  parts+=("$where")
fi

ctx_pct="$(to_pct "${ctx:-}")"
if [[ -n "$ctx_pct" ]]; then
  filled=$(((ctx_pct + 5) / 10))
  bar=""
  for ((i = 0; i < 10; i++)); do
    if ((i < filled)); then bar+="▓"; else bar+="░"; fi
  done
  parts+=("ctx $(color_for "$ctx_pct")${bar} ${ctx_pct}%${reset}")
fi

five_pct="$(to_pct "${five_hour:-}")"
if [[ -n "$five_pct" ]]; then
  parts+=("5h $(color_for "$five_pct")${five_pct}%${reset}")
fi

sep=" ${dim}│${reset} "
out=""
for p in "${parts[@]}"; do
  out+="${out:+$sep}$p"
done
printf '%s\n' "$out"
