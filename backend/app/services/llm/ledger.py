"""Haiku の使用量を llm_usage に記録し、実行履歴の費用に足す（メインの流れから1件ずつ）。"""

from sqlmodel import Session

from app.models import LlmUsage, Run
from app.services.llm.client import Usage


def record_usage(
    session: Session, run: Run | None, usage: Usage, *, purpose: str, topic_id: int | None = None
) -> None:
    session.add(
        LlmUsage(
            run_id=run.id if run else None,
            topic_id=topic_id,
            purpose=purpose,
            model_id=usage.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cost_usd=usage.cost_usd,
        )
    )
    if run is not None:
        run.cost_usd += usage.cost_usd
        session.add(run)
