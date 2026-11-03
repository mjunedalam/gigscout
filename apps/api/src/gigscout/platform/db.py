"""Database engine and session factory."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from gigscout.platform.tables import Base

SessionFactory = Callable[[], Session]


def create_db(url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Create tables if needed and return (engine, session factory). SQLite gets WAL + foreign keys."""
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:
        event.listen(engine, "connect", _sqlite_pragmas)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
