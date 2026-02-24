from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    shelly_host: Mapped[str | None] = mapped_column(String, nullable=True)
    shelly_token: Mapped[str | None] = mapped_column(String, nullable=True)
    main_metric: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    points: Mapped[list[DataPoint]] = relationship("DataPoint", back_populates="device", cascade="all, delete-orphan")
    rules: Mapped[list[RuleSet]] = relationship("RuleSet", back_populates="device", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship("Event", back_populates="device", cascade="all, delete-orphan")


class DataPoint(Base):
    __tablename__ = "data_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    on: Mapped[float | None] = mapped_column(Float, nullable=True)
    lux: Mapped[float | None] = mapped_column(Float, nullable=True)

    device: Mapped[Device] = relationship("Device", back_populates="points")


class RuleSet(Base):
    __tablename__ = "rule_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device: Mapped[Device] = relationship("Device", back_populates="rules")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    device: Mapped[Device] = relationship("Device", back_populates="events")
