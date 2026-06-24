import aiohttp
import asyncio
from typing import Any, Dict, Optional
from utils.config import get_config
from api.salad_client import SaladApiError, _AUTH_HEADER
import logging
logger = logging.getLogger(__name__)

class AsyncSaladClient:
    """
    Asynchronous client for high-performance concurrent API polling.
    """
    def __init__(self, api_key: str, account_name: str = "") -> None:
        self.api_key = api_key
        self.account_name = account_name
        self._cfg = get_config().api
        self._base = self._cfg.base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            _AUTH_HEADER: self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get(self, session: aiohttp.ClientSession, path: str) -> Any:
        url = f"{self._base}{path}"
        # logger.debug("[%s] ASYNC GET %s", self.account_name, url)
        try:
            async with session.get(url, headers=self._headers(), timeout=self._cfg.timeout_seconds) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise SaladApiError(resp.status, url, text)
                return await resp.json()
        except Exception as e:
            if not isinstance(e, SaladApiError):
                logger.error("[%s] ASYNC GET Error %s: %s", self.account_name, url, e)
            raise

    async def _post(self, session: aiohttp.ClientSession, path: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base}{path}"
        # logger.debug("[%s] ASYNC POST %s", self.account_name, url)
        try:
            async with session.post(url, headers=self._headers(), json=json_data or {}, timeout=self._cfg.timeout_seconds) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise SaladApiError(resp.status, url, text)
                try:
                    return await resp.json()
                except Exception:
                    return {}
        except Exception as e:
            if not isinstance(e, SaladApiError):
                logger.error("[%s] ASYNC POST Error %s: %s", self.account_name, url, e)
            raise

    async def list_instances(self, session: aiohttp.ClientSession, org_name: str, project_name: str, group_name: str) -> Dict[str, Any]:
        path = f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances"
        return await self._get(session, path)

    async def query_log_entries(
        self,
        session: aiohttp.ClientSession,
        org_name: str,
        container_group: Optional[str] = None,
        machine_id: Optional[str] = None,
        query: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        query_parts = []
        if machine_id:
            query_parts.append(f'resource.labels.machine_id="{machine_id}"')
        if container_group:
            query_parts.append(f'resource.labels.container_group_name="{container_group}"')
        if query:
            query_parts.append(f'({query})')
        
        query_str = " AND ".join(query_parts) if query_parts else 'text_log != ""'

        import datetime
        now = datetime.datetime.utcnow()
        if not end_time:
            end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not start_time:
            start_time = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        body: Dict[str, Any] = {
            "query": query_str,
            "start_time": start_time,
            "end_time": end_time
        }
        return await self._post(session, f"/organizations/{org_name}/log-entries", json_data=body)
