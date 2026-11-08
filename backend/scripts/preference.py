"""好みメモと修正案だけを作る（収集はしない）。G5 の確認用。

評価（👍/👎/実はよかった）から Haiku が好みメモを書き、興味プロファイルの修正案を出す。
結果は DB に保存する（修正案は承認するまでプロファイルに反映されない）。

使い方（backend/ で）:
    uv run python -m scripts.preference            # 評価が20件たまっているときだけ
    uv run python -m scripts.preference --force    # 件数に関係なく作る
"""

import argparse
import asyncio

from sqlmodel import Session, col, select

from app.db import engine
from app.models import Run
from app.services.app_settings import load_settings
from app.services.llm.backend import AnthropicBackend
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.preference import current_memo, list_proposals, maybe_update
from app.services.runs import month_cost


async def main_async(force: bool) -> None:
    with Session(engine) as session:
        settings = load_settings(session)
        model = session.exec(
            select(Run.model_id).where(col(Run.model_id) != "").order_by(col(Run.id).desc())
        ).first()
        if not model:
            raise SystemExit("採点済みの実行がありません。先に make collect を実行してください")
        llm = Llm(
            AnthropicBackend(),
            model,
            Budget(
                run_limit_usd=settings.run_limit_usd,
                month_limit_usd=settings.month_limit_usd,
                month_spent_usd=month_cost(session),
            ),
        )
        report = await maybe_update(session, llm, run=None, settings=settings, force=force)
        print(report)
        print("\n--- 好みメモ ---\n" + (current_memo(session) or "（なし）"))
        for p in list_proposals(session, "pending"):
            print(f"\n--- 修正案 #{p.id} [{p.kind}] ---")
            print(f"変更前: {p.before_text or '（なし）'}\n変更後: {p.after_text or '（削除）'}")
            print(f"理由: {p.reason}\n根拠: {[e.title_ja for e in p.evidence]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="好みメモと修正案を作る")
    parser.add_argument("--force", action="store_true", help="評価の件数に関係なく作る")
    args = parser.parse_args()
    asyncio.run(main_async(args.force))


if __name__ == "__main__":
    main()
