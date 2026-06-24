"""
database/connection.py
=======================
SQLAlchemy engine, session factory, and Base.

Usage:
    from database.connection import get_session, engine

    with get_session() as session:
        session.add(some_orm_object)
        session.commit()
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from utils.config import get_config

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _get_db_url() -> str:
    cfg = get_config()
    return f"sqlite:///{cfg.database.path}"


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine (created on first call)."""
    global _engine
    if _engine is None:
        url = _get_db_url()
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        # Enable WAL mode for better concurrency with SQLite
        @event.listens_for(_engine, "connect")
        def _set_wal(dbapi_conn, _conn_record):  # type: ignore[misc]
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA cache_size=-65536")   # 64 MB page cache
            dbapi_conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, faster than FULL
            dbapi_conn.execute("PRAGMA temp_store=MEMORY")   # keep temp tables in RAM
            dbapi_conn.execute("PRAGMA mmap_size=268435456") # 256 MB memory-mapped I/O
            dbapi_conn.execute("PRAGMA busy_timeout=5000")   # wait up to 5s on lock instead of failing

        logger.info("Database engine created: %s", url)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that yields a database session and handles commit/rollback."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
