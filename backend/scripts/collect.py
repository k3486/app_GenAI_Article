"""記事を集めて、本文を取る（段階4）。採点・整理記事は段階5・6でつなぐ。

使い方（backend/ で）:
    uv run python -m scripts.collect                  # 全部の情報源で実行
    uv run python -m scripts.collect --dry-run        # DB に書かず、候補と絞り込みだけを確認
    uv run python -m scripts.collect --source openai-news --source simon-willison
    uv run python -m scripts.collect --no-browser     # ブラウザでの取り直しをしない
先に表を作っておく（make migrate）。
"""

import argparse
import asyncio
from collections import Counter

from sqlmodel import Session

from app.db import engine
from app.services.collect.run import CollectSummary, fetch_stats, run_collection
from app.services.collect.source_config import load_sources

_REASON = {
    "already_seen": "取得済み",
    "old": "古い",
    "not_ai": "AI関連でない",
    "language": "言語",
    "over_cap": "件数の上限",
    "duplicate": "重複",
}


def _drops(counter: Counter[str]) -> str:
    return "、".join(f"{_REASON.get(k, k)}{v}" for k, v in counter.most_common()) or "-"


def _print(summary: CollectSummary, *, dry_run: bool, session: Session) -> None:
    print("\n=== 候補の取得と絞り込み（情報源ごと）===")
    for line in summary.sources:
        mark = "×" if line.error else " "
        print(
            f"{mark} {line.name:34} 候補{line.candidates:4} → 通過{line.kept:3}"
            f"  除外: {_drops(line.dropped)}"
        )
        if line.error:
            print(f"      失敗: {line.error[:110]}")
    print(f"\n候補 {summary.discovered} 件 → 通過 {summary.kept} 件")
    if dry_run or summary.run_id is None:
        print("（--dry-run のため、DB には書いていません）")
        return
    fetch = summary.fetch
    print(
        f"本文の取得: 対象 {fetch.attempted} 件 → 全文 {fetch.full}・概要のみ {fetch.partial}"
        f"・失敗 {fetch.failed}・対象外 {fetch.skipped}（ブラウザで取り直し {fetch.browser_used}）"
    )
    print("\n=== 本文の取得結果（情報源ごと）===")
    for stat in fetch_stats(session, summary.run_id):
        reasons = "、".join(f"{k} {v}" for k, v in stat.reasons.most_common(3)) or "-"
        print(
            f"{stat.source:34} {stat.total:3}件: 全文{stat.full:3} 概要{stat.partial:3}"
            f" 失敗{stat.failed:3} 対象外{stat.skipped:2}  平均{stat.avg_chars:6}字"
            f"  理由: {reasons}"
        )
    print(f"\n実行 #{summary.run_id}: {summary.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="記事を集めて、本文を取る")
    parser.add_argument("--source", action="append", help="この情報源（key）だけ。複数指定できる")
    parser.add_argument("--since-days", type=int, default=3, help="直近何日分を見るか（既定 3）")
    parser.add_argument("--max-candidates", type=int, help="候補の最大件数（既定は画面の設定）")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザでの取り直しをしない")
    parser.add_argument("--dry-run", action="store_true", help="DB に書かない")
    args = parser.parse_args()

    config = load_sources()
    with Session(engine) as session:
        summary = asyncio.run(
            run_collection(
                session,
                config,
                only_keys=set(args.source) if args.source else None,
                since_days=args.since_days,
                max_candidates=args.max_candidates,
                use_browser=not args.no_browser,
                dry_run=args.dry_run,
            )
        )
        _print(summary, dry_run=args.dry_run, session=session)


if __name__ == "__main__":
    main()
