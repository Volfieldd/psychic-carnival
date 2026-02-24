from __future__ import annotations

from datetime import datetime
import statistics
from typing import Any

import numpy as np


def preprocess(points: list[dict[str, Any]], metric: str, sampling_sec: int = 30) -> list[dict[str, Any]]:
    if not points:
        return []
    points = sorted(points, key=lambda x: x["ts"])
    vals = [p[metric] for p in points if p.get(metric) is not None]
    if not vals:
        return points
    q1, q3 = np.quantile(vals, [0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - 3 * iqr, q3 + 3 * iqr
    for p in points:
        if p.get(metric) is not None:
            p[metric] = float(max(low, min(high, p[metric])))

    bucketed = {}
    for p in points:
        t = int(p["ts"].timestamp())
        bt = t - (t % sampling_sec)
        key = datetime.fromtimestamp(bt)
        bucketed.setdefault(key, []).append(p)

    out = []
    for ts in sorted(bucketed.keys()):
        group = bucketed[ts]
        item = {"ts": ts, "watts": None, "on": None, "lux": None}
        for m in ["watts", "on", "lux"]:
            vals = [g[m] for g in group if g.get(m) is not None]
            if vals:
                item[m] = float(statistics.median(vals))
        out.append(item)
    return out


def condition_true(value: float | None, cond: dict[str, Any]) -> bool:
    if value is None:
        return False
    op = cond.get("op")
    if op == "gte":
        return value >= cond["value"]
    if op == "lte":
        return value <= cond["value"]
    if op == "between":
        return cond["min"] <= value <= cond["max"]
    return False


def simulate(points: list[dict[str, Any]], metric: str, rule: dict[str, Any], sampling_sec: int = 30):
    states = []
    events = []
    current = "OFF"
    counters = {}
    for p in points:
        new_state = current
        for state in rule.get("states", []):
            cond = state.get("when", {})
            name = state.get("name", "UNKNOWN")
            key = f"{name}:{cond}"
            counters.setdefault(key, 0)
            if condition_true(p.get(metric), cond):
                counters[key] += sampling_sec
            else:
                counters[key] = 0
            if counters[key] >= cond.get("for_sec", sampling_sec):
                new_state = name
        if new_state != current:
            events.append({"ts": p["ts"], "type": "STATE_CHANGE", "payload": {"from": current, "to": new_state}})
            current = new_state
        states.append({"ts": p["ts"], "state": current})

    if rule.get("patterns", {}).get("drops_to_zero", {}).get("enabled"):
        drops = 0
        for i in range(1, len(points)):
            prev = points[i - 1].get(metric) or 0
            cur = points[i].get(metric) or 0
            if prev > 0 and cur == 0:
                drops += 1
        if drops >= rule["patterns"]["drops_to_zero"].get("min_drops", 2):
            events.append({"ts": points[-1]["ts"], "type": "DROPS_TO_ZERO", "payload": {"drops": drops}})

    return states, events


def propose_rule(points: list[dict[str, Any]], metric: str, device_type: str):
    vals = np.array([p[metric] for p in points if p.get(metric) is not None], dtype=float)
    if len(vals) == 0:
        return {"name": "empty", "states": []}, "No data", 0.0

    p50 = float(np.quantile(vals, 0.5))
    p90 = float(np.quantile(vals, 0.9))
    if metric == "watts":
        start = max(5.0, p90 * 0.6)
        idle_low, idle_high = 1.0, max(5.0, p50 * 0.5)
        rule = {
            "metric": metric,
            "sampling_sec": 30,
            "states": [
                {"name": "RUNNING", "when": {"op": "gte", "value": round(start, 2), "for_sec": 60}},
                {"name": "IDLE_ON", "when": {"op": "between", "min": idle_low, "max": round(idle_high, 2), "for_sec": 180}},
                {"name": "OFF", "when": {"op": "lte", "value": 0.5, "for_sec": 60}},
            ],
            "patterns": {
                "oscillation": {"enabled": True, "band": [round(p50 * 0.5, 2), round(p50 * 1.5, 2)], "period_sec": 120, "tolerance_sec": 60, "for_cycles": 3},
                "drops_to_zero": {"enabled": True, "min_drops": 2},
            },
        }
    elif metric == "on":
        rule = {"metric": metric, "sampling_sec": 10, "states": [{"name": "RUNNING", "when": {"op": "gte", "value": 1, "for_sec": 10}}, {"name": "OFF", "when": {"op": "lte", "value": 0, "for_sec": 10}}], "patterns": {"drops_to_zero": {"enabled": False}}}
    else:
        thr = round(float(np.quantile(vals, 0.7)), 2)
        rule = {"metric": metric, "sampling_sec": 30, "states": [{"name": "RUNNING", "when": {"op": "gte", "value": thr, "for_sec": 60}}, {"name": "OFF", "when": {"op": "lte", "value": max(0.0, thr * 0.4), "for_sec": 120}}], "patterns": {"drops_to_zero": {"enabled": False}}}
    exp = f"Template {device_type} ajusté par quantiles (p50={p50:.2f}, p90={p90:.2f})."
    score = min(0.99, max(0.55, len(vals) / 5000))
    return rule, exp, score
