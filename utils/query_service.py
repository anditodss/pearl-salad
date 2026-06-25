"""
utils/query_service.py
========================
Read-only query helpers that aggregate data from the DB for the UI.
These functions return DTOs (not ORM objects) safe for Streamlit consumption.

Caching strategy
----------------
get_all_instances() is the hot path — called by /api/instances, /api/stats,
and /api/gpu-summary on every frontend poll.  To avoid hitting SQLite on every
request we keep a process-wide in-memory cache (_instance_cache).  The cache
is invalidated by invalidate_cache() which is called from the event bus
(notify_data_updated) immediately after each sync/monitor cycle completes.
"""
from __future__ import annotations

import datetime
import logging
import statistics
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from database.connection import get_session
from models.orm import Account, Action, ContainerGroup, HashrateHistory, Instance, Organization
from models.schemas import ActionDTO, DashboardStats, GpuSummaryDTO, InstanceDTO
from utils.config import get_config
from utils.helpers import instance_status, get_gpu_cost_per_hour

logger = logging.getLogger(__name__)

# ─── In-memory cache ─────────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_instance_cache: Optional[List[InstanceDTO]] = None
_cache_dirty: bool = True   # start dirty so first request populates it


def invalidate_cache() -> None:
    """Mark the cache as stale.  Called after every sync/monitor cycle."""
    global _cache_dirty
    with _cache_lock:
        _cache_dirty = True
    logger.debug("Query cache invalidated")


def get_dashboard_stats() -> DashboardStats:
    """Return top-level summary metrics for the dashboard."""
    with get_session() as session:
        n_accounts = session.query(Account).count()
        n_orgs = session.query(Organization).count()
        n_groups = session.query(ContainerGroup).count()

    instances = get_all_instances()
    n_instances = len(instances)

    gpu_types = {i.gpu_type for i in instances if i.gpu_type}

    statuses = [i.status for i in instances]
    last_check: Optional[datetime.datetime] = None
    checked = [i.last_checked_at for i in instances if i.last_checked_at]
    if checked:
        last_check = max(checked)
        
    total_cost = sum(i.cost_per_hour or 0.0 for i in instances)

    return DashboardStats(
        total_accounts=n_accounts,
        total_organizations=n_orgs,
        total_container_groups=n_groups,
        total_instances=n_instances,
        total_gpu_types=len(gpu_types),
        good_count=statuses.count("GOOD"),
        warning_count=statuses.count("WARNING"),
        bad_count=statuses.count("BAD"),
        unknown_count=statuses.count("UNKNOWN"),
        last_check=last_check,
        total_cost_per_hour=total_cost,
    )


def get_all_instances() -> List[InstanceDTO]:
    """Return a flat list of all instances with hierarchy and performance data.

    Result is served from the in-memory cache when clean.  The cache is
    marked dirty by invalidate_cache() after every sync/monitor cycle.
    """
    global _instance_cache, _cache_dirty

    with _cache_lock:
        if not _cache_dirty and _instance_cache is not None:
            return _instance_cache  # fast path — no DB hit

    cfg = get_config()
    threshold = cfg.monitoring.efficiency_threshold

    dtos: List[InstanceDTO] = []
    with get_session() as session:
        instances: List[Instance] = (
            session.query(Instance)
            .options(
                joinedload(Instance.container_group)
                .joinedload(ContainerGroup.organization)
                .joinedload(Organization.account)
            )
            .all()
        )
        for inst in instances:
            group = inst.container_group
            if group is None:
                continue
            org = group.organization
            if org is None:
                continue
            account = org.account
            if account is None:
                continue

            cost = get_gpu_cost_per_hour(inst.gpu_type)
            dtos.append(InstanceDTO(
                db_id=inst.id,
                instance_id=inst.instance_id,
                machine_id=inst.machine_id,
                gpu_type=inst.gpu_type,
                state=inst.state,
                account_name=account.name,
                org_name=org.org_name,
                group_name=group.group_name,
                latest_hashrate=inst.latest_hashrate,
                gpu_median_hashrate=inst.gpu_median_hashrate,
                benchmark_hashrate=getattr(inst, "benchmark_hashrate", None),
                efficiency=inst.efficiency,
                consecutive_bad_checks=inst.consecutive_bad_checks,
                is_bad=inst.is_bad,
                status=instance_status(inst.latest_hashrate, cost),
                last_checked_at=inst.last_checked_at,
                api_create_time=inst.api_create_time,
                cost_per_hour=cost,
            ))

    with _cache_lock:
        _instance_cache = dtos
        _cache_dirty = False

    logger.debug("Query cache refreshed — %d instance(s)", len(dtos))
    return dtos


def get_bad_instances() -> List[InstanceDTO]:
    """Return only instances currently flagged as bad."""
    return [i for i in get_all_instances() if i.is_bad]


def get_gpu_summary() -> List[GpuSummaryDTO]:
    """Aggregate performance stats per GPU type (uses cached instance list)."""
    instances = get_all_instances()  # served from cache if clean
    gpu_map: Dict[str, List[InstanceDTO]] = defaultdict(list)
    for inst in instances:
        key = inst.gpu_type or "unknown"
        gpu_map[key].append(inst)

    summaries: List[GpuSummaryDTO] = []
    for gpu_type, insts in gpu_map.items():
        rates = [i.latest_hashrate for i in insts if i.latest_hashrate is not None]
        summaries.append(GpuSummaryDTO(
            gpu_type=gpu_type,
            instance_count=len(insts),
            median_hashrate=statistics.median(rates) if rates else None,
            avg_hashrate=statistics.mean(rates) if rates else None,
            min_hashrate=min(rates) if rates else None,
            max_hashrate=max(rates) if rates else None,
            bad_count=sum(1 for i in insts if i.is_bad),
        ))

    return sorted(summaries, key=lambda s: s.instance_count, reverse=True)


def get_recent_actions(limit: int = 100) -> List[ActionDTO]:
    """Return the most recent remediation actions."""
    dtos: List[ActionDTO] = []
    with get_session() as session:
        rows: List[Action] = (
            session.query(Action)
            .options(
                joinedload(Action.instance)
                .joinedload(Instance.container_group)
                .joinedload(ContainerGroup.organization)
                .joinedload(Organization.account)
            )
            .order_by(Action.created_at.desc())
            .limit(limit)
            .all()
        )
        for row in rows:
            inst = row.instance
            if inst is None:
                continue
            group = inst.container_group
            org = group.organization if group else None
            account = org.account if org else None

            dtos.append(ActionDTO(
                id=row.id,
                instance_id=inst.instance_id,
                machine_id=inst.machine_id,
                account_name=account.name if account else "unknown",
                org_name=org.org_name if org else "unknown",
                group_name=group.group_name if group else "unknown",
                action_type=row.action_type,
                reason=row.reason,
                success=row.success,
                created_at=row.created_at,
            ))

    return dtos
