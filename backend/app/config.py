"""Central settings, read once from the environment (backend/.env locally)."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR.parent / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "queryece.db"
CHROMA_DIR = DATA_DIR / "chroma"
MODEL_CACHE_DIR = DATA_DIR / "models"

# --- LLM (Groq) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Separate per-model quota on Groq: used for summaries and as a 429 fallback.
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")

# --- Embeddings ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# --- Crawler ---
CRAWL_INTERVAL_HOURS = float(os.getenv("CRAWL_INTERVAL_HOURS", "168"))  # weekly
CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "600"))
CRAWL_DELAY_SECONDS = float(os.getenv("CRAWL_DELAY_SECONDS", "0.3"))
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"

# --- Auth ---
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
# Outgoing mail for sign-up codes (e.g. Gmail: smtp.gmail.com, port 587, an App Password).
# If SMTP_HOST is empty, codes are written to the server log instead (local demo mode).
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
if "gmail" in SMTP_HOST:
    # Google shows app passwords in groups of four ("abcd efgh ..."); the spaces aren't part of it.
    SMTP_PASSWORD = SMTP_PASSWORD.replace(" ", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]


def _jwt_secret() -> str:
    """Use JWT_SECRET if set, else a random secret persisted next to the DB."""
    if os.getenv("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    secret_file = DATA_DIR / ".jwt_secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(48))
    return secret_file.read_text().strip()


JWT_SECRET = _jwt_secret()
