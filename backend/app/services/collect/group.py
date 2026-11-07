"""同じ話題をまとめる（記事 → 話題）。

1. 同じ共通リンク（link_key。いまは arXiv ID）を持つ記事は、Haiku を使わずまとめる。
2. 残りは Haiku が、既存の話題（直近3日）と新着の記事を見て判定する。迷ったらまとめない。
代表の優先順位: 公式 → 紹介記事 → 論文（同順位は早く出たもの）。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlmodel import Session, col, select

from app.models import Article, ArticleText, Run, RunIssue, Source, Topic
from app.schemas.analysis import GroupOutput
from app.services.llm.client import Llm
from app.services.llm.errors import BudgetExceededError, LlmError
from app.services.llm.ledger import record_usage
from app.services.llm.skills import Skill, load_skill

WINDOW_DAYS = 3
CHUNK = 40  # 1回の呼び出しで判定する新着の件数
NEW_EXCERPT = 500
# Haiku に見せる記事 ID は、話題 ID と数字が重ならないよう、この値を足す（取り違え防止）
ARTICLE_ID_OFFSET = 100_000
TOPIC_EXCERPT = 150
_KIND_RANK = {"official": 0, "media": 1, "paper": 2}


@dataclass
class GroupReport:
    new_topics: int = 0
    joined: int = 0  # 既存の話題に入れた記事
    merged: int = 0  # 新着どうしでまとめた記事（代表以外）
    llm_failed: bool = False
    budget_stopped: bool = False


def _rank(article: Article, kinds: dict[int | None, str]) -> tuple[int, datetime]:
    kind = kinds.get(article.source_id, "media")
    rank = _KIND_RANK.get(kind, 1)
    if article.is_paper and kind != "official":
        rank = max(rank, 2)
    return rank, article.published_at


def _excerpt(session: Session, article: Article, limit: int) -> str:
    text = session.get(ArticleText, article.id)
    body = text.body if text else article.summary
    return " ".join(body.split())[:limit]


def _new_topic(session: Session, run: Run, now: datetime) -> Topic:
    topic = Topic(selection="pending", run_id=run.id, created_at=now)
    session.add(topic)
    session.flush()
    return topic


def _attach(session: Session, articles: list[Article], topic_id: int, roles: list[str]) -> None:
    for article, role in zip(articles, roles, strict=True):
        article.topic_id = topic_id
        article.role = role
        article.stage = "grouped"
        session.add(article)


def _make_topic(
    session: Session,
    run: Run,
    members: list[Article],
    kinds: dict[int | None, str],
    now: datetime,
) -> int:
    ordered = sorted(members, key=lambda a: _rank(a, kinds))
    topic = _new_topic(session, run, now)
    assert topic.id is not None
    _attach(
        session,
        ordered,
        topic.id,
        ["representative"] + ["related"] * (len(ordered) - 1),
    )
    return topic.id


def _link_groups(new: list[Article]) -> list[list[Article]]:
    by_key: dict[str, list[Article]] = {}
    for article in new:
        if article.link_key:
            by_key.setdefault(article.link_key, []).append(article)
    return [group for group in by_key.values() if len(group) >= 2]


async def group_new(
    session: Session,
    llm: Llm | None,
    *,
    run: Run,
    now: datetime,
) -> GroupReport:
    """本文を取れた新着（stage=fetched）を話題にまとめる。llm が None のときは機械的な分だけ。"""
    report = GroupReport()
    new = list(
        session.exec(
            select(Article)
            .where(col(Article.stage) == "fetched", col(Article.topic_id).is_(None))
            .order_by(col(Article.published_at))
        ).all()
    )
    if not new:
        return report
    kinds: dict[int | None, str] = {
        s.id: s.kind for s in session.exec(select(Source)).all() if s.id is not None
    }
    since = now - timedelta(days=WINDOW_DAYS)

    # 1. 共通リンク: 既存の話題に同じ link_key があればそこへ、新着どうしならまとめる
    existing_by_key: dict[str, int] = {}
    for article in session.exec(
        select(Article).where(
            col(Article.link_key).is_not(None),
            col(Article.topic_id).is_not(None),
            col(Article.published_at) >= since,
        )
    ).all():
        if article.link_key and article.topic_id:
            existing_by_key.setdefault(article.link_key, article.topic_id)
    rest: list[Article] = []
    for group in _link_groups(new):
        key = group[0].link_key
        if key in existing_by_key:
            _attach(session, group, existing_by_key[key], ["related"] * len(group))
            report.joined += len(group)
        else:
            _make_topic(session, run, group, kinds, now)
            report.new_topics += 1
            report.merged += len(group) - 1
    done = {a.id for a in new if a.stage == "grouped"}
    for article in new:
        if article.id in done:
            continue
        key = article.link_key
        if key and key in existing_by_key:
            _attach(session, [article], existing_by_key[key], ["related"])
            report.joined += 1
        else:
            rest.append(article)
    session.commit()

    # 2. Haiku で判定（失敗・上限のときは、まとめずに単独の話題にする）
    skill = load_skill("group") if llm is not None else None
    for start in range(0, len(rest), CHUNK):
        chunk = rest[start : start + CHUNK]
        output: GroupOutput | None = None
        if llm is not None and skill is not None and not report.budget_stopped:
            try:
                output = await _ask(session, llm, skill, chunk, run=run, since=since)
            except BudgetExceededError:
                report.budget_stopped = True
            except LlmError as error:
                report.llm_failed = True
                session.add(
                    RunIssue(
                        run_id=run.id or 0,
                        source_name="Haiku",
                        stage="話題のまとめ",
                        message=f"判定に失敗したため、{len(chunk)}件を単独の話題にしました（{error}）",
                    )
                )
        _apply_group(session, run, chunk, output, kinds, now, report)
        session.commit()
    return report


async def _ask(
    session: Session, llm: Llm, skill: Skill, chunk: list[Article], *, run: Run, since: datetime
) -> GroupOutput:
    topics = session.exec(
        select(Topic).where(col(Topic.created_at) >= since).order_by(col(Topic.id).desc())
    ).all()
    lines: list[str] = []
    for topic in topics:
        rep = session.exec(
            select(Article).where(
                col(Article.topic_id) == topic.id, col(Article.role) == "representative"
            )
        ).first()
        if rep is not None:
            lines.append(
                f"- 話題ID {topic.id}: {rep.title_original} / "
                f"{_excerpt(session, rep, TOPIC_EXCERPT)}"
            )
    context = "# 既存の話題（直近3日）\n" + ("\n".join(lines) if lines else "（まだありません）")
    news = "\n".join(
        f'<article id="{(a.id or 0) + ARTICLE_ID_OFFSET}">\nタイトル: {a.title_original}\n'
        f"冒頭: {_excerpt(session, a, NEW_EXCERPT)}\n</article>"
        for a in chunk
    )
    result = await llm.run(
        skill,
        context=context,
        user=f"# 新着の記事\n{news}",
        output_type=GroupOutput,
        effort="medium",  # low だとニュースレターや別の話題を誤ってまとめた（2026-11-07 実測）
        max_tokens=4000,
    )
    record_usage(session, run, result.usage, purpose="group")
    return result.parsed


def _apply_group(
    session: Session,
    run: Run,
    chunk: list[Article],
    output: GroupOutput | None,
    kinds: dict[int | None, str],
    now: datetime,
    report: GroupReport,
) -> None:
    by_id = {(a.id or 0) + ARTICLE_ID_OFFSET: a for a in chunk}
    used: set[int] = set()
    if output is not None:
        valid_topics = set(session.exec(select(Topic.id)).all())
        for join in output.joins:
            article = by_id.get(join.article_id)
            if article is None or article.id in used or join.topic_id not in valid_topics:
                continue
            _attach(session, [article], join.topic_id, ["related"])
            used.add(article.id or 0)
            report.joined += 1
        for ids in output.same_topic_sets:
            members = [
                by_id[i] for i in dict.fromkeys(ids) if i in by_id and by_id[i].id not in used
            ]
            if len(members) < 2:
                continue
            _make_topic(session, run, members, kinds, now)
            used.update(a.id or 0 for a in members)
            report.new_topics += 1
            report.merged += len(members) - 1
    for article in chunk:
        if article.id in used:
            continue
        _make_topic(session, run, [article], kinds, now)
        report.new_topics += 1
