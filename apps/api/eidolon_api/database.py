from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight schema drift handling (no full migrations in this PoC).
    # We only add additive columns; destructive changes are intentionally avoided.
    inspector = inspect(engine)
    try:
        brand_cols = {col["name"] for col in inspector.get_columns("brands")}
    except Exception:
        brand_cols = set()

    if "entity_key" not in brand_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE brands ADD COLUMN entity_key VARCHAR(140)"))
            conn.execute(text("UPDATE brands SET entity_key = '' WHERE entity_key IS NULL"))
