"""Stage 4 — Failure mechanism and causal investigation (Causal Reasoning).

Reuses the Evidence Engine's rule-based hypotheses (it does not re-implement them) on the
records the integrity stage accepted, then adds what the engine does not do:
- adjusts each confidence for data quality and sensor trust, with the formula shown;
- compares each mechanism's typical indicators with the observed condition;
- names mechanisms the engine has no rules for, without scoring them;
- ranks the measurements that would best separate the competing explanations.
"""

from __future__ import annotations

from ..context import ClaimBuilder, RunContext
from ..types import ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S4", "Failure mechanisms and causes", "Causal Reasoning"
TRUST_FACTOR = 0.7     # applied when a hypothesis leans on a disputed sensor


def _match(ind, s3) -> str:
    p, d = ind["param"], ind["direction"]
    if p in s3["params"]:
        v = s3["params"][p]
        if v["status"] == "normal":
            return "absent"
        moved = v["deviation_pct"] > 0 if d == "high" else v["deviation_pct"] < 0
        if not moved:
            return "absent"
        return "observed (disputed sensor)" if v["status"] == "alarm_unconfirmed" else "observed"
    if p in s3.get("conditions", {}):
        st = s3["conditions"][p]["status"]
        return {"abnormal": "observed", "normal": "absent", "borderline": "partial"}[st]
    return "unknown"


def label_for(conf: float, high: float, medium: float) -> str:
    return "High" if conf >= high else "Medium" if conf >= medium else "Low"


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    prof = ctx.profile
    s2, s3 = ctx.results["S2"].data, ctx.results["S3"].data
    cap, trust = s2["cap"], s2["trust"]
    usable = ctx.usable_ids()
    ev = ctx.engine(usable)
    by_id = {r.record_id: r for r in ctx.records}
    suspect = {p for p, t in trust.items() if t == "suspect"}
    modes = {m["engine_hypothesis"]: m for m in prof["failure_modes"] if m.get("engine_hypothesis")}
    excluded = len(s2["excluded_ids"])
    if excluded:
        cb.add(ClaimKind.FACT, f"The Evidence Engine was re-run on {ev.record_count} usable records; "
               f"{excluded} record(s) excluded by the integrity stage are not used.",
               f"أُعيد تشغيل محرك الأدلة على {ev.record_count} سجلًا صالحًا.")

    ranking = []
    for h in ev.hypotheses:
        mode = modes.get(h.hypothesis_id, {})
        sup_ids = tuple(dict.fromkeys(i for f in h.supporting for i in f.record_ids))
        leans_on_suspect = (not mode.get("instrument_for")) and any(
            by_id[i].source_type == "sensor" and by_id[i].parameter in suspect for i in sup_ids if i in by_id)
        factor = TRUST_FACTOR if leans_on_suspect else 1.0
        adjusted = round(h.confidence * cap * factor, 3)
        label = label_for(adjusted, ev.high_threshold, ev.medium_threshold)
        symptoms = {f"{ctx.label(i['param'])} {i['direction']}": _match(i, s3) for i in mode.get("indicators", [])}
        ranking.append({
            "hypothesis_id": h.hypothesis_id, "name": h.name, "mode_name": mode.get("name", h.name),
            "engine_confidence": round(h.confidence, 3), "data_cap": cap, "trust_factor": factor,
            "adjusted": adjusted, "label": label, "coverage": h.coverage,
            "contested_factor": h.contested_factor,
            "supporting": tuple((f.finding_id, f.title, f.record_ids) for f in h.supporting),
            "refuting": tuple((f.finding_id, f.title, f.record_ids) for f in h.refuting),
            "missing": tuple((f.finding_id, f.title) for f in h.missing),
            "symptoms": symptoms, "consequence": mode.get("consequence"),
            "consequence_note": mode.get("consequence_note", ""),
            "checks": tuple(mode.get("discriminating_checks", ())),
            "actions": h.recommended_actions, "evidence": sup_ids})
    ranking.sort(key=lambda x: (-x["adjusted"], x["hypothesis_id"]))
    for n, r in enumerate(ranking, start=1):
        r["rank"] = n
        formula = f"engine {r['engine_confidence']:.2f} × data cap {r['data_cap']:.2f}" + \
                  (f" × sensor-trust {r['trust_factor']:.1f}" if r["trust_factor"] < 1 else "")
        parts = [f"for: {'; '.join(t for _, t, _ in r['supporting']) or 'nothing matched'}"]
        if r["refuting"]:
            parts.append(f"against: {'; '.join(t for _, t, _ in r['refuting'])}")
        if r["missing"]:
            parts.append(f"missing: {'; '.join(t for _, t in r['missing'])}")
        r["claim_id"] = cb.add(ClaimKind.HYPOTHESIS,
               f"#{n} {r['mode_name']}: confidence {r['adjusted']:.0%} ({r['label']}; {formula}). " + ". ".join(parts) + ".",
               f"#{n} {r['mode_name']}: ثقة {r['adjusted']:.0%}.",
               evidence=r["evidence"][:15],
               finding_refs=tuple(i for i, _, _ in r["supporting"] + r["refuting"]) + tuple(i for i, _ in r["missing"]),
               confidence=r["adjusted"], key=n == 1 and r["label"] != "Low").claim_id

    for m in prof["failure_modes"]:
        if m.get("engine_hypothesis"):
            continue
        seen = {f"{ctx.label(i['param'])} {i['direction']}": _match(i, s3) for i in m["indicators"]}
        obs = [k for k, v in seen.items() if v.startswith("observed")]
        unk = [k for k, v in seen.items() if v == "unknown"]
        cb.add(ClaimKind.UNCERTAINTY,
               f"{m['name']}: not scored — no rule set exists for it. Typical indicators observed: "
               f"{', '.join(obs) or 'none'}; unknown: {', '.join(unk) or 'none'}. To assess it: "
               f"{'; '.join(m['discriminating_checks'])}.",
               f"{m['name']}: لم يُقيَّم لعدم وجود قواعد له.")

    lead = ranking[0] if ranking and ranking[0]["label"] != "Low" else None
    contradictions = s2.get("contradictions", ())
    if lead and lead["contested_factor"] < 1:
        cb.add(ClaimKind.FINDING, f"The leading explanation is contested: contradictions touch its supporting "
               f"records (contested factor {lead['contested_factor']:.2f}).",
               "التفسير الأرجح متنازع عليه بسبب تناقضات.", finding_refs=tuple(contradictions))
    if not lead:
        cb.add(ClaimKind.FINDING, "No failure mechanism reaches medium confidence: the evidence does not support "
               "a fault.", "لا توجد آلية عطل مدعومة بالأدلة.", key=True)

    checks = ctx.checks(usable)[:3]
    for c in checks:
        best = max(c["outcomes"], key=lambda o: o["impact"])
        cb.add(ClaimKind.RECOMMENDATION, f"Discriminating check: {c['title']} — {best['label_en']}, the leader's "
               f"confidence would change by {best['delta']:+.2f}" + (" and the leader would change" if best["flip"] else "") + ".",
               f"فحص مميِّز: {c['title_ar']}.", evidence=tuple(c["record_ids"][:8]), finding_refs=(c["finding_id"],))

    status = StageStatus.AWAITING_EVIDENCE if lead and lead["missing"] else StageStatus.COMPLETED
    summary = (f"Leading explanation: {lead['mode_name']} at {lead['adjusted']:.0%} ({lead['label']}); "
               f"{len(lead['missing'])} required check(s) missing." if lead else
               "No failure mechanism is supported by the evidence.")
    return StageResult(
        STAGE_ID, NAME, DIVISION, status, summary,
        (f"التفسير الأرجح: {lead['mode_name']} بثقة {lead['adjusted']:.0%}." if lead else "لا توجد آلية عطل مدعومة."),
        cb.all(),
        frozen_map({"ranking": tuple(ranking), "leading": lead["hypothesis_id"] if lead else None,
                    "checks": tuple({"finding_id": c["finding_id"], "title": c["title"], "title_ar": c["title_ar"],
                                     "kind": c["kind"], "impact": c["impact"], "record_ids": tuple(c["record_ids"])}
                                    for c in checks),
                    "contradictions": tuple(contradictions)}),
        ("Hypotheses and their weights come from config/hypotheses.json (rule-based, hand-written for one pump type).",
         "Typical indicators organise the review; matching indicators do not prove a mechanism.",
         "Confidence is evidence strength, not a probability of failure."),
        ("Evidence Engine (usable records)", "S2 grade and sensor trust", "S3 condition", "failure-mode library"))
