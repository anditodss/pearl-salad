"""
database/migrations.py
=======================
Schema management: create and (optionally) drop all tables.
Also handles additive column migrations for existing databases using
SQLite-compatible PRAGMA checks (since SQLite does not support
ALTER TABLE ... ADD COLUMN IF NOT EXISTS).

Call init_db() at application startup.
"""
from __future__ import annotations

import logging

from database.connection import get_engine
from models.orm import Base

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create all tables if they don't already exist, then apply column migrations."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database schema initialised (tables: %s)", list(Base.metadata.tables.keys()))

    # Apply any additive migrations for existing databases
    _apply_column_migrations(engine)


def _apply_column_migrations(engine) -> None:
    """
    Add new columns to existing tables without destroying data.
    SQLite does not support IF NOT EXISTS for ADD COLUMN, so we inspect
    the current schema first via PRAGMA table_info.
    """
    migrations = [
        # (table_name, column_name, column_definition)
        ("instances",     "benchmark_hashrate",    "REAL"),
        ("instances",     "needs_reallocation",    "INTEGER NOT NULL DEFAULT 0"),
        ("instances",     "failure_count",         "INTEGER NOT NULL DEFAULT 0"),
        ("instances",     "first_failure",         "DATETIME"),
        ("instances",     "last_failure",          "DATETIME"),
        ("instance_logs", "parsed_hashrate_ths",   "REAL"),
    ]

    with engine.connect() as conn:
        for table, col, col_def in migrations:
            # Check existing columns
            result = conn.execute(
                # pragma_table_info is available in SQLite 3.16+
                __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
            )
            existing_cols = {row[1] for row in result}  # row[1] = column name

            if col not in existing_cols:
                try:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
                        )
                    )
                    conn.commit()
                    logger.info("Migration: added column %s.%s (%s)", table, col, col_def)
                except Exception as exc:
                    logger.warning("Migration: could not add %s.%s — %s", table, col, exc)


def drop_all() -> None:
    """Drop all tables — USE WITH CAUTION (development only)."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    logger.warning("All database tables dropped.")
