"""
services/account_service.py
============================
Manages Salad accounts — loads from config and syncs to DB.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy.orm import Session

from database.connection import get_session
from models.orm import Account
from utils.config import AccountConfig, get_config

logger = logging.getLogger(__name__)


def sync_accounts() -> List[Account]:
    """
    Upsert all accounts from config.json into the database.
    Returns the list of Account ORM objects (with IDs).
    """
    cfg = get_config()
    accounts: List[Account] = []

    with get_session() as session:
        active_names = set()
        for acc_cfg in cfg.accounts:
            account = _upsert_account(session, acc_cfg)
            accounts.append(account)
            active_names.add(acc_cfg.name)

        # Delete orphaned accounts
        if active_names:
            orphaned = session.query(Account).filter(Account.name.notin_(active_names)).all()
        else:
            orphaned = session.query(Account).all()
            
        for acc in orphaned:
            session.delete(acc)
        
        session.commit()

    logger.info("Synced %d account(s) to database (deleted %d orphaned)", len(accounts), len(orphaned))
    return accounts


def _upsert_account(session: Session, acc_cfg: AccountConfig) -> Account:
    """Insert or update a single account row."""
    account = session.query(Account).filter_by(name=acc_cfg.name).first()
    if account is None:
        account = Account(name=acc_cfg.name)
        session.add(account)
        session.flush()
        logger.debug("Created account: %s", acc_cfg.name)
    else:
        logger.debug("Account already exists: %s", acc_cfg.name)
    return account


def get_account_map() -> Dict[str, int]:
    """Return {account_name: account_db_id} for all accounts in DB."""
    with get_session() as session:
        rows = session.query(Account.name, Account.id).all()
        return {name: aid for name, aid in rows}
