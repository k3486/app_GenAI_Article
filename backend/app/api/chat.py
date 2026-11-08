"""壁打ち（話題ごとの Haiku との対話）とメモ。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.db import get_session
from app.schemas.chat import AskIn, ChatState, NoteIn, NoteOut
from app.services import chat as chat_service
from app.services.llm.errors import LlmError

router = APIRouter(tags=["chat"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_llm_factory() -> chat_service.LlmFactory:
    """壁打ち用の Haiku の口を作る関数（テストでは差し替える）。"""
    return chat_service.make_llm


LlmFactoryDep = Annotated[chat_service.LlmFactory, Depends(get_llm_factory)]


@router.get("/topics/{topic_id}/chat")
def get_chat(topic_id: int, session: SessionDep) -> ChatState:
    return chat_service.get_chat(session, topic_id)


@router.post("/topics/{topic_id}/chat")
async def ask(
    topic_id: int, body: AskIn, session: SessionDep, make_llm: LlmFactoryDep
) -> ChatState:
    try:
        return await chat_service.ask(session, make_llm, topic_id, body.question)
    except chat_service.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="話題が見つかりません") from None
    except chat_service.RoundsExceededError:
        raise HTTPException(
            status_code=409,
            detail=f"この話題の質問は{chat_service.ROUNDS_LIMIT}回までです",
        ) from None
    except LlmError as error:
        raise HTTPException(
            status_code=503, detail=f"Haiku を使えません（{type(error).__name__}）"
        ) from None


@router.post("/topics/{topic_id}/notes", status_code=201)
def add_note(topic_id: int, body: NoteIn, session: SessionDep) -> NoteOut:
    try:
        return chat_service.add_note(session, topic_id, body.text, body.chat_message_id)
    except chat_service.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="話題が見つかりません") from None
    except chat_service.NoteNotFoundError:
        raise HTTPException(status_code=404, detail="元の回答が見つかりません") from None


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, session: SessionDep) -> Response:
    try:
        chat_service.delete_note(session, note_id)
    except chat_service.NoteNotFoundError:
        raise HTTPException(status_code=404, detail="メモが見つかりません") from None
    return Response(status_code=204)
