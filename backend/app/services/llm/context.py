"""採点の指示文に差し込む「興味プロファイル」と「最近の評価（👍/👎/実はよかった）」。"""

from sqlmodel import Session, col, select

from app.models import Score, Topic

FEEDBACK_LIMIT = 10
_DISLIKE_REASONS = {
    "not_interested": "興味なし",
    "already_known": "もう知っていた",
    "low_quality": "質が低い",
}


def _lines(rows: list[tuple[Topic, Score]], *, with_reason: bool = False) -> str:
    if not rows:
        return "（まだありません）"
    out: list[str] = []
    for topic, score in rows:
        reason = ""
        if with_reason and topic.dislike_reason:
            reason = f"［{_DISLIKE_REASONS.get(topic.dislike_reason, topic.dislike_reason)}］"
        out.append(f"- {score.title_ja}{reason}（{score.category}）")
    return "\n".join(out)


def _recent(session: Session, *conditions: object) -> list[tuple[Topic, Score]]:
    stmt = (
        select(Topic, Score).join(Score, col(Score.topic_id) == col(Topic.id)).where(*conditions)  # type: ignore[arg-type]
    )
    return list(session.exec(stmt).all())


def build_scoring_context(session: Session, profile: str) -> str:
    likes = _recent(session, col(Topic.rating) == "like")
    dislikes = _recent(session, col(Topic.rating) == "dislike")
    missed = _recent(session, col(Topic.missed).is_(True))
    likes.sort(key=lambda r: r[0].rated_at or r[1].scored_at, reverse=True)
    dislikes.sort(key=lambda r: r[0].rated_at or r[1].scored_at, reverse=True)
    missed.sort(key=lambda r: r[0].missed_at or r[1].scored_at, reverse=True)
    return (
        f"# 興味プロファイル\n{profile.strip()}\n\n"
        "# 最近の評価（利用者の好みの手がかり）\n"
        f"## 👍 を付けた記事\n{_lines(likes[:FEEDBACK_LIMIT])}\n\n"
        f"## 👎 を付けた記事\n{_lines(dislikes[:FEEDBACK_LIMIT], with_reason=True)}\n\n"
        f"## 落選していたが「実はよかった」とされた記事\n{_lines(missed[:FEEDBACK_LIMIT])}"
    )
