"""What If simulations.

Changes are applied to a *copy* of the observations. The originals are never
modified: Observation objects are frozen, the input list is never touched,
and every run reports a fingerprint of the originals taken before and after
the simulation so the dashboard can prove they are unchanged.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .domain import AnalysisResult, EngineConfig, Observation
from .evidence_engine import analyse

CHANGE_KINDS = ("exclude_source", "exclude_records", "override_value",
                "scale_parameter", "add_record")

# Templates for hypothetical evidence the user can add in the dashboard.
EVIDENCE_TEMPLATES: dict[str, dict[str, Any]] = {
    "alignment_offset_mm": {"source_type": "inspection", "unit": "mm", "default": 0.03,
                            "label": "Laser alignment check (offset, mm)"},
    "strainer_dp_bar": {"source_type": "inspection", "unit": "bar", "default": 0.2,
                        "label": "Suction strainer check (differential pressure, bar)"},
    "handheld_vibration_mm_s": {"source_type": "inspection", "unit": "mm/s", "default": 3.0,
                                "label": "Handheld vibration check (mm/s)"},
    "oil_iron_ppm": {"source_type": "lab", "unit": "ppm", "default": 15.0,
                     "label": "Oil analysis (iron, ppm)"},
    "vib_sensor_cal": {"source_type": "calibration", "unit": "", "default": None,
                       "label": "New vibration sensor calibration certificate"},
    "discharge_pressure_bar": {"source_type": "sensor", "unit": "bar", "default": 2.5,
                               "label": "Discharge pressure reading (bar)"},
}


@dataclass(frozen=True)
class WhatIfChange:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        p = self.params
        if self.kind == "exclude_source":
            return f"Ignore all {p['source_type'].replace('_', ' ')} records"
        if self.kind == "exclude_records":
            return f"Ignore record(s) {', '.join(p['record_ids'])}"
        if self.kind == "override_value":
            return f"Set {p['record_id']} value to {p['value']:g}"
        if self.kind == "scale_parameter":
            return f"Multiply all {p['parameter']} readings by {p['factor']:g}"
        if self.kind == "add_record":
            val = "" if p.get("value") is None else f" = {p['value']:g}"
            return f"Add hypothetical {p['parameter']}{val}"
        return self.kind

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WhatIfChange":
        if raw.get("kind") not in CHANGE_KINDS:
            raise ValueError(f"Unknown change kind: {raw.get('kind')}")
        return cls(raw["kind"], dict(raw.get("params", {})))


def fingerprint(observations: Iterable[Observation]) -> str:
    """Short SHA-256 of the observations' content (order independent)."""
    rows = sorted(json.dumps(o.to_dict(), sort_keys=True) for o in observations)
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def apply_changes(observations: Iterable[Observation],
                  changes: Iterable[WhatIfChange]) -> list[Observation]:
    """Return a NEW list with the changes applied. Input is left untouched."""
    working = list(observations)  # shallow copy; items are immutable
    known = {o.record_id for o in working}
    end_ts = max((o.timestamp for o in working), default="2026-01-01T00:00:00")
    added = 0
    for ch in changes:
        p = ch.params
        if ch.kind == "exclude_source":
            working = [o for o in working if o.source_type != p["source_type"]]
        elif ch.kind == "exclude_records":
            missing = set(p["record_ids"]) - known
            if missing:
                raise ValueError(f"Unknown record(s): {', '.join(sorted(missing))}")
            drop = set(p["record_ids"])
            working = [o for o in working if o.record_id not in drop]
        elif ch.kind == "override_value":
            if p["record_id"] not in known:
                raise ValueError(f"Unknown record: {p['record_id']}")
            working = [dataclasses.replace(o, value=float(p["value"]), hypothetical=True)
                       if o.record_id == p["record_id"] else o for o in working]
        elif ch.kind == "scale_parameter":
            f = float(p["factor"])
            working = [dataclasses.replace(o, value=round(o.value * f, 2), hypothetical=True)
                       if o.parameter == p["parameter"] and o.value is not None else o
                       for o in working]
        elif ch.kind == "add_record":
            param = p["parameter"]
            tpl = EVIDENCE_TEMPLATES.get(param, {})
            added += 1
            value = p.get("value", tpl.get("default"))
            ref = working[0] if working else None
            working.append(Observation(
                record_id=f"WHATIF-{added:03d}",
                scenario_id=ref.scenario_id if ref else "",
                timestamp=p.get("timestamp") or end_ts,
                asset_id=ref.asset_id if ref else "",
                source_type=p.get("source_type") or tpl.get("source_type", "inspection"),
                parameter=param,
                value=None if value is None else float(value),
                unit=p.get("unit", tpl.get("unit", "")),
                text="Hypothetical record added in What If simulation",
                source="What If simulation",
                hypothetical=True,
            ))
        else:
            raise ValueError(f"Unknown change kind: {ch.kind}")
    return working


@dataclass
class WhatIfResult:
    changes: list[WhatIfChange]
    baseline: AnalysisResult
    scenario: AnalysisResult
    fingerprint_before: str
    fingerprint_after: str

    @property
    def originals_unchanged(self) -> bool:
        return self.fingerprint_before == self.fingerprint_after

    def comparison(self) -> list[dict[str, Any]]:
        rows = []
        for b in self.baseline.assessments:
            s = self.scenario.assessment(b.hypothesis_id)
            rows.append({
                "hypothesis_id": b.hypothesis_id,
                "hypothesis": b.name,
                "baseline_confidence": b.confidence,
                "scenario_confidence": s.confidence,
                "delta": round(s.confidence - b.confidence, 3),
                "baseline_rank": b.rank,
                "scenario_rank": s.rank,
            })
        return rows

    def set_changes(self) -> dict[str, list[str]]:
        def keys(fs):
            return {f.key for f in fs}
        bc, sc = keys(self.baseline.contradictions), keys(self.scenario.contradictions)
        bm, sm = keys(self.baseline.missing), keys(self.scenario.missing)
        return {
            "contradictions_resolved": sorted(bc - sc),
            "contradictions_new": sorted(sc - bc),
            "missing_resolved": sorted(bm - sm),
            "missing_new": sorted(sm - bm),
        }

    def summary(self) -> str:
        bt, st_ = self.baseline.top, self.scenario.top
        if bt is None or st_ is None:
            return "No hypotheses to compare."
        if bt.hypothesis_id == st_.hypothesis_id:
            return (f"Leading hypothesis unchanged: {st_.name} "
                    f"({bt.confidence:.0%} → {st_.confidence:.0%}).")
        return (f"Leading hypothesis changes from {bt.name} ({bt.confidence:.0%}) "
                f"to {st_.name} ({st_.confidence:.0%}).")

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "change_descriptions": [c.describe() for c in self.changes],
            "summary": self.summary(),
            "comparison": self.comparison(),
            "set_changes": self.set_changes(),
            "fingerprint_before": self.fingerprint_before,
            "fingerprint_after": self.fingerprint_after,
            "originals_unchanged": self.originals_unchanged,
        }


def run_whatif(observations: Iterable[Observation], config: EngineConfig,
               changes: Iterable[WhatIfChange]) -> WhatIfResult:
    originals = tuple(observations)
    changes = list(changes)
    before = fingerprint(originals)
    baseline = analyse(originals, config)
    scenario = analyse(apply_changes(originals, changes), config)
    after = fingerprint(originals)
    return WhatIfResult(changes, baseline, scenario, before, after)
