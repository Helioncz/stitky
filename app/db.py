"""SQLAlchemy engine a session. Lokálně SQLite, na serveru Postgres (Supabase)."""
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        # WAL: čtení neblokuje zápis (víc uživatelů naráz), busy_timeout místo okamžité chyby „database is locked“
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401 – registrace tabulek

    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Jednoduchá migrace: create_all nepřidá nové sloupce do existující tabulky, tak je doplníme.

    Jen přidávání nullable sloupců – přejmenování/mazání je potřeba řešit ručně.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ddl}'))
                    if (table.name, col.name) == ("revisions", "locked_at"):
                        # revize vydané před zavedením zamykání byly zamčené rovnou při vydání
                        conn.execute(text("UPDATE revisions SET locked_at = issued_at"))
                    if (table.name, col.name) == ("revisions", "locked_by_id"):
                        conn.execute(text("UPDATE revisions SET locked_by_id = issued_by_id"))
