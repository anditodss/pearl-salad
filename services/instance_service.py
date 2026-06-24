"""
services/instance_service.py
==============================
Fetches instances for every container group and persists them.

All API calls are fired concurrently with ThreadPoolExecutor — one thread per
container group. DB writes are batched into a single session after all fetches
complete. This turns N sequential HTTP calls into ~1 round-trip time.

Endpoint:
    GET /organizations/{org_name}/containers/{group_name}/instances
    Header: Salad-Api-Key: <api_key>
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from api.salad_client import SaladClient, SaladApiError
from database.connection import get_session
from models.orm import Account, ContainerGroup, Instance, Organization
from models.schemas import SaladInstance, SaladInstanceList
from utils.client_cache import get_salad_client

logger = logging.getLogger(__name__)


import asyncio
import aiohttp
from api.async_salad_client import AsyncSaladClient

def sync_instances() -> int:
    """
    Fetch instances for every container group — all in parallel via aiohttp.
    Returns total instances upserted.
    """
    tasks: List[Tuple[str, str, str, str, int, str]] = []
    with get_session() as session:
        groups: List[ContainerGroup] = session.query(ContainerGroup).all()
        for group in groups:
            # Zero-Waste: Skip groups that are stopped or have 0 replicas
            if group.status == "stopped" or group.replicas == 0:
                continue

            org: Organization = session.query(Organization).get(group.organization_id)
            if org is None:
                continue
            account: Account = session.query(Account).get(org.account_id)
            if account is None:
                continue
            try:
                # Validate API key exists by checking the sync cache
                _ = get_salad_client(account.name)
            except ValueError:
                continue
            
            # (api_key, org_name_str, account_name, group_id, group_name)
            tasks.append((account.name, org.org_name, group.id, group.group_name))

    if not tasks:
        return 0

    fetch_results = asyncio.run(_async_fetch_all_instances(tasks))

    total = 0
    with get_session() as session:
        for group_id, account_name, org_name, group_name, items in fetch_results:
            group = session.query(ContainerGroup).get(group_id)
            if group is None:
                continue

            active_instance_ids = set()
            for item in items:
                instance = _upsert_instance(session, group, item)
                active_instance_ids.add(instance.id)
                total += 1

            if active_instance_ids:
                orphaned = session.query(Instance).filter(
                    Instance.container_group_id == group.id,
                    Instance.id.notin_(active_instance_ids)
                ).all()
            else:
                orphaned = session.query(Instance).filter_by(container_group_id=group.id).all()

            for inst in orphaned:
                session.delete(inst)

            logger.debug(
                "[%s/%s/%s] Upserted %d instance(s), deleted %d orphaned",
                account_name, org_name, group_name, len(items), len(orphaned),
            )

    logger.info("Synced %d instance(s) in total (asyncio)", total)
    return total

async def _async_fetch_all_instances(tasks_info):
    from utils.config import get_config
    cfg = get_config()
    accounts = {acc.name: acc.api_key for acc in cfg.accounts}
    # Use a TCPConnector and ThreadedResolver to limit concurrent connections to prevent DNS exhaustion on Windows
    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, limit=15)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Create an AsyncSaladClient per account
        clients = {}
        for acc_name, api_key in accounts.items():
            clients[acc_name] = AsyncSaladClient(api_key, acc_name)
            
        cors = []
        for account_name, org_name_str, group_id, group_name in tasks_info:
            if account_name not in clients:
                continue
            cors.append(
                _async_fetch_single_group(
                    clients[account_name], session, org_name_str, account_name, group_id, group_name
                )
            )
        results = await asyncio.gather(*cors, return_exceptions=True)
        
        valid_results = []
        for res in results:
            if isinstance(res, Exception):
                logger.error("Async fetch instances error: %s", res)
            elif res is not None:
                valid_results.append(res)
        return valid_results

async def _async_fetch_single_group(
    client: AsyncSaladClient,
    session: aiohttp.ClientSession,
    org_name_str: str,
    account_name: str,
    group_id: int,
    group_name: str,
):
    if "/" in org_name_str:
        actual_org, actual_proj = org_name_str.split("/", 1)
    else:
        actual_org = org_name_str
        actual_proj = ""
        
    from api.salad_client import SaladApiError
    from models.schemas import SaladInstanceList
    
    try:
        raw = await client.list_instances(session, actual_org, actual_proj, group_name)
        parsed = SaladInstanceList(**raw) if isinstance(raw, dict) else SaladInstanceList()
        return (group_id, account_name, org_name_str, group_name, parsed.instances)
    except SaladApiError as exc:
        logger.error("[%s/%s/%s] Failed to fetch instances: %s", account_name, org_name_str, group_name, exc)
        return None
    except Exception as exc:
        logger.error("[%s/%s/%s] Unexpected error fetching instances: %s", account_name, org_name_str, group_name, exc)
        return None


def _upsert_instance(session: Session, group: ContainerGroup, item: SaladInstance) -> Instance:
    instance = (
        session.query(Instance)
        .filter_by(container_group_id=group.id, instance_id=item.instance_id)
        .first()
    )
    state_str: Optional[str] = item.state

    if instance is None:
        instance = Instance(
            container_group_id=group.id,
            instance_id=item.instance_id,
            machine_id=item.machine_id,
            state=state_str,
            api_create_time=getattr(item, "create_time", None) or getattr(item, "update_time", None),
            api_update_time=getattr(item, "update_time", None),
        )
        session.add(instance)
    else:
        instance.machine_id = item.machine_id
        instance.state = state_str
        instance.api_create_time = getattr(item, "create_time", None) or getattr(item, "update_time", None)
        instance.api_update_time = getattr(item, "update_time", None)

    session.flush()
    return instance
