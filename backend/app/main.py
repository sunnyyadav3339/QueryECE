import logging
import threading
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, CRAWL_INTERVAL_HOURS, ENABLE_SCHEDULER, GROQ_API_KEY
from app.db.database import SessionLocal, init_db
from app.db.models import Page
from app.ingest.pipeline import run_pipeline
from app.routers import auth, chats, data, outreach

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("queryece")


def _safe_crawl():
    try:
        run_pipeline()
    except Exception:
        log.exception("scheduled crawl failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY is not set: chat will return an error until it is configured.")
    scheduler = None
    if ENABLE_SCHEDULER:
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(_safe_crawl, "interval", hours=CRAWL_INTERVAL_HOURS, id="crawl",
                          max_instances=1, coalesce=True)
        scheduler.start()
        with SessionLocal() as db:
            empty = db.query(Page).count() == 0
        if empty:  # first boot: build the index in the background
            log.info("index is empty; starting initial crawl")
            threading.Thread(target=_safe_crawl, daemon=True).start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="QueryECE API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(data.router)
app.include_router(outreach.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "QueryECE API"}
