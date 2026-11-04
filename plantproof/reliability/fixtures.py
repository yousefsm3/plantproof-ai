"""Deterministic generator for the Reliability Brain's extra synthetic assets.

These files exist only to exercise the Brain on cases the original three scenarios do not
cover: a healthy pump (P-302), a pump with poor-quality records (P-303) and an asset type
the Brain does not support yet (K-101). All values are fictional.

Run:  python -m plantproof.reliability.fixtures   (rewrites data/reliability/*.csv)
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from ..domain import OBS_FIELDS, PROJECT_ROOT

OUT_DIR = PROJECT_ROOT / "data" / "reliability"
NORMAL = {   # parameter: (unit, mean, noise)
    "vibration_mm_s": ("mm/s", 2.9, 0.12),
    "bearing_temp_c": ("°C", 61.5, 0.6),
    "seal_pot_level_pct": ("%", 86.0, 0.5),
    "suction_pressure_bar": ("bar", 1.85, 0.03),
    "discharge_pressure_bar": ("bar", 4.5, 0.06),
    "flow_m3h": ("m³/h", 118.0, 1.6),
    "motor_current_a": ("A", 42.0, 0.4),
}


def _row(rid, sid, ts, asset, stype, param, value=None, unit="", status="", subject="",
         text="", source="") -> dict:
    return {"record_id": rid, "scenario_id": sid, "timestamp": ts, "asset_id": asset,
            "source_type": stype, "parameter": param,
            "value": "" if value is None else repr(round(value, 3)) if isinstance(value, float) else value,
            "unit": unit, "status": status, "subject": subject, "text": text, "source": source,
            "hypothetical": "false"}


def _sensors(asset, sid, start, hours, rng, prefix, skip=(), drift=None):
    rows, n = [], 0
    for h in range(hours):
        if h in skip:
            continue
        ts = (start + timedelta(hours=h)).isoformat()
        for p, (unit, mean, noise) in NORMAL.items():
            n += 1
            v = mean + rng.gauss(0, noise) + (drift(p, h) if drift else 0.0)
            rows.append(_row(f"{prefix}-SEN-{n:04d}", sid, ts, asset, "sensor", p, v, unit,
                             source="Online condition monitoring"))
    return rows


def p302_routine() -> list[dict]:
    """Healthy pump with complete supporting evidence: nothing should be flagged."""
    rng, start, sid, a = random.Random(3021), datetime(2026, 10, 28), "P302R", "P-302"
    rows = [
        _row("P302-CAL-0001", sid, "2026-06-03T09:00:00", a, "calibration", "vib_sensor_cal",
             text="Vibration transmitter calibrated, as-found within tolerance.", source="Instrument workshop"),
        _row("P302-MNT-0001", sid, "2026-10-21T10:00:00", a, "maintenance", "lubrication",
             text="Routine bearing lubrication completed (WO-50211).", source="Maintenance team"),
    ]
    rows += _sensors(a, sid, start, 48, rng, "P302")
    rows += [
        _row("P302-LAB-0001", sid, "2026-10-29T10:00:00", a, "lab", "oil_iron_ppm", 11.0, "ppm", source="Oil laboratory"),
        _row("P302-LAB-0002", sid, "2026-10-29T10:00:00", a, "lab", "oil_water_ppm", 110.0, "ppm", source="Oil laboratory"),
        _row("P302-LAB-0003", sid, "2026-10-29T10:00:00", a, "lab", "oil_particle_iso", 15.0, "ISO code", source="Oil laboratory"),
        _row("P302-LAB-0004", sid, "2026-10-29T10:00:00", a, "lab", "oil_viscosity_change_pct", 2.0, "%", source="Oil laboratory"),
        _row("P302-INS-0001", sid, "2026-10-29T14:00:00", a, "inspection", "handheld_vibration_mm_s", 2.8, "mm/s",
             text="Handheld check during reliability round.", source="Reliability technician"),
        _row("P302-INS-0002", sid, "2026-10-29T14:10:00", a, "inspection", "seal_leak_ml_min", 0.0, "ml/min",
             text="No visible seal leakage.", source="Reliability technician"),
        _row("P302-INS-0003", sid, "2026-10-29T14:20:00", a, "inspection", "alignment_offset_mm", 0.03, "mm",
             text="Laser alignment check within tolerance.", source="Reliability technician"),
        _row("P302-INS-0004", sid, "2026-10-29T14:30:00", a, "inspection", "strainer_dp_bar", 0.1, "bar",
             text="Suction strainer differential pressure normal.", source="Reliability technician"),
        _row("P302-OPS-0001", sid, "2026-10-29T08:00:00", a, "operator_log", "shift_check", status="normal",
             subject="overall", text="Pump running normally, no unusual noise.", source="Field operator"),
    ]
    return rows


def p303_poor_data() -> list[dict]:
    """Pump whose records have gaps, duplicates, conflicts, impossible values and bad rows."""
    rng, start, sid, a = random.Random(3031), datetime(2026, 10, 28), "P303Q", "P-303"
    rows = _sensors(a, sid, start, 48, rng, "P303", skip=range(10, 22),
                    drift=lambda p, h: 0.08 * max(0, h - 30) if p == "vibration_mm_s" else 0.0)
    by_id = {r["record_id"]: r for r in rows}
    first = rows[0]
    rows.append(dict(first))                                     # duplicate record id
    vib = next(r for r in rows if r["parameter"] == "vibration_mm_s" and r["timestamp"].endswith("T05:00:00"))
    rows.append({**vib, "record_id": "P303-SEN-9001", "value": "6.4"})   # conflicting measurement
    flow = next(r for r in rows if r["parameter"] == "flow_m3h" and r["timestamp"].endswith("T06:00:00"))
    by_id[flow["record_id"]]["value"] = "-5.0"                  # impossible negative flow
    lvl = next(r for r in rows if r["parameter"] == "seal_pot_level_pct" and r["timestamp"].endswith("T07:00:00"))
    by_id[lvl["record_id"]]["value"] = "140.0"                  # impossible level
    rows.append(_row("P303-SEN-9002", sid, "2026-13-40T99:00:00", a, "sensor", "vibration_mm_s", 3.0, "mm/s",
                     source="Online condition monitoring"))      # unparseable timestamp
    rows.append(_row("P303-SEN-9003", sid, "2026-10-29T03:00:00", a, "scada", "vibration_mm_s", 3.0, "mm/s",
                     source="Unknown export"))                    # unknown source type
    rows.append(_row("P303-OPS-0001", sid, "2026-10-29T20:00:00", a, "operator_log", "shift_check",
                     status="normal", subject="overall", text="Running OK.", source=""))  # no source
    return rows


def k101_routine() -> list[dict]:
    """A reciprocating compressor: the Brain has no examination profile for it yet."""
    rng, start, sid, a = random.Random(1011), datetime(2026, 10, 28), "K101R", "K-101"
    rows, n = [], 0
    for h in range(24):
        ts = (start + timedelta(hours=h)).isoformat()
        for p, unit, mean, noise in (("discharge_temp_c", "°C", 118.0, 1.0), ("rod_load_pct", "%", 64.0, 1.5)):
            n += 1
            rows.append(_row(f"K101-SEN-{n:04d}", sid, ts, a, "sensor", p, mean + rng.gauss(0, noise), unit,
                             source="Compressor monitoring"))
    return rows


FIXTURES = {"P-302_routine.csv": p302_routine, "P-303_poor_data.csv": p303_poor_data,
            "K-101_routine.csv": k101_routine}


def write_all(out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, make in FIXTURES.items():
        path = out_dir / name
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=OBS_FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(make())
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in write_all():
        print("wrote", p)
