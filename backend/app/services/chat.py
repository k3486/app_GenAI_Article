"""壁打ち（整理記事の画面での Haiku との対話）とメモ。

Haiku は読み取り専用のツール4つ（記事の本文・関連記事・過去記事の検索・★の記事の検索）を、
必要なときに自分で呼ぶ。ツールが読むのは DB だけで、書き込みも外部への通信もしない。
会話は話題ごとに DB へ保存し、1回の回答あたりの費用に上限（$0.05）をかける。
"""

import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, col, select

from app.models import (
    Article,
    ArticleText,
    ChatMessage,
    Digest,
    Note,
    Run,
    Score,
    Source,
    Topic,
)
from app.schemas.chat import ChatMessageOut, ChatState, NoteOut
from app.services.app_settings import load_settings
from app.services.collect.score import _clean
from app.services.llm.agent import Tool, ToolError, run_agent
from app.services.llm.backend import AnthropicBackend, ToolSpec
from app.services.llm.budget import Budget
from app.services.llm.client import Llm
from app.services.llm.errors import LlmUnavailableError
from app.services.llm.ledger import record_usage
from app.services.llm.skills import load_skill
from app.services.runs import month_cost
from app.services.search import index_topic, search_topic_ids

ROUNDS_LIMIT = 20  # 1つの話題で、質問できる回数（設計で決定）
ANSWER_LIMIT_USD = 0.05  # 1回の回答にかける費用の上限
BODY_LIMIT = 20_000
RELATED_LIMIT = 3
RELATED_BODY_LIMIT = 6_000
SEARCH_HITS = 5
MAX_SEARCH_TERMS = 5


class TopicNotFoundError(Exception):
    pass


class RoundsExceededError(Exception):
    pass


class NoteNotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


# --- ツール（読み取り専用） -----------------------------------------------------


class _TopicArgs(BaseModel):
    topic_id: int


class _QueryArgs(BaseModel):
    query: str = Field(min_length=1, max_length=100)


def _parse[T: BaseModel](model: type[T], arguments: dict[str, Any]) -> T:
    try:
        return model.model_validate(arguments)
    except ValidationError as error:
        raise ToolError("引数が正しくありません") from error


def _representative(session: Session, topic_id: int) -> Article | None:
    return session.exec(
        select(Article).where(
            col(Article.topic_id) == topic_id, col(Article.role) == "representative"
        )
    ).first()


def _body(session: Session, article: Article, limit: int) -> str:
    row = session.get(ArticleText, article.id)
    return (row.body if row else article.summary)[:limit]


def _read_article(session: Session, arguments: dict[str, Any]) -> str:
    topic_id = _parse(_TopicArgs, arguments).topic_id
    rep = _representative(session, topic_id)
    if rep is None:
        raise ToolError(f"話題 {topic_id} は見つかりません")
    state = "全文" if rep.fetch_status == "full" else "概要のみ（全文未取得）"
    return (
        f"タイトル: {rep.title_original}\n本文の状態: {state}\n\n{_body(session, rep, BODY_LIMIT)}"
    )


def _read_related(session: Session, arguments: dict[str, Any]) -> str:
    topic_id = _parse(_TopicArgs, arguments).topic_id
    related = session.exec(
        select(Article)
        .where(
            col(Article.topic_id) == topic_id,
            col(Article.role) == "related",
            col(Article.fetch_status) == "full",
        )
        .order_by(col(Article.published_at))
    ).all()[:RELATED_LIMIT]
    if not related:
        return "本文のある関連記事はありません"
    return "\n\n".join(
        f"## {a.title_original}\n{_body(session, a, RELATED_BODY_LIMIT)}" for a in related
    )


def _search(session: Session, arguments: dict[str, Any], *, favorites: bool) -> str:
    query = _parse(_QueryArgs, arguments).query
    # 空白で区切った語ごとに探し、多くの語に当たった話題を上に出す（語の並びを1語句として探さない）
    terms = list(dict.fromkeys(query.split()))[:MAX_SEARCH_TERMS]
    matches: Counter[int] = Counter()
    for term in terms:
        matches.update(search_topic_ids(session, term))
    if not matches:
        return "見つかりませんでした"
    stmt = (
        select(Topic, Score)
        .join(Score, col(Score.topic_id) == col(Topic.id))
        .where(col(Topic.id).in_(list(matches)))
    )
    if favorites:
        stmt = stmt.where(col(Topic.starred).is_(True))
    found = sorted(session.exec(stmt).all(), key=lambda r: (-matches[r[0].id or 0], -r[1].total))
    rows = found[:SEARCH_HITS]
    if not rows:
        return "見つかりませんでした"
    return "\n".join(
        f"話題ID {t.id}｜{s.title_ja}｜{s.summary_1line}｜{t.created_at:%Y-%m-%d}｜{s.total}点"
        for t, s in rows
    )


def make_tools(session: Session) -> list[Tool]:
    """壁打ちで Haiku に使わせるツール。どれも DB を読むだけ。"""
    topic_schema = {
        "type": "object",
        "properties": {"topic_id": {"type": "integer", "description": "話題 ID"}},
        "required": ["topic_id"],
        "additionalProperties": False,
    }
    query_schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "検索語（100字まで）"}},
        "required": ["query"],
        "additionalProperties": False,
    }
    return [
        Tool(
            ToolSpec("read_article", "話題の代表記事の本文を読む", topic_schema),
            lambda a: _read_article(session, a),
        ),
        Tool(
            ToolSpec("read_related", "話題の関連記事（他媒体）の本文を読む", topic_schema),
            lambda a: _read_related(session, a),
        ),
        Tool(
            ToolSpec("search_articles", "過去に集めた記事を検索語で探す", query_schema),
            lambda a: _search(session, a, favorites=False),
        ),
        Tool(
            ToolSpec("search_favorites", "★を付けた記事だけを検索語で探す", query_schema),
            lambda a: _search(session, a, favorites=True),
        ),
    ]


# --- 会話 ----------------------------------------------------------------------


def _digest_text(digest: Digest) -> str:
    lines = ["## 3行まとめ", *(f"- {line}" for line in digest.lead)]
    for section in digest.sections:
        lines.append(f"## {section['heading']}")
        for p in section["paragraphs"]:
            mark = "（AI の意見）" if p["inference"] else ""
            lines.append(f"{mark}{p['text']}")
    return "\n".join(lines)


def build_context(session: Session, topic: Topic, score: Score) -> str:
    """最初に Haiku へ渡す文脈（整理記事＋代表記事の本文）。変わらないのでキャッシュされる。"""
    parts = [f"# 話題 {topic.id}: {score.title_ja}"]
    digest = session.get(Digest, topic.id)
    if digest is not None:
        parts.append("# 整理記事（AI が書いたもの）\n" + _digest_text(digest))
    else:
        parts.append("# 要約\n" + "\n".join(score.summary_5lines))
    rep = _representative(session, topic.id or 0)
    if rep is not None:
        source = session.get(Source, rep.source_id) if rep.source_id else None
        state = "全文" if rep.fetch_status == "full" else "概要のみ（全文未取得）"
        parts.append(
            "<article>\n"
            f"タイトル: {_clean(rep.title_original)}\n"
            f"情報源: {source.name if source else rep.domain}\n"
            f"本文の状態: {state}\n"
            f"<本文>\n{_clean(_body(session, rep, BODY_LIMIT))}\n</本文>\n</article>"
        )
    return "\n\n".join(parts)


def _to_out(m: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut.model_validate(m, from_attributes=True)


def _history_entry(message: ChatMessageOut) -> dict[str, Any]:
    """履歴を Haiku に渡す形にする。回答には、使ったツールの記録を添える。

    ツールの結果そのものは履歴に残さない。記録がないと、Haiku は「検索していないのに、検索したと
    書いた」と思い違いをして、事実と違う訂正をしてしまう。
    """
    if message.role == "assistant" and message.tool_log:
        used = "、".join(
            f"{call['name']}({json.dumps(call['input'], ensure_ascii=False)})"
            for call in message.tool_log
        )
        return {
            "role": "assistant",
            "content": (
                f"{message.content}\n\n"
                f"［システムの記録: この回答の前に、実際に次のツールを実行した: {used}］"
            ),
        }
    return {"role": message.role, "content": message.content}


def get_chat(session: Session, topic_id: int) -> ChatState:
    messages = session.exec(
        select(ChatMessage)
        .where(col(ChatMessage.topic_id) == topic_id)
        .order_by(col(ChatMessage.id))
    ).all()
    return ChatState(
        messages=[_to_out(m) for m in messages],
        rounds_used=sum(1 for m in messages if m.role == "user"),
        rounds_limit=ROUNDS_LIMIT,
    )


def make_llm(session: Session) -> Llm:
    """壁打ち用の Haiku の口。直近の更新で使ったモデルで、1回の回答の上限をかける。"""
    model = session.exec(
        select(Run.model_id).where(col(Run.model_id) != "").order_by(col(Run.id).desc())
    ).first()
    if not model:
        raise LlmUnavailableError("使う Haiku が決まっていません（更新を一度実行してください）")
    settings = load_settings(session)
    return Llm(
        AnthropicBackend(),
        model,
        Budget(
            run_limit_usd=ANSWER_LIMIT_USD,
            month_limit_usd=settings.month_limit_usd,
            month_spent_usd=month_cost(session),
        ),
    )


LlmFactory = Callable[[Session], Llm]


async def ask(
    session: Session, make: LlmFactory, topic_id: int, question: str, now: datetime | None = None
) -> ChatState:
    """質問を1つ受けて、Haiku の回答まで作って保存する。失敗したときは何も保存しない。"""
    topic = session.get(Topic, topic_id)
    score = session.get(Score, topic_id)
    if topic is None or score is None:
        raise TopicNotFoundError
    state = get_chat(session, topic_id)
    if state.rounds_used >= ROUNDS_LIMIT:
        raise RoundsExceededError
    now = now or _now()
    llm = make(session)  # キーが無いときは LlmUnavailableError
    history: list[dict[str, Any]] = [_history_entry(m) for m in state.messages]
    history.append({"role": "user", "content": question})
    result = await run_agent(
        llm,
        load_skill("chat"),
        context=build_context(session, topic, score),
        history=history,
        tools=make_tools(session),
    )
    session.add(ChatMessage(topic_id=topic_id, role="user", content=question, created_at=now))
    session.add(
        ChatMessage(
            topic_id=topic_id,
            role="assistant",
            content=result.text,
            tool_log=result.tool_log,
            cost_usd=result.usage.cost_usd,
            status="limited" if result.limited else "ok",
            created_at=now,
        )
    )
    if result.usage.cost_usd > 0:
        record_usage(session, None, result.usage, purpose="chat", topic_id=topic_id)
    session.commit()
    return get_chat(session, topic_id)


# --- メモ ----------------------------------------------------------------------


def _note_out(note: Note) -> NoteOut:
    return NoteOut.model_validate(note, from_attributes=True)


def add_note(
    session: Session,
    topic_id: int,
    text: str,
    chat_message_id: int | None = None,
    now: datetime | None = None,
) -> NoteOut:
    if session.get(Topic, topic_id) is None:
        raise TopicNotFoundError
    if chat_message_id is not None:
        message = session.get(ChatMessage, chat_message_id)
        if message is None or message.topic_id != topic_id:
            raise NoteNotFoundError
    note = Note(
        topic_id=topic_id, chat_message_id=chat_message_id, text=text, created_at=now or _now()
    )
    session.add(note)
    session.flush()
    index_topic(session, topic_id)  # メモも検索の対象
    session.commit()
    session.refresh(note)
    return _note_out(note)


def delete_note(session: Session, note_id: int) -> None:
    note = session.get(Note, note_id)
    if note is None:
        raise NoteNotFoundError
    topic_id = note.topic_id
    session.delete(note)
    session.flush()
    index_topic(session, topic_id)
    session.commit()
