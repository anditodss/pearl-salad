"""
services/log_collection_service.py
=====================================
Polls Salad API for container log entries and stores them in SQLite.

Official Endpoint (confirmed):
    POST /organizations/{org_name}/log-entries
    — Returns up to 500 log entries per call
    — Supports filtering by container_group, machine_id, time range
    — Logs retained for up to 90 days on Salad's side

Abstraction Layer:
    This module exposes a LogSource abstract base class.
    Swap out SaladApiLogSource with any other implementation (e.g.,
    FileLogSource for local files, DatadogLogSource, etc.) without
    changing the rest of the application.
"""
from __future__ import annotations

import datetime
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.salad_client import SaladApiError, SaladClient
from database.connection import get_session
from models.orm import Account, ContainerGroup, Instance, InstanceLog, Organization
from utils.config import get_config
from utils.client_cache import get_salad_client
from utils.hashrate_parser import HashrateParser, ParsedMetrics

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Log Entry DTO
# ─────────────────────────────────────────────────────────────────────────────

class RawLogEntry:
    """Normalised log entry returned by any LogSource."""

    __slots__ = ("timestamp", "message", "machine_id", "container_group")

    def __init__(
        self,
        timestamp: datetime.datetime,
        message: str,
        machine_id: Optional[str] = None,
        container_group: Optional[str] = None,
    ) -> None:
        self.timestamp = timestamp
        self.message = message
        self.machine_id = machine_id
        self.container_group = container_group

    def __repr__(self) -> str:
        return f"<RawLogEntry ts={self.timestamp} machine={self.machine_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Log Source (Abstraction Layer)
# ─────────────────────────────────────────────────────────────────────────────

class LogSource(ABC):
    """
    Abstract base class for log sources.
    Implement this to swap in alternative log backends (Datadog, file, etc.)
    without changing any other code in the application.
    """

    @abstractmethod
    def fetch_logs(
        self,
        org_name: str,
        container_group: Optional[str] = None,
        machine_id: Optional[str] = None,
        since: Optional[datetime.datetime] = None,
        query: Optional[str] = None,
    ) -> List[RawLogEntry]:
        """
        Fetch raw log entries.

        Args:
            org_name:        Organization name.
            container_group: Optional filter by container group name.
            machine_id:      Optional filter by machine/instance ID.
            since:           Only return logs after this UTC datetime.
            query:           Optional query string to filter logs natively.

        Returns:
            List of RawLogEntry objects, sorted by timestamp ascending.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Salad API Log Source (Production Implementation)
# ─────────────────────────────────────────────────────────────────────────────

class SaladApiLogSource(LogSource):
    """
    Fetches logs via the official Salad API:
        POST /organizations/{org_name}/log-entries

    Supports retry via the SaladClient session (urllib3 Retry adapter).
    Rate limit (429) is handled automatically by the retry adapter.
    """

    def __init__(self, client: SaladClient) -> None:
        self._client = client

    def fetch_logs(
        self,
        org_name: str,
        container_group: Optional[str] = None,
        machine_id: Optional[str] = None,
        since: Optional[datetime.datetime] = None,
        query: Optional[str] = None,
    ) -> List[RawLogEntry]:
        start_time: Optional[str] = None
        if since is not None:
            start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            raw: Dict[str, Any] = self._client.query_log_entries(
                org_name=org_name,
                container_group=container_group,
                machine_id=machine_id,
                start_time=start_time,
                query=query,
            )
        except SaladApiError as exc:
            logger.warning(
                "[%s] Log query failed (status=%d): %s",
                self._client.account_name, exc.status_code, exc
            )
            return []
        except Exception as exc:
            logger.error("[%s] Unexpected error fetching logs: %s", self._client.account_name, exc)
            return []

        entries = raw.get("items") or raw.get("entries") or []
        result: List[RawLogEntry] = []
        for entry in entries:
            try:
                ts_raw = entry.get("time") or entry.get("timestamp") or entry.get("receive_time") or ""
                ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
                
                # Extract message from text_log or json_log.message
                message = entry.get("text_log")
                if not message and "json_log" in entry and isinstance(entry["json_log"], dict):
                    message = entry["json_log"].get("message")
                if not message:
                    message = entry.get("message") or entry.get("log") or ""

                resource = entry.get("resource", {})
                labels = resource.get("labels", {})

                result.append(
                    RawLogEntry(
                        timestamp=ts,
                        message=message,
                        machine_id=labels.get("machine_id"),
                        container_group=labels.get("container_group_name"),
                    )
                )
            except Exception as parse_exc:
                logger.debug("Failed to parse log entry %r: %s", entry, parse_exc)

        result.sort(key=lambda e: e.timestamp)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Log Collection Service
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import aiohttp
from api.async_salad_client import AsyncSaladClient

def collect_logs(log_source_factory=None) -> int:
    """
    Poll logs for every running instance across all accounts and organizations.
    Returns total number of new log rows inserted.
    """
    cfg = get_config()
    parser = HashrateParser()

    # 1. Gather all tasks
    tasks = []
    with get_session() as session:
        for acc_cfg in cfg.accounts:
            for org_name_str in acc_cfg.organizations:
                actual_org = org_name_str.split("/")[0] if "/" in org_name_str else org_name_str

                account = session.query(Account).filter_by(name=acc_cfg.name).first()
                if account is None:
                    continue
                org = session.query(Organization).filter_by(
                    account_id=account.id, org_name=org_name_str
                ).first()
                if org is None:
                    continue

                groups: List[ContainerGroup] = (
                    session.query(ContainerGroup)
                    .filter_by(organization_id=org.id)
                    .all()
                )

                for group in groups:
                    # Zero-Waste: Check if group has any running/allocating instances
                    active_count = session.query(Instance).filter(
                        Instance.container_group_id == group.id,
                        Instance.state.in_(["running", "allocating", "starting", "downloading", "extracting"])
                    ).count()
                    
                    if active_count == 0:
                        continue

                    now_utc = datetime.datetime.utcnow()
                    since = now_utc - datetime.timedelta(minutes=2)

                    query_str = 'text_log contains "proof_per_sec" OR text_log contains "hashrate"'
                    tasks.append((acc_cfg.name, actual_org, group.group_name, None, since, query_str, group.id))

    if not tasks:
        return 0

    # 2. Fire HTTP requests concurrently via aiohttp
    fetch_results = asyncio.run(_async_fetch_all_logs(tasks, cfg))

    # 3. Write results to DB
    total_inserted = 0
    with get_session() as session:
        for group_id, group_name, logs in fetch_results:
            inserted = _store_logs(session, group_id, group_name, logs, parser)
            total_inserted += inserted

    logger.info("Log collection complete — %d new log row(s) inserted (asyncio)", total_inserted)
    return total_inserted

async def _async_fetch_all_logs(tasks_info, cfg):
    accounts = {acc.name: acc.api_key for acc in cfg.accounts}
    resolver = aiohttp.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, limit=15)
    async with aiohttp.ClientSession(connector=connector) as session:
        clients = {}
        for acc_name, api_key in accounts.items():
            clients[acc_name] = AsyncSaladClient(api_key, acc_name)
            
        cors = []
        for account_name, actual_org, group_name, machine_id, since, query_str, group_id in tasks_info:
            if account_name not in clients:
                continue
            cors.append(
                _async_fetch_single_log(
                    clients[account_name], session, actual_org, group_name, machine_id, since, query_str, group_id
                )
            )
        results = await asyncio.gather(*cors, return_exceptions=True)
        
        valid_results = []
        for res in results:
            if isinstance(res, Exception):
                logger.error("Async fetch logs error: %s", res)
            elif res is not None:
                group_id, group_name, logs = res
                if logs:
                    valid_results.append((group_id, group_name, logs))
        return valid_results

async def _async_fetch_single_log(
    client: AsyncSaladClient,
    session: aiohttp.ClientSession,
    actual_org: str,
    group_name: str,
    machine_id: Optional[str],
    since: datetime.datetime,
    query: str,
    group_id: int
):
    start_time = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        raw = await client.query_log_entries(
            session=session,
            org_name=actual_org,
            container_group=group_name,
            machine_id=machine_id,
            start_time=start_time,
            query=query,
        )
    except Exception as exc:
        logger.warning("[%s] Log query failed: %s", client.account_name, exc)
        return None

    entries = raw.get("items") or raw.get("entries") or []
    result = []
    for entry in entries:
        try:
            ts_raw = entry.get("time") or entry.get("timestamp") or entry.get("receive_time") or ""
            ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            
            message = entry.get("text_log")
            if not message and "json_log" in entry and isinstance(entry["json_log"], dict):
                message = entry["json_log"].get("message")
            if not message:
                message = entry.get("message") or entry.get("log") or ""

            resource = entry.get("resource", {})
            labels = resource.get("labels", {})

            result.append(
                RawLogEntry(
                    timestamp=ts,
                    message=message,
                    machine_id=labels.get("machine_id"),
                    container_group=labels.get("container_group_name"),
                )
            )
        except Exception as parse_exc:
            pass

    result.sort(key=lambda e: e.timestamp)
    return (group_id, group_name, result)


def _store_logs(
    session: Session,
    group_id: int,
    group_name: str,
    logs: List[RawLogEntry],
    parser: "HashrateParser",
) -> int:
    """Persist new log entries to the DB. Returns count of inserted rows."""
    if not logs:
        return 0

    # Pre-fetch mapping of machine_id -> instance_id for this group
    instances = session.query(Instance).filter_by(container_group_id=group_id).all()
    machine_to_inst_id = {i.machine_id: i.id for i in instances if i.machine_id}

    new_logs = []
    for entry in logs:
        inst_id = machine_to_inst_id.get(entry.machine_id)
        if not inst_id:
            continue

        # Check existing using a quick count or relying on unique constraint (better to rely on exception if many, but let's check manually to avoid rollback)
        # To avoid N+1 queries, we could fetch existing, but we can also just use a set of existing (inst_id, timestamp)
        # Actually, let's just query existing for this inst_id since the last fetch
        pass # handled below

    min_ts = min(e.timestamp for e in logs)
    max_ts = max(e.timestamp for e in logs)

    # Load all existing timestamps for instances in this group within the time range
    existing = set()
    for inst_id_val, ts in session.query(InstanceLog.instance_id, InstanceLog.timestamp).filter(
        InstanceLog.instance_id.in_(list(machine_to_inst_id.values())),
        InstanceLog.timestamp.between(min_ts, max_ts)
    ).all():
        existing.add((inst_id_val, ts))

    # Load instance objects so we can update them
    instances_list = session.query(Instance).filter_by(container_group_id=group_id).all()
    inst_dict = {i.id: i for i in instances_list}

    for entry in logs:
        inst_id = machine_to_inst_id.get(entry.machine_id)
        if not inst_id or (inst_id, entry.timestamp) in existing:
            continue

        metrics: Optional[ParsedMetrics] = parser.parse(entry.message)

        log_row = InstanceLog(
            instance_id=inst_id,
            timestamp=entry.timestamp,
            raw_log=entry.message,
            parsed_hashrate=metrics.hashrate if metrics else None,
            parsed_hashrate_ths=metrics.hashrate_ths if metrics else None,
            parsed_gpu_type=metrics.gpu_type if metrics else None,
            parsed_machine_id=metrics.machine_id if metrics else None,
        )
        new_logs.append(log_row)

        # Update the Instance immediately for real-time UI dashboard
        if metrics:
            inst_obj = inst_dict.get(inst_id)
            if inst_obj:
                if metrics.gpu_type:
                    inst_obj.gpu_type = metrics.gpu_type
                if metrics.hashrate_ths is not None:
                    inst_obj.latest_hashrate = metrics.hashrate_ths
                elif metrics.hashrate is not None:
                    inst_obj.latest_hashrate = metrics.hashrate

                # Compute real-time efficiency so the Health badge updates instantly
                if inst_obj.gpu_type and inst_obj.latest_hashrate is not None:
                    from utils.benchmarks import get_benchmark
                    from utils.helpers import safe_divide
                    
                    benchmark = get_benchmark(inst_obj.gpu_type) or inst_obj.benchmark_hashrate
                    if benchmark and benchmark > 0:
                        inst_obj.benchmark_hashrate = benchmark
                        inst_obj.efficiency = safe_divide(inst_obj.latest_hashrate, benchmark)

    if new_logs:
        session.bulk_save_objects(new_logs)
        session.flush()
        logger.debug(
            "Stored %d log row(s) for container group %s",
            len(new_logs), group_name,
        )

    return len(new_logs)
