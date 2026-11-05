"""Database engine and session factory."""

import secrets
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, event, insert, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from gigscout.platform.tables import DEFAULT_WORKSPACE, Base, utcnow

SessionFactory = Callable[[], Session]

# Columns added after the first release. create_all only creates missing tables, so older databases get these
# added in place. Each needs a default that is valid for existing rows.
ADDED_COLUMNS = {
    ("pitch_settings", "research_first"): "BOOLEAN DEFAULT 0",
    ("replies", "verified"): "BOOLEAN DEFAULT 1",
    ("outreach", "message_id"): "VARCHAR(255)",
    ("outreach", "in_reply_to"): "VARCHAR(255)",
    ("outreach", "evidence"): "JSON",
    ("outreach", "claims"): "JSON",
    ("lead_states", "deal_value_usd"): "FLOAT",
    ("runs", "activity"): "JSON DEFAULT '[]'",
    ("connectors", "lead_kind"): "VARCHAR(16) DEFAULT 'project'",
    ("outreach", "sent_by"): "VARCHAR(254)",
    ("lead_states", "base_score"): "FLOAT",
    ("lead_states", "learned"): "FLOAT DEFAULT 0",
    ("lead_states", "learned_note"): "TEXT DEFAULT ''",
    # workspaces: everything that existed before belongs to the first one
    ("agency_profiles", "workspace_id"): "INTEGER NOT NULL DEFAULT 1",
    ("runs", "workspace_id"): "INTEGER NOT NULL DEFAULT 1",
    ("schedules", "workspace_id"): "INTEGER NOT NULL DEFAULT 1",
    ("outreach", "workspace_id"): "INTEGER NOT NULL DEFAULT 1",
    ("audit_logs", "workspace_id"): "INTEGER DEFAULT 1",
    ("digest_settings", "workspace_id"): "INTEGER NOT NULL DEFAULT 1",
    ("users", "home_workspace_id"): "INTEGER",
    ("lead_states", "assigned_to"): "INTEGER",
    ("lead_states", "follow_up_on"): "DATE",
    ("lead_states", "score_parts"): "JSON",
    ("outreach", "kind"): "VARCHAR(12) DEFAULT 'first'",
    ("outreach", "run_id"): "VARCHAR(36)",
    ("outreach", "reviewed_by"): "VARCHAR(254)",
    ("outreach", "reviewed_at"): "TIMESTAMP WITH TIME ZONE",
    ("outreach", "review_note"): "TEXT DEFAULT ''",
}
# Tables whose key changed to include the workspace: SQLite cannot alter a key, so they are rebuilt (rows kept).
REKEYED = ("lead_states", "crm_links", "integration_tokens", "connectors", "source_toggles")


def create_db(url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Create tables if needed and return (engine, session factory). SQLite gets WAL + foreign keys."""
    is_sqlite = url.startswith("sqlite")
    if is_sqlite and url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:
        event.listen(engine, "connect", _sqlite_pragmas)
    Base.metadata.create_all(engine)
    _ensure_default_workspace(engine)
    _add_missing_columns(engine)
    _rekey_for_workspaces(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for (table, column), ddl in ADDED_COLUMNS.items():
            if inspector.has_table(table) and column not in {c["name"] for c in inspector.get_columns(table)}:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _ensure_default_workspace(engine: Engine) -> None:
    """Workspace 1 always exists. When it is first created, every existing user joins it (admins as owners)."""
    with engine.begin() as conn:
        if conn.scalar(text("SELECT COUNT(*) FROM workspaces")):
            return
        name = conn.scalar(text("SELECT name FROM agency_profiles ORDER BY id LIMIT 1")) or "My company"
        conn.execute(insert(Base.metadata.tables["workspaces"]).values(
            id=DEFAULT_WORKSPACE, name=name, form_key=secrets.token_urlsafe(24), created_at=utcnow()))
        if engine.dialect.name == "postgresql":  # an explicit id leaves the sequence behind; move it past 1
            conn.exec_driver_sql("SELECT setval(pg_get_serial_sequence('workspaces', 'id'), "
                                 "(SELECT MAX(id) FROM workspaces))")
        for user_id, role in conn.execute(text("SELECT id, role FROM users")):
            conn.execute(insert(Base.metadata.tables["memberships"]).values(
                user_id=user_id, workspace_id=DEFAULT_WORKSPACE, role="owner" if role == "admin" else "member",
                created_at=utcnow()))


def _rekey_for_workspaces(engine: Engine) -> None:
    inspector = inspect(engine)
    for name in REKEYED:
        if not inspector.has_table(name) or "workspace_id" in {c["name"] for c in inspector.get_columns(name)}:
            continue
        table = Base.metadata.tables[name]
        old_columns = {c["name"] for c in inspector.get_columns(name)}
        shared = ", ".join(c.name for c in table.columns if c.name in old_columns)
        with engine.begin() as conn:
            for index in inspector.get_indexes(name):  # names would clash with the new table's indexes
                conn.exec_driver_sql(f"DROP INDEX {index['name']}")
            conn.exec_driver_sql(f"ALTER TABLE {name} RENAME TO {name}__old")
            table.create(conn)
            conn.exec_driver_sql(
                f"INSERT INTO {name} ({shared}, workspace_id) SELECT {shared}, {DEFAULT_WORKSPACE} FROM {name}__old")
            conn.exec_driver_sql(f"DROP TABLE {name}__old")


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
