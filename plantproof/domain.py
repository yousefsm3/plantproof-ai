"""Domain models and configuration loading for PlantProof AI.

Everything here is plain Python (standard library only) so it can be
tested anywhere, without Streamlit installed.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_DIR = DATA_DIR / "scenarios"
HYPOTHESES_PATH = CONFIG_DIR / "hypotheses.json"
COST_PATH = CONFIG_DIR / "cost_assumptions.json"
SCENARIO_INDEX_PATH = SCENARIO_DIR / "index.json"

ALLOWED_OPS = (">", ">=", "<", "<=", "==")
SOURCE_TYPES = ("sensor", "operator_log", "inspection", "lab", "calibration",
                "maintenance", "event")

OBS_FIELDS = ("record_id", "scenario_id", "timestamp", "asset_id", "source_type",
              "parameter", "value", "unit", "status", "subject", "text", "source",
              "hypothetical")


class ConfigError(ValueError):
    """Raised when a configuration file is missing or invalid."""


# --------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """One source record. Frozen: it can never be changed after creation."""

    record_id: str
    scenario_id: str
    timestamp: str          # ISO 8601, e.g. 2026-10-13T23:10:00
    asset_id: str
    source_type: str        # one of SOURCE_TYPES
    parameter: str          # e.g. vibration_mm_s, thermal_check
    value: float | None = None
    unit: str = ""
    status: str | None = None    # "normal" / "abnormal" for qualitative claims
    subject: str | None = None   # parameter a claim is about, or "overall"
    text: str = ""
    source: str = ""             # system or role, never a personal name
    hypothetical: bool = False   # True only for What If records

    @property
    def ts(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)

    @property
    def evidence_key(self) -> str:
        return f"{self.source_type}:{self.parameter}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Observation":
        """Build from a dict or a CSV row (where everything is a string)."""
        def opt_str(v: Any) -> str | None:
            if v is None:
                return None
            v = str(v).strip()
            return v or None

        value = raw.get("value")
        if value is None or (isinstance(value, str) and value.strip() == ""):
            value = None
        else:
            value = float(value)
        hyp = raw.get("hypothetical", False)
        if isinstance(hyp, str):
            hyp = hyp.strip().lower() in ("true", "1", "yes")
        obs = cls(
            record_id=str(raw["record_id"]).strip(),
            scenario_id=str(raw["scenario_id"]).strip(),
            timestamp=str(raw["timestamp"]).strip(),
            asset_id=str(raw.get("asset_id", "")).strip(),
            source_type=str(raw["source_type"]).strip(),
            parameter=str(raw["parameter"]).strip(),
            value=value,
            unit=str(raw.get("unit") or ""),
            status=opt_str(raw.get("status")),
            subject=opt_str(raw.get("subject")),
            text=str(raw.get("text") or ""),
            source=str(raw.get("source") or ""),
            hypothetical=bool(hyp),
        )
        obs.ts  # validates the timestamp format
        if obs.source_type not in SOURCE_TYPES:
            raise ValueError(f"Unknown source_type '{obs.source_type}' in {obs.record_id}")
        return obs


def read_observations_csv(path: Path) -> list[Observation]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Observation.from_dict(row) for row in csv.DictReader(fh)]


def write_observations_csv(observations: Iterable[Observation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OBS_FIELDS, lineterminator="\n")
        writer.writeheader()
        for obs in observations:
            row = obs.to_dict()
            row["value"] = "" if obs.value is None else repr(obs.value)
            row["status"] = obs.status or ""
            row["subject"] = obs.subject or ""
            row["hypothetical"] = "true" if obs.hypothetical else "false"
            writer.writerow(row)


def load_scenario_index(path: Path = SCENARIO_INDEX_PATH) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["scenarios"]


# --------------------------------------------------------------------------
# Findings and analysis results
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """A single traceable statement produced by the engine."""

    finding_id: str
    kind: str                       # contradiction | missing | support | refute
    title: str
    detail: str
    record_ids: tuple[str, ...] = ()
    hypothesis_ids: tuple[str, ...] = ()
    severity: str = "medium"        # low | medium | high
    key: str = ""                   # stable key used by the Blind Test

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["record_ids"] = list(self.record_ids)
        d["hypothesis_ids"] = list(self.hypothesis_ids)
        return d


@dataclass
class HypothesisAssessment:
    hypothesis_id: str
    name: str
    support_score: float
    support_possible: float
    refute_score: float
    support_ratio: float
    coverage: float
    contested_factor: float
    confidence: float
    confidence_label: str
    rank: int = 0
    supporting: list[Finding] = field(default_factory=list)
    refuting: list[Finding] = field(default_factory=list)
    missing: list[Finding] = field(default_factory=list)
    recommended_actions: tuple[str, ...] = ()

    @property
    def record_ids(self) -> list[str]:
        ids: list[str] = []
        for f in self.supporting + self.refuting + self.missing:
            for rid in f.record_ids:
                if rid not in ids:
                    ids.append(rid)
        return ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "name": self.name,
            "support_score": self.support_score,
            "support_possible": self.support_possible,
            "refute_score": self.refute_score,
            "support_ratio": self.support_ratio,
            "coverage": self.coverage,
            "contested_factor": self.contested_factor,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "rank": self.rank,
            "supporting": [f.to_dict() for f in self.supporting],
            "refuting": [f.to_dict() for f in self.refuting],
            "missing": [f.to_dict() for f in self.missing],
            "recommended_actions": list(self.recommended_actions),
        }


@dataclass
class AnalysisResult:
    scenario_id: str
    record_count: int
    window_start: str
    window_end: str
    assessments: list[HypothesisAssessment]
    contradictions: list[Finding]
    missing: list[Finding]

    @property
    def top(self) -> HypothesisAssessment | None:
        return self.assessments[0] if self.assessments else None

    def assessment(self, hypothesis_id: str) -> HypothesisAssessment:
        for a in self.assessments:
            if a.hypothesis_id == hypothesis_id:
                return a
        raise KeyError(hypothesis_id)

    def all_findings(self) -> list[Finding]:
        out = list(self.contradictions) + list(self.missing)
        for a in self.assessments:
            out += a.supporting + a.refuting
        return out

    def findings_for_record(self, record_id: str) -> list[Finding]:
        return [f for f in self.all_findings() if record_id in f.record_ids]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "record_count": self.record_count,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "assessments": [a.to_dict() for a in self.assessments],
            "contradictions": [f.to_dict() for f in self.contradictions],
            "missing": [f.to_dict() for f in self.missing],
        }


# --------------------------------------------------------------------------
# Engine configuration (config/hypotheses.json)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Condition:
    source_type: str
    parameter: str
    op: str
    threshold: float

    @property
    def key(self) -> str:
        return f"{self.source_type}:{self.parameter}"

    def describe(self) -> str:
        return f"{self.parameter} {self.op} {self.threshold:g}"


@dataclass(frozen=True)
class Rule:
    label: str
    weight: float
    conditions: tuple[Condition, ...]
    mode: str = "any"        # any: at least one match; all: every record matches
    window_h: float = 1.0    # for multi-condition rules: records must co-occur


@dataclass(frozen=True)
class RequiredEvidence:
    source_type: str
    parameter: str
    label: str
    max_age_days: float | None = None

    @property
    def key(self) -> str:
        return f"{self.source_type}:{self.parameter}"


@dataclass(frozen=True)
class Hypothesis:
    id: str
    name: str
    description: str
    supports: tuple[Rule, ...]
    refutes: tuple[Rule, ...]
    required: tuple[RequiredEvidence, ...]
    recommended_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlarmLimit:
    parameter: str
    alarm: float
    direction: str   # high | low
    unit: str = ""

    def breached(self, value: float | None) -> bool:
        if value is None:
            return False
        return value > self.alarm if self.direction == "high" else value < self.alarm


@dataclass(frozen=True)
class CrossCheck:
    label: str
    reference_parameter: str
    compare_parameter: str
    window_h: float
    tolerance_pct: float


@dataclass(frozen=True)
class EngineConfig:
    hypotheses: tuple[Hypothesis, ...]
    limits: dict[str, AlarmLimit]
    claim_window_h: float
    cross_checks: tuple[CrossCheck, ...]
    contested_penalty: float
    min_contested_factor: float
    coverage_floor: float
    high_threshold: float
    medium_threshold: float

    def hypothesis(self, hypothesis_id: str) -> Hypothesis:
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        raise KeyError(hypothesis_id)

    def required_evidence_catalogue(self) -> dict[str, str]:
        """All evidence keys any hypothesis requires -> human label."""
        out: dict[str, str] = {}
        for h in self.hypotheses:
            for r in h.required:
                out.setdefault(r.key, r.label)
        return out


def _parse_condition(raw: dict[str, Any], where: str) -> Condition:
    for k in ("source_type", "parameter", "op", "threshold"):
        if k not in raw:
            raise ConfigError(f"{where}: condition missing '{k}'")
    if raw["op"] not in ALLOWED_OPS:
        raise ConfigError(f"{where}: op '{raw['op']}' not in {ALLOWED_OPS}")
    if raw["source_type"] not in SOURCE_TYPES:
        raise ConfigError(f"{where}: unknown source_type '{raw['source_type']}'")
    return Condition(raw["source_type"], raw["parameter"], raw["op"], float(raw["threshold"]))


def _parse_rule(raw: dict[str, Any], where: str) -> Rule:
    label = raw.get("label") or where
    weight = float(raw.get("weight", 1))
    if weight <= 0:
        raise ConfigError(f"{where}: weight must be positive")
    mode = raw.get("mode", "any")
    if mode not in ("any", "all"):
        raise ConfigError(f"{where}: mode must be 'any' or 'all'")
    if "conditions" in raw:
        conds = tuple(_parse_condition(c, where) for c in raw["conditions"])
    else:
        conds = (_parse_condition(raw, where),)
    if not conds:
        raise ConfigError(f"{where}: rule has no conditions")
    if mode == "all" and len(conds) > 1:
        raise ConfigError(f"{where}: mode 'all' supports a single condition only")
    return Rule(label, weight, conds, mode, float(raw.get("window_h", 1.0)))


def parse_engine_config(raw: dict[str, Any]) -> EngineConfig:
    hyps = []
    seen = set()
    for i, h in enumerate(raw.get("hypotheses", [])):
        hid = h.get("id")
        if not hid or hid in seen:
            raise ConfigError(f"hypothesis #{i}: missing or duplicate id")
        seen.add(hid)
        supports = tuple(_parse_rule(r, f"{hid}.supports[{j}]") for j, r in enumerate(h.get("supports", [])))
        if not supports:
            raise ConfigError(f"{hid}: at least one supporting rule is required")
        refutes = tuple(_parse_rule(r, f"{hid}.refutes[{j}]") for j, r in enumerate(h.get("refutes", [])))
        required = tuple(
            RequiredEvidence(r["source_type"], r["parameter"], r.get("label", r["parameter"]),
                             r.get("max_age_days"))
            for r in h.get("required_evidence", [])
        )
        hyps.append(Hypothesis(hid, h.get("name", hid), h.get("description", ""),
                               supports, refutes, required,
                               tuple(h.get("recommended_actions", []))))
    if not hyps:
        raise ConfigError("No hypotheses configured")

    limits = {}
    for p, lim in raw.get("alarm_limits", {}).items():
        if lim.get("direction") not in ("high", "low"):
            raise ConfigError(f"alarm_limits.{p}: direction must be high or low")
        limits[p] = AlarmLimit(p, float(lim["alarm"]), lim["direction"], lim.get("unit", ""))

    cr = raw.get("contradiction_rules", {})
    checks = tuple(
        CrossCheck(c.get("label", "Cross-check"), c["reference_parameter"],
                   c["compare_parameter"], float(c.get("window_h", 1)),
                   float(c["tolerance_pct"]))
        for c in cr.get("cross_checks", [])
    )
    sc = raw.get("scoring", {})
    cfg = EngineConfig(
        hypotheses=tuple(hyps),
        limits=limits,
        claim_window_h=float(cr.get("claim_window_h", 2)),
        cross_checks=checks,
        contested_penalty=float(sc.get("contested_penalty", 0.9)),
        min_contested_factor=float(sc.get("min_contested_factor", 0.7)),
        coverage_floor=float(sc.get("coverage_floor", 0.5)),
        high_threshold=float(sc.get("high_threshold", 0.6)),
        medium_threshold=float(sc.get("medium_threshold", 0.3)),
    )
    for name in ("contested_penalty", "min_contested_factor", "coverage_floor"):
        v = getattr(cfg, name)
        if not 0 <= v <= 1:
            raise ConfigError(f"scoring.{name} must be between 0 and 1")
    return cfg


def load_engine_config(path: Path = HYPOTHESES_PATH) -> EngineConfig:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    return parse_engine_config(raw)
