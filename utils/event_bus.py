"""
utils/event_bus.py
===================
Minimal in-process event bus for Server-Sent Events (SSE).

The scheduler runs in background threads (APScheduler). When a sync completes,
it calls notify_data_updated(). The SSE endpoint in app.py has one asyncio.Queue
per connected client. notify_data_updated() puts an event into every queue,
which the SSE handler immediately streams to the browser.

Result: the frontend is notified within milliseconds of a sync completing,
instead of waiting for the next polling cycle.
"""
from __future__ import annotations

import asyncio
import threading
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Thread-safe set of asyncio queues — one per connected SSE client
_queues: Set[asyncio.Queue] = set()
_lock = threading.Lock()


def register(q: asyncio.Queue) -> None:
    """Register a new SSE client queue."""
    with _lock:
        _queues.add(q)
    logger.debug("SSE client connected (%d total)", len(_queues))


def unregister(q: asyncio.Queue) -> None:
    """Remove a disconnected SSE client queue."""
    with _lock:
        _queues.discard(q)
    logger.debug("SSE client disconnected (%d remaining)", len(_queues))


def notify_data_updated(event: str = "data_updated", data: str = "1") -> None:
    """
    Called from background threads (scheduler) after a sync completes.
    Puts an event and data into every connected client's queue.
    Also invalidates the in-memory query cache so the next API request
    reads fresh data from the DB.
    Thread-safe.
    """
    try:
        from utils.query_service import invalidate_cache, get_all_instances
        import json
        invalidate_cache()
        instances = get_all_instances()
        result = []
        for inst in instances:
            result.append({
                "id": inst.db_id,
                "salad_id": inst.instance_id,
                "machine_id": inst.machine_id,
                "account_name": inst.account_name,
                "state": inst.state,
                "status": inst.status,
                "gpu_type": inst.gpu_type,
                "latest_hashrate": inst.latest_hashrate,
                "benchmark_hashrate": inst.benchmark_hashrate,
                "efficiency": inst.efficiency,
                "is_bad": 1 if inst.is_bad else 0,
                "container_group_name": inst.group_name,
                "cost_per_hour": inst.cost_per_hour
            })
        data = json.dumps(result)
    except Exception as e:
        logger.error(f"Error packing SSE data: {e}")
        pass

    with _lock:
        queues = list(_queues)

    if not queues:
        return

    for q in queues:
        try:
            q.put_nowait((event, data))
        except asyncio.QueueFull:
            pass  # client is too slow, skip

    logger.debug("SSE: broadcast '%s' to %d client(s)", event, len(queues))
