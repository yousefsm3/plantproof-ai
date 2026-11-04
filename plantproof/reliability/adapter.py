"""Thin, read-only adapter between the Reliability Brain and the original platform.

Rules (enforced by tests):
- import only public names from the original package;
- never write to the original store, files or results;
- copy everything into the Brain's own frozen types;
- fingerprint the original observations before and after a run.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .. import advisor, advisor_qa, cost_model, early_warning, fact_check, whatif
from ..domain import (CONFIG_DIR as ENGINE_CONFIG_DIR, SCENARIO_DIR, EngineConfig, Observation,
                      load_engine_config, load_scenario_index, read_observations_csv)
from ..evidence_engine import analyse
from ..domain import PROJECT_ROOT
from .registry import Case
from .types import Record, RejectedRow

FIXTURE_DIR = PROJECT_ROOT / "data" / "reliability"
ENGINE_CONFIG_FILES = (ENGINE_CONFIG_DIR / "hypotheses.json", ENGINE_CONFIG_DIR / "cost_assumptions.json")


@dataclass(frozen=True)
class FindingView:
    finding_id: str
    kind: str
    title: str
    detail: str
    record_ids: tuple[str, ...]
    hypothesis_ids: tuple[str, ...]
    key: str


@dataclass(frozen=True)
class HypothesisView:
    hypothesis_id: str
    name: str
    confidence: float
    label: str
    rank: int
    coverage: float
    contested_factor: float
    supporting: tuple[FindingView, ...]
    refuting: tuple[FindingView, ...]
    missing: tuple[FindingView, ...]
    recommended_actions: tuple[str, ...]


@dataclass(frozen=True)
class EngineView:
    """The Evidence Engine's result, copied into frozen Brain types."""
    record_count: int
    hypotheses: tuple[HypothesisView, ...]
    contradictions: tuple[FindingView, ...]
    missing: tuple[FindingView, ...]
    medium_threshold: float
    high_threshold: float


@dataclass(frozen=True)
class WarningView:
    available: bool
    train_hours: int = 0
    threshold: float = 0.0
    first_warning_at: str | None = None
    first_warning_drivers: tuple[tuple[str, float], ...] = ()
    first_warning_records: tuple[str, ...] = ()
    first_alarm: tuple[str, str, str] | None = None
    lead_hours: float | None = None
    flagged_hours: int = 0
    reason: str = ""


@dataclass
class CaseData:
    """Everything the Brain reads for one case. ``observations`` are the originals (frozen)."""
    case: Case
    observations: tuple[Observation, ...]
    records: tuple[Record, ...]
    rejected: tuple[RejectedRow, ...]
    fingerprint: str
    source_label: str
    engine_config: EngineConfig = field(repr=False, default=None)  # type: ignore[assignment]


def _copy(o: Observation, case_id: str) -> Record:
    return Record(o.record_id, case_id, o.timestamp, o.asset_id, o.source_type, o.parameter,
                  o.value, o.unit, o.status, o.subject, o.text, o.source)


def read_tolerant(path: Path) -> tuple[tuple[Observation, ...], tuple[RejectedRow, ...]]:
    """Read a records CSV, keeping rows that parse and reporting the ones that do not."""
    good, bad = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            try:
                good.append(Observation.from_dict(row))
            except (KeyError, ValueError, TypeError) as exc:
                bad.append(RejectedRow(n, str(row.get("record_id") or "?"), str(exc)))
    return tuple(good), tuple(bad)


def load_case(case: Case, store: Any = None, config: EngineConfig | None = None) -> CaseData:
    """Load a case read-only. Scenario cases come from the platform's store when one is
    given (the same data the app shows), otherwise from the scenario CSV."""
    cfg = config or load_engine_config()
    if case.source == "scenario":
        if store is not None:
            obs, rejected = tuple(store.observations(case.scenario_id)), ()
            label = f"PlantProof store, scenario {case.scenario_id}"
        else:
            meta = next(s for s in load_scenario_index() if s["id"] == case.scenario_id)
            obs, rejected = tuple(read_observations_csv(SCENARIO_DIR / meta["file"])), ()
            label = f"data/scenarios/{meta['file']}"
    else:
        obs, rejected = read_tolerant(FIXTURE_DIR / str(case.file))
        label = f"data/reliability/{case.file}"
    records = tuple(_copy(o, case.case_id) for o in obs)
    return CaseData(case, obs, records, rejected, whatif.fingerprint(obs), label, cfg)


def fingerprint(data: CaseData) -> str:
    return whatif.fingerprint(data.observations)


def _subset(data: CaseData, record_ids: Iterable[str] | None) -> tuple[Observation, ...]:
    """The case's observations, optionally limited to some IDs (first copy of a repeated ID)."""
    if record_ids is None:
        return data.observations
    keep, seen, out = set(record_ids), set(), []
    for o in data.observations:
        if o.record_id in keep and o.record_id not in seen:
            seen.add(o.record_id)
            out.append(o)
    return tuple(out)


def _fv(f) -> FindingView:
    return FindingView(f.finding_id, f.kind, f.title, f.detail, tuple(f.record_ids),
                       tuple(f.hypothesis_ids), f.key)


def engine_view(data: CaseData, record_ids: Iterable[str] | None = None) -> EngineView:
    """Run the existing Evidence Engine on the case (optionally on a subset of records)."""
    obs = _subset(data, record_ids)
    r = analyse(obs, data.engine_config, data.case.case_id)
    hyps = tuple(HypothesisView(
        a.hypothesis_id, a.name, a.confidence, a.confidence_label, a.rank, a.coverage,
        a.contested_factor, tuple(_fv(f) for f in a.supporting), tuple(_fv(f) for f in a.refuting),
        tuple(_fv(f) for f in a.missing), tuple(a.recommended_actions)) for a in r.assessments)
    cfg = data.engine_config
    return EngineView(r.record_count, hyps, tuple(_fv(f) for f in r.contradictions),
                      tuple(_fv(f) for f in r.missing), cfg.medium_threshold, cfg.high_threshold)


def warning_view(data: CaseData, record_ids: Iterable[str] | None = None) -> WarningView:
    obs = _subset(data, record_ids)
    ew = early_warning.detect(list(obs), data.engine_config.limits)
    if ew is None:
        return WarningView(False, reason="Not enough complete hourly sensor data to train the model.")
    fw = ew.first_warning
    return WarningView(True, ew.train_hours, ew.threshold, fw.timestamp if fw else None,
                       tuple(fw.drivers) if fw else (), tuple(fw.record_ids) if fw else (),
                       ew.first_alarm, ew.lead_hours, sum(h.flagged for h in ew.hours))


def next_checks(data: CaseData, record_ids: Iterable[str] | None = None) -> tuple[dict, ...]:
    obs = _subset(data, record_ids)
    r = analyse(obs, data.engine_config, data.case.case_id)
    return tuple(dict(c) for c in advisor.next_best_checks(obs, data.engine_config, r))


def cost_view(hypothesis_id: str) -> dict[str, float] | None:
    try:
        return dict(cost_model.estimate(hypothesis_id, cost_model.load_cost_assumptions()).totals)
    except (KeyError, ValueError):
        return None


def fact_check_sentences(data: CaseData, text: str, record_ids: Iterable[str] | None = None):
    """Independent check of generated sentences with the platform's own fact checker."""
    obs = _subset(data, record_ids)
    r = analyse(obs, data.engine_config, data.case.case_id)
    return tuple(fact_check.check(text, obs, r, data.engine_config))


def alarm_limits(data: CaseData) -> dict[str, tuple[float, str, str]]:
    """parameter -> (alarm value, direction high|low, unit), copied from the engine config."""
    return {p: (lim.alarm, lim.direction, lim.unit) for p, lim in data.engine_config.limits.items()}


def cross_check_parameters(data: CaseData) -> tuple[tuple[str, str], ...]:
    """(independent reference parameter, online parameter) pairs the engine cross-checks."""
    return tuple((c.reference_parameter, c.compare_parameter) for c in data.engine_config.cross_checks)


def plain_label(parameter: str) -> str:
    """The wording the platform's own fact checker recognises for a parameter."""
    return advisor_qa.PARAMS.get(parameter, (parameter.replace("_", " "), ""))[0]
