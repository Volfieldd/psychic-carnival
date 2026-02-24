from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    name: str
    type: str = Field(pattern="^(power|light|lux|other)$")
    source_type: str = Field(pattern="^(csv|shelly)$")
    shelly_host: str | None = None
    shelly_token: str | None = None
    main_metric: str = Field(pattern="^(watts|on|lux)$")


class DeviceUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    source_type: str | None = None
    shelly_host: str | None = None
    shelly_token: str | None = None
    main_metric: str | None = None


class DeviceOut(DeviceCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RuleCreate(BaseModel):
    name: str
    json: dict[str, Any]


class RuleOut(BaseModel):
    id: int
    device_id: int
    name: str
    json: dict[str, Any]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AnalyzeRequest(BaseModel):
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    template: str | None = None


class SimulateRequest(BaseModel):
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    rule_json: dict[str, Any] | None = None
    rule_id: int | None = None


class ShellyPullRequest(BaseModel):
    from_ts: datetime
    to_ts: datetime
    interval_sec: int = 30


class EventOut(BaseModel):
    ts: datetime
    type: str
    payload: dict[str, Any]


class CurrentStatusOut(BaseModel):
    state: str
    last_event: EventOut | None
    window_sec: int
