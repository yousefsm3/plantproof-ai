"""Evidence engine: rule-based, transparent and fully traceable.

Given a set of observations and the engine configuration it:
  1. detects contradictions between records,
  2. detects missing or out-of-date evidence for each hypothesis,
  3. scores each hypothesis from supporting and refuting rules,
  4. adjusts confidence for missing evidence and contested records,
  5. links every finding to the source record IDs it is based on.

No LLM, no randomness, no network: the same input always gives the same result.

Confidence formula (also shown in the dashboard):
    support_ratio    = max(0, matched_support - matched_refute) / possible_support
    coverage         = required evidence present / required evidence total
    coverage_factor  = coverage_floor + (1 - coverage_floor) * coverage
    contested_factor = max(min_contested_factor,
                           contested_penalty ** contradictions_touching_support)
    confidence       = support_ratio * coverage_factor * contested_factor
"""

from __future__ import annotations

import operator
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from .domain import (AnalysisResult, Condition, EngineConfig, Finding,
                     HypothesisAssessment, Observation, Rule)

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt,
        "<=": operator.le, "==": operator.eq}


def _matches(obs: Observation, cond: Condition) -> bool:
    return obs.value is not None and _OPS[cond.op](obs.value, cond.threshold)


def _hours_between(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds()) / 3600.0


class _Index:
    """Lookup of observations by evidence key (source_type:parameter)."""

    def __init__(self, observations: Iterable[Observation]):
        self.by_key: dict[str, list[Observation]] = defaultdict(list)
        self.by_param: dict[str, list[Observation]] = defaultdict(list)
        for o in observations:
            self.by_key[o.evidence_key].append(o)
            self.by_param[o.parameter].append(o)

    def get(self, key: str) -> list[Observation]:
        return self.by_key.get(key, [])


def evaluate_rule(rule: Rule, index: _Index) -> tuple[bool, list[str]]:
    """Return (matched, record_ids that justify the match)."""
    first = rule.conditions[0]
    candidates = index.get(first.key)

    if rule.mode == "all":
        if candidates and all(_matches(o, first) for o in candidates):
            return True, [o.record_id for o in candidates]
        return False, []

    anchors = [o for o in candidates if _matches(o, first)]
    if len(rule.conditions) == 1:
        return bool(anchors), [o.record_id for o in anchors]

    # Multi-condition: every other condition must have a matching record
    # within window_h of the anchor record.
    ids: list[str] = []
    for anchor in anchors:
        partners: list[Observation] = []
        ok = True
        for cond in rule.conditions[1:]:
            near = [o for o in index.get(cond.key)
                    if _matches(o, cond) and _hours_between(o.ts, anchor.ts) <= rule.window_h]
            if not near:
                ok = False
                break
            partners.append(min(near, key=lambda o: _hours_between(o.ts, anchor.ts)))
        if ok:
            for o in [anchor, *partners]:
                if o.record_id not in ids:
                    ids.append(o.record_id)
    return bool(ids), ids


def detect_contradictions(observations: list[Observation], config: EngineConfig,
                          index: _Index) -> list[Finding]:
    found: list[tuple[str, Finding]] = []

    # 1) A record says "normal" while sensors of that asset are in alarm nearby.
    for claim in observations:
        if claim.status != "normal":
            continue
        params = ([claim.subject] if claim.subject in config.limits
                  else list(config.limits))
        breaches: list[Observation] = []
        details: list[str] = []
        for p in params:
            limit = config.limits[p]
            hits = [o for o in index.get(f"sensor:{p}")
                    if o.asset_id == claim.asset_id
                    and _hours_between(o.ts, claim.ts) <= config.claim_window_h
                    and limit.breached(o.value)]
            if hits:
                breaches += hits
                worst = (max if limit.direction == "high" else min)(h.value for h in hits)
                details.append(f"{p} reached {worst:g} {limit.unit} "
                               f"(alarm {'>' if limit.direction == 'high' else '<'} {limit.alarm:g})")
        if breaches:
            found.append((claim.timestamp, Finding(
                finding_id="", kind="contradiction",
                title=f"{claim.source_type.replace('_', ' ').capitalize()} reports normal "
                      f"while sensors are in alarm",
                detail=f"{claim.record_id} ({claim.source}) says: \"{claim.text}\". "
                       f"Within ±{config.claim_window_h:g} h: " + "; ".join(details) + ".",
                record_ids=(claim.record_id, *[b.record_id for b in breaches]),
                severity="high",
                key=claim.record_id,
            )))

    # 2) Independent measurements of the same quantity disagree.
    for check in config.cross_checks:
        for ref in index.by_param.get(check.reference_parameter, []):
            if ref.value is None:
                continue
            near = [o for o in index.by_param.get(check.compare_parameter, [])
                    if o.value is not None and o.asset_id == ref.asset_id
                    and _hours_between(o.ts, ref.ts) <= check.window_h]
            if not near:
                continue
            other = min(near, key=lambda o: (_hours_between(o.ts, ref.ts), o.record_id))
            diff_pct = abs(other.value - ref.value) / max(abs(ref.value), 1e-9) * 100
            if diff_pct > check.tolerance_pct:
                found.append((ref.timestamp, Finding(
                    finding_id="", kind="contradiction",
                    title=f"{check.label} disagree",
                    detail=f"{ref.record_id} measured {ref.value:g} {ref.unit}, "
                           f"{other.record_id} measured {other.value:g} {other.unit} "
                           f"({diff_pct:.0f}% apart, tolerance {check.tolerance_pct:g}%).",
                    record_ids=(ref.record_id, other.record_id),
                    severity="high",
                    key=ref.record_id,
                )))

    found.sort(key=lambda t: (t[0], t[1].key))
    out = []
    for i, (_, f) in enumerate(found, start=1):
        out.append(Finding(f"C-{i:02d}", f.kind, f.title, f.detail, f.record_ids,
                           f.hypothesis_ids, f.severity, f.key))
    return out


def analyse(observations: Iterable[Observation], config: EngineConfig,
            scenario_id: str | None = None) -> AnalysisResult:
    """Run the full analysis. The input is never modified."""
    obs = sorted(observations, key=lambda o: (o.timestamp, o.record_id))
    index = _Index(obs)
    sensors = [o for o in obs if o.source_type == "sensor"] or obs
    if obs:
        end = max(o.ts for o in obs)
        w_start, w_end = sensors[0].timestamp, obs[-1].timestamp
    else:
        end = datetime.now()
        w_start = w_end = ""
    sid = scenario_id or (obs[0].scenario_id if obs else "")

    contradictions = detect_contradictions(obs, config, index)

    assessments: list[HypothesisAssessment] = []
    missing_by_key: dict[str, dict] = {}

    for hyp in config.hypotheses:
        supporting, refuting, missing = [], [], []
        support_score = refute_score = 0.0
        possible = sum(r.weight for r in hyp.supports)

        for j, rule in enumerate(hyp.supports, start=1):
            ok, ids = evaluate_rule(rule, index)
            if ok:
                support_score += rule.weight
                supporting.append(Finding(
                    f"S-{hyp.id}-{j}", "support", rule.label,
                    f"Matched: {' and '.join(c.describe() for c in rule.conditions)} "
                    f"(weight {rule.weight:g}, {len(ids)} record(s)).",
                    tuple(ids), (hyp.id,), "medium", f"{hyp.id}:support:{j}"))

        for j, rule in enumerate(hyp.refutes, start=1):
            ok, ids = evaluate_rule(rule, index)
            if ok:
                refute_score += rule.weight
                refuting.append(Finding(
                    f"R-{hyp.id}-{j}", "refute", rule.label,
                    f"Matched: {' and '.join(c.describe() for c in rule.conditions)} "
                    f"(weight {rule.weight:g}, {len(ids)} record(s)).",
                    tuple(ids), (hyp.id,), "medium", f"{hyp.id}:refute:{j}"))

        present = 0
        for req in hyp.required:
            records = index.get(req.key)
            reason, ids = None, ()
            if not records:
                reason = "No record found."
            elif req.max_age_days is not None:
                latest = max(records, key=lambda o: o.ts)
                age = (end - latest.ts).total_seconds() / 86400
                if age > req.max_age_days:
                    reason = (f"Out of date: latest record {latest.record_id} is "
                              f"{age:.0f} days old (limit {req.max_age_days:g} days).")
                    ids = (latest.record_id,)
            if reason is None:
                present += 1
                continue
            missing.append(Finding(f"M-{hyp.id}-{req.parameter}", "missing", req.label,
                                   reason, ids, (hyp.id,), "medium", req.key))
            entry = missing_by_key.setdefault(req.key, {"label": req.label, "reason": reason,
                                                        "ids": ids, "hyps": []})
            entry["hyps"].append(hyp.id)

        coverage = present / len(hyp.required) if hyp.required else 1.0
        ratio = max(0.0, support_score - refute_score) / possible if possible else 0.0
        ratio = min(1.0, ratio)
        support_ids = {rid for f in supporting for rid in f.record_ids}
        touching = sum(1 for c in contradictions if support_ids.intersection(c.record_ids))
        contested = max(config.min_contested_factor, config.contested_penalty ** touching)
        cov_factor = config.coverage_floor + (1 - config.coverage_floor) * coverage
        confidence = round(ratio * cov_factor * contested, 3)
        if confidence >= config.high_threshold:
            label = "High"
        elif confidence >= config.medium_threshold:
            label = "Medium"
        else:
            label = "Low"

        assessments.append(HypothesisAssessment(
            hyp.id, hyp.name, support_score, possible, refute_score, round(ratio, 3),
            round(coverage, 3), round(contested, 3), confidence, label,
            supporting=supporting, refuting=refuting, missing=missing,
            recommended_actions=hyp.recommended_actions))

    assessments.sort(key=lambda a: (-a.confidence, a.hypothesis_id))
    for i, a in enumerate(assessments, start=1):
        a.rank = i

    missing_global = []
    for i, (key, m) in enumerate(sorted(missing_by_key.items()), start=1):
        missing_global.append(Finding(
            f"M-{i:02d}", "missing", m["label"], m["reason"], tuple(m["ids"]),
            tuple(m["hyps"]), "medium", key))

    return AnalysisResult(sid, len(obs), w_start, w_end, assessments,
                          contradictions, missing_global)
