"""Deterministic synthetic data generator for PlantProof AI.

All data is fictional. Running this module always produces exactly the same
records (fixed random seeds), which keeps demos and tests repeatable.

Regenerate the committed CSV files with:
    python -m plantproof.data_gen
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from .domain import SCENARIO_DIR, Observation, write_observations_csv

ASSET_ID = "P-301"
ASSET_NAME = "Cooling water pump P-301 (Line 3)"
HOURS = 48

SCENARIOS = {
    "A": {
        "seed": 301,
        "start": datetime(2026, 10, 12, 0, 0),
        "title": "Scenario A - P-301 trip, 13 Oct 2026",
        "summary": ("Pump P-301 tripped on a high vibration alarm at 23:10 on 13 Oct. "
                    "Line 3 stopped. Investigate the cause before restart."),
    },
    "B": {
        "seed": 302,
        "start": datetime(2026, 10, 19, 0, 0),
        "title": "Scenario B - P-301 trip, 20 Oct 2026",
        "summary": ("Pump P-301 tripped on a high vibration alarm at 23:10 on 20 Oct. "
                    "Line 3 stopped. Investigate the cause before restart."),
    },
}

SENSORS = (
    ("vibration_mm_s", "mm/s"),
    ("bearing_temp_c", "°C"),
    ("discharge_pressure_bar", "bar"),
    ("motor_current_a", "A"),
)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _sensor_values(sid: str, h: int, rnd: random.Random) -> dict[str, float]:
    u = rnd.uniform
    if sid == "A":   # gradual bearing degradation from hour ~28
        vib = 2.8 + u(-0.2, 0.2) + max(0, h - 30) * 0.36
        temp = 61.0 + u(-0.8, 0.8) + max(0, h - 28) * 1.45
        pres = 4.55 + u(-0.12, 0.12)
        cur = 42.0 + u(-0.6, 0.6) + max(0, h - 34) * 0.15
    else:            # step change in vibration only (faulty transmitter)
        vib = (2.9 + u(-0.2, 0.2)) if h < 30 else (8.4 + u(-0.5, 0.6))
        temp = 62.5 + u(-0.8, 0.8)
        pres = 4.5 + u(-0.12, 0.12)
        cur = 41.8 + u(-0.6, 0.6)
    return {"vibration_mm_s": vib, "bearing_temp_c": temp,
            "discharge_pressure_bar": pres, "motor_current_a": cur}


def generate_scenario(sid: str) -> list[Observation]:
    spec = SCENARIOS[sid]
    rnd = random.Random(spec["seed"])
    start: datetime = spec["start"]
    out: list[Observation] = []

    def at(hour: float) -> str:
        return _iso(start + timedelta(hours=hour))

    def add(rid: str, ts: str, source_type: str, parameter: str, value=None, unit="",
            status=None, subject=None, text="", source=""):
        out.append(Observation(rid, sid, ts, ASSET_ID, source_type, parameter,
                               None if value is None else round(float(value), 2),
                               unit, status, subject, text, source))

    # Hourly sensor readings from the plant historian
    n = 0
    for h in range(HOURS):
        values = _sensor_values(sid, h, rnd)
        for param, unit in SENSORS:
            n += 1
            add(f"{sid}-SEN-{n:04d}", at(h), "sensor", param, values[param], unit,
                text="Hourly average from plant historian", source="DCS historian")

    normal_log = "Shift check: P-301 running normally, no unusual noise reported."

    if sid == "A":
        add("A-MNT-0001", "2026-10-02T10:00:00", "maintenance", "lubrication",
            text="Routine bearing lubrication completed (WO-48211).", source="Maintenance team")
        add("A-CAL-0001", "2026-03-04T09:00:00", "calibration", "vib_sensor_cal",
            text="Vibration transmitter calibrated, as-found within tolerance.",
            source="Instrument workshop")
        add("A-OPS-0001", at(6), "operator_log", "shift_check", status="normal",
            subject="overall", text=normal_log, source="Night shift operator")
        add("A-OPS-0002", at(18), "operator_log", "shift_check", status="normal",
            subject="overall", text=normal_log, source="Day shift operator")
        add("A-OPS-0003", at(30), "operator_log", "shift_check", status="normal",
            subject="overall", text=normal_log, source="Night shift operator")
        add("A-LAB-0001", at(40), "lab", "oil_iron_ppm", 86, "ppm",
            text="Oil sample from bearing housing: iron 86 ppm.", source="Site laboratory")
        add("A-OPS-0004", at(44), "operator_log", "shift_check", status="normal",
            subject="overall",
            text="Shift handover: P-301 running normally, no unusual noise reported.",
            source="Day shift operator")
        add("A-INS-0001", at(45), "inspection", "handheld_vibration_mm_s", 8.1, "mm/s",
            text="Route inspection with handheld analyser: 8.1 mm/s at drive end.",
            source="Reliability technician")
        add("A-INS-0002", at(46), "inspection", "thermal_check", status="normal",
            subject="bearing_temp_c",
            text="Thermal camera round: bearing housing temperature looks normal.",
            source="Reliability technician")
        add("A-EVT-0001", _iso(start + timedelta(hours=47, minutes=10)), "event", "trip",
            status="abnormal", subject="overall",
            text="P-301 tripped on high vibration alarm (DCS).", source="DCS alarm log")
    else:
        add("B-MNT-0001", "2026-10-09T10:00:00", "maintenance", "lubrication",
            text="Routine bearing lubrication completed (WO-48377).", source="Maintenance team")
        add("B-CAL-0001", "2024-08-15T09:00:00", "calibration", "vib_sensor_cal",
            text="Vibration transmitter calibrated, as-found within tolerance.",
            source="Instrument workshop")
        add("B-OPS-0001", at(6), "operator_log", "shift_check", status="normal",
            subject="overall", text=normal_log, source="Night shift operator")
        add("B-OPS-0002", at(18), "operator_log", "shift_check", status="normal",
            subject="overall", text=normal_log, source="Day shift operator")
        add("B-OPS-0003", at(33), "operator_log", "shift_check", status="normal",
            subject="overall",
            text="Shift check: P-301 sounds and feels normal despite vibration alarm.",
            source="Night shift operator")
        add("B-INS-0001", at(34), "inspection", "handheld_vibration_mm_s", 2.7, "mm/s",
            text="Route inspection with handheld analyser: 2.7 mm/s at drive end.",
            source="Reliability technician")
        add("B-INS-0002", at(36), "inspection", "thermal_check", status="normal",
            subject="bearing_temp_c",
            text="Thermal camera round: bearing housing temperature looks normal.",
            source="Reliability technician")
        add("B-LAB-0001", at(36), "lab", "oil_iron_ppm", 14, "ppm",
            text="Oil sample from bearing housing: iron 14 ppm.", source="Site laboratory")
        add("B-EVT-0001", _iso(start + timedelta(hours=47, minutes=10)), "event", "trip",
            status="abnormal", subject="overall",
            text="P-301 tripped on high vibration alarm (DCS).", source="DCS alarm log")

    out.sort(key=lambda o: (o.timestamp, o.record_id))
    return out


def scenario_index() -> dict:
    return {
        "_comment": "Synthetic demo scenarios. All data is fictional.",
        "scenarios": [
            {
                "id": sid,
                "title": spec["title"],
                "asset_id": ASSET_ID,
                "asset_name": ASSET_NAME,
                "summary": spec["summary"],
                "file": f"scenario_{sid}.csv",
            }
            for sid, spec in SCENARIOS.items()
        ],
    }


def write_all(target: Path = SCENARIO_DIR) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for sid in SCENARIOS:
        p = target / f"scenario_{sid}.csv"
        write_observations_csv(generate_scenario(sid), p)
        paths.append(p)
    idx = target / "index.json"
    idx.write_text(json.dumps(scenario_index(), indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    paths.append(idx)
    return paths


if __name__ == "__main__":
    for p in write_all():
        print("wrote", p)
