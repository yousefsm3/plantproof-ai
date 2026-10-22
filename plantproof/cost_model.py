"""Transparent low / base / high cost impact simulator.

Formula for each case (low, base and high are computed independently, each
using that case's inputs - a consistent-scenario approach, not statistics):

    Lost production = downtime_hours x lost_margin_per_hour
    Repair labour   = labour_hours  x labour_rate_per_hour
    Parts           = parts
    Total           = Lost production + Repair labour + Parts

The confidence-weighted base cost blends every hypothesis's base total using
the engine's confidences normalised to sum to 1.
All figures are illustrative and synthetic.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import COST_PATH, ConfigError, HypothesisAssessment

CASES = ("low", "base", "high")


@dataclass
class CostLine:
    component: str
    formula: str
    low: float
    base: float
    high: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class CostEstimate:
    hypothesis_id: str
    description: str
    currency_symbol: str
    lines: list[CostLine]
    inputs: dict[str, dict[str, float]]

    @property
    def totals(self) -> dict[str, float]:
        return {c: round(sum(getattr(line, c) for line in self.lines), 2) for c in CASES}

    def to_dict(self) -> dict[str, Any]:
        return {"hypothesis_id": self.hypothesis_id, "description": self.description,
                "currency_symbol": self.currency_symbol,
                "lines": [line.to_dict() for line in self.lines],
                "inputs": self.inputs, "totals": self.totals}


def _check_range(name: str, r: Any) -> dict[str, float]:
    if not isinstance(r, dict) or any(c not in r for c in CASES):
        raise ConfigError(f"{name}: needs low, base and high values")
    vals = {c: float(r[c]) for c in CASES}
    if any(v < 0 for v in vals.values()):
        raise ConfigError(f"{name}: values must not be negative")
    if not vals["low"] <= vals["base"] <= vals["high"]:
        raise ConfigError(f"{name}: values must satisfy low <= base <= high")
    return vals


def validate_assumptions(raw: dict[str, Any]) -> dict[str, Any]:
    out = {
        "currency": raw.get("currency", "GBP"),
        "currency_symbol": raw.get("currency_symbol", "£"),
        "lost_margin_per_hour": _check_range("lost_margin_per_hour", raw.get("lost_margin_per_hour")),
        "labour_rate_per_hour": _check_range("labour_rate_per_hour", raw.get("labour_rate_per_hour")),
        "profiles": {},
    }
    profiles = raw.get("profiles") or {}
    if not profiles:
        raise ConfigError("cost profiles are missing")
    for hid, prof in profiles.items():
        out["profiles"][hid] = {
            "description": prof.get("description", ""),
            "downtime_hours": _check_range(f"{hid}.downtime_hours", prof.get("downtime_hours")),
            "labour_hours": _check_range(f"{hid}.labour_hours", prof.get("labour_hours")),
            "parts": _check_range(f"{hid}.parts", prof.get("parts")),
        }
    return out


def load_cost_assumptions(path: Path = COST_PATH) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return validate_assumptions(json.load(fh))
    except FileNotFoundError as exc:
        raise ConfigError(f"Cost file not found: {path}") from exc


def with_overrides(assumptions: dict[str, Any], hypothesis_id: str,
                   overrides: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Return a validated copy with user overrides. The original is unchanged.

    overrides keys: lost_margin_per_hour, labour_rate_per_hour (global) or
    downtime_hours, labour_hours, parts (for the given hypothesis).
    """
    new = copy.deepcopy(assumptions)
    for key, rng in overrides.items():
        if key in ("lost_margin_per_hour", "labour_rate_per_hour"):
            new[key] = dict(rng)
        elif key in ("downtime_hours", "labour_hours", "parts"):
            new["profiles"][hypothesis_id][key] = dict(rng)
        else:
            raise ConfigError(f"Unknown cost input: {key}")
    return validate_assumptions(new)


def estimate(hypothesis_id: str, assumptions: dict[str, Any]) -> CostEstimate:
    try:
        prof = assumptions["profiles"][hypothesis_id]
    except KeyError as exc:
        raise ConfigError(f"No cost profile for hypothesis '{hypothesis_id}'") from exc
    sym = assumptions["currency_symbol"]
    margin, rate = assumptions["lost_margin_per_hour"], assumptions["labour_rate_per_hour"]
    dt, lh, parts = prof["downtime_hours"], prof["labour_hours"], prof["parts"]

    lines = [
        CostLine("Lost production", f"downtime hours × lost margin per hour ({sym}/h)",
                 *[round(dt[c] * margin[c], 2) for c in CASES]),
        CostLine("Repair labour", f"labour hours × labour rate ({sym}/h)",
                 *[round(lh[c] * rate[c], 2) for c in CASES]),
        CostLine("Parts", "parts and materials", *[round(parts[c], 2) for c in CASES]),
    ]
    inputs = {"downtime_hours": dt, "lost_margin_per_hour": margin,
              "labour_hours": lh, "labour_rate_per_hour": rate, "parts": parts}
    return CostEstimate(hypothesis_id, prof["description"], sym, lines, inputs)


def weighted_estimate(assessments: list[HypothesisAssessment],
                      assumptions: dict[str, Any]) -> dict[str, Any] | None:
    """Confidence-weighted base cost across hypotheses. None if all confidences are 0."""
    usable = [a for a in assessments if a.hypothesis_id in assumptions["profiles"]]
    total_conf = sum(a.confidence for a in usable)
    if total_conf <= 0:
        return None
    rows, value = [], 0.0
    for a in usable:
        w = a.confidence / total_conf
        base = estimate(a.hypothesis_id, assumptions).totals["base"]
        value += w * base
        rows.append({"hypothesis": a.name, "confidence": a.confidence,
                     "weight": round(w, 3), "base_total": base,
                     "contribution": round(w * base, 2)})
    return {"value": round(value, 2), "rows": rows}


def format_money(value: float, symbol: str = "£") -> str:
    return f"{symbol}{value:,.0f}"
