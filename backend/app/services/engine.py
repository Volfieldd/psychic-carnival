from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SimulationResult:
    states: list[dict[str, Any]]
    events: list[dict[str, Any]]
    metrics: dict[str, float]


def preprocess(df: pd.DataFrame, sampling_sec: int = 10) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out = out.sort_values("ts").set_index("ts")
    out = out.resample(f"{sampling_sec}s").mean().interpolate(limit=3)
    out["value"] = out["value"].rolling(3, min_periods=1).median()
    return out.reset_index()


def detect_oscillation(values: np.ndarray, tolerance: float = 0.15, min_cycles: int = 3) -> dict[str, Any]:
    if len(values) < 8:
        return {"detected": False, "cycles": 0}
    centered = values - np.mean(values)
    signs = np.sign(centered)
    cross = np.sum(np.abs(np.diff(signs)) > 0)
    cycles = cross // 2
    amplitude = (np.percentile(values, 90) - np.percentile(values, 10)) / max(np.mean(values), 1e-6)
    detected = cycles >= min_cycles and amplitude >= tolerance
    return {"detected": bool(detected), "cycles": int(cycles), "amplitude": float(amplitude)}


def segment_active(df: pd.DataFrame, rule: dict[str, Any]) -> pd.Series:
    cond = rule["states"][0]["entry"]
    op = cond["op"]
    val = cond.get("value", 0)
    if op == "gte":
        mask = df["value"] >= val
    elif op == "lte":
        mask = df["value"] <= val
    elif op == "between":
        low, high = cond["range"]
        mask = df["value"].between(low, high)
    else:
        mask = df["value"] > val
    for_sec = cond.get("for_sec", 0)
    if for_sec > 0 and len(mask) > 1:
        sample_sec = max(1, int((df["ts"].iloc[1] - df["ts"].iloc[0]).total_seconds()))
        window = max(1, int(for_sec / sample_sec))
        mask = mask.rolling(window, min_periods=1).mean() == 1
    return mask.fillna(False)


def simulate_rule(df: pd.DataFrame, rule: dict[str, Any], metric_name: str = "watts") -> SimulationResult:
    if df.empty:
        return SimulationResult(states=[], events=[], metrics={"active_ratio": 0.0})
    active = segment_active(df, rule)
    states = [{"ts": r.ts.isoformat(), "state": "RUNNING" if a else "IDLE"} for r, a in zip(df.itertuples(), active)]
    events = []
    prev = False
    for row, curr in zip(df.itertuples(), active):
        if curr and not prev:
            events.append({"ts": row.ts.isoformat(), "event": "START"})
        if prev and not curr:
            events.append({"ts": row.ts.isoformat(), "event": "STOP"})
        prev = bool(curr)
    metrics = {"active_ratio": float(active.mean())}
    if metric_name == "watts":
        metrics["energy_wh"] = float(np.trapz(df["value"], dx=1) / 3600)
    return SimulationResult(states=states, events=events, metrics=metrics)


def propose_rule(df: pd.DataFrame, template: dict[str, Any], metric: str = "watts") -> dict[str, Any]:
    if df.empty:
        threshold = template["thresholds"]["start"]
    else:
        threshold = float(np.percentile(df["value"], 85))
    idle = float(np.percentile(df["value"], 15)) if not df.empty else template["thresholds"]["idle"]
    osc = detect_oscillation(df["value"].to_numpy(), template["params"]["tolerance"], int(template["params"]["min_cycles"])) if not df.empty else {"detected": False, "cycles": 0}
    dsl = {
        "metric": metric,
        "states": [
            {
                "name": "RUNNING",
                "entry": {"type": "threshold", "op": "gte", "value": round(threshold, 2), "for_sec": int(template["params"]["min_duration_sec"])},
                "exit": {"type": "threshold", "op": "lte", "value": round(idle, 2), "for_sec": 30},
            }
        ],
        "patterns": {
            "oscillation": osc,
            "plateau": {"enabled": template["patterns"].get("plateau", False)},
            "duty_cycle": {"enabled": template["patterns"].get("duty_cycle", False)},
            "drops_to_zero": {"enabled": template["patterns"].get("drops_to_zero", False)},
        },
        "events": ["START", "STOP"],
    }
    confidence = min(0.95, 0.55 + (0.1 if osc.get("detected") else 0) + (0.2 if threshold > idle else 0))
    return {
        "dsl": dsl,
        "explanation": f"Threshold start ajusté au p85={threshold:.1f}, idle au p15={idle:.1f}. Oscillation détectée={osc.get('detected', False)}.",
        "confidence": confidence,
    }
