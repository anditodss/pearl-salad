"""
models/orm.py
=============
SQLAlchemy ORM table definitions.

Tables:
  accounts          — Salad accounts from config.json
  organizations     — Organizations under each account
  container_groups  — Container groups under each organization
  instances         — Instances under each container group
  hashrate_history  — Per-check hashrate snapshot per instance
  actions           — Remediation actions (reallocate/restart)
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


# ─────────────────────────────────────────────────────────────────────────────
# accounts
# ─────────────────────────────────────────────────────────────────────────────
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    organizations: Mapped[List["Organization"]] = relationship(
        "Organization", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# organizations
# ─────────────────────────────────────────────────────────────────────────────
class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("account_id", "org_name", name="uq_account_org"),)

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    org_name: Mapped[str] = Column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = Column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    account: Mapped["Account"] = relationship("Account", back_populates="organizations")
    container_groups: Mapped[List["ContainerGroup"]] = relationship(
        "ContainerGroup", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization org_name={self.org_name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# container_groups
# ─────────────────────────────────────────────────────────────────────────────
class ContainerGroup(Base):
    __tablename__ = "container_groups"
    __table_args__ = (UniqueConstraint("organization_id", "group_name", name="uq_org_group"),)

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    group_name: Mapped[str] = Column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = Column(String(255), nullable=True)
    status: Mapped[Optional[str]] = Column(String(64), nullable=True)
    replicas: Mapped[Optional[int]] = Column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="container_groups")
    instances: Mapped[List["Instance"]] = relationship(
        "Instance", back_populates="container_group", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ContainerGroup group_name={self.group_name!r} status={self.status!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# instances
# ─────────────────────────────────────────────────────────────────────────────
class Instance(Base):
    __tablename__ = "instances"
    __table_args__ = (
        UniqueConstraint("container_group_id", "instance_id", name="uq_group_instance"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    container_group_id: Mapped[int] = Column(
        Integer, ForeignKey("container_groups.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[str] = Column(String(255), nullable=False, index=True)
    machine_id: Mapped[Optional[str]] = Column(String(255), nullable=True)
    gpu_type: Mapped[Optional[str]] = Column(String(255), nullable=True, index=True)
    state: Mapped[Optional[str]] = Column(String(64), nullable=True)
    api_create_time: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)
    api_update_time: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)

    # Performance tracking
    latest_hashrate: Mapped[Optional[float]] = Column(Float, nullable=True)
    gpu_median_hashrate: Mapped[Optional[float]] = Column(Float, nullable=True)
    benchmark_hashrate: Mapped[Optional[float]] = Column(Float, nullable=True)  # expected from GPU benchmark table
    efficiency: Mapped[Optional[float]] = Column(Float, nullable=True)
    consecutive_bad_checks: Mapped[int] = Column(Integer, default=0, nullable=False)
    is_bad: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)

    # Bad node detector tracking
    needs_reallocation: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    failure_count: Mapped[int] = Column(Integer, default=0, nullable=False)
    first_failure: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)
    last_failure: Mapped[Optional[datetime.datetime]] = Column(DateTime, nullable=True)

    created_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    container_group: Mapped["ContainerGroup"] = relationship(
        "ContainerGroup", back_populates="instances"
    )
    hashrate_history: Mapped[List["HashrateHistory"]] = relationship(
        "HashrateHistory", back_populates="instance", cascade="all, delete-orphan"
    )
    actions: Mapped[List["Action"]] = relationship(
        "Action", back_populates="instance", cascade="all, delete-orphan"
    )
    logs: Mapped[List["InstanceLog"]] = relationship(
        "InstanceLog", back_populates="instance", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Instance instance_id={self.instance_id!r} gpu={self.gpu_type!r} state={self.state!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# hashrate_history
# ─────────────────────────────────────────────────────────────────────────────
class HashrateHistory(Base):
    __tablename__ = "hashrate_history"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = Column(
        Integer, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hashrate: Mapped[Optional[float]] = Column(Float, nullable=True)
    gpu_median: Mapped[Optional[float]] = Column(Float, nullable=True)
    efficiency: Mapped[Optional[float]] = Column(Float, nullable=True)
    is_bad: Mapped[bool] = Column(Boolean, default=False)
    checked_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, index=True)

    instance: Mapped["Instance"] = relationship("Instance", back_populates="hashrate_history")

    def __repr__(self) -> str:
        return f"<HashrateHistory instance_id={self.instance_id} hashrate={self.hashrate}>"


# ─────────────────────────────────────────────────────────────────────────────
# instance_logs
# ─────────────────────────────────────────────────────────────────────────────
class InstanceLog(Base):
    """
    Stores raw log lines collected from Salad API per instance.

    Source: POST /organizations/{org}/log-entries
    Logs are keyed by (instance_id, timestamp) to avoid duplicates.
    """
    __tablename__ = "instance_logs"
    __table_args__ = (
        UniqueConstraint("instance_id", "timestamp", name="uq_log_instance_timestamp"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = Column(
        Integer, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime.datetime] = Column(DateTime, nullable=False, index=True)
    raw_log: Mapped[str] = Column(Text, nullable=False)

    # Extracted fields (populated by hashrate parser, may be null)
    parsed_hashrate: Mapped[Optional[float]] = Column(Float, nullable=True)      # raw value from log
    parsed_hashrate_ths: Mapped[Optional[float]] = Column(Float, nullable=True)  # normalised to TH/s
    parsed_gpu_type: Mapped[Optional[str]] = Column(String(255), nullable=True)
    parsed_machine_id: Mapped[Optional[str]] = Column(String(255), nullable=True)

    collected_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow)

    instance: Mapped["Instance"] = relationship("Instance", back_populates="logs")

    def __repr__(self) -> str:
        return f"<InstanceLog instance_id={self.instance_id} ts={self.timestamp}>"


# ─────────────────────────────────────────────────────────────────────────────
# actions
# ─────────────────────────────────────────────────────────────────────────────
class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = Column(
        Integer, ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # REALLOCATE | RECREATE | RESTART
    action_type: Mapped[str] = Column(String(64), nullable=False)
    reason: Mapped[Optional[str]] = Column(Text, nullable=True)
    success: Mapped[Optional[bool]] = Column(Boolean, nullable=True)
    response_body: Mapped[Optional[str]] = Column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=_utcnow, index=True)

    instance: Mapped["Instance"] = relationship("Instance", back_populates="actions")

    def __repr__(self) -> str:
        return f"<Action instance_id={self.instance_id} type={self.action_type!r} ok={self.success}>"
