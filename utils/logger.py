"""
utils/logger.py
================
Structured logging setup for the entire application.

Call setup_logging() once at startup (done in app.py).
Use get_logger(__name__) in every module.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "salad_fleet.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with console + rotating file handlers."""
    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates on hot-reload
    root.handlers.clear()

    # ── Console handler ────────────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console)

    # ── Rotating file handler (10 MB × 5 backups) ─────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Use as: logger = get_logger(__name__)"""
    return logging.getLogger(name)
