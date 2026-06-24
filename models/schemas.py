"""
models/schemas.py
=================
Pydantic schemas used for:
1. Parsing Salad API JSON responses
2. Internal data transfer objects (DTOs) between service layers
3. UI data shapes passed to Streamlit pages
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Salad API response schemas
# ─────────────────────────────────────────────────────────────────────────────

class SaladOrganization(BaseModel):
    """Response item from GET /organizations/{org_name}/projects (not listed directly)
    Note: Salad API does NOT have a 'list organizations' endpoint.
    Organizations are read from config.json directly.
    """
    name: str
    display_name: Optional[str] = None


class SaladContainerResources(BaseModel):
    """Container resource spec from container group response."""
    cpu: Optional[int] = None
    memory: Optional[int] = None
    gpu_classes: Optional[List[str]] = Field(default_factory=list)


class SaladContainerSpec(BaseModel):
    """Container spec nested inside a container group."""
    resources: Optional[SaladContainerResources] = None


class SaladContainerGroup(BaseModel):
    """Response item from GET .../containers"""
    id: Optional[str] = None
    name: str
    display_name: Optional[str] = None
    status: Optional[str] = None
    replicas: Optional[int] = None
    container: Optional[SaladContainerSpec] = None


class SaladContainerGroupList(BaseModel):
    """Paginated list response from GET .../containers"""
    items: List[SaladContainerGroup] = Field(default_factory=list)


class SaladInstanceState(BaseModel):
    """State nested inside an instance response."""
    status: Optional[str] = None
    description: Optional[str] = None


class SaladInstance(BaseModel):
    """Response item from GET .../instances.

    The Salad API returns instance objects with:
      - 'machine_id' as the unique identifier
      - 'state' as a plain string (e.g. 'running', 'allocating')
      - Various other fields like cpu_percent, create_time, etc.
    We accept all extra fields via model_config.
    """
    model_config = {"extra": "allow"}

    id: str  # This is the actual instance_id
    machine_id: str
    state: Optional[str] = None
    update_time: Optional[datetime.datetime] = None
    create_time: Optional[datetime.datetime] = None
    version: Optional[int] = None

    @property
    def instance_id(self) -> str:
        """Return the true instance identifier."""
        return self.id


class SaladInstanceList(BaseModel):
    """Response from GET .../instances"""
    instances: List[SaladInstance] = Field(default_factory=list)


class SaladLogEntry(BaseModel):
    """Single log entry from GET .../logs"""
    message: Optional[str] = None
    timestamp: Optional[datetime.datetime] = None


class SaladLogResponse(BaseModel):
    """Response from GET .../logs"""
    # The actual field name depends on the API — handle both
    entries: Optional[List[SaladLogEntry]] = Field(default_factory=list)
    items: Optional[List[SaladLogEntry]] = None

    def get_messages(self) -> List[str]:
        """Return all log message strings."""
        source = self.items if self.items else (self.entries or [])
        return [e.message for e in source if e.message]


# ─────────────────────────────────────────────────────────────────────────────
# Internal DTOs
# ─────────────────────────────────────────────────────────────────────────────

class InstanceDTO(BaseModel):
    """Flattened instance view used across service and UI layers."""
    # Identity
    db_id: int
    instance_id: str
    machine_id: Optional[str]
    gpu_type: Optional[str]
    state: Optional[str]

    # Hierarchy
    account_name: str
    org_name: str
    group_name: str

    # Performance
    latest_hashrate: Optional[float]         # actual hashrate from logs
    gpu_median_hashrate: Optional[float]     # legacy field (= benchmark now)
    benchmark_hashrate: Optional[float]      # expected from GPU benchmark table
    efficiency: Optional[float]              # actual / benchmark (0.0–1.0+)
    consecutive_bad_checks: int
    is_bad: bool
    status: str  # GOOD | WARNING | BAD | UNKNOWN

    last_checked_at: Optional[datetime.datetime]
    api_create_time: Optional[datetime.datetime]
    cost_per_hour: float = 0.0


class GpuSummaryDTO(BaseModel):
    """Aggregated stats for a single GPU type."""
    gpu_type: str
    instance_count: int
    median_hashrate: Optional[float]
    avg_hashrate: Optional[float]
    min_hashrate: Optional[float]
    max_hashrate: Optional[float]
    bad_count: int


class ActionDTO(BaseModel):
    """Flattened action view for the UI."""
    id: int
    instance_id: str
    machine_id: Optional[str]
    account_name: str
    org_name: str
    group_name: str
    action_type: str
    reason: Optional[str]
    success: Optional[bool]
    created_at: datetime.datetime


class DashboardStats(BaseModel):
    """Top-level summary numbers for the dashboard."""
    total_accounts: int
    total_organizations: int
    total_container_groups: int
    total_instances: int
    total_gpu_types: int
    good_count: int
    warning_count: int
    bad_count: int
    unknown_count: int
    last_check: Optional[datetime.datetime]
    total_cost_per_hour: float = 0.0
