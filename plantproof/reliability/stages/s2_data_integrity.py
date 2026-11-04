"""Stage 2 — Data integrity and evidence examination (Trust & Verification).

Checks the records before anything is concluded from them, grades their quality, decides
which records are usable, and rates how far each online sensor can be trusted. The grade
caps every later confidence: poor data can never silently produce a confident conclusion.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from ..context import ClaimBuilder, RunContext
from ..types import Check, ClaimKind, StageResult, StageStatus, frozen_map

STAGE_ID, NAME, DIVISION = "S2", "Data integrity and evidence", "Trust & Verification"
WEIGHT = {"high": 3, "medium": 2, "low": 1}
GRADES = ((0.95, "A", 1.0), (0.80, "B", 0.9), (0.60, "C", 0.75), (0.0, "D", 0.5))


def grade_for(score: float) -> tuple[str, float]:
    for floor, g, cap in GRADES:
        if score >= floor:
            return g, cap
    return "D", 0.5


def run(ctx: RunContext) -> StageResult:
    cb = ClaimBuilder(STAGE_ID)
    prof, recs, data = ctx.profile, ctx.records, ctx.data
    checks: list[dict] = []
    excluded: set[str] = set()

    def check(cid, name, severity, passed, detail, ids=()):
        checks.append({"check_id": cid, "name": name, "severity": severity, "passed": passed,
                       "detail": detail, "record_ids": tuple(ids)})

    # D1 unreadable rows
    rej = data.rejected
    check("D1", "Every row is readable", "high", not rej,
          "All rows parsed." if not rej else
          f"{len(rej)} row(s) rejected: " + "; ".join(f"row {r.row_number} ({r.record_id}): {r.reason}" for r in rej[:5]))
    # (rejected rows are not records, so they are named in the text, never cited as evidence)

    # D2 duplicate record IDs
    dup_ids = [i for i, n in Counter(r.record_id for r in recs).items() if n > 1]
    check("D2", "Record IDs are unique", "high", not dup_ids,
          "No duplicate IDs." if not dup_ids else f"Duplicate IDs (first copy kept): {', '.join(dup_ids)}", dup_ids)

    # D3/D4 conflicting or repeated measurements of the same quantity at the same time
    groups = defaultdict(list)
    seen_ids = set()
    for r in recs:
        if r.value is None or r.record_id in seen_ids:
            continue
        seen_ids.add(r.record_id)
        groups[(r.timestamp, r.source_type, r.parameter)].append(r)
    conflicts, repeats = [], []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        if len({r.value for r in rows}) > 1:
            conflicts.append(rows)
            excluded.update(r.record_id for r in rows)
        else:
            repeats.append(rows)
            excluded.update(r.record_id for r in rows[1:])
    check("D3", "No conflicting measurements", "high", not conflicts,
          "No conflicts." if not conflicts else "; ".join(
              f"{rows[0].parameter} at {rows[0].timestamp[11:16]}: " + " vs ".join(f"{r.value:g} ({r.record_id})" for r in rows)
              for rows in conflicts) + ". All conflicting readings excluded.",
          [r.record_id for rows in conflicts for r in rows])
    check("D4", "No repeated observations", "medium", not repeats,
          "No repeats." if not repeats else f"{len(repeats)} repeated reading(s); one copy kept each.",
          [r.record_id for rows in repeats for r in rows[1:]])

    # D5 physically impossible or empty sensor readings
    invalid = []
    for r in recs:
        if r.source_type != "sensor":
            continue
        spec = prof["sensors"].get(r.parameter)
        if r.value is None or (spec and not spec["min"] <= r.value <= spec["max"]):
            invalid.append(r)
            excluded.add(r.record_id)
            if r.value is not None and spec:
                op, thr = ("<", spec["min"]) if r.value < spec["min"] else (">", spec["max"])
                cb.add(ClaimKind.FINDING,
                       f"{ctx.label(r.parameter)} reading {r.value:g} {r.unit} ({r.record_id}) is outside the "
                       f"plausible range {spec['min']:g}–{spec['max']:g}; excluded.",
                       f"قراءة {r.value:g} خارج المدى المعقول، واستُبعدت.",
                       evidence=(r.record_id,), check=Check(r.parameter, op, thr, "all"))
    check("D5", "Sensor readings are physically plausible", "high", not invalid,
          "All readings plausible." if not invalid else f"{len(invalid)} implausible or empty reading(s) excluded.",
          [r.record_id for r in invalid])

    # D6 completeness of hourly sensor series
    cadence = prof.get("sensor_cadence_s", 3600)
    coverage, gaps = {}, {}
    for p in prof["sensors"]:
        stamps = sorted({r.ts for r in recs if r.source_type == "sensor" and r.parameter == p
                         and r.record_id not in excluded})
        if len(stamps) < 2:
            continue
        expected = int((stamps[-1] - stamps[0]).total_seconds() // cadence) + 1
        coverage[p] = round(len(stamps) / expected, 3)
        gaps[p] = [(a.isoformat(), b.isoformat()) for a, b in zip(stamps, stamps[1:])
                   if (b - a).total_seconds() > 1.5 * cadence]
    worst = min(coverage.values()) if coverage else 0.0
    sev = "high" if worst < 0.8 else "medium"
    gap_txt = "; ".join(f"{ctx.label(p)} {g[0][0][5:16]}→{g[0][1][5:16]}" for p, g in gaps.items() if g)[:300]
    check("D6", "Sensor series are complete", sev, worst >= 0.95,
          f"Lowest coverage {worst:.0%}." + (f" Gaps: {gap_txt}" if gap_txt else ""))

    # D7 traceability: every record names its source
    no_source = [r.record_id for r in recs if not r.source.strip()]
    check("D7", "Every record names its source", "low", not no_source,
          "All records name a source." if not no_source else f"No source on: {', '.join(no_source[:8])}", no_source)

    # D8 source reliability: calibration and independent cross-checks of online sensors
    end = max((r.ts for r in recs), default=datetime.now())
    trust: dict[str, str] = {}
    trust_reason: dict[str, str] = {}
    cal_ids = []
    for cal in prof.get("calibrations", []):
        p = cal["covers"]
        cal_recs = sorted((r for r in recs if r.source_type == "calibration" and r.parameter == cal["parameter"]),
                          key=lambda r: r.timestamp)
        if not cal_recs:
            trust[p], trust_reason[p] = "unverified", "no calibration record"
            cb.add(ClaimKind.MISSING, f"No calibration record for the {ctx.label(p).lower()} transmitter.",
                   "لا يوجد سجل معايرة لحساس الاهتزاز.")
            continue
        last = cal_recs[-1]
        age = (end - last.ts).days
        cal_ids.append(last.record_id)
        if age > cal["max_age_days"]:
            trust[p], trust_reason[p] = "unverified", f"calibration {age} days old (limit {cal['max_age_days']})"
            cb.add(ClaimKind.FACT, f"The {ctx.label(p).lower()} transmitter was last calibrated {age} days before the "
                   f"end of the window (limit {cal['max_age_days']} days): calibration is overdue.",
                   f"معايرة حساس الاهتزاز متأخرة ({age} يومًا).", evidence=(last.record_id,))
        else:
            trust[p], trust_reason[p] = "trusted", f"calibrated {age} days earlier"
            cb.add(ClaimKind.FACT, f"The {ctx.label(p).lower()} transmitter was calibrated {age} days before the end "
                   f"of the window (within the {cal['max_age_days']}-day limit).",
                   f"حساس الاهتزاز معاير قبل {age} يومًا.", evidence=(last.record_id,))
    by_id = {r.record_id: r for r in recs}
    pairs = {(x["independent"], x["online"]) for x in prof.get("cross_check_pairs", [])}
    engine = ctx.engine()
    for c in engine.contradictions:
        params = {by_id[i].parameter for i in c.record_ids if i in by_id}
        for indep, online in pairs:
            if indep in params and online in params:
                trust[online], trust_reason[online] = "suspect", f"disputed by independent measurement ({c.finding_id})"
        cb.add(ClaimKind.FINDING, f"Evidence Engine contradiction {c.finding_id}: {c.title}.",
               f"تناقض من محرك الأدلة {c.finding_id}.", evidence=tuple(c.record_ids[:12]),
               finding_refs=(c.finding_id,), key=True)
    for p in prof["sensors"]:
        trust.setdefault(p, "trusted" if p in coverage else "no data")
        trust_reason.setdefault(p, "no calibration rule in profile" if p in coverage else "no readings")
    weak = {p: t for p, t in trust.items() if t in ("suspect", "unverified")}
    check("D8", "Online sensors are trustworthy", "medium" if "suspect" not in weak.values() else "high",
          not weak, "No trust issues." if not weak else
          "; ".join(f"{ctx.label(p)}: {t} ({trust_reason[p]})" for p, t in weak.items()), cal_ids)

    # grade
    total = sum(WEIGHT[c["severity"]] for c in checks)
    lost = sum(WEIGHT[c["severity"]] for c in checks if not c["passed"])
    score = round(1 - lost / total, 3)
    grade, cap = grade_for(score)
    for c in checks:
        cb.add(ClaimKind.FACT if c["passed"] else ClaimKind.FINDING,
               f"{c['check_id']} {c['name']}: {'pass' if c['passed'] else 'FAIL'}. {c['detail']}",
               "", evidence=c["record_ids"][:12])
    usable = tuple(sorted({r.record_id for r in recs} - excluded))
    sensors_usable = [i for i in usable if by_id[i].source_type == "sensor"]
    cb.add(ClaimKind.FINDING, f"Data quality grade {grade} (score {score:.2f}); later confidence is capped at "
           f"{cap:.0%}. {len(usable)} of {len(set(by_id))} records are usable.",
           f"درجة جودة البيانات {grade}، والثقة لاحقًا لا تتجاوز {cap:.0%}.", key=True)

    status = StageStatus.COMPLETED if sensors_usable else StageStatus.INSUFFICIENT_DATA
    return StageResult(
        STAGE_ID, NAME, DIVISION, status,
        f"Data quality {grade} ({score:.2f}); {sum(not c['passed'] for c in checks)} of {len(checks)} checks failed; "
        f"confidence cap {cap:.0%}.",
        f"جودة البيانات {grade}؛ فشل {sum(not c['passed'] for c in checks)} من {len(checks)} فحوصات.",
        cb.all(),
        frozen_map({"grade": grade, "score": score, "cap": cap, "checks": tuple(checks),
                    "usable_ids": usable, "excluded_ids": tuple(sorted(excluded)),
                    "coverage": dict(coverage), "gaps": {k: tuple(v) for k, v in gaps.items()},
                    "trust": dict(trust), "trust_reason": dict(trust_reason),
                    "contradictions": tuple(c.finding_id for c in engine.contradictions)}),
        ("Calibration status is recorded only for the vibration transmitter; other sensors are assumed trusted "
         "unless the data says otherwise.",
         "Plausibility ranges are wide physical limits, not process limits."),
        ("records", "rejected rows", "examination profile", "Evidence Engine contradictions"))
