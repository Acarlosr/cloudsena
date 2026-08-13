from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Conversation, Message, Video
from app.db.session import get_db
from app.schemas import AskRequest, ConversationOut, MessageOut, SearchRequest
from app.services import enrichment, rag
from app.services.search import SearchScope, hybrid_search

log = get_logger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/search")
async def search(payload: SearchRequest, db: Session = Depends(get_db)) -> dict:
    """Busca híbrida pura — sem passar por um LLM. Rápida e barata."""
    scope = SearchScope(
        library_id=payload.library_id, video_ids=payload.video_ids, course=payload.course
    )
    hits = await hybrid_search(db, payload.query, scope, top_k=payload.top_k)
    return {
        "query": payload.query,
        "count": len(hits),
        "results": [h.to_dict() for h in hits[: payload.top_k]],
    }


@router.post("/ask")
async def ask(payload: AskRequest, db: Session = Depends(get_db)) -> dict:
    """Pergunta em linguagem natural com resposta ancorada em citações."""
    task = "chat_complex" if payload.deep_reasoning else "chat"

    conversation = None
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(404, "Conversa não encontrada")
    else:
        title = await rag.suggest_title(db, payload.question)
        conversation = Conversation(
            title=title,
            scope_type="video" if payload.video_ids else ("course" if payload.course else "library"),
            scope_id=str(payload.video_ids[0] if payload.video_ids else payload.course or payload.library_id or ""),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(
        Message(conversation_id=conversation.id, role="user", content=payload.question)
    )
    db.commit()

    answer = await rag.answer_question(
        db,
        payload.question,
        library_id=payload.library_id,
        video_ids=payload.video_ids,
        course=payload.course,
        task=task,
        use_rerank=payload.rerank,
    )

    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer.text,
        citations=answer.citations,
        model=answer.model,
        provider=answer.provider,
        tokens_in=answer.tokens_in,
        tokens_out=answer.tokens_out,
        cost_usd=answer.cost_usd,
        latency_ms=answer.latency_ms,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "conversation_id": conversation.id,
        "conversation_title": conversation.title,
        "message_id": message.id,
        **answer.to_dict(),
    }


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(limit: int = 50, db: Session = Depends(get_db)) -> list[ConversationOut]:
    conversations = db.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    ).all()
    out: list[ConversationOut] = []
    for conv in conversations:
        item = ConversationOut.model_validate(conv)
        item.message_count = int(
            db.scalar(
                select(func.count(Message.id)).where(Message.conversation_id == conv.id)
            )
            or 0
        )
        out.append(item)
    return out


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
def get_conversation(conversation_id: int, db: Session = Depends(get_db)) -> list[MessageOut]:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversa não encontrada")
    return [MessageOut.model_validate(m) for m in conversation.messages]


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)) -> None:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversa não encontrada")
    db.delete(conversation)
    db.commit()


@router.get("/videos/{video_id}/suggested-questions")
def suggested_questions(video_id: int, db: Session = Depends(get_db)) -> list[str]:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Vídeo não encontrado")
    if video.summary and video.summary.suggested_questions:
        return video.summary.suggested_questions[:6]
    return []


@router.post("/courses/summary")
async def course_summary(
    library_id: int, course: str, db: Session = Depends(get_db)
) -> dict:
    text = await enrichment.summarize_course(db, library_id, course)
    return {"course": course, "summary": text}
