from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.config import DB_PATH
from app.db.models import Base

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL lets the API keep reading while the crawler writes.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _add_missing_columns(conn):
    """create_all() never alters existing tables; add new nullable/defaulted columns by hand."""
    for table in Base.metadata.sorted_tables:
        existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table.name}")'))}
        if not existing:
            continue
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
            if col.server_default is not None:
                ddl += f" NOT NULL DEFAULT {col.server_default.arg}"
            conn.execute(text(ddl))


def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _add_missing_columns(conn)
        # Keyword (BM25) index over chunks; complements the vector index.
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "chunk_id UNINDEXED, title, heading, body, tokenize='porter unicode61')"
        ))


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
