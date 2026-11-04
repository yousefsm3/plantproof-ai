"""Stage 1 — Asset identity and context (Asset Intelligence).

Establishes what the asset is, which examination profile applies, which records and
parameters exist, and which specifications are unknown. Never invents a specification.
"""

from __future__ import annotations

from collections import Counter

from ..context import ClaimBuilder, RunContext
from ..types import ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S1", "Asset identity and context", "Asset Intelligence"


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    a = ctx.asset
    recs = ctx.records
    cb.add(ClaimKind.FACT, f"Asset {a.asset_id}: {a.name}, type '{a.type}', location "
           f"{a.location or 'unknown'} (from the Brain's asset registry).",
           f"المعدة {a.asset_id}: {a.name}، النوع «{a.type}»، الموقع {a.location or 'غير معروف'} (من سجل المعدات).")

    if ctx.profile is None:
        cb.add(ClaimKind.UNCERTAINTY,
               f"No examination profile exists for asset type '{a.type}'. Pump rules are not applied "
               f"to other equipment, so the examination stops here.",
               f"لا يوجد ملف فحص لنوع المعدة «{a.type}»، ولا تُطبّق قواعد المضخات على معدات أخرى، فيتوقف الفحص هنا.",
               key=True)
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.BLOCKED,
                           f"Asset type '{a.type}' is not supported yet.",
                           f"نوع المعدة «{a.type}» غير مدعوم حاليًا.", cb.all(),
                           frozen_map({"supported": False, "asset_type": a.type,
                                       "record_count": len(recs)}),
                           ("Supported types are those with a profile in config/reliability/profiles/.",),
                           ("asset registry",))

    if not recs:
        cb.add(ClaimKind.MISSING, "No readable records exist for this case.",
               "لا توجد سجلات قابلة للقراءة لهذه الحالة.", key=True)
        return StageResult(STAGE_ID, NAME, DIVISION, StageStatus.INSUFFICIENT_DATA,
                           "No records to examine.", "لا توجد سجلات للفحص.", cb.all(),
                           frozen_map({"supported": True, "record_count": 0}), (), ("records",))

    by_type = Counter(r.source_type for r in recs)
    first, last = min(recs, key=lambda r: r.timestamp), max(recs, key=lambda r: r.timestamp)
    sensors = sorted({r.parameter for r in recs if r.source_type == "sensor"})
    expected = list(ctx.profile["sensors"])
    present = [p for p in expected if p in sensors]
    absent = [p for p in expected if p not in sensors]
    unexpected = [p for p in sensors if p not in expected]

    cb.add(ClaimKind.FACT, f"{len(recs)} readable records from {first.timestamp[:16].replace('T', ' ')} "
           f"to {last.timestamp[:16].replace('T', ' ')}: " + ", ".join(f"{n} {t}" for t, n in by_type.most_common()) + ".",
           f"{len(recs)} سجل قابل للقراءة.", evidence=(first.record_id, last.record_id))
    cb.add(ClaimKind.FACT, f"Sensor parameters available: {', '.join(ctx.label(p) for p in present) or 'none'}.",
           "الحساسات المتوفرة: " + "، ".join(present), evidence=tuple(
               next(r.record_id for r in recs if r.source_type == "sensor" and r.parameter == p) for p in present))
    if absent:
        cb.add(ClaimKind.MISSING, f"Profile parameters with no data: {', '.join(ctx.label(p) for p in absent)}.",
               "متغيرات متوقعة بدون بيانات: " + "، ".join(absent))
    if unexpected:
        cb.add(ClaimKind.UNCERTAINTY, f"Sensor parameters outside the pump profile, not examined: {', '.join(unexpected)}.",
               "متغيرات خارج ملف المضخة ولم تُفحص.")

    # criticality: only what the registry states
    if a.criticality:
        cb.add(ClaimKind.ASSUMPTION, f"Criticality {a.criticality}: {a.criticality_source or 'registry entry'}",
               f"الأهمية {a.criticality} حسب سجل المعدات (افتراض للعرض).")
    else:
        cb.add(ClaimKind.MISSING, "Criticality is not recorded for this asset; severity cannot be raised for it.",
               "أهمية المعدة غير مسجلة.")

    specs = dict(a.specs)
    unknown_specs = [f["label"] for f in ctx.profile.get("spec_fields", []) if f["key"] not in specs]
    if unknown_specs:
        cb.add(ClaimKind.MISSING, f"Design data not available: {', '.join(unknown_specs)}. "
               "Checks that need them (e.g. NPSH margin, operating point against the pump curve) cannot be made.",
               "بيانات التصميم غير متوفرة، فبعض الفحوصات غير ممكنة.")

    # operating context: trip events and the operating point before them
    events = [r for r in recs if r.source_type == "event"]
    for e in events:
        cb.add(ClaimKind.FACT, f"Event at {e.timestamp[:16].replace('T', ' ')}: {e.text}",
               f"حدث: {e.text}", evidence=(e.record_id,))
    op = {}
    for p in ("flow_m3h", "discharge_pressure_bar", "suction_pressure_bar"):
        series = sorted((r for r in recs if r.source_type == "sensor" and r.parameter == p and r.value is not None),
                        key=lambda r: r.timestamp)
        if series:
            r0 = series[0]
            op[p] = (r0.value, r0.unit, r0.record_id)
    if op:
        cb.add(ClaimKind.MEASURED, "Operating point at the start of the window: " +
               ", ".join(f"{ctx.label(p)} {v:g} {u}" for p, (v, u, _) in op.items()) + ".",
               "نقطة التشغيل في بداية الفترة.", evidence=tuple(i for _, _, i in op.values()))

    status = StageStatus.COMPLETED if present else StageStatus.INSUFFICIENT_DATA
    return StageResult(
        STAGE_ID, NAME, DIVISION, status,
        f"{a.asset_id} identified as {ctx.profile['name'].lower()}; {len(present)} of {len(expected)} "
        f"profile sensors have data; {len(unknown_specs)} design values unknown.",
        f"تم تعريف {a.asset_id}؛ {len(present)} من {len(expected)} حساسات لها بيانات.",
        cb.all(),
        frozen_map({"supported": True, "asset_type": a.type, "profile_id": ctx.profile["profile_id"],
                    "record_count": len(recs), "by_source_type": dict(by_type),
                    "window_start": first.timestamp, "window_end": last.timestamp,
                    "sensors_present": tuple(present), "sensors_absent": tuple(absent),
                    "unknown_specs": tuple(unknown_specs), "criticality": a.criticality,
                    "events": tuple(e.record_id for e in events)}),
        ("Asset type, location and criticality come from a synthetic registry, not a plant system.",),
        ("asset registry", "examination profile", "records"))
