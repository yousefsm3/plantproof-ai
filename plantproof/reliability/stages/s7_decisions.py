"""Stage 7 — Engineering decision intelligence (Decision Intelligence).

Turns verified results into prioritised recommendations. Each one states its action,
justification, evidence, the risk it addresses, its confidence, its priority and what is
still missing. Recommendations are decision support: they never authorise starting,
stopping or modifying equipment.
"""

from __future__ import annotations

from ..context import ClaimBuilder, RunContext
from ..types import ClaimKind, Recommendation, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S7", "Engineering decisions", "Decision Intelligence"
ORDER = {"P1": 0, "P2": 1, "P3": 2}


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    res = ctx.results
    s2, s3, s4, s5, s6 = (res[k] for k in ("S2", "S3", "S4", "S5", "S6"))
    risk = s5.data.get("risk", "Unknown")
    high_risk = risk in ("Critical", "High")
    grade = s2.data["grade"]
    lead_id = s4.data.get("leading")
    lead = next((r for r in s4.data.get("ranking", ()) if r["hypothesis_id"] == lead_id), None)
    lead_label = s6.data["label_overrides"].get(lead_id, lead["label"]) if lead else None
    recs: list[Recommendation] = []

    def add(priority, category, en, ar, why, evidence=(), risk_addr="", conf="Medium", missing=()):
        recs.append(Recommendation(f"R-{len(recs) + 1:02d}", priority, category, en, ar, why,
                                   tuple(evidence)[:12], risk_addr, conf, tuple(missing)))

    # 1. the assessment itself is not reliable enough
    reasons = []
    if s6.status.value == "verification_rejected":
        reasons.append("verification rejected key claims")
    if grade == "D":
        reasons.append(f"data quality grade {grade}")
    if s3.status.value == "insufficient_data":
        reasons.append("condition could not be assessed")
    if reasons:
        add("P1", "escalate", "Escalate to a qualified reliability engineer; do not act on this automated "
            "assessment alone.", "صعّد إلى مهندس موثوقية مؤهل، ولا تعتمد على هذا التقييم وحده.",
            "The examination is not reliable enough: " + "; ".join(reasons) + ".",
            risk_addr="Acting on an unreliable assessment", conf="High", missing=tuple(reasons))

    # 2. instruments that cannot be trusted
    for p, t in s2.data["trust"].items():
        if t == "suspect":
            v = s3.data.get("params", {}).get(p, {})
            add("P1", "diagnose", f"Verify the {ctx.label(p).lower()} transmitter (calibration, mounting, cabling) "
                "before relying on its alarms.", "تحقق من حساس الاهتزاز قبل الاعتماد على إنذاراته.",
                f"{ctx.label(p)} is {s2.data['trust_reason'][p]}.",
                evidence=(v.get("latest_id"),) if v.get("latest_id") else (),
                risk_addr="A false alarm, or a real fault hidden by a faulty sensor", conf="High")

    # 3. data problems
    failed = [c for c in s2.data["checks"] if not c["passed"] and c["severity"] == "high" and c["check_id"] != "D8"]
    if failed:
        add("P1" if grade == "D" else "P2", "data",
            "Correct the record problems: " + "; ".join(c["name"].lower() for c in failed) + ".",
            "صحّح مشاكل السجلات.", "Failed integrity checks: " + "; ".join(f"{c['check_id']} {c['detail']}" for c in failed)[:400],
            evidence=[i for c in failed for i in c["record_ids"]], risk_addr="Conclusions drawn from bad data",
            conf="High")

    # 4. contradictions and missing evidence, ranked by how much they would change the conclusion
    for c in s4.data.get("checks", ()):
        if c["kind"] == "contradiction":
            add("P1" if high_risk else "P2", "resolve", f"Resolve the conflicting record {c['record_ids'][0]}: "
                f"{c['title'].lower()}.", f"احسم السجل المتعارض: {c['title_ar']}.",
                f"Records disagree ({c['finding_id']}); the leading explanation would change by up to "
                f"{c['impact']:.2f} if it proves wrong.", evidence=c["record_ids"],
                risk_addr="Restarting on a wrong diagnosis", conf="High")
        else:
            add("P2" if high_risk else "P3", "diagnose", f"Carry out the missing check: {c['title'].lower()}.",
                f"نفّذ الفحص الناقص: {c['title_ar']}.",
                f"Required evidence {c['finding_id']} is absent; its result would change the leading confidence by "
                f"up to {c['impact']:.2f}.", evidence=c["record_ids"],
                risk_addr="An unconfirmed or wrong cause", conf="Medium", missing=(c["title"],))

    # 5. hold the restart decision when the risk is high
    if high_risk and lead:
        add("P1", "hold", "Hold the restart decision for a qualified engineer until the leading cause is "
            "confirmed or ruled out.", "أجّل قرار إعادة التشغيل حتى يؤكد مهندس مؤهل السبب.",
            f"Risk {risk}: {s5.data['basis']}.", evidence=lead["evidence"],
            risk_addr=f"Secondary damage from {lead['mode_name'].lower()}",
            conf="High" if lead_label == "High" else "Medium",
            missing=tuple(t for _, t in lead["missing"]))

    # 6. what to do if the leading cause is confirmed (the platform's own action list)
    if lead:
        add("P2", "if_confirmed", f"If {lead['mode_name'].lower()} is confirmed: " + "; ".join(a.lower() for a in lead["actions"]) + ".",
            "إذا تأكد السبب: نفّذ الإجراءات المقترحة.",
            f"Leading explanation at {lead['adjusted']:.0%} ({lead_label}).", evidence=lead["evidence"],
            risk_addr=lead["consequence_note"], conf=lead_label or "Low",
            missing=tuple(t for _, t in lead["missing"]))

    # 7. drifting parameters with no alarm
    watch = [v for v in s3.data.get("params", {}).values() if v["status"] == "watch"]
    if watch:
        add("P3" if not high_risk else "P2", "review", "Review operating conditions: " + ", ".join(
            f"{v['label'].lower()} {v['deviation_pct']:+.0f}% from baseline" for v in watch) + ".",
            "راجع ظروف التشغيل.", "Parameters have moved from their baseline without crossing an alarm.",
            evidence=[v["latest_id"] for v in watch], risk_addr="Developing fault not yet alarmed", conf="Medium")

    # 8. nothing indicated
    if not recs or (risk == "Low" and s3.data.get("condition") == "Normal"):
        add("P3", "monitor", "Continue monitoring at the current interval; the evidence indicates no action.",
            "استمر في المراقبة بالمعدل الحالي.", f"Condition {s3.data.get('condition')}, risk {risk}, no supported "
            "failure mechanism. Absence of evidence is not proof of health.", conf="Medium")

    recs.sort(key=lambda r: (ORDER[r.priority], r.rec_id))
    for r in recs:
        cb.add(ClaimKind.RECOMMENDATION, f"{r.priority} {r.action_en} Why: {r.justification}", r.action_ar,
               evidence=r.evidence)
    cb.add(ClaimKind.ASSUMPTION, "These recommendations support qualified engineers. They do not authorise "
           "starting, stopping or modifying equipment; site procedures and permits always apply.",
           "هذه توصيات لدعم القرار ولا تُجيز تشغيل المعدة أو إيقافها.")
    p1 = sum(r.priority == "P1" for r in recs)
    return StageResult(
        STAGE_ID, NAME, DIVISION, StageStatus.COMPLETED,
        f"{len(recs)} recommendation(s), {p1} urgent (P1).", f"{len(recs)} توصيات، منها {p1} عاجلة.",
        cb.all(), frozen_map({"recommendations": tuple(recs), "risk": risk}),
        ("Priorities follow fixed rules from risk, verification and data quality; site context may change them.",),
        ("S2", "S3", "S4", "S5", "S6"))
