import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.agent import respond
from app.auth import current_user
from app.db.database import get_db
from app.db.models import Chat, Message, User

router = APIRouter(prefix="/api/chats", tags=["chats"])


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def _chat_out(chat: Chat) -> dict:
    return {"id": chat.id, "title": chat.title, "created_at": chat.created_at, "updated_at": chat.updated_at}


def _own_chat(chat_id: str, user: User, db: Session) -> Chat:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(404, "Chat not found")
    return chat


@router.get("")
def list_chats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    chats = db.query(Chat).filter_by(user_id=user.id).order_by(Chat.updated_at.desc()).all()
    return [_chat_out(c) for c in chats]


@router.post("")
def create_chat(user: User = Depends(current_user), db: Session = Depends(get_db)):
    chat = Chat(id=uuid.uuid4().hex, user_id=user.id, title="New chat")
    db.add(chat)
    db.commit()
    return _chat_out(chat)


@router.get("/{chat_id}")
def get_chat(chat_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    chat = _own_chat(chat_id, user, db)
    messages = db.query(Message).filter_by(chat_id=chat.id).order_by(Message.id).all()
    return {
        **_chat_out(chat),
        "messages": [{"id": m.id, "role": m.role, "content": m.content, "sources": m.sources or [],
                      "created_at": m.created_at} for m in messages],
    }


@router.patch("/{chat_id}")
def rename_chat(chat_id: str, body: RenameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    chat = _own_chat(chat_id, user, db)
    chat.title = body.title.strip()
    db.commit()
    return _chat_out(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_chat(chat_id, user, db))
    db.commit()
    return {"ok": True}


@router.post("/{chat_id}/messages")
async def send_message(chat_id: str, body: MessageIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Server-sent events stream: {type: status|token|sources|done|error, ...}."""
    _own_chat(chat_id, user, db)
    user_id = user.id

    async def events():
        async for event in respond(chat_id, user_id, body.content.strip()):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
