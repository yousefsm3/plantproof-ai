"""AI sensor trust: is the problem in the machine, or in the instrument that reports it?

A failing machine rarely changes only one measurement. A worn bearing raises vibration and
bearing temperature together; a leaking seal moves the seal pot level and often the
pressures. A drifting or faulty transmitter, on the other hand, changes its own reading while
every physically related measurement stays where it was.

Method (transparent, runs inside the app, no external AI service):
1. Take the first `train_hours` of hourly readings as the healthy baseline.
2. For every sensor, learn a ridge regression that predicts it from all the other sensors
   on that baseline: the AI learns how the sensors normally move together.
3. In the assessment window (the last `window` hours) compare each sensor with
   a) its own baseline level (how far it has moved: the "own" z-score) and
   b) what its peers say it should read (the "peer" z-score of the regression residual).
4. A sensor that has moved strongly while its peers predict it should not have moved, and
   while no peer has moved, is suspect. Several sensors moving together point to the machine.
5. Independent records are then weighed: a handheld reading of the same quantity, the
   calibration age of the transmitter, thermal checks and oil analysis.

The verdict is one of: machine, sensor, normal, undetermined. It is decision support for a
qualified engineer, not a diagnosis. Nothing here changes the observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .domain import Observation
from .early_warning import SENSOR_ORDER

MOVED_Z = 3.0          # a sensor has clearly left its baseline
PEER_Z = 3.0           # a sensor clearly disagrees with what its peers predict
CAL_MAX_DAYS = 365     # calibration older than this weakens trust in a transmitter

# a handheld or lab record that independently checks a sensor: record parameter -> sensor
INDEPENDENT_CHECKS = {"handheld_vibration_mm_s": "vibration_mm_s"}
CAL_PARAMS = {"vib_sensor_cal": "vibration_mm_s"}
LABELS = {"vibration_mm_s": "vibration", "bearing_temp_c": "bearing temperature",
          "seal_pot_level_pct": "seal pot level", "suction_pressure_bar": "suction pressure",
          "discharge_pressure_bar": "discharge pressure", "flow_m3h": "flow",
          "motor_current_a": "motor current"}
LABELS_AR = {"vibration_mm_s": "الاهتزاز", "bearing_temp_c": "حرارة المحمل",
             "seal_pot_level_pct": "مستوى خزان مانع التسرب", "suction_pressure_bar": "ضغط السحب",
             "discharge_pressure_bar": "ضغط الطرد", "flow_m3h": "التدفق",
             "motor_current_a": "تيار المحرك"}


def label(p: str) -> str:
    return LABELS.get(p, p)


@dataclass
class SensorView:
    parameter: str
    baseline_mean: float
    latest: float
    own_z: float            # how far it moved from its own baseline
    peer_z: float           # how far it is from what the other sensors predict
    moved: bool
    disagrees: bool
    record_ids: list[str]


@dataclass
class Clue:
    text: str
    text_ar: str
    points_to: str          # "sensor" or "machine"
    record_ids: list[str]


@dataclass
class TrustVerdict:
    verdict: str                     # machine | sensor | normal | undetermined
    headline: str
    headline_ar: str
    suspect: str | None              # the sensor in question, when there is one
    sensors: list[SensorView]
    clues: list[Clue] = field(default_factory=list)
    support: str = "Low"             # Low | Medium | High: strength of the evidence, not a probability
    window: tuple[str, str] | None = None
    train_hours: int = 0
    series: dict[str, list] = field(default_factory=dict)  # suspect/lead sensor: time, actual, peer-predicted
    method_note: str = ("Ridge regression of each sensor on its peers, learned from the "
                        "healthy baseline, plus independent checks.")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    Xb = np.hstack([X, np.ones((len(X), 1))])
    reg = alpha * np.eye(Xb.shape[1])
    reg[-1, -1] = 0.0
    return np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)


def assess(observations: list[Observation], train_hours: int = 18,
           window: int = 6) -> TrustVerdict:
    table: dict[str, dict[str, Observation]] = {}
    for o in observations:
        if o.source_type == "sensor" and o.value is not None:
            table.setdefault(o.timestamp, {})[o.parameter] = o
    params = [p for p in SENSOR_ORDER if table and all(p in row for row in table.values())]
    stamps = sorted(table)
    if len(params) < 3 or len(stamps) < train_hours + window:
        return TrustVerdict("undetermined", "Not enough sensor history to judge",
                            "لا توجد قراءات كافية للحكم", None, [], support="Low",
                            train_hours=train_hours)

    X = np.array([[table[t][p].value for p in params] for t in stamps], dtype=float)
    mean, sd = X[:train_hours].mean(axis=0), X[:train_hours].std(axis=0, ddof=1)
    sd[sd == 0] = 1e-9
    Z = (X - mean) / sd
    win = slice(len(stamps) - window, len(stamps))

    views: list[SensorView] = []
    series_all: dict[str, tuple] = {}
    for j, p in enumerate(params):
        others = [k for k in range(len(params)) if k != j]
        coef = _ridge(Z[:train_hours][:, others], Z[:train_hours, j], alpha=8.0)
        pred = np.hstack([Z[:, others], np.ones((len(Z), 1))]) @ coef
        resid = Z[:, j] - pred
        rsd = max(float(resid[:train_hours].std(ddof=1)), 0.5)   # floor: a small baseline overfits
        series_all[p] = (list(stamps), [float(v) for v in X[:, j]],
                         [float(mean[j] + sd[j] * v) for v in pred])
        own = float(np.median(Z[win, j]))
        peer = float(np.median(resid[win]) / rsd)
        views.append(SensorView(p, round(float(mean[j]), 2), round(float(X[-1, j]), 2),
                                round(own, 1), round(peer, 1), abs(own) >= MOVED_Z,
                                abs(own) >= MOVED_Z and abs(peer) >= PEER_Z, [table[stamps[-1]][p].record_id]))

    moved = [v for v in views if v.moved]
    by_param = {v.parameter: v for v in views}
    clues: list[Clue] = []
    window_span = (stamps[win][0], stamps[-1])

    if not moved:
        return TrustVerdict("normal", "All sensors agree with each other and with the baseline",
                            "كل الحساسات متوافقة مع بعضها ومع الوضع الطبيعي", None, views,
                            support="Medium", window=window_span, train_hours=train_hours)

    lead = max(moved, key=lambda v: abs(v.own_z))
    names = ", ".join(label(v.parameter) for v in moved)
    if len(moved) >= 2:
        clues.append(Clue(f"{len(moved)} related measurements moved together ({names}): a real change "
                          "in the machine usually shows on more than one measurement.",
                          f"{len(moved)} حساسات مرتبطة تغيّرت معًا: التغير الحقيقي في المعدة "
                          "يظهر عادة في أكثر من قراءة.", "machine",
                          [i for v in moved for i in v.record_ids]))
    else:
        quiet = [v for v in views if v is not lead]
        clues.append(Clue(f"Only {label(lead.parameter)} moved (z {lead.own_z:+.1f}). The other "
                          f"{len(quiet)} sensors predict it should read near normal "
                          f"(peer disagreement z {lead.peer_z:+.1f}).",
                          f"تغيّر حساس واحد فقط ({LABELS_AR.get(lead.parameter, lead.parameter)})، وباقي الحساسات تتوقع أن "
                          "تكون قراءته قريبة من الطبيعي.", "sensor", lead.record_ids))

    # independent checks of every sensor that moved
    for v in moved:
        for o in observations:
            if INDEPENDENT_CHECKS.get(o.parameter) == v.parameter and o.value is not None:
                if abs(o.value - v.baseline_mean) <= abs(v.latest - o.value):
                    clues.append(Clue(f"Independent handheld reading {o.value:g} {o.unit} is close to "
                                      f"normal ({v.baseline_mean:g}), not to the transmitter "
                                      f"({v.latest:g}).",
                                      f"القراءة اليدوية المستقلة {o.value:g} قريبة من الطبيعي، وليست "
                                      "قريبة من قراءة الحساس.", "sensor", [o.record_id]))
                else:
                    clues.append(Clue(f"Independent handheld reading {o.value:g} {o.unit} confirms "
                                      "the transmitter.", "القراءة اليدوية المستقلة تؤكد قراءة الحساس.",
                                      "machine", [o.record_id]))
        cal = [o for o in observations if CAL_PARAMS.get(o.parameter) == v.parameter]
        if cal:
            last = max(cal, key=lambda o: o.timestamp)
            age = (_ts(stamps[-1]) - _ts(last.timestamp)).days
            if age > CAL_MAX_DAYS:
                clues.append(Clue(f"The {label(v.parameter)} transmitter was last calibrated {age} days ago "
                                  f"(over {CAL_MAX_DAYS}).", f"آخر معايرة للحساس قبل {age} يومًا.",
                                  "sensor", [last.record_id]))
            else:
                clues.append(Clue(f"The {label(v.parameter)} transmitter was calibrated {age} days ago "
                                  "(in date).", f"الحساس معايَر قبل {age} يومًا (ضمن المدة).",
                                  "machine", [last.record_id]))
    if len(moved) == 1:   # a single moved sensor: does an independent physical check agree?
        for o in observations:
            if (o.source_type == "inspection" and o.parameter == "thermal_check"
                    and (o.status or "").lower() == "normal"):
                clues.append(Clue("Thermal camera round found the bearing housing normal.",
                                  "فحص الكاميرا الحرارية وجد حرارة المحمل طبيعية.", "sensor",
                                  [o.record_id]))

    def _with_series(v: TrustVerdict) -> TrustVerdict:
        key = v.suspect or lead.parameter
        t, actual, predicted = series_all[key]
        v.series = {"parameter": key, "time": t, "actual": actual, "predicted": predicted}
        return v

    to_sensor = sum(c.points_to == "sensor" for c in clues)
    to_machine = sum(c.points_to == "machine" for c in clues)
    if to_sensor > to_machine:
        support = "High" if to_sensor >= 3 and to_machine == 0 else "Medium"
        return _with_series(TrustVerdict("sensor", f"Check the {label(lead.parameter)} sensor before touching the machine",
                            "افحص الحساس قبل أي تدخل في المعدة", lead.parameter, views, clues,
                            support, window_span, train_hours))
    if to_machine > to_sensor:
        support = "High" if to_machine >= 2 and to_sensor == 0 else "Medium"
        return _with_series(TrustVerdict("machine", "The change is real: several independent signals agree",
                            "التغير حقيقي في المعدة: عدة مؤشرات مستقلة متفقة", None, views, clues,
                            support, window_span, train_hours))
    return _with_series(TrustVerdict("undetermined", "The signals conflict: collect one more independent check",
                        "المؤشرات متعارضة: اجمع فحصًا مستقلًا إضافيًا", lead.parameter, views,
                        clues, "Low", window_span, train_hours))
