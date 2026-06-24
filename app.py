"""
Salad Fleet Manager — app.py (FastAPI Backend)
==============================
Backend API entry point.

Responsibilities:
1. Initialise logging
2. Load config
3. Init database schema
4. Start background scheduler
5. Expose REST API for Next.js frontend
"""
import logging
import os
import json
import asyncio
from typing import List, AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from utils.logger import setup_logging
from utils.config import load_config, reload_config, _CONFIG_PATH
from database.migrations import init_db
from scheduler.jobs import start_scheduler, _sync_job, _log_job, _monitor_job

from utils.query_service import (
    get_dashboard_stats,
    get_gpu_summary,
    get_all_instances,
    get_recent_actions
)

from database.connection import get_session
from models.orm import Instance, ContainerGroup, Organization, Account
from api.salad_client import SaladClient

class AccountUpdate(BaseModel):
    name: str
    api_key: str
    organizations: List[str]

class AccountsUpdatePayload(BaseModel):
    accounts: List[AccountUpdate]

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Starting Salad Fleet Manager API...")
    
    try:
        load_config()
    except FileNotFoundError as exc:
        logger.error(f"Configuration error: {exc}")
        raise RuntimeError(f"Config not found: {exc}")
        
    init_db()
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down API...")

app = FastAPI(title="Salad Fleet Manager API", lifespan=lifespan)

# Allow CORS for local Next.js development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/events")
async def sse_events():
    """
    Server-Sent Events endpoint.
    The browser subscribes once; the server pushes 'data_updated' whenever
    a sync or monitor cycle completes. No more polling lag.
    """
    from utils.event_bus import register, unregister

    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    register(queue)

    async def stream() -> AsyncGenerator[str, None]:
        try:
            # Send an initial ping so the browser knows the connection is live
            yield "event: ping\ndata: connected\n\n"
            while True:
                try:
                    event_name, event_data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {event_name}\ndata: {event_data}\n\n"
                except asyncio.TimeoutError:
                    # keepalive comment so the connection doesn't drop
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )

@app.get("/api/scheduler-status")
def scheduler_status():
    from scheduler.jobs import get_job_status
    status = get_job_status()
    jobs = []
    for j in status.get("jobs", []):
        next_run = j.get("next_run")
        jobs.append({
            "id": j["id"],
            "name": j["name"],
            "next_run": next_run.isoformat() if next_run else None,
        })
    return {"running": status.get("running", False), "jobs": jobs}

@app.get("/api/stats")
def get_stats():
    try:
        instances = get_all_instances()  # served from cache — one DB hit max
        stats = get_dashboard_stats()
        total_hashrate = sum(i.latest_hashrate for i in instances if i.latest_hashrate is not None)
        return {
            "total_accounts": stats.total_accounts,
            "total_organizations": stats.total_organizations,
            "total_container_groups": stats.total_container_groups,
            "total_instances": stats.total_instances,
            "total_gpu_types": stats.total_gpu_types,
            "good_count": stats.good_count,
            "warning_count": stats.warning_count,
            "bad_count": stats.bad_count,
            "unknown_count": stats.unknown_count,
            "last_check": stats.last_check.isoformat() if stats.last_check else None,
            "total_hashrate": total_hashrate,
            "total_cost_per_hour": stats.total_cost_per_hour
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gpu-summary")
def get_gpu_data():
    try:
        gpus = get_gpu_summary()
        return [
            {
                "gpu_type": g.gpu_type,
                "instance_count": g.instance_count,
                "median_hashrate": g.median_hashrate,
                "avg_hashrate": g.avg_hashrate,
                "min_hashrate": g.min_hashrate,
                "max_hashrate": g.max_hashrate,
                "bad_count": g.bad_count
            } for g in gpus
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/instances")
def get_instances():
    try:
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
        return result
    except Exception as e:
        logger.error(f"Error in get_instances API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/instances/{db_id}/reallocate")
def reallocate_instance_api(db_id: int):
    try:
        with get_session() as session:
            inst: Instance = session.query(Instance).get(db_id)
            if not inst:
                raise HTTPException(status_code=404, detail="Instance not found in database.")
                
            group: ContainerGroup = session.query(ContainerGroup).get(inst.container_group_id)
            org: Organization = session.query(Organization).get(group.organization_id)
            account: Account = session.query(Account).get(org.account_id)
            
            from utils.config import get_config
            cfg = get_config()
            api_key = next((a.api_key for a in cfg.accounts if a.name == account.name), None)
            if not api_key:
                raise HTTPException(status_code=500, detail=f"API Key not found for account {account.name}")
                
            if "/" in org.org_name:
                actual_org, actual_proj = org.org_name.split("/", 1)
            else:
                actual_org = org.org_name
                actual_proj = ""
                
            client = SaladClient(api_key=api_key, account_name=account.name)
            try:
                client.reallocate_instance(actual_org, actual_proj, group.group_name, inst.instance_id)
            except Exception as client_exc:
                if "404" in str(client_exc):
                    logger.info(f"Instance {inst.instance_id} no longer exists on Salad. Deleting locally.")
                    session.delete(inst)
                    session.commit()
                    from utils.query_service import invalidate_cache
                    invalidate_cache()
                    import threading
                    import time
                    from scheduler.jobs import _sync_job
                    def delayed_sync():
                        time.sleep(1)
                        try:
                            _sync_job()
                        except Exception as e:
                            logger.error(f"Delayed sync failed: {e}")
                    threading.Thread(target=delayed_sync, daemon=True).start()
                    raise HTTPException(status_code=404, detail="Salad has already automatically deleted or reallocated this instance. The dashboard will now refresh.")
                else:
                    raise client_exc
            
            try:
                # Update local DB so UI shows transition immediately
                inst.state = "reallocating"
                session.commit()
            except Exception as db_exc:
                # If the background sync job deleted the instance while the API call was happening,
                # session.commit() will raise a StaleDataError. We can safely ignore it.
                session.rollback()
                logger.warning(f"Could not update local state for {inst.instance_id}, it was likely deleted by a concurrent background sync: {db_exc}")
            
            from utils.query_service import invalidate_cache
            invalidate_cache()
            
            # Trigger a background sync after a short delay so Salad has time to transition it
            import threading
            import time
            from scheduler.jobs import _sync_job
            def delayed_sync():
                time.sleep(3)
                try:
                    _sync_job()
                except Exception as e:
                    logger.error(f"Delayed sync failed: {e}")
                    
            threading.Thread(target=delayed_sync, daemon=True).start()
            
            return {"status": "success", "message": f"Successfully requested reallocation for instance {inst.instance_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reallocate API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync")
def force_sync():
    import threading
    def _run():
        try:
            _sync_job()
            _log_job()
            _monitor_job()
        except Exception as e:
            logger.error(f"Background sync failed: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "accepted", "message": "Sync started in background."}

@app.get("/api/actions")
def get_actions(action_type: str = "ALL"):
    try:
        actions = get_recent_actions(limit=200)
        if action_type != "ALL":
            actions = [a for a in actions if a.action_type == action_type]
        
        result = []
        for a in actions:
            result.append({
                "id": a.id,
                "instance_id": a.instance_id,
                "machine_id": a.machine_id or "—",
                "account_name": a.account_name,
                "org_name": a.org_name,
                "group_name": a.group_name,
                "action_type": a.action_type,
                "reason": a.reason or "—",
                "success": a.success,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        return result
    except Exception as e:
        logger.error(f"Error in get_actions API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config")
def get_current_config():
    try:
        has_env_override = bool(os.getenv("SALAD_API_KEY") or os.getenv("SALAD_ACCOUNT_1_API_KEY"))
        
        if not _CONFIG_PATH.exists():
            return {"accounts": [], "has_env_override": has_env_override}
            
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        accounts = data.get("accounts", [])
        masked_accounts = []
        for acc in accounts:
            api_key = acc.get("api_key", "")
            masked_key = f"{api_key[:6]}••••••••" if len(api_key) > 6 else "••••••••"
            masked_accounts.append({
                "name": acc.get("name", ""),
                "api_key": masked_key,
                "organizations": acc.get("organizations", [])
            })
            
        return {
            "accounts": masked_accounts,
            "has_env_override": has_env_override
        }
    except Exception as e:
        logger.error(f"Error in get_current_config API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/accounts/add")
def add_account(payload: AccountUpdate):
    try:
        if not _CONFIG_PATH.exists():
            data = {"accounts": [], "monitoring": {}}
        else:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        accounts = data.get("accounts", [])
        
        if any(acc.get("name") == payload.name for acc in accounts):
            raise HTTPException(status_code=400, detail=f"Account with name '{payload.name}' already exists.")
            
        accounts.append({
            "name": payload.name,
            "api_key": payload.api_key,
            "organizations": payload.organizations
        })
        
        data["accounts"] = accounts
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        reload_config()
        
        # Trigger an immediate background sync so the UI populates the new account's data
        import threading
        from scheduler.jobs import _sync_job, _log_job, _monitor_job
        def _run_initial_sync():
            try:
                _sync_job()
                _log_job()
                _monitor_job()
            except Exception as e:
                logger.error(f"Background sync failed after adding account: {e}")
        threading.Thread(target=_run_initial_sync, daemon=True).start()
        
        return {"status": "success", "message": f"Account '{payload.name}' added successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in add_account API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class DeleteAccountPayload(BaseModel):
    name: str

@app.post("/api/config/accounts/delete")
def delete_account(payload: DeleteAccountPayload):
    try:
        if not _CONFIG_PATH.exists():
            raise HTTPException(status_code=404, detail="config.json not found.")
            
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        accounts = data.get("accounts", [])
        original_len = len(accounts)
        accounts = [acc for acc in accounts if acc.get("name") != payload.name]
        
        if len(accounts) == original_len:
            raise HTTPException(status_code=404, detail=f"Account '{payload.name}' not found.")
            
        data["accounts"] = accounts
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        reload_config()
        return {"status": "success", "message": f"Account '{payload.name}' deleted successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in delete_account API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
