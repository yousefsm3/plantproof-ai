"""Stage 3 — Equipment health examination (Asset Intelligence).

Describes the current condition from the usable records only. Measured values (what a
record says) are kept apart from findings (what the Brain infers from them).
"""

from __future__ import annotations

from statistics import median

from .. import adapter
from ..context import ClaimBuilder, RunContext
from ..types import Check, ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S3", "Equipment health", "Asset Intelligence"
STATUS_AR = {"normal": "طبيعي", "watch": "تحت المراقبة", "alarm": "إنذار",
             "alarm_unconfirmed": "إنذار غير مؤكد", "abnormal": "غير طبيعي", "borderline": "حدّي"}


def _slope_per_hour(points) -> float:
    """Least-squares slope of value against hours (0 if fewer than 3 points)."""
    if len(points) < 3:
        return 0.0
    t0 = points[0].ts
    xs = [(p.ts - t0).total_seconds() / 3600 for p in points]
    ys = [p.value for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return 0.0 if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    prof = ctx.profile
    s2 = ctx.results["S2"].data
    trust = s2.get("trust", {})
    limits = adapter.alarm_limits(ctx.data)
    params: dict[str, dict] = {}

    for p, spec in prof["sensors"].items():
        series = ctx.sensor_series(p)
        if len(series) < 4:
            continue
        start = series[0].ts
        base_pts = [r for r in series if (r.ts - start).total_seconds() <= prof["baseline_hours"] * 3600]
        base_pts = base_pts if len(base_pts) >= 3 else series[:3]
        baseline = median(r.value for r in base_pts)
        end = series[-1].ts
        trend_pts = [r for r in series if (end - r.ts).total_seconds() <= prof["trend_hours"] * 3600]
        recent = median(r.value for r in series[-6:])
        latest = series[-1]
        slope = _slope_per_hour(trend_pts)
        dev = (recent - baseline) / abs(baseline) if baseline else 0.0
        lim = limits.get(p)
        status = "normal"
        if lim:
            alarm, direction, _unit = lim
            beyond = latest.value > alarm if direction == "high" else latest.value < alarm
            span = alarm - baseline
            progress = (recent - baseline) / span if span else 0.0
            if beyond:
                status = "alarm"
            elif progress >= prof["watch_fraction"]:
                status = "watch"
        if status == "normal" and abs(dev) * 100 >= prof["watch_deviation_pct"]:
            status = "watch"
        if status == "alarm" and trust.get(p) == "suspect":
            status = "alarm_unconfirmed"
        trend = "rising" if slope * prof["trend_hours"] > 0.05 * abs(baseline or 1) else \
                "falling" if slope * prof["trend_hours"] < -0.05 * abs(baseline or 1) else "steady"
        params[p] = {"label": spec["label"], "unit": spec["unit"], "baseline": round(baseline, 3),
                     "recent": round(recent, 3), "latest": latest.value, "latest_id": latest.record_id,
                     "deviation_pct": round(dev * 100, 1), "slope_per_h": round(slope, 4),
                     "trend": trend, "status": status, "trust": trust.get(p, "trusted"),
                     "alarm": lim[0] if lim else None, "direction": lim[1] if lim else None,
                     "baseline_ids": tuple(r.record_id for r in base_pts[:3])}

        # measured value, with a check the verification stage re-runs on the cited record
        chk = None
        if lim:
            alarm, direction, _ = lim
            if status in ("alarm", "alarm_unconfirmed"):
                chk = Check(p, ">" if direction == "high" else "<", alarm, "latest")
            else:
                chk = Check(p, "<=" if direction == "high" else ">=", alarm, "latest")
        cb.add(ClaimKind.MEASURED,
               f"{spec['label']} latest {latest.value:g} {spec['unit']} at {latest.timestamp[5:16].replace('T', ' ')}; "
               f"baseline {baseline:.3g}" + (f"; alarm limit {lim[0]:g}" if lim else "") + ".",
               f"{spec['label']}: آخر قراءة {latest.value:g} {spec['unit']}.",
               evidence=(latest.record_id,), check=chk)
        if status != "normal":
            note = {"alarm": "is beyond its alarm limit",
                    "alarm_unconfirmed": "is beyond its alarm limit, but this sensor is disputed",
                    "watch": "has moved well away from its baseline"}[status]
            cb.add(ClaimKind.FINDING,
                   f"{spec['label']} {note} ({dev * 100:+.0f}% from baseline, trend {trend}).",
                   f"{spec['label']}: {STATUS_AR[status]}.",
                   evidence=(latest.record_id,) + params[p]["baseline_ids"][:1],
                   check=chk if status != "watch" else None, key=status == "alarm")

    if len(params) < 2:
        cb.add(ClaimKind.MISSING, "Fewer than two sensor parameters have enough usable readings to assess health.",
               "لا توجد قراءات كافية لتقييم الحالة.", key=True)
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.INSUFFICIENT_DATA,
                           "Not enough usable sensor data to assess health.", "البيانات غير كافية لتقييم الحالة.",
                           cb.all(), frozen_map({"params": params, "condition": "Unknown"}), (), ("S2 usable records",))

    # latest lab and inspection results against the profile's condition bands
    conditions: dict[str, dict] = {}
    for p, band in prof["condition_bands"].items():
        rows = sorted((r for r in ctx.usable_records() if r.parameter == p and r.value is not None),
                      key=lambda r: r.timestamp)
        if not rows:
            continue
        r = rows[-1]
        st = "abnormal" if r.value > band["abnormal_above"] else \
             "normal" if r.value <= band["normal_at_or_below"] else "borderline"
        conditions[p] = {"label": band["label"], "unit": band["unit"], "value": r.value,
                         "record_id": r.record_id, "status": st, "source_type": band["source_type"]}
        chk = Check(p, ">", band["abnormal_above"], "latest") if st == "abnormal" else \
              Check(p, "<=", band["normal_at_or_below"], "latest") if st == "normal" else None
        cb.add(ClaimKind.MEASURED, f"{band['label']} {r.value:g} {band['unit']} ({band['source_type']}, "
               f"{r.timestamp[:10]}): {st}.", f"{band['label']}: {STATUS_AR[st]}.",
               evidence=(r.record_id,), check=chk, key=st == "abnormal")

    # anomalies from the existing learned-baseline model (reused, not re-implemented)
    ew = ctx.warning(ctx.usable_ids())
    if not ew.available:
        cb.add(ClaimKind.UNCERTAINTY, f"Anomaly model not run: {ew.reason}", "لم يعمل نموذج الشذوذ.")
    elif ew.first_warning_at:
        drivers = ", ".join(f"{ctx.label(p)} ({z:+g}σ)" for p, z in ew.first_warning_drivers) or "several sensors"
        lead = (f"{ew.lead_hours:g} h before the first alarm" if ew.lead_hours and ew.lead_hours > 0 else
                "at the same hour as the first alarm" if ew.lead_hours == 0 else "with no alarm crossed")
        cb.add(ClaimKind.FINDING, f"The learned-baseline model flagged unusual behaviour from "
               f"{ew.first_warning_at[5:16].replace('T', ' ')}, {lead}; drivers: {drivers}. "
               "This is an anomaly score, not a failure probability.",
               "نموذج الشذوذ لاحظ سلوكًا غير طبيعي. هذه درجة شذوذ وليست احتمال عطل.",
               evidence=ew.first_warning_records[:7])
    else:
        cb.add(ClaimKind.FINDING, "The learned-baseline model found no unusual behaviour in this window.",
               "لم يجد نموذج الشذوذ سلوكًا غير طبيعي.")

    statuses = [v["status"] for v in params.values()]
    abnormal_cond = [k for k, v in conditions.items() if v["status"] == "abnormal"]
    if "alarm" in statuses:
        condition = "Alarm"
    elif "alarm_unconfirmed" in statuses:
        condition = "Alarm (unconfirmed)"
    elif "watch" in statuses or abnormal_cond:
        condition = "Degraded"
    else:
        condition = "Normal"
    cond_ar = {"Alarm": "إنذار", "Alarm (unconfirmed)": "إنذار غير مؤكد", "Degraded": "متدهورة", "Normal": "طبيعية"}
    cb.add(ClaimKind.FINDING, f"Overall condition: {condition}. Sensors in alarm: "
           f"{', '.join(v['label'] for v in params.values() if v['status'] == 'alarm') or 'none'}; under watch: "
           f"{', '.join(v['label'] for v in params.values() if v['status'] == 'watch') or 'none'}; abnormal lab or "
           f"inspection results: {', '.join(conditions[k]['label'] for k in abnormal_cond) or 'none'}.",
           f"الحالة العامة: {cond_ar[condition]}.", key=True)
    return StageResult(
        STAGE_ID, NAME, DIVISION, StageStatus.COMPLETED,
        f"Condition {condition}: {statuses.count('alarm')} sensor(s) in alarm"
        + (f", {statuses.count('alarm_unconfirmed')} in alarm on a disputed sensor" if 'alarm_unconfirmed' in statuses else "")
        + f", {statuses.count('watch')} under watch, "
        f"{len(abnormal_cond)} abnormal lab/inspection result(s).",
        f"الحالة {cond_ar[condition]}.", cb.all(),
        frozen_map({"params": params, "conditions": conditions, "condition": condition,
                    "anomaly": {"available": ew.available, "first_warning_at": ew.first_warning_at,
                                "lead_hours": ew.lead_hours, "drivers": ew.first_warning_drivers,
                                "first_alarm": ew.first_alarm, "records": ew.first_warning_records}}),
        (f"Baseline = median of the first {prof['baseline_hours']} h; trend = least-squares slope over the last "
         f"{prof['trend_hours']} h. A 48 h window cannot show long-term degradation.",),
        ("S2 usable records", "alarm limits", "condition bands", "early-warning model"))
