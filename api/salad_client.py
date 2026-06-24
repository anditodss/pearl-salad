"""
api/salad_client.py
====================
Low-level HTTP client for the Salad Cloud public REST API.

Confirmed endpoints (from official docs / SDK):
  GET  /organizations/{org}/containers
  GET  /organizations/{org}/containers/{group}/instances
  GET  /organizations/{org}/containers/{group}/instances/{instance_id}
  POST /organizations/{org}/containers/{group}/instances/{instance_id}/reallocate
  POST /organizations/{org}/containers/{group}/instances/{group}/instances/{instance_id}/recreate
  POST /organizations/{org}/containers/{group}/instances/{instance_id}/restart

  # Log Entries (separate Log Entries section in API docs):
  GET  /organizations/{org}/containers/{group}/instances/{instance_id}/logs
  # TODO: Verify exact path — may require a project_name segment
  # Fallback: parse logs via container group status endpoint

Authentication: Salad-Api-Key header
Base URL: https://api.salad.com/api/public
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config import ApiConfig, get_config

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
BASE_URL = "https://api.salad.com/api/public"
_AUTH_HEADER = "Salad-Api-Key"


def _build_session(api_config: ApiConfig) -> Session:
    """Create a requests.Session with retry logic."""
    session = Session()
    retry = Retry(
        total=api_config.max_retries,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class SaladApiError(Exception):
    """Raised when the Salad API returns a non-2xx status code."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"Salad API error {status_code} for {url}: {body[:200]}")


class SaladClient:
    """
    Thread-safe HTTP client for one Salad API key.

    Usage:
        client = SaladClient(api_key="sk-...")
        groups = client.list_container_groups("my-org")
    """

    def __init__(self, api_key: str, account_name: str = "") -> None:
        self.api_key = api_key
        self.account_name = account_name
        cfg = get_config()
        self._cfg = cfg.api
        self._session = _build_session(self._cfg)
        self._base = self._cfg.base_url.rstrip("/")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            _AUTH_HEADER: self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base}{path}"
        logger.debug("[%s] GET %s", self.account_name, url)
        resp: Response = self._session.get(
            url,
            headers=self._headers(),
            params=params,
            timeout=self._cfg.timeout_seconds,
        )
        self._raise_for_status(resp, url)
        return resp.json()

    def _post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base}{path}"
        logger.debug("[%s] POST %s", self.account_name, url)
        resp: Response = self._session.post(
            url,
            headers=self._headers(),
            json=json or {},
            timeout=self._cfg.timeout_seconds,
        )
        self._raise_for_status(resp, url)
        # Some action endpoints return 202 with empty body
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def _raise_for_status(resp: Response, url: str) -> None:
        if resp.status_code >= 400:
            raise SaladApiError(resp.status_code, url, resp.text)

    # ── Public API methods ────────────────────────────────────────────────────

    def get_organizations(self) -> Dict[str, Any]:
        """
        GET /organizations
        TODO: The official public Salad API currently does not expose a well-documented
        endpoint to list all organizations for an account without knowing the org name first.
        Currently, organizations must be defined via config/env.
        """
        # Uncomment and use if Salad adds a public /organizations endpoint
        # return self._get("/organizations")
        raise NotImplementedError("Salad API does not provide a public /organizations list endpoint.")

    def query_log_entries(
        self,
        org_name: str,
        container_group: Optional[str] = None,
        machine_id: Optional[str] = None,
        query: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /organizations/{org_name}/log-entries

        Official Salad endpoint for querying log entries at the organization level.
        Supports filtering by container group name, machine_id, and time range.

        Args:
            org_name:        Organization name (no project prefix needed).
            container_group: Filter by container group name (optional).
            machine_id:      Filter by specific machine/instance ID (optional).
            start_time:      ISO 8601 timestamp (required).
            end_time:        ISO 8601 timestamp (required).

        Returns:
            API response dict. Typically: { "items": [ LogEntry, ... ] }
            Max 500 log entries per request. Logs retained for up to 90 days.
        """
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

        return self._post(f"/organizations/{org_name}/log-entries", json=body)

    def list_gpu_classes(self, org_name: str) -> Dict[str, Any]:
        """
        GET /organizations/{org_name}/gpu-classes
        Returns: { "items": [ { "id": "uuid", "name": "RTX 3090", ... }, ... ] }
        """
        return self._get(f"/organizations/{org_name}/gpu-classes")

    def list_container_groups(self, org_name: str, project_name: str) -> Dict[str, Any]:
        """
        GET /organizations/{org_name}/projects/{project_name}/containers
        Returns: { "items": [ ContainerGroup, ... ] }
        """
        return self._get(f"/organizations/{org_name}/projects/{project_name}/containers")

    def list_instances(self, org_name: str, project_name: str, group_name: str) -> Dict[str, Any]:
        """
        GET /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances
        Returns: { "instances": [ Instance, ... ] }
        """
        return self._get(f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances")

    def get_instance(self, org_name: str, project_name: str, group_name: str, instance_id: str) -> Dict[str, Any]:
        """
        GET /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}
        """
        return self._get(
            f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}"
        )

    def get_instance_logs(
        self, org_name: str, project_name: str, group_name: str, instance_id: str
    ) -> Dict[str, Any]:
        """
        GET /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/logs
        """
        try:
            return self._get(
                f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/logs"
            )
        except SaladApiError as exc:
            if exc.status_code == 404:
                logger.warning(
                    "[%s] Log endpoint not found for instance %s (404) — skipping",
                    self.account_name,
                    instance_id,
                )
                return {}
            raise

    def reallocate_instance(
        self, org_name: str, project_name: str, group_name: str, instance_id: str
    ) -> Dict[str, Any]:
        """
        POST /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/reallocate
        """
        return self._post(
            f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/reallocate"
        )

    def recreate_instance(
        self, org_name: str, project_name: str, group_name: str, instance_id: str
    ) -> Dict[str, Any]:
        """
        POST /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/recreate
        """
        return self._post(
            f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/recreate"
        )

    def restart_instance(
        self, org_name: str, project_name: str, group_name: str, instance_id: str
    ) -> Dict[str, Any]:
        """
        POST /organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/restart
        """
        return self._post(
            f"/organizations/{org_name}/projects/{project_name}/containers/{group_name}/instances/{instance_id}/restart"
        )
