"""
services/monitoring_service.py
================================
Core monitoring logic.

Flow per cycle (every 15 minutes):
  1. Load all instances with their container group / org / account context.
  2. For each instance, read the latest hashrate from container logs (InstanceLog).
  3. Look up the GPU benchmark expected hashrate from utils.benchmarks.
  4. Compute:
       efficiency = actual_hashrate / benchmark_hashrate
  5. Flag as bad when efficiency < 85%.
  6. Increment consecutive_bad_checks counter.
  7. When consecutive_bad_checks >= 2 (two consecutive 15-min cycles = 30 min):
       a. Check daily reallocation cap (max 3 per instance per 24 h).
       b. If cap not reached → reallocate / recreate / restart (per strategy).
       c. Log action to DB.
  8. Record HashrateHistory snapshot for every instance.
  9. Purge old InstanceLog rows older than log_retention_days.

Efficiency is always relative to the benchmark table, NOT the peer median.
If a GPU type has no benchmark entry the efficiency is None and the instance
is treated as UNKNOWN (never flagged bad or reallocated).
"""
from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.salad_client import SaladApiError, SaladClient
from database.connection import get_session
from models.orm import (
    Account,
    Action,
    ContainerGroup,
    HashrateHistory,
    Instance,
    InstanceLog,
    Organization,
)
from models.schemas import SaladContainerGroupList
from utils.benchmarks import get_benchmark
from utils.client_cache import get_salad_client
from utils.config import get_config
from utils.helpers import instance_status, safe_divide, get_gpu_cost_per_hour

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_monitoring_cycle() -> Dict[str, int]:
    """
    Full monitoring cycle.
    Returns a summary dict: {'checked': N, 'bad': N, 'actions': N}
    """
    cfg = get_config()

    checked = 0
    bad = 0
    actions_taken = 0

    gpu_lookup_cache: Dict[str, Any] = {}

    with get_session() as session:
        # ── Batch load: instances + their group/org/account in one JOIN query ──
        rows = (
            session.query(Instance, ContainerGroup, Organization, Account)
            .join(ContainerGroup, Instance.container_group_id == ContainerGroup.id)
            .join(Organization, ContainerGroup.organization_id == Organization.id)
            .join(Account, Organization.account_id == Account.id)
            .all()
        )

        # ── Batch load: latest hashrate per instance (one subquery, not N queries) ──
        latest_log_subq = (
            session.query(
                InstanceLog.instance_id,
                func.max(InstanceLog.timestamp).label("max_ts"),
            )
            .filter(InstanceLog.parsed_hashrate.isnot(None))
            .group_by(InstanceLog.instance_id)
            .subquery()
        )
        latest_logs = (
            session.query(InstanceLog)
            .join(
                latest_log_subq,
                (InstanceLog.instance_id == latest_log_subq.c.instance_id)
                & (InstanceLog.timestamp == latest_log_subq.c.max_ts),
            )
            .all()
        )
        # Prefer the TH/s-normalised hashrate when available (vLLM format logs).
        # Fall back to raw parsed_hashrate for generic log formats.
        hashrate_map: Dict[int, float] = {}
        for log in latest_logs:
            if log.parsed_hashrate is None:
                continue
            # Use the TH/s field if it exists and is populated (new column)
            ths_val = getattr(log, "parsed_hashrate_ths", None)
            hashrate_map[log.instance_id] = ths_val if ths_val is not None else log.parsed_hashrate

        instances: List[Instance] = []

        for inst, group, org, account in rows:
            try:
                client = get_salad_client(account.name)
            except ValueError:
                continue

            # ── GPU type: API-sourced only ──────────────────────────────────
            api_gpu_type = _ensure_gpu_type(
                session, inst, group, client, org.org_name, account.name, gpu_lookup_cache
            )
            if api_gpu_type:
                inst.gpu_type = api_gpu_type

            # ── Hashrate from batch-loaded log map ──────────────────────────
            hashrate = hashrate_map.get(inst.id)
            inst.latest_hashrate = hashrate
            inst.last_checked_at = datetime.datetime.utcnow()

            # ── Benchmark expected hashrate ─────────────────────────────────
            benchmark = get_benchmark(inst.gpu_type)
            inst.benchmark_hashrate = benchmark

            # Keep gpu_median_hashrate for backwards-compat (set to benchmark)
            inst.gpu_median_hashrate = benchmark

            instances.append(inst)
            checked += 1

        # ── Step 2: evaluate efficiency and flag bad instances ────────────────
        threshold = cfg.monitoring.efficiency_threshold
        consecutive_limit = cfg.monitoring.consecutive_failures

        for inst in instances:
            benchmark = inst.benchmark_hashrate

            efficiency: Optional[float] = None
            if inst.latest_hashrate is not None and benchmark and benchmark > 0:
                efficiency = safe_divide(inst.latest_hashrate, benchmark)
            inst.efficiency = efficiency

            # Determine if bad using the new cost-based logic
            cost = get_gpu_cost_per_hour(inst.gpu_type)
            status = instance_status(inst.latest_hashrate, cost)
            is_bad_now = (status == "BAD")
            if is_bad_now:
                inst.consecutive_bad_checks += 1
                inst.is_bad = True
                bad += 1

                # Bad node tracker
                inst.failure_count = (inst.failure_count or 0) + 1
                now_utc = datetime.datetime.utcnow()
                inst.last_failure = now_utc
                if inst.first_failure is None:
                    inst.first_failure = now_utc

                if inst.consecutive_bad_checks >= consecutive_limit:
                    inst.needs_reallocation = True
            else:
                inst.consecutive_bad_checks = 0
                inst.is_bad = False
                inst.needs_reallocation = False

            # ── Record history snapshot ──────────────────────────────────
            history = HashrateHistory(
                instance_id=inst.id,
                hashrate=inst.latest_hashrate,
                gpu_median=benchmark,       # store benchmark as reference
                efficiency=efficiency,
                is_bad=is_bad_now,
            )
            session.add(history)

            # Note: Automatic reallocation has been disabled.
            # Instances are flagged with needs_reallocation=True, but remediation
            # must be triggered manually via the UI.
            
        session.flush()

    # ── Step 3: purge old logs ────────────────────────────────────────────────
    _purge_old_logs(cfg.monitoring.log_retention_days)

    logger.info(
        "Monitoring cycle complete — checked=%d bad=%d actions=%d",
        checked, bad, actions_taken,
    )
    return {"checked": checked, "bad": bad, "actions": actions_taken}


# ─────────────────────────────────────────────────────────────────────────────
# Log retention / purge
# ─────────────────────────────────────────────────────────────────────────────

def _purge_old_logs(retention_days: int) -> None:
    """
    Delete InstanceLog rows older than *retention_days* days.
    Also prune HashrateHistory older than retention_days * 2 (keep longer for trend charts).

    Storage estimate (500 instances, 4 checks/hr, 30 days):
        instance_logs:    ~1.4M rows  ≈ 70 MB
        hashrate_history: ~1.4M rows  ≈ 70 MB
    """
    if retention_days <= 0:
        return

    log_cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
    history_cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days * 2)

    try:
        with get_session() as session:
            deleted_logs = (
                session.query(InstanceLog)
                .filter(InstanceLog.timestamp < log_cutoff)
                .delete(synchronize_session=False)
            )
            deleted_history = (
                session.query(HashrateHistory)
                .filter(HashrateHistory.checked_at < history_cutoff)
                .delete(synchronize_session=False)
            )
            session.flush()
            if deleted_logs or deleted_history:
                logger.info(
                    "Log purge: removed %d instance_logs (>%dd) and %d hashrate_history (>%dd)",
                    deleted_logs, retention_days,
                    deleted_history, retention_days * 2,
                )
    except Exception as exc:
        logger.warning("Log purge failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_gpu_type(
    session: Session,
    inst: Instance,
    group: ContainerGroup,
    client: SaladClient,
    org_name_str: str,
    account_name: str,
    cache: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Fetch GPU type from the container group's container spec (Salad API).
    This is the single authoritative source — logs are NOT used for gpu_type.

    Skips the API call if we already have a resolved human-readable name
    (i.e. not a raw UUID, which is 36 chars). Re-queries if we only have a UUID.
    """
    UUID_LEN = 36
    if inst.gpu_type and len(inst.gpu_type) < UUID_LEN:
        return inst.gpu_type  # already resolved to a name, use cached value

    if "/" in org_name_str:
        actual_org, actual_proj = org_name_str.split("/", 1)
    else:
        actual_org = org_name_str
        actual_proj = ""

    if cache is None:
        cache = {}

    cache_key_cg = f"cg:{account_name}:{org_name_str}"
    
    try:
        if cache_key_cg in cache:
            raw = cache[cache_key_cg]
        else:
            raw = client.list_container_groups(actual_org, actual_proj)
            cache[cache_key_cg] = raw

        parsed = SaladContainerGroupList(**raw) if isinstance(raw, dict) else SaladContainerGroupList()
        for cg in parsed.items:
            if cg.name == group.group_name:
                gpu_classes = (
                    cg.container.resources.gpu_classes
                    if cg.container and cg.container.resources
                    else []
                )
                if gpu_classes:
                    uuid = gpu_classes[0]
                    try:
                        cache_key_gpu = f"gpu:{account_name}:{actual_org}"
                        if cache_key_gpu in cache:
                            gpu_data = cache[cache_key_gpu]
                        else:
                            gpu_data = client.list_gpu_classes(actual_org)
                            cache[cache_key_gpu] = gpu_data

                        for item in gpu_data.get("items", []):
                            if item.get("id") == uuid:
                                inst.gpu_type = item.get("name")
                                return inst.gpu_type
                        inst.gpu_type = uuid
                        return uuid
                    except Exception as e:
                        logger.warning(
                            "[%s/%s] Failed to map GPU UUID %s: %s",
                            account_name, org_name_str, uuid, e,
                        )
                        inst.gpu_type = uuid
                        return uuid
    except SaladApiError as exc:
        logger.warning("[%s/%s] Could not fetch GPU type: %s", account_name, org_name_str, exc)

    return None


def _remediate(
    session: Session,
    client: SaladClient,
    inst: Instance,
    org_name_str: str,
    group_name: str,
    account_name: str,
) -> bool:
    """
    Try to remediate a bad instance using the following priority:
      1. REALLOCATE  — move to a new node
      2. RECREATE    — destroy and re-create on a new node
      3. RESTART     — restart on the same node (last resort)

    Records the action in the database.
    Returns True if any action succeeded.
    """
    cfg = get_config()
    is_dry_run = cfg.monitoring.dry_run
    chosen_strategy = cfg.monitoring.remediation_strategy.lower()

    benchmark = inst.benchmark_hashrate
    if inst.efficiency is not None and benchmark:
        reason = (
            f"consecutive_bad_checks={inst.consecutive_bad_checks} "
            f"efficiency={inst.efficiency:.2%} "
            f"actual={inst.latest_hashrate:.2f} expected={benchmark:.2f}"
        )
    else:
        reason = f"consecutive_bad_checks={inst.consecutive_bad_checks} no_hashrate_data"

    if "/" in org_name_str:
        actual_org, actual_proj = org_name_str.split("/", 1)
    else:
        actual_org = org_name_str
        actual_proj = ""

    # Determine strategy order
    if chosen_strategy == "auto":
        strategies = [
            ("REALLOCATE", client.reallocate_instance),
            ("RECREATE",   client.recreate_instance),
            ("RESTART",    client.restart_instance),
        ]
    elif chosen_strategy == "reallocate":
        strategies = [
            ("REALLOCATE", client.reallocate_instance),
            ("RESTART",    client.restart_instance),
        ]
    elif chosen_strategy == "recreate":
        strategies = [
            ("RECREATE",   client.recreate_instance),
            ("RESTART",    client.restart_instance),
        ]
    elif chosen_strategy == "restart":
        strategies = [("RESTART", client.restart_instance)]
    else:
        strategies = [("RESTART", client.restart_instance)]

    for action_type, method in strategies:
        try:
            if is_dry_run:
                resp = {"status": "dry_run", "message": f"Would have executed {action_type}"}
                logger.info(
                    "[%s/%s/%s] [DRY RUN] Would execute %s for instance_id=%s",
                    account_name, org_name_str, group_name, action_type, inst.instance_id,
                )
            else:
                resp = method(actual_org, actual_proj, group_name, inst.instance_id)

            action = Action(
                instance_id=inst.id,
                action_type=action_type + ("_DRY_RUN" if is_dry_run else ""),
                reason=reason,
                success=True,
                response_body=str(resp),
            )
            session.add(action)
            session.flush()

            if not is_dry_run:
                logger.info(
                    "[%s/%s/%s] %s SUCCESS — instance_id=%s efficiency=%.2f%% (expected=%.2f)",
                    account_name, org_name_str, group_name, action_type, inst.instance_id,
                    (inst.efficiency or 0) * 100,
                    inst.benchmark_hashrate or 0,
                )
            return True

        except SaladApiError as exc:
            action = Action(
                instance_id=inst.id,
                action_type=action_type,
                reason=reason,
                success=False,
                response_body=str(exc),
            )
            session.add(action)
            logger.warning(
                "[%s/%s/%s] %s FAILED for instance %s: %s",
                account_name, org_name_str, group_name, action_type, inst.instance_id, exc,
            )

    return False
