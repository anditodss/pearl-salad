"""
scheduler/jobs.py
==================
APScheduler background job management.

The scheduler runs three recurring jobs:
  1. sync_job    — every sync_interval_minutes (default 2 min): sync accounts → orgs → groups → instances
  2. log_job     — every sync_interval_minutes (default 2 min): collect logs
  3. monitor_job — every check_interval_minutes (default 15 min): evaluate performance

The scheduler is started lazily and lives in the FastAPI process.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from utils.config import get_config

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Job functions (imported lazily to avoid circular imports at module load)
# ─────────────────────────────────────────────────────────────────────────────

def _sync_job() -> None:
    """Full data sync: accounts → orgs → container groups → instances."""
    from services.account_service import sync_accounts
    from services.organization_service import sync_organizations
    from services.container_group_service import sync_container_groups
    from services.instance_service import sync_instances
    from utils.event_bus import notify_data_updated

    logger.info("Scheduler: starting sync job")
    try:
        sync_accounts()
        sync_organizations()
        sync_container_groups()
        sync_instances()
        logger.info("Scheduler: sync job complete")
        notify_data_updated("sync_complete")
    except Exception as exc:
        logger.error("Scheduler: sync job failed — %s", exc, exc_info=True)


def _log_job() -> None:
    """Poll Salad API for log entries and store them in SQLite."""
    from services.log_collection_service import collect_logs

    logger.info("Scheduler: starting log collection job")
    try:
        inserted = collect_logs()
        logger.info("Scheduler: log collection complete — %d new log row(s)", inserted)
    except Exception as exc:
        logger.error("Scheduler: log collection job failed — %s", exc, exc_info=True)


def _monitor_job() -> None:
    """Evaluate instance performance and remediate bad ones."""
    from services.monitoring_service import run_monitoring_cycle
    from utils.event_bus import notify_data_updated

    logger.info("Scheduler: starting monitor job")
    try:
        result = run_monitoring_cycle()
        logger.info(
            "Scheduler: monitor job complete — checked=%d bad=%d actions=%d",
            result.get("checked", 0),
            result.get("bad", 0),
            result.get("actions", 0),
        )
        notify_data_updated("monitor_complete")
    except Exception as exc:
        logger.error("Scheduler: monitor job failed — %s", exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def get_scheduler() -> BackgroundScheduler:
    """Return the global scheduler instance (creates it if needed)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone="UTC",
        )
    return _scheduler


def start_scheduler() -> None:
    """Start the scheduler with configured interval jobs."""
    with _lock:
        sched = get_scheduler()
        if sched.running:
            logger.debug("Scheduler already running")
            return

        cfg = get_config()
        sync_min = cfg.monitoring.sync_interval_minutes
        monitor_min = cfg.monitoring.check_interval_minutes

        # Sync job — runs frequently to pick up state changes quickly
        sched.add_job(
            _sync_job,
            trigger=IntervalTrigger(minutes=sync_min),
            id="sync_job",
            name="Salad Data Sync",
            replace_existing=True,
        )

        # Log collection job — polls logs after each sync
        sched.add_job(
            _log_job,
            trigger=IntervalTrigger(minutes=sync_min),
            id="log_job",
            name="Log Collection",
            replace_existing=True,
        )

        # Monitor job — evaluates performance (heavier, runs less often)
        sched.add_job(
            _monitor_job,
            trigger=IntervalTrigger(minutes=monitor_min),
            id="monitor_job",
            name="Performance Monitor",
            replace_existing=True,
        )

        sched.start()
        logger.info("Scheduler started — sync_interval=%g min  monitor_interval=%g min", sync_min, monitor_min)

        # Run both jobs immediately on first start without modifying the apscheduler triggers
        _run_initial_jobs()


def _run_initial_jobs() -> None:
    """Kick off the first sync → log collection → monitor cycle in a background thread."""
    def _run():
        _sync_job()
        _log_job()
        _monitor_job()

    t = threading.Thread(target=_run, daemon=True, name="initial-sync")
    t.start()


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        _scheduler = None


def is_running() -> bool:
    """Return True if the scheduler is currently running."""
    return _scheduler is not None and _scheduler.running


def get_job_status() -> dict:
    """Return status info for the UI."""
    sched = get_scheduler()
    if not sched.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in sched.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time,
        })
    return {"running": True, "jobs": jobs}
