"""Database plumbing: the engine, sessions, and the safety switches for SQLite.

Three words you will meet:
    engine   = the connection to the database file
    session  = one conversation with the database (add rows, read rows, commit)
    commit   = "save everything I did in this session"
"""

import sqlite3
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import Base


@event.listens_for(Engine, "connect")
def _turn_on_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless we switch them on for EVERY new connection.

    With this switch on, a medicine cannot point to an elder who does not exist.
    It applies to connections opened by this app. Another program that opens the same
    file (a database viewer, for example) has to switch foreign keys on for itself.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_engine(database_url: str) -> Engine:
    """Create the connection to a SQLite database (tests pass "sqlite://" for a throw-away one)."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Dawai Saathi uses SQLite only")

    # FastAPI handles requests on several threads, so SQLite must allow that.
    options = {"connect_args": {"check_same_thread": False}}

    if url.database in (None, "", ":memory:"):
        # An in-memory database vanishes when its connection closes, so keep ONE shared connection.
        return create_engine(database_url, poolclass=StaticPool, **options)

    # A database file: make sure its folder exists (SQLite will not create folders).
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, **options)


# The real engine and session factory used by the running app
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def init_db(target_engine: Engine = engine) -> None:
    """Create every table that does not exist yet. Safe to run as many times as you like."""
    Base.metadata.create_all(target_engine)


def get_db() -> Iterator[Session]:
    """Give one request its own database session, and always close it afterwards.

    Routes ask for it with:  db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
