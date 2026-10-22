"""Blind Test: score an analysis against separately stored reference answers.

This is the ONLY module that reads data/reference_answers.json. The evidence
engine never imports this module or reads that file, so its conclusions cannot
be tuned to the answers at run time. (The repository is public, so humans can
still read the file - the dashboard discloses this.)

Scoring (100 points):
    Root cause      50 points if ranked first, 25 if ranked second
    Contradictions  30 x F1 score against the expected contradiction keys
    Missing evidence 20 x F1 score against the expected missing-evidence keys
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .domain import DATA_DIR, AnalysisResult

REFERENCE_PATH = DATA_DIR / "reference_answers.json"

ROOT_CAUSE_POINTS = 50
SECOND_PLACE_POINTS = 25
CONTRADICTION_POINTS = 30
MISSING_POINTS = 20


@dataclass(frozen=True)
class Reference:
    scenario_id: str
    root_cause: str
    expected_contradictions: frozenset[str]
    expected_missing: frozenset[str]
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"scenario_id": self.scenario_id, "root_cause": self.root_cause,
                "expected_contradictions": sorted(self.expected_contradictions),
                "expected_missing": sorted(self.expected_missing),
                "rationale": self.rationale}


@dataclass
class Submission:
    """An answer to be scored: from the engine, or typed in by an analyst."""

    ranking: list[str]                       # hypothesis ids, best first
    contradiction_keys: set[str] = field(default_factory=set)
    missing_keys: set[str] = field(default_factory=set)
    source: str = "engine"

    @property
    def root_cause(self) -> str | None:
        return self.ranking[0] if self.ranking else None

    def to_dict(self) -> dict[str, Any]:
        return {"ranking": list(self.ranking),
                "contradiction_keys": sorted(self.contradiction_keys),
                "missing_keys": sorted(self.missing_keys), "source": self.source}


@dataclass
class ScoreComponent:
    name: str
    points: float
    max_points: float
    detail: str
    true_positives: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)


@dataclass
class BlindTestScore:
    scenario_id: str
    total: float
    components: list[ScoreComponent]
    submission: Submission
    reference: Reference

    @property
    def grade(self) -> str:
        if self.total >= 85:
            return "Excellent"
        if self.total >= 65:
            return "Good"
        if self.total >= 40:
            return "Partial"
        return "Needs review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "total": self.total,
            "grade": self.grade,
            "components": [c.__dict__ for c in self.components],
            "submission": self.submission.to_dict(),
            "reference": self.reference.to_dict(),
        }


def load_reference(scenario_id: str, path: Path = REFERENCE_PATH) -> Reference:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        raw = data["scenarios"][scenario_id]
    except KeyError as exc:
        raise KeyError(f"No reference answers for scenario '{scenario_id}'") from exc
    return Reference(scenario_id, raw["root_cause"],
                     frozenset(raw.get("expected_contradictions", [])),
                     frozenset(raw.get("expected_missing", [])),
                     raw.get("rationale", ""))


def available_scenarios(path: Path = REFERENCE_PATH) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return sorted(json.load(fh)["scenarios"])


def submission_from_analysis(result: AnalysisResult) -> Submission:
    return Submission(
        ranking=[a.hypothesis_id for a in result.assessments],
        contradiction_keys={f.key for f in result.contradictions},
        missing_keys={f.key for f in result.missing},
        source="engine",
    )


def _f1(expected: frozenset[str], submitted: set[str]) -> tuple[float, list, list, list]:
    tp = sorted(expected & submitted)
    fp = sorted(submitted - expected)
    fn = sorted(expected - submitted)
    if not expected and not submitted:
        return 1.0, tp, fp, fn
    precision = len(tp) / len(submitted) if submitted else 0.0
    recall = len(tp) / len(expected) if expected else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return f1, tp, fp, fn


def score(submission: Submission, reference: Reference) -> BlindTestScore:
    components = []

    if submission.root_cause == reference.root_cause:
        pts, detail = ROOT_CAUSE_POINTS, "Correct root cause ranked first."
    elif reference.root_cause in submission.ranking[:2]:
        pts, detail = SECOND_PLACE_POINTS, "Correct root cause ranked second."
    else:
        pts, detail = 0, f"Expected root cause not in the top two (submitted: {submission.root_cause})."
    components.append(ScoreComponent("Root cause", pts, ROOT_CAUSE_POINTS, detail))

    for name, maxp, expected, submitted in (
        ("Contradictions", CONTRADICTION_POINTS, reference.expected_contradictions,
         submission.contradiction_keys),
        ("Missing evidence", MISSING_POINTS, reference.expected_missing,
         submission.missing_keys),
    ):
        f1, tp, fp, fn = _f1(expected, set(submitted))
        components.append(ScoreComponent(
            name, round(maxp * f1, 1), maxp,
            f"F1 {f1:.2f}: {len(tp)} correct, {len(fp)} extra, {len(fn)} missed.",
            tp, fp, fn))

    total = round(sum(c.points for c in components), 1)
    return BlindTestScore(reference.scenario_id, total, components, submission, reference)
