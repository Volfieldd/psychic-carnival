from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    metrics: Mapped[list] = mapped_column(JSON, default=list)
    source_config: Mapped[dict] = mapped_column(JSON, default=dict)

    points: Mapped[list[SeriesPoint]] = relationship("SeriesPoint", back_populates="device")
    rules: Mapped[list[Rule]] = relationship("Rule", back_populates="device")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class SeriesPoint(Base):
    __tablename__ = "series_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    value: Mapped[float] = mapped_column(Float)

    device: Mapped[Device] = relationship("Device", back_populates="points")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    dsl: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    device: Mapped[Device] = relationship("Device", back_populates="rules")
