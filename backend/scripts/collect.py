"""記事を集めて、本文を取り、話題をまとめて、採点・選定する（整理記事は G4 でつなぐ）。

使い方（backend/ で）:
    uv run python -m scripts.collect                  # 全部の情報源で実行
    uv run python -m scripts.collect --dry-run        # DB に書かず、候補と絞り込みだけを確認
    uv run python -m scripts.collect --source openai-news --source simon-willison
    uv run python -m scripts.collect --no-browser     # ブラウザでの取り直しをしない
    uv run python -m scripts.collect --no-llm         # Haiku を使わない（集めて本文を取るだけ）
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
    _print_analysis(summary)
    print(f"\n実行 #{summary.run_id}: {summary.status}")


def _print_analysis(summary: CollectSummary) -> None:
    if summary.group is None:
        print("\n（Haiku を使わない設定のため、話題のまとめ・採点は行っていません）")
        return
    g = summary.group
    print(f"\n=== 話題のまとめ・採点・選定（モデル: {summary.model_id or '未使用'}）===")
    print(
        f"話題のまとめ: 新しい話題 {g.new_topics}・既存の話題に追加 {g.joined}"
        f"・新着どうしでまとめた {g.merged}" + ("（判定に失敗した分あり）" if g.llm_failed else "")
    )
    if summary.score is not None:
        sc = summary.score
        print(f"採点: {sc.scored} 件・失敗 {sc.failed}・次回に回した {sc.deferred}")
    print(f"この回の Haiku の費用: ${summary.cost_usd:.4f}")
    if summary.select is not None:
        se = summary.select
        print(f"選定: 選定 {se.selected}・重大ニュース {se.major}・落選 {se.rejected}")


def main() -> None:
    parser = argparse.ArgumentParser(description="記事を集めて、本文を取る")
    parser.add_argument("--source", action="append", help="この情報源（key）だけ。複数指定できる")
    parser.add_argument("--since-days", type=int, default=3, help="直近何日分を見るか（既定 3）")
    parser.add_argument("--max-candidates", type=int, help="候補の最大件数（既定は画面の設定）")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザでの取り直しをしない")
    parser.add_argument("--no-llm", action="store_true", help="Haiku を使わない")
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
                use_llm=not args.no_llm,
                dry_run=args.dry_run,
            )
        )
        _print(summary, dry_run=args.dry_run, session=session)


if __name__ == "__main__":
    main()
