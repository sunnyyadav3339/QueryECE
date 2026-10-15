import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import create_token, current_user, hash_password, verify_password
from app.config import JWT_SECRET
from app.db.database import get_db
from app.db.models import Chat, EmailCode, Message, User
from app.mailer import MailError, send_verification_code

router = APIRouter(prefix="/api", tags=["auth"])


CODE_TTL_MINUTES = 10
CODE_MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def _clean_interests(v):
    if v is None:
        return v
    return list(dict.fromkeys(i.strip()[:60] for i in v if i and i.strip()))[:20]


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=128)
    program: str | None = Field(default=None, max_length=80)
    year: str | None = Field(default=None, max_length=40)
    interests: list[str] | None = None

    _interests = field_validator("interests")(classmethod(lambda cls, v: _clean_interests(v)))

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


class VerifyIn(BaseModel):
    email: str
    code: str = Field(min_length=4, max_length=12)


class ResendIn(BaseModel):
    email: str


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    program: str | None = Field(default=None, max_length=80)
    year: str | None = Field(default=None, max_length=40)
    bio: str | None = Field(default=None, max_length=1000)
    interests: list[str] | None = None

    _interests = field_validator("interests")(classmethod(lambda cls, v: _clean_interests(v)))


def user_out(user: User, db: Session) -> dict:
    chats = db.query(Chat).filter_by(user_id=user.id).count()
    questions = (db.query(Message).join(Chat).filter(Chat.user_id == user.id, Message.role == "user").count())
    return {
        "id": user.id, "name": user.name, "email": user.email, "program": user.program,
        "year": user.year, "bio": user.bio, "interests": user.interests or [],
        "created_at": user.created_at, "stats": {"chats": chats, "questions": questions},
    }


def _hash_code(user_id: int, code: str) -> str:
    return hmac.new(JWT_SECRET.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


async def _send_code(user: User, db: Session, *, enforce_cooldown: bool) -> dict:
    """Issue a fresh code (replacing any previous one) and email it."""
    now = datetime.now(timezone.utc)
    pending = user.email_code
    if enforce_cooldown and pending and (now - _aware(pending.sent_at)).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = RESEND_COOLDOWN_SECONDS - int((now - _aware(pending.sent_at)).total_seconds())
        raise HTTPException(429, f"Please wait {wait}s before requesting another code.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    if pending is None:
        pending = EmailCode(user_id=user.id)
        db.add(pending)
    pending.code_hash = _hash_code(user.id, code)
    pending.expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    pending.sent_at, pending.attempts = now, 0
    db.commit()
    try:
        await asyncio.to_thread(send_verification_code, user.email, user.name, code, CODE_TTL_MINUTES)
    except MailError as exc:
        raise HTTPException(502, str(exc))
    return {"verification_required": True, "email": user.email, "resend_after": RESEND_COOLDOWN_SECONDS}


@router.post("/auth/register")
async def register(body: RegisterIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email).first()
    if user and user.email_verified:
        raise HTTPException(409, "An account with this email already exists")
    if user is None:
        user = User(email=body.email, interests=[], email_verified=False)
        db.add(user)
    # Re-registering an unverified email simply restarts sign-up with the new details.
    user.name, user.password_hash = body.name.strip(), hash_password(body.password)
    user.program, user.year = body.program, body.year
    user.interests = body.interests or []
    db.commit()
    return await _send_code(user, db, enforce_cooldown=False)


@router.post("/auth/verify")
def verify(body: VerifyIn, db: Session = Depends(get_db)):
    invalid = HTTPException(400, "That code is incorrect or has expired.")
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or user.email_verified or not user.email_code:
        raise invalid
    pending = user.email_code
    if _aware(pending.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(400, "That code has expired. Request a new one.")
    if pending.attempts >= CODE_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Request a new code.")
    if not hmac.compare_digest(pending.code_hash, _hash_code(user.id, body.code.strip())):
        pending.attempts += 1
        db.commit()
        raise invalid
    user.email_verified = True
    db.delete(pending)
    db.commit()
    return {"token": create_token(user.id), "user": user_out(user, db)}


@router.post("/auth/resend")
async def resend(body: ResendIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or user.email_verified:
        # Same response either way: don't reveal which emails are registered.
        return {"verification_required": True, "email": body.email, "resend_after": RESEND_COOLDOWN_SECONDS}
    return await _send_code(user, db, enforce_cooldown=True)


@router.post("/auth/login")
async def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    if not user.email_verified:
        # Correct password but never verified: finish sign-up with a code
        # (reuse a recent one rather than emailing on every attempt).
        pending = user.email_code
        if pending and (datetime.now(timezone.utc) - _aware(pending.sent_at)).total_seconds() < RESEND_COOLDOWN_SECONDS:
            return {"verification_required": True, "email": user.email, "resend_after": RESEND_COOLDOWN_SECONDS}
        return await _send_code(user, db, enforce_cooldown=False)
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
