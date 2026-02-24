from __future__ import annotations

from datetime import datetime
import io

import pandas as pd
import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import load_app_config
from app.core.database import Base, engine, get_db
from app.models.models import Device, Rule, SeriesPoint, Source
from app.schemas.schemas import AnalyzeRequest, DeviceCreate, DeviceOut, IngestPush, RuleCreate, RuleOut, SimulateRequest, SourceCreate, SourceOut
from app.services.engine import preprocess, propose_rule, simulate_rule

app = FastAPI(title="Energy Pattern Analyzer", version="0.1.0")
Base.metadata.create_all(bind=engine)
app_config = load_app_config()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/devices", response_model=DeviceOut)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    db_device = Device(**payload.model_dump())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device


@app.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return db.scalars(select(Device)).all()


@app.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, db: Session = Depends(get_db)):
    item = db.get(Device, device_id)
    if not item:
        raise HTTPException(404, "device not found")
    return item


@app.delete("/devices/{device_id}")
def delete_device(device_id: str, db: Session = Depends(get_db)):
    item = db.get(Device, device_id)
    if not item:
        raise HTTPException(404, "device not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/sources", response_model=SourceOut)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    item = Source(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.scalars(select(Source)).all()


@app.post("/ingest/csv")
async def ingest_csv(device_id: str = Query(...), metric: str = Query("watts"), ts_col: str = Query("ts"), value_col: str = Query("value"), file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "device not found")
    data = await file.read()
    try:
        frame = pd.read_csv(io.BytesIO(data))
        frame["ts"] = pd.to_datetime(frame[ts_col])
        frame["value"] = pd.to_numeric(frame[value_col])
    except Exception as exc:
        raise HTTPException(400, f"csv parsing error: {exc}")
    rows = [SeriesPoint(device_id=device_id, metric=metric, ts=row.ts.to_pydatetime(), value=float(row.value)) for row in frame[["ts", "value"]].itertuples(index=False)]
    db.add_all(rows)
    db.commit()
    return {"ingested": len(rows)}


@app.post("/ingest/push")
def ingest_push(payload: IngestPush, db: Session = Depends(get_db)):
    if not db.get(Device, payload.device_id):
        raise HTTPException(404, "device not found")
    rows = [SeriesPoint(device_id=payload.device_id, metric=payload.metric, ts=p.ts, value=p.value) for p in payload.points]
    db.add_all(rows)
    db.commit()
    return {"ingested": len(rows)}


@app.post("/ingest/shelly/pull")
def ingest_shelly_pull(device_id: str, from_ts: datetime, to_ts: datetime, interval_sec: int = 10, db: Session = Depends(get_db)):
    if not db.get(Device, device_id):
        raise HTTPException(404, "device not found")
    # MVP stub: generates synthetic points compatible with shelly integration.
    rng = pd.date_range(from_ts, to_ts, freq=f"{interval_sec}s")
    vals = 100 + 900 * (np.sin(np.linspace(0, 6, len(rng))) > 0).astype(int)
    rows = [SeriesPoint(device_id=device_id, metric="watts", ts=ts.to_pydatetime(), value=float(v)) for ts, v in zip(rng, vals)]
    db.add_all(rows)
    db.commit()
    return {"ingested": len(rows), "source": "shelly-simulated"}


@app.get("/series")
def get_series(device_id: str, metric: str = "watts", from_ts: datetime | None = None, to_ts: datetime | None = None, downsample_sec: int | None = None, db: Session = Depends(get_db)):
    clauses = [SeriesPoint.device_id == device_id, SeriesPoint.metric == metric]
    if from_ts:
        clauses.append(SeriesPoint.ts >= from_ts)
    if to_ts:
        clauses.append(SeriesPoint.ts <= to_ts)
    rows = db.scalars(select(SeriesPoint).where(and_(*clauses)).order_by(SeriesPoint.ts)).all()
    frame = pd.DataFrame([{"ts": r.ts, "value": r.value} for r in rows])
    if frame.empty:
        return []
    ds = downsample_sec or int(app_config.defaults["sampling_sec"])
    frame = preprocess(frame, sampling_sec=ds)
    return [{"ts": row.ts.isoformat(), "value": float(row.value)} for row in frame.itertuples(index=False)]


@app.post("/rules", response_model=RuleOut)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    if not db.get(Device, payload.device_id):
        raise HTTPException(404, "device not found")
    item = Rule(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/rules", response_model=list[RuleOut])
def list_rules(device_id: str | None = None, db: Session = Depends(get_db)):
    query = select(Rule)
    if device_id:
        query = query.where(Rule.device_id == device_id)
    return db.scalars(query).all()


@app.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleCreate, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@app.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": True}


def _load_series_df(db: Session, device_id: str, metric: str, from_ts: datetime | None, to_ts: datetime | None):
    clauses = [SeriesPoint.device_id == device_id, SeriesPoint.metric == metric]
    if from_ts:
        clauses.append(SeriesPoint.ts >= from_ts)
    if to_ts:
        clauses.append(SeriesPoint.ts <= to_ts)
    rows = db.scalars(select(SeriesPoint).where(and_(*clauses)).order_by(SeriesPoint.ts)).all()
    return pd.DataFrame([{"ts": r.ts, "value": r.value} for r in rows])


@app.post("/simulate")
def simulate(payload: SimulateRequest, db: Session = Depends(get_db)):
    frame = _load_series_df(db, payload.device_id, payload.metric, payload.from_ts, payload.to_ts)
    frame = preprocess(frame, int(app_config.defaults["sampling_sec"]))
    dsl = payload.dsl
    if payload.rule_id:
        db_rule = db.get(Rule, payload.rule_id)
        if not db_rule:
            raise HTTPException(404, "rule not found")
        dsl = db_rule.dsl
    if not dsl:
        raise HTTPException(400, "dsl or rule_id required")
    result = simulate_rule(frame, dsl, payload.metric)
    return {"states": result.states, "events": result.events, "metrics": result.metrics}


@app.post("/analyze/oneshot")
def analyze_oneshot(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    device = db.get(Device, payload.device_id)
    if not device:
        raise HTTPException(404, "device not found")
    frame = preprocess(_load_series_df(db, payload.device_id, payload.metric, payload.from_ts, payload.to_ts), int(app_config.defaults["sampling_sec"]))
    template = app_config.templates.get(device.type, app_config.templates["other"]).model_dump()
    proposal = propose_rule(frame, template, payload.metric)
    return proposal


@app.post("/analyze/auto")
def analyze_auto(payload: AnalyzeRequest, days: int = 7, db: Session = Depends(get_db)):
    out = analyze_oneshot(payload, db)
    out["period_days"] = days
    return out


@app.get("/status/current")
def status_current(device_id: str, metric: str = "watts", db: Session = Depends(get_db)):
    status_window_min = int(app_config.defaults["status_window_min"])
    to_ts = datetime.utcnow()
    from_ts = to_ts - pd.Timedelta(minutes=status_window_min)
    frame = preprocess(_load_series_df(db, device_id, metric, from_ts, to_ts), int(app_config.defaults["sampling_sec"]))
    rules = db.scalars(select(Rule).where(Rule.device_id == device_id)).all()
    if not rules:
        return {"state": "UNKNOWN", "reason": "no rule"}
    sim = simulate_rule(frame, rules[0].dsl, metric)
    state = sim.states[-1]["state"] if sim.states else "UNKNOWN"
    return {"state": state, "last_event": sim.events[-1] if sim.events else None, "metrics": sim.metrics}


@app.get("/config/effective")
def effective_config():
    return app_config.model_dump()
