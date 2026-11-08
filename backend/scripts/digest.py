"""整理記事の試し作り: 選定済みで未作成の話題から、種類ごとに N 件だけ作る（収集はしない）。

G4 の確認用。作った整理記事は DB に保存する（費用は llm_usage に残す）。

使い方（backend/ で）:
    uv run python -m scripts.digest                 # 種類ごとに1件（点数の高い順）
    uv run python -m scripts.digest --per-type 2
    uv run python -m scripts.digest --topic 12 --topic 34
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.db import engine
from app.models import Digest, Run, Score, Topic
from app.services.app_settings import load_settings
from app.services.collect.digest import digest_selected
from app.services.llm.backend import AnthropicBackend
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.runs import month_cost


def _pick_per_type(session: Session, per_type: int) -> list[int]:
    rows = session.exec(
        select(Topic, Score)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .where(
            col(Topic.selection).in_(["selected", "major"]),
            col(Topic.id).not_in(select(Digest.topic_id)),
        )
        .order_by(col(Score.total).desc())
    ).all()
    taken: dict[str, list[int]] = {}
    for topic, score in rows:
        ids = taken.setdefault(score.article_type, [])
        if len(ids) < per_type and topic.id is not None:
            ids.append(topic.id)
    return [i for ids in taken.values() for i in ids]


async def main_async(per_type: int, topics: list[int] | None) -> None:
    with Session(engine) as session:
        settings = load_settings(session)
        model = session.exec(
            select(Run.model_id).where(col(Run.model_id) != "").order_by(col(Run.id).desc())
        ).first()
        if not model:
            raise SystemExit("採点済みの実行がありません。先に make collect を実行してください")
        only = topics or _pick_per_type(session, per_type)
        if not only:
            raise SystemExit("整理記事を作る対象（選定済みで未作成の話題）がありません")
        llm = Llm(
            AnthropicBackend(),
            model,
            Budget(
                run_limit_usd=settings.run_limit_usd,
                month_limit_usd=settings.month_limit_usd,
                month_spent_usd=month_cost(session),
            ),
        )
        report = await digest_selected(
            session, llm, run=None, settings=settings, now=datetime.now(UTC), only=only
        )
        print(f"対象 {len(only)} 件 → 作成 {report.created}・失敗 {report.failed}")
        for topic_id in only:
            digest = session.get(Digest, topic_id)
            score = session.get(Score, topic_id)
            if digest is None or score is None:
                continue
            size = sum(len(p["text"]) for s in digest.sections for p in s["paragraphs"])
            print(f"  話題 {topic_id} [{digest.article_type}] {score.title_ja[:34]} … {size}字")


def main() -> None:
    parser = argparse.ArgumentParser(description="整理記事の試し作り")
    parser.add_argument("--per-type", type=int, default=1, help="種類ごとの件数（既定 1）")
    parser.add_argument("--topic", type=int, action="append", help="この話題 ID だけ")
    args = parser.parse_args()
    asyncio.run(main_async(args.per_type, args.topic))


if __name__ == "__main__":
    main()
