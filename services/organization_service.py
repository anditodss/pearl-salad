"""
services/organization_service.py
==================================
NOTE: The Salad API does NOT expose a "list organizations" endpoint.
Organizations must be provided in config.json under each account.
This service reads org names from config and syncs them to the database.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from database.connection import get_session
from models.orm import Account, Organization
from utils.config import AccountConfig, get_config

logger = logging.getLogger(__name__)


def sync_organizations() -> List[Tuple[str, str]]:
    """
    Upsert all organizations from config.json into the database.

    Config format expected per account:
        { "name": "my-account", "api_key": "...", "organizations": ["org-1", "org-2"] }

    Returns a list of (account_name, org_name) tuples.
    """
    cfg = get_config()
    result: List[Tuple[str, str]] = []

    with get_session() as session:
        active_org_ids = set()
        
        for acc_cfg in cfg.accounts:
            account = session.query(Account).filter_by(name=acc_cfg.name).first()
            if account is None:
                logger.warning("Account %r not found in DB — run sync_accounts() first", acc_cfg.name)
                continue

            org_names: List[str] = getattr(acc_cfg, "organizations", [])
            if not org_names:
                logger.warning(
                    "Account %r has no organizations listed in config.json — "
                    "add an 'organizations' list to each account entry.",
                    acc_cfg.name,
                )
                continue

            for org_name in org_names:
                org = _upsert_org(session, account, org_name)
                active_org_ids.add(org.id)
                result.append((acc_cfg.name, org_name))

        # Delete orphaned organizations
        if active_org_ids:
            orphaned = session.query(Organization).filter(Organization.id.notin_(active_org_ids)).all()
        else:
            orphaned = session.query(Organization).all()
            
        for org in orphaned:
            session.delete(org)
            
        session.commit()

    logger.info("Synced %d organization(s) across all accounts (deleted %d orphaned)", len(result), len(orphaned))
    return result


def _upsert_org(session: Session, account: Account, org_name: str) -> Organization:
    org = (
        session.query(Organization)
        .filter_by(account_id=account.id, org_name=org_name)
        .first()
    )
    if org is None:
        org = Organization(account_id=account.id, org_name=org_name)
        session.add(org)
        session.flush()
        logger.debug("Created organization: account=%s org=%s", account.name, org_name)
    return org


def get_org_map() -> Dict[Tuple[int, str], int]:
    """Return {(account_id, org_name): org_db_id} for all orgs in DB."""
    with get_session() as session:
        rows = session.query(Organization.account_id, Organization.org_name, Organization.id).all()
        return {(acc_id, name): oid for acc_id, name, oid in rows}
