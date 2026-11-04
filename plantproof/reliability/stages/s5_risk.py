"""Stage 5 — Failure risk and degradation (Failure Risk).

Risk = consequence severity × evidence strength, from a fixed, documented matrix.
Evidence strength is the adjusted confidence band, not a probability. No failure
probability and no remaining useful life is produced: the data cannot support either.
"""

from __future__ import annotations

from .. import adapter
from ..context import ClaimBuilder, RunContext
from ..types import ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S5", "Failure risk and degradation", "Failure Risk"
MATRIX = {("High", "Strong"): "Critical", ("High", "Moderate"): "High",
          ("Medium", "Strong"): "High", ("Medium", "Moderate"): "Medium",
          ("Low", "Strong"): "Medium", ("Low", "Moderate"): "Low"}
STRENGTH = {"High": "Strong", "Medium": "Moderate", "Low": "Weak"}
RISK_AR = {"Critical": "حرج", "High": "مرتفع", "Medium": "متوسط", "Low": "منخفض"}


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    s3, s4 = ctx.results["S3"], ctx.results["S4"]
    if s3.status is StageStatus.INSUFFICIENT_DATA:
        cb.add(ClaimKind.UNCERTAINTY, "Risk cannot be assessed: the equipment condition is unknown.",
               "لا يمكن تقييم الخطر لأن حالة المعدة غير معروفة.", key=True)
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.INSUFFICIENT_DATA,
                           "Risk not assessed: condition unknown.", "لم يُقيَّم الخطر.", cb.all(),
                           frozen_map({"risk": "Unknown"}), (), ("S3",))
    if ctx.results["S2"].data.get("grade") == "D":
        cb.add(ClaimKind.UNCERTAINTY, "Risk is undetermined: data quality grade D is too poor to rate risk either "
               "way. A low score here would be a false reassurance.",
               "الخطر غير محدد لأن جودة البيانات ضعيفة جدًا.", key=True)
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.INSUFFICIENT_DATA,
                           "Risk undetermined: data quality D.", "الخطر غير محدد بسبب جودة البيانات.", cb.all(),
                           frozen_map({"risk": "Undetermined", "basis": "data quality D", "rul": "unavailable",
                                       "probability": "not estimated"}), (), ("S2 grade",))
    ranking = s4.data["ranking"]
    lead = next((r for r in ranking if r["hypothesis_id"] == s4.data["leading"]), None)
    condition = s3.data["condition"]
    crit = ctx.asset.criticality

    if lead:
        consequence = lead["consequence"] or "Medium"
        severity = consequence
        sev_note = f"consequence of {lead['mode_name'].lower()}: {lead['consequence_note']}"
        if crit == "High" and severity == "Medium":
            severity, sev_note = "High", sev_note + " Raised to High: the asset is registered as High criticality."
        strength = STRENGTH[lead["label"]]
        risk = MATRIX[(severity, strength)]
        basis = f"{severity} severity × {strength.lower()} evidence ({lead['adjusted']:.0%})"
        cb.add(ClaimKind.FINDING, f"Risk {risk}: {basis}. Severity basis — {sev_note}",
               f"مستوى الخطر {RISK_AR[risk]}.", evidence=lead["evidence"][:10],
               finding_refs=tuple(i for i, _, _ in lead["supporting"]), confidence=lead["adjusted"], key=True)
    else:
        severity, strength = None, "Weak"
        risk = {"Alarm": "Medium", "Alarm (unconfirmed)": "Medium"}.get(condition, "Low")
        basis = ("an alarm with no supported explanation" if risk == "Medium"
                 else "no supported failure mechanism")
        cb.add(ClaimKind.FINDING, f"Risk {risk}: {basis} (condition {condition}).",
               f"مستوى الخطر {RISK_AR[risk]}.", key=True)
    if crit is None:
        cb.add(ClaimKind.MISSING, "Asset criticality is unknown, so the consequence for the plant is not weighted.",
               "أهمية المعدة غير معروفة.")

    # direction of the indicators that support the leading explanation
    params = s3.data["params"]
    trend_items, trend_ids = [], []
    if lead:
        mode = next((m for m in ctx.profile["failure_modes"] if m.get("engine_hypothesis") == lead["hypothesis_id"]), {})
        for ind in mode.get("indicators", []):
            v = params.get(ind["param"])
            if not v:
                continue
            worsening = (v["trend"] == "rising" and ind["direction"] == "high") or \
                        (v["trend"] == "falling" and ind["direction"] == "low")
            trend_items.append((v["label"], "worsening" if worsening else v["trend"]))
            trend_ids.append(v["latest_id"])
    direction = ("worsening" if any(t == "worsening" for _, t in trend_items) else
                 "steady" if trend_items else "not assessed")
    if trend_items:
        cb.add(ClaimKind.FINDING, "Trend of the supporting indicators over the last "
               f"{ctx.profile['trend_hours']} h: " + ", ".join(f"{a} {b}" for a, b in trend_items) + ".",
               "اتجاه المؤشرات الداعمة.", evidence=tuple(trend_ids))

    anomaly = s3.data.get("anomaly", {})
    if anomaly.get("lead_hours"):
        cb.add(ClaimKind.FINDING, f"Early-warning indicator: unusual behaviour was flagged {anomaly['lead_hours']:g} h "
               "before the first alarm.", "إنذار مبكر قبل أول إنذار.", evidence=tuple(anomaly.get("records", ()))[:7])

    exposure = adapter.cost_view(lead["hypothesis_id"]) if lead else None
    if exposure:
        cb.add(ClaimKind.FINDING, f"Illustrative cost if {lead['mode_name'].lower()} is confirmed: "
               f"${exposure['low']:,.0f}–${exposure['high']:,.0f} (base ${exposure['base']:,.0f}), from the "
               "platform's cost assumptions, not site data.", "تكلفة توضيحية من افتراضات المنصة.")

    cb.add(ClaimKind.UNCERTAINTY, "Likelihood is not given as a probability: there is no validated failure-rate or "
           "run-to-failure data for this asset. Evidence strength is reported instead.",
           "لا يُعطى احتمال عطل رقمي لعدم وجود بيانات معتمدة.")
    cb.add(ClaimKind.UNCERTAINTY, "Remaining useful life: unavailable. A 48 h window with no run-to-failure "
           "history cannot support a validated estimate.", "العمر المتبقي غير متاح.")
    return StageResult(
        STAGE_ID, NAME, DIVISION, StageStatus.COMPLETED,
        f"Risk {risk} ({basis}); indicator trend {direction}.", f"مستوى الخطر {RISK_AR[risk]}.", cb.all(),
        frozen_map({"risk": risk, "severity": severity, "strength": strength, "basis": basis,
                    "trend": direction, "trend_items": tuple(trend_items), "exposure": exposure,
                    "lead_hours": anomaly.get("lead_hours"), "criticality": crit,
                    "rul": "unavailable", "probability": "not estimated"}),
        ("Risk levels use a fixed 3×2 matrix (severity × evidence strength); it is a triage aid, not a "
         "quantitative risk assessment.", "Costs are the platform's illustrative assumptions."),
        ("S3 condition and trends", "S4 leading explanation", "failure-mode consequences", "asset criticality"))
