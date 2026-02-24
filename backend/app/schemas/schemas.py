from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DeviceBase(BaseModel):
    id: str
    name: str
    type: str
    metrics: list[str] = []
    source_config: dict[str, Any] = {}


class DeviceCreate(DeviceBase):
    pass


class SourceBase(BaseModel):
    name: str
    kind: str
    config: dict[str, Any] = {}


class SourceCreate(SourceBase):
    pass


class SourceOut(SourceBase):
    id: int

    class Config:
        from_attributes = True


class DeviceOut(DeviceBase):
    class Config:
        from_attributes = True


class RuleBase(BaseModel):
    name: str
    dsl: dict[str, Any]
    explanation: str = ""
    confidence: float = 0


class RuleCreate(RuleBase):
    device_id: str


class RuleOut(RuleBase):
    id: int
    device_id: str

    class Config:
        from_attributes = True


class SeriesPointIn(BaseModel):
    ts: datetime
    value: float


class IngestPush(BaseModel):
    device_id: str
    metric: str
    points: list[SeriesPointIn]


class AnalyzeRequest(BaseModel):
    device_id: str
    metric: str = "watts"
    from_ts: datetime | None = None
    to_ts: datetime | None = None


class SimulateRequest(BaseModel):
    device_id: str
    metric: str = "watts"
    rule_id: int | None = None
    dsl: dict[str, Any] | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
