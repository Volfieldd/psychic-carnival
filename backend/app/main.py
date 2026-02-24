from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import logging
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import Base, engine, get_db
from app.models.models import DataPoint, Device, Event, RuleSet
from app.schemas.schemas import AnalyzeRequest, CurrentStatusOut, DeviceCreate, DeviceOut, DeviceUpdate, RuleCreate, RuleOut, ShellyPullRequest, SimulateRequest
from app.services.engine import preprocess, propose_rule, simulate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("energy-mvp")

app = FastAPI(title="Energy Pattern Analyzer MVP", version="1.0.0")
Base.metadata.create_all(bind=engine)


def parse_ts(raw: str, tz_name: str):
    raw = str(raw).strip()
    if raw.isdigit():
        v = int(raw)
        if v > 10_000_000_000:
            dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(v, tz=timezone.utc)
        return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo:
        return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
    return dt


def must_device(db: Session, device_id: int):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "device not found")
    return d


def load_points(db: Session, device_id: int, from_ts: datetime | None, to_ts: datetime | None):
    q = select(DataPoint).where(DataPoint.device_id == device_id)
    if from_ts:
        q = q.where(DataPoint.ts >= from_ts)
    if to_ts:
        q = q.where(DataPoint.ts <= to_ts)
    return db.scalars(q.order_by(DataPoint.ts)).all()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/devices", response_model=DeviceOut)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    item = Device(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return db.scalars(select(Device).order_by(Device.created_at.desc())).all()


@app.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    return must_device(db, device_id)


@app.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db)):
    item = must_device(db, device_id)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@app.delete("/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    item = must_device(db, device_id)
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/devices/{device_id}/ingest/csv")
def ingest_csv(device_id: int, file: UploadFile = File(...), timezone_name: str = Query("Europe/Paris"), db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    try:
        sample = file.file.read(2048).decode("utf-8", errors="ignore")
        file.file.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        text = io.TextIOWrapper(file.file, encoding="utf-8", errors="ignore")
        reader = csv.DictReader(text, delimiter=delimiter)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        required = ["timestamp", device.main_metric]
        missing = [c for c in required if c not in headers]
        if missing:
            raise HTTPException(400, f"Missing required columns for {device.type}: {', '.join(missing)}")

        added = 0
        batch = []
        for row in reader:
            ts = parse_ts(row[headers["timestamp"]], timezone_name)
            dp = DataPoint(device_id=device_id, ts=ts)
            if "watts" in headers and row.get(headers["watts"], "") != "":
                dp.watts = float(row[headers["watts"]])
            if "on" in headers and row.get(headers["on"], "") != "":
                dp.on = float(row[headers["on"]])
            if "lux" in headers and row.get(headers["lux"], "") != "":
                dp.lux = float(row[headers["lux"]])
            batch.append(dp)
            if len(batch) >= 1000:
                db.add_all(batch)
                db.commit()
                added += len(batch)
                batch = []
        if batch:
            db.add_all(batch)
            db.commit()
            added += len(batch)
        log.info("CSV ingest done device=%s rows=%s", device_id, added)
        return {"ingested": added}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("csv ingest failed")
        raise HTTPException(400, f"CSV parsing failed: {exc}")


@app.post("/devices/{device_id}/ingest/shelly_pull")
def ingest_shelly_pull(device_id: int, payload: ShellyPullRequest, db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    if payload.from_ts >= payload.to_ts:
        raise HTTPException(400, "from_ts must be before to_ts")
    ts = payload.from_ts
    points = []
    while ts <= payload.to_ts:
        value = 0.0
        if device.shelly_host:
            try:
                headers = {"Authorization": f"Bearer {device.shelly_token}"} if device.shelly_token else {}
                r = httpx.get(f"http://{device.shelly_host}/rpc/Switch.GetStatus?id=0", headers=headers, timeout=2)
                if r.status_code < 300:
                    data = r.json()
                    value = float(data.get("apower", 0.0)) if device.main_metric == "watts" else float(data.get("output", 0))
            except Exception:
                pass
        dp = DataPoint(device_id=device_id, ts=ts)
        setattr(dp, device.main_metric, value)
        points.append(dp)
        ts = datetime.fromtimestamp(ts.timestamp() + payload.interval_sec)
    db.add_all(points)
    db.commit()
    return {"ingested": len(points)}


@app.get("/devices/{device_id}/stats")
def stats(device_id: int, db: Session = Depends(get_db)):
    must_device(db, device_id)
    min_ts, max_ts, count = db.execute(select(func.min(DataPoint.ts), func.max(DataPoint.ts), func.count(DataPoint.id)).where(DataPoint.device_id == device_id)).one()
    if count == 0:
        return {"count": 0, "from": None, "to": None, "holes": 0}
    rows = db.scalars(select(DataPoint.ts).where(DataPoint.device_id == device_id).order_by(DataPoint.ts)).all()
    gaps = 0
    if len(rows) >= 3:
        deltas = [(rows[i] - rows[i - 1]).total_seconds() for i in range(1, len(rows))]
        expected = sorted(deltas)[len(deltas) // 2]
        gaps = sum(1 for d in deltas if d > expected * 2)
    return {"count": count, "from": min_ts, "to": max_ts, "holes": gaps}


@app.get("/devices/{device_id}/series")
def series(device_id: int, from_ts: datetime | None = None, to_ts: datetime | None = None, downsample_sec: int = 30, db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    rows = load_points(db, device_id, from_ts, to_ts)
    points = [{"ts": r.ts, "watts": r.watts, "on": r.on, "lux": r.lux} for r in rows]
    processed = preprocess(points, metric=device.main_metric, sampling_sec=max(1, downsample_sec))
    return [{"ts": p["ts"].isoformat(), "watts": p["watts"], "on": p["on"], "lux": p["lux"]} for p in processed]


@app.get("/devices/{device_id}/rules", response_model=list[RuleOut])
def list_rules(device_id: int, db: Session = Depends(get_db)):
    must_device(db, device_id)
    return db.scalars(select(RuleSet).where(RuleSet.device_id == device_id).order_by(RuleSet.created_at.desc())).all()


@app.post("/devices/{device_id}/rules", response_model=RuleOut)
def create_rule(device_id: int, payload: RuleCreate, db: Session = Depends(get_db)):
    must_device(db, device_id)
    item = RuleSet(device_id=device_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleCreate, db: Session = Depends(get_db)):
    item = db.get(RuleSet, rule_id)
    if not item:
        raise HTTPException(404, "rule not found")
    item.name = payload.name
    item.json = payload.json
    db.commit()
    db.refresh(item)
    return item


@app.post("/rules/{rule_id}/activate")
def activate_rule(rule_id: int, db: Session = Depends(get_db)):
    item = db.get(RuleSet, rule_id)
    if not item:
        raise HTTPException(404, "rule not found")
    db.query(RuleSet).filter(RuleSet.device_id == item.device_id).update({RuleSet.is_active: False})
    item.is_active = True
    db.commit()
    return {"activated": True}


@app.post("/devices/{device_id}/analyze/oneshot")
def analyze(device_id: int, payload: AnalyzeRequest, db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    rows = load_points(db, device_id, payload.from_ts, payload.to_ts)
    points = preprocess([{"ts": r.ts, "watts": r.watts, "on": r.on, "lux": r.lux} for r in rows], device.main_metric, 30)
    rule, explanation, score = propose_rule(points, device.main_metric, device.type)
    return {"proposed_rule": rule, "explanations": explanation, "score": score}


@app.post("/devices/{device_id}/simulate")
def simulate_endpoint(device_id: int, payload: SimulateRequest, db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    if payload.rule_id:
        r = db.get(RuleSet, payload.rule_id)
        if not r or r.device_id != device_id:
            raise HTTPException(404, "rule not found")
        rule = r.json
    elif payload.rule_json:
        rule = payload.rule_json
    else:
        raise HTTPException(400, "rule_json or rule_id required")

    rows = load_points(db, device_id, payload.from_ts, payload.to_ts)
    points = preprocess([{"ts": r.ts, "watts": r.watts, "on": r.on, "lux": r.lux} for r in rows], device.main_metric, int(rule.get("sampling_sec", 30)))
    states, events = simulate(points, device.main_metric, rule, int(rule.get("sampling_sec", 30)))
    for e in events[-200:]:
        db.add(Event(device_id=device_id, ts=e["ts"], type=e["type"], payload=e["payload"]))
    db.commit()
    return {"states": [{"ts": s["ts"].isoformat(), "state": s["state"]} for s in states], "events": [{"ts": e["ts"].isoformat(), "type": e["type"], "payload": e["payload"]} for e in events], "metrics": {"events": len(events), "samples": len(points)}}


@app.get("/devices/{device_id}/status/current", response_model=CurrentStatusOut)
def current_status(device_id: int, window_sec: int = 600, db: Session = Depends(get_db)):
    device = must_device(db, device_id)
    active = db.scalars(select(RuleSet).where(RuleSet.device_id == device_id, RuleSet.is_active.is_(True))).first()
    if not active:
        raise HTTPException(400, "No active rule")
    end = datetime.utcnow()
    start = datetime.fromtimestamp(end.timestamp() - window_sec)
    rows = load_points(db, device_id, start, end)
    points = preprocess([{"ts": r.ts, "watts": r.watts, "on": r.on, "lux": r.lux} for r in rows], device.main_metric, int(active.json.get("sampling_sec", 30)))
    states, events = simulate(points, device.main_metric, active.json, int(active.json.get("sampling_sec", 30)))
    last_event = events[-1] if events else None
    return {"state": states[-1]["state"] if states else "UNKNOWN", "last_event": last_event, "window_sec": window_sec}
