from datetime import datetime

import pandas as pd

from app.services.engine import detect_oscillation, preprocess, simulate_rule


def test_detect_oscillation_true():
    vals = [0, 10, 0, 10, 0, 10, 0, 10, 0]
    out = detect_oscillation(pd.Series(vals).to_numpy(), tolerance=0.2, min_cycles=3)
    assert out["detected"] is True
    assert out["cycles"] >= 3


def test_segmentation_and_simulation_start_stop():
    ts = pd.date_range(datetime(2024, 1, 1), periods=10, freq="10s")
    vals = [0, 0, 1200, 1300, 1250, 100, 0, 0, 0, 0]
    df = pd.DataFrame({"ts": ts, "value": vals})
    rule = {
        "states": [{"entry": {"op": "gte", "value": 1000, "for_sec": 10}, "exit": {"op": "lte", "value": 100}}]
    }
    result = simulate_rule(df, rule)
    assert any(e["event"] == "START" for e in result.events)
    assert any(e["event"] == "STOP" for e in result.events)


def test_preprocess_resample():
    ts = pd.to_datetime(["2024-01-01T00:00:00", "2024-01-01T00:00:09", "2024-01-01T00:00:21"])
    df = pd.DataFrame({"ts": ts, "value": [1, 2, 3]})
    out = preprocess(df, sampling_sec=10)
    assert len(out) >= 2
    assert "value" in out.columns
