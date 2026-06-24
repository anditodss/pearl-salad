"""
utils/config.py
================
Config loader — reads config.json and returns a validated AppConfig.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ─── Pydantic Models ──────────────────────────────────────────────────────────


class AccountConfig(BaseModel):
    name: str
    api_key: str
    organizations: List[str] = Field(
        default_factory=list,
        description="List of org names to monitor under this account",
    )


class MonitoringConfig(BaseModel):
    check_interval_minutes: float = 1.0           # 60 seconds between monitor cycles
    sync_interval_minutes: float = 0.5            # 30 seconds between sync/log-collection cycles
    efficiency_threshold: float = 0.85
    consecutive_failures: int = 2                  # bad checks needed before reallocation
    log_lines_per_instance: int = 100
    dry_run: bool = False
    remediation_strategy: str = "reallocate"      # Can be: reallocate, recreate, restart, auto
    log_retention_days: int = 30                  # auto-purge logs older than N days

    @field_validator("efficiency_threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError("efficiency_threshold must be between 0 and 1")
        return v


class HashrateConfig(BaseModel):
    regex_pattern: Optional[str] = None
    unit: str = "H/s"


class DatabaseConfig(BaseModel):
    path: str = "database.db"


class ApiConfig(BaseModel):
    base_url: str = "https://api.salad.com/api/public"
    timeout_seconds: int = 30
    max_retries: int = 3


class UiConfig(BaseModel):
    page_title: str = "Salad Fleet Manager"
    refresh_interval_seconds: int = 30


class AppConfig(BaseModel):
    accounts: List[AccountConfig] = Field(default_factory=list)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    hashrate: HashrateConfig = Field(default_factory=HashrateConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    ui: UiConfig = Field(default_factory=UiConfig)


# ─── Loader ───────────────────────────────────────────────────────────────────

_config: Optional[AppConfig] = None
_CONFIG_PATH = Path("config.json")


def load_config(path: str | Path = _CONFIG_PATH) -> AppConfig:
    """Load and validate config.json and env variables. Raises FileNotFoundError if config.json is missing."""
    global _config
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"config.json not found at '{p.resolve()}'. "
            "Copy config.json.example → config.json and set your configuration."
        )
    with p.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    _config = AppConfig(**raw)

    # Load from .env if present
    load_dotenv()

    env_accounts = []

    # 1. Single account configuration
    single_api_key = os.getenv("SALAD_API_KEY")
    if single_api_key:
        name = os.getenv("SALAD_ACCOUNT_NAME", "default-account")
        orgs_raw = os.getenv("SALAD_PROJECTS", "")
        orgs = [o.strip() for o in orgs_raw.split(",") if o.strip()]
        env_accounts.append(
            AccountConfig(name=name, api_key=single_api_key, organizations=orgs)
        )

    # 2. Multi-account configuration
    i = 1
    while True:
        api_key = os.getenv(f"SALAD_ACCOUNT_{i}_API_KEY")
        name_key = f"SALAD_ACCOUNT_{i}_NAME"
        orgs_key = f"SALAD_ACCOUNT_{i}_PROJECTS"
        
        # If we don't find the api key, check if any other keys exist for index i to see if we should warn/continue
        if not api_key:
            if os.getenv(name_key) or os.getenv(orgs_key):
                logger.warning(
                    "Found %s but corresponding %s is missing. Skipping account %d.",
                    name_key if os.getenv(name_key) else orgs_key,
                    f"SALAD_ACCOUNT_{i}_API_KEY",
                    i
                )
                i += 1
                continue
            else:
                # No more account environment variables found
                break

        name = os.getenv(name_key, f"account-{i}")
        orgs_raw = os.getenv(orgs_key, "")
        orgs = [o.strip() for o in orgs_raw.split(",") if o.strip()]
        env_accounts.append(
            AccountConfig(name=name, api_key=api_key, organizations=orgs)
        )
        i += 1

    if env_accounts:
        _config.accounts = env_accounts
        logger.info("Loaded %d accounts from environment variables (.env)", len(env_accounts))

    logger.info(
        "Config loaded — accounts=%d interval=%.2fm threshold=%.0f%%",
        len(_config.accounts),
        _config.monitoring.check_interval_minutes,
        _config.monitoring.efficiency_threshold * 100,
    )
    return _config


def get_config() -> AppConfig:
    """Return the cached config (loads on first call)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """Force a reload from disk."""
    global _config
    _config = None
    return get_config()
