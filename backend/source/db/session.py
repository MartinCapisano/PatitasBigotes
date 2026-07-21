from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from source.db.config import get_database_url

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_transactional() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def read_session_scope(db: Session | None):
    owns_session = db is None
    session = db or SessionLocal()
    try:
        yield session, owns_session
    finally:
        if owns_session:
            session.close()


@contextmanager
def write_session_scope(db: Session):
    if db is None:
        raise RuntimeError("db session is required for mutating operations")
    yield db, False
