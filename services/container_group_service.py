"""
services/container_group_service.py
=====================================
Fetches container groups from Salad API and persists them.

Endpoint:
    GET /organizations/{org_name}/containers
    Header: Salad-Api-Key: <api_key>
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from api.salad_client import SaladClient, SaladApiError
from database.connection import get_session
from models.orm import Account, ContainerGroup, Organization
from models.schemas import SaladContainerGroup, SaladContainerGroupList
from utils.config import get_config
from utils.client_cache import get_salad_client

logger = logging.getLogger(__name__)


def sync_container_groups() -> int:
    """
    For every (account, org) pair in config + DB, fetch container groups in parallel.
    All HTTP calls are fired concurrently; DB writes are batched into one session.
    Returns the total number of groups upserted.
    """
    cfg = get_config()

    # Build list of (client, org_name_str, account_name) to fetch in parallel
    tasks: List[Tuple[SaladClient, str, str]] = []
    with get_session() as session:
        for acc_cfg in cfg.accounts:
            account = session.query(Account).filter_by(name=acc_cfg.name).first()
            if account is None:
                continue
            try:
                client = get_salad_client(acc_cfg.name)
            except ValueError:
                continue
            for org_name in getattr(acc_cfg, "organizations", []):
                tasks.append((client, org_name, acc_cfg.name))

    if not tasks:
        return 0

    # Fire all HTTP requests concurrently
    raw_results: List[Tuple[str, str, list]] = []  # (org_name, account_name, items)
    with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as pool:
        futures = {
            pool.submit(_fetch_groups, client, org_name, account_name): (org_name, account_name)
            for client, org_name, account_name in tasks
        }
        for future in as_completed(futures):
            org_name, account_name = futures[future]
            try:
                items = future.result()
                raw_results.append((org_name, account_name, items))
            except Exception as exc:
                logger.error("[%s/%s] Container group fetch failed: %s", account_name, org_name, exc)

    # Write all results to DB in a single session
    total = 0
    with get_session() as session:
        for org_name, account_name, items in raw_results:
            # Find account and org in DB
            account = session.query(Account).filter_by(name=account_name).first()
            if account is None:
                continue
            org = session.query(Organization).filter_by(account_id=account.id, org_name=org_name).first()
            if org is None:
                logger.warning("Org %r not in DB — skipping", org_name)
                continue

            active_group_ids = set()
            for item in items:
                group = _upsert_group(session, org, item)
                active_group_ids.add(group.id)
                total += 1

            # Remove orphaned groups
            if active_group_ids:
                orphaned = session.query(ContainerGroup).filter(
                    ContainerGroup.organization_id == org.id,
                    ContainerGroup.id.notin_(active_group_ids)
                ).all()
            else:
                orphaned = session.query(ContainerGroup).filter_by(organization_id=org.id).all()
            for g in orphaned:
                session.delete(g)

    logger.info("Synced %d container group(s) in total (parallel)", total)
    return total


def _fetch_groups(client: SaladClient, org_name_str: str, account_name: str) -> list:
    """Fetch container groups for one org. Called in a thread pool."""
    if "/" in org_name_str:
        actual_org, actual_proj = org_name_str.split("/", 1)
    else:
        actual_org = org_name_str
        actual_proj = ""
    try:
        raw = client.list_container_groups(actual_org, actual_proj)
        parsed = SaladContainerGroupList(**raw) if isinstance(raw, dict) else SaladContainerGroupList()
        logger.debug("[%s/%s] Fetched %d group(s)", account_name, org_name_str, len(parsed.items))
        return parsed.items
    except SaladApiError as exc:
        logger.error("[%s/%s] Failed to fetch container groups: %s", account_name, org_name_str, exc)
        return []


def _upsert_group(session, org: Organization, item: SaladContainerGroup) -> ContainerGroup:
    group = (
        session.query(ContainerGroup)
        .filter_by(organization_id=org.id, group_name=item.name)
        .first()
    )
    if group is None:
        group = ContainerGroup(
            organization_id=org.id,
            group_name=item.name,
            display_name=item.display_name,
            status=item.status,
            replicas=item.replicas,
        )
        session.add(group)
    else:
        group.display_name = item.display_name
        group.status = item.status
        group.replicas = item.replicas
    session.flush()
    return group
