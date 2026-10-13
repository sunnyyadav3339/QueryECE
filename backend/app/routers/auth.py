from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import create_token, current_user, hash_password, verify_password
from app.db.database import get_db
from app.db.models import Chat, Message, User

router = APIRouter(prefix="/api", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    program: str | None = Field(default=None, max_length=80)
    year: str | None = Field(default=None, max_length=40)
    bio: str | None = Field(default=None, max_length=1000)
    interests: list[str] | None = None

    @field_validator("interests")
    @classmethod
    def _interests(cls, v):
        if v is None:
            return v
        cleaned = list(dict.fromkeys(i.strip()[:60] for i in v if i and i.strip()))
        return cleaned[:20]


def user_out(user: User, db: Session) -> dict:
    chats = db.query(Chat).filter_by(user_id=user.id).count()
    questions = (db.query(Message).join(Chat).filter(Chat.user_id == user.id, Message.role == "user").count())
    return {
        "id": user.id, "name": user.name, "email": user.email, "program": user.program,
        "year": user.year, "bio": user.bio, "interests": user.interests or [],
        "created_at": user.created_at, "stats": {"chats": chats, "questions": questions},
    }


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=body.name.strip(), email=body.email, password_hash=hash_password(body.password), interests=[])
    db.add(user)
    db.commit()
    return {"token": create_token(user.id), "user": user_out(user, db)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(user.id), "user": user_out(user, db)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(user, db)


@router.put("/me")
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and not (value or "").strip():
            continue
        setattr(user, field, value)
    db.commit()
    return user_out(user, db)
