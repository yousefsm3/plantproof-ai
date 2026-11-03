"""AI early warning: an unsupervised model that learns how the pump normally behaves.

Method (transparent, no external AI service):
1. Take the first `train_hours` of hourly sensor readings as the "healthy" baseline.
2. Learn each sensor's normal level and spread, and how the sensors move together
   (a shrunk covariance matrix, so a small baseline still gives a stable model).
3. Score every hour by its Mahalanobis distance from that baseline: how unusual the whole
   set of readings is, taking the sensors' normal relationships into account.
4. The alert threshold is learned from the baseline itself (the largest baseline score
   times a safety margin). An hour is flagged when it, and the hour after it, exceed it.
5. For each flagged hour, report which sensors drive the score (their z-scores), so the
   warning can be checked against the raw records.

The lead time is the gap between the model's first warning and the first reading that
crossed a configured alarm limit. Nothing here changes the observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .domain import Observation

SENSOR_ORDER = ("vibration_mm_s", "bearing_temp_c", "seal_pot_level_pct", "suction_pressure_bar",
                "discharge_pressure_bar", "flow_m3h", "motor_current_a")


@dataclass
class HourScore:
    timestamp: str
    score: float
    flagged: bool
    drivers: list[tuple[str, float]]          # (parameter, z-score), strongest first
    record_ids: list[str]                     # sensor records of this hour


@dataclass
class EarlyWarning:
    parameters: list[str]
    train_hours: int
    threshold: float
    hours: list[HourScore]
    first_warning: HourScore | None
    first_alarm: tuple[str, str, str] | None  # (timestamp, parameter, record_id)
    lead_hours: float | None
    baseline: dict[str, tuple[float, float]] = field(default_factory=dict)  # param -> (mean, sd)

    @property
    def warned_before_alarm(self) -> bool:
        return self.lead_hours is not None and self.lead_hours > 0


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _first_alarm(observations: list[Observation], limits: dict) -> tuple[str, str, str] | None:
    """limits: parameter -> AlarmLimit (from EngineConfig.limits)."""
    hits = []
    for o in observations:
        lim = limits.get(o.parameter)
        if o.source_type != "sensor" or lim is None or o.value is None:
            continue
        if (o.value > lim.alarm) if lim.direction == "high" else (o.value < lim.alarm):
            hits.append((o.timestamp, o.parameter, o.record_id))
    return min(hits) if hits else None


def detect(observations: list[Observation], limits: dict, train_hours: int = 18,
           shrink: float = 0.5, margin: float = 1.5, consecutive: int = 2) -> EarlyWarning | None:
    """Fit the baseline on the first hours and score every hour. None if data is too thin."""
    table: dict[str, dict[str, Observation]] = {}
    for o in observations:
        if o.source_type == "sensor" and o.value is not None:
            table.setdefault(o.timestamp, {})[o.parameter] = o
    params = [p for p in SENSOR_ORDER if all(p in row for row in table.values())]
    stamps = sorted(table)
    if len(params) < 2 or len(stamps) < train_hours + consecutive:
        return None

    X = np.array([[table[t][p].value for p in params] for t in stamps], dtype=float)
    train = X[:train_hours]
    mean = train.mean(axis=0)
    sd = train.std(axis=0, ddof=1)
    sd[sd == 0] = 1e-9
    Z = (X - mean) / sd
    corr = np.corrcoef(Z[:train_hours], rowvar=False)
    corr = np.nan_to_num(corr)
    cov = (1 - shrink) * corr + shrink * np.eye(len(params))
    inv = np.linalg.inv(cov)
    scores = np.sqrt(np.einsum("ij,jk,ik->i", Z, inv, Z) / len(params))
    threshold = float(scores[:train_hours].max() * margin)

    over = scores > threshold
    hours = []
    for i, t in enumerate(stamps):
        flagged = bool(i >= train_hours and all(over[i:i + consecutive])
                       and i + consecutive <= len(stamps))
        order = np.argsort(-np.abs(Z[i]))
        drivers = [(params[j], round(float(Z[i][j]), 1)) for j in order if abs(Z[i][j]) >= 3][:3]
        hours.append(HourScore(t, round(float(scores[i]), 2), flagged, drivers,
                               [table[t][p].record_id for p in params]))
    first = next((h for h in hours if h.flagged), None)
    alarm = _first_alarm(observations, limits)
    lead = None
    if first and alarm:
        lead = (_ts(alarm[0]) - _ts(first.timestamp)).total_seconds() / 3600
    return EarlyWarning(params, train_hours, round(threshold, 2), hours, first, alarm,
                        lead, {p: (round(float(mean[j]), 2), round(float(sd[j]), 3))
                              for j, p in enumerate(params)})
