"""点数のぶれの検査: 採点済みの記事から N 件を選び、同じ記事を R 回採点し直して差を見る。

基準・モデルを変えたときの前後比較に使う（結果は DB に保存しない。費用だけ llm_usage に残す）。

使い方（backend/ で）:
    uv run python -m scripts.score_variance               # 10件×3回
    uv run python -m scripts.score_variance --count 10 --repeat 3
"""

import argparse
import asyncio
import statistics
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.db import engine
from app.models import Article, Run, Score, Source
from app.schemas.analysis import ScoreOutput
from app.services.app_settings import load_settings
from app.services.collect.score import _build_job  # 本番と同じ材料の作り方を使う
from app.services.llm.backend import AnthropicBackend
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.context import build_scoring_context
from app.services.llm.ledger import record_usage
from app.services.llm.skills import load_skill
from app.services.preference import current_memo
from app.services.runs import month_cost
from app.services.scoring import compute_total


async def main_async(count: int, repeat: int) -> None:
    with Session(engine) as session:
        settings = load_settings(session)
        last_model = session.exec(
            select(Run.model_id).where(col(Run.model_id) != "").order_by(col(Run.id).desc())
        ).first()
        if not last_model:
            raise SystemExit("採点済みの実行がありません。先に make collect を実行してください")
        rows = session.exec(
            select(Score, Article, Source)
            .join(Article, col(Article.topic_id) == col(Score.topic_id))
            .join(Source, col(Source.id) == col(Article.source_id), isouter=True)
            .where(col(Article.role) == "representative")
            .order_by(col(Score.total))
        ).all()
        step = max(1, len(rows) // count)
        picked = rows[::step][:count]  # 点数の低いものから高いものまで、均等に選ぶ
        llm = Llm(
            AnthropicBackend(),
            last_model,
            Budget(
                run_limit_usd=settings.run_limit_usd,
                month_limit_usd=settings.month_limit_usd,
                month_spent_usd=month_cost(session),
            ),
        )
        skill = load_skill("score")
        context = build_scoring_context(session, settings.profile, current_memo(session))
        weights = settings.weights.as_dict()
        print(f"モデル {last_model} / スキルの版 {skill.version} / {len(picked)}件 × {repeat}回")
        spreads: list[int] = []
        for score, article, source in picked:
            job = _build_job(session, article, source)
            results = await asyncio.gather(
                *(
                    llm.run(
                        skill,
                        context=context,
                        user=job.user,
                        output_type=ScoreOutput,
                        effort="low",
                        max_tokens=4000,
                    )
                    for _ in range(repeat)
                )
            )
            totals = []
            for r in results:
                record_usage(session, None, r.usage, purpose="score", topic_id=score.topic_id)
                o = r.parsed
                totals.append(
                    compute_total(
                        {
                            "interest": o.interest,
                            "practical": o.practical,
                            "freshness": o.freshness,
                            "trust": o.trust,
                            "depth": o.depth,
                        },
                        weights,
                        official=job.official,
                    )
                )
            session.commit()
            spreads.append(max(totals) - min(totals))
            print(f"元 {score.total:3} → {totals}  幅 {spreads[-1]:2}  {score.title_ja[:34]}")
        print(
            f"\n幅の平均 {statistics.mean(spreads):.1f} 点・最大 {max(spreads)} 点"
            f"（{datetime.now(UTC):%Y-%m-%d}）"
        )
        print(f"費用の合計: ${llm.budget.run_spent:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="点数のぶれの検査")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main_async(args.count, args.repeat))


if __name__ == "__main__":
    main()
