"""Free-form, evidence-based question answering for the advisor (no LLM).

A question in English or Arabic is matched against what the investigation
actually contains - record IDs, hypotheses, sensors, lab results, maintenance,
inspections, operator logs - and the answer is assembled only from those
records. Every statement carries the record IDs it rests on. If nothing in the
records matches, the advisor says so instead of guessing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from .cost_model import estimate, format_money
from .domain import AnalysisResult, EngineConfig, Finding, Observation
from .translations import ar

# ---------------------------------------------------------------- vocabulary
PARAMS: dict[str, tuple[str, str]] = {
    "vibration_mm_s": ("online vibration", "الاهتزاز المباشر"),
    "handheld_vibration_mm_s": ("handheld vibration", "الاهتزاز بالجهاز اليدوي"),
    "bearing_temp_c": ("bearing temperature", "حرارة المحمل"),
    "thermal_check": ("thermal camera check", "الفحص الحراري"),
    "discharge_pressure_bar": ("discharge pressure", "ضغط التصريف"),
    "suction_pressure_bar": ("suction pressure", "ضغط السحب"),
    "strainer_dp_bar": ("suction strainer check", "فحص مصفاة السحب"),
    "flow_m3h": ("flow", "التدفق"),
    "motor_current_a": ("motor current", "تيار المحرك"),
    "seal_pot_level_pct": ("seal pot level", "مستوى خزان مانع التسريب"),
    "seal_leak_ml_min": ("seal leakage", "تسريب مانع التسريب"),
    "oil_iron_ppm": ("iron in oil", "الحديد في الزيت"),
    "oil_water_ppm": ("water in oil", "الماء في الزيت"),
    "oil_particle_iso": ("oil particle count", "الجزيئات في الزيت"),
    "oil_viscosity_change_pct": ("oil viscosity change", "تغير لزوجة الزيت"),
    "alignment_offset_mm": ("shaft alignment", "محاذاة العمود"),
    "lubrication": ("bearing lubrication", "تزييت المحمل"),
    "seal_replacement": ("seal replacement", "تغيير مانع التسريب"),
    "bearing_replacement": ("bearing replacement", "تغيير المحمل"),
    "vib_sensor_cal": ("vibration sensor calibration", "معايرة حساس الاهتزاز"),
    "shift_check": ("operator shift check", "فحص المشغّل في الوردية"),
    "trip": ("pump trip", "توقف المضخة"),
}

SOURCE_AR = {"sensor": "حساس", "operator_log": "سجل مشغّل", "inspection": "فحص",
             "lab": "مختبر", "calibration": "معايرة", "maintenance": "صيانة", "event": "حدث"}

# topic -> (aliases, parameters, source types)
TOPICS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "vibration": (("vibration", "vibrat", "vib ", "اهتزاز", "هزه", "هزة"),
                  ("vibration_mm_s", "handheld_vibration_mm_s"), ()),
    "temperature": (("temperature", "temp", "heat", "حراره", "سخونه"),
                    ("bearing_temp_c", "thermal_check"), ()),
    "suction": (("suction", "npsh", "strainer", "سحب", "شفط", "مصفاه"),
                ("suction_pressure_bar", "strainer_dp_bar"), ()),
    "pressure": (("pressure", "ضغط"),
                 ("discharge_pressure_bar", "suction_pressure_bar"), ()),
    "flow": (("flow", "تدفق", "الدفق"), ("flow_m3h",), ()),
    "current": (("motor current", "motor", "amps", "تيار", "المحرك", "ماطور", "موتور"),
                ("motor_current_a",), ()),
    "seal": (("seal", "leak", "مانع", "تسريب", "تهريب", "سيل", "يسرب", "يهرب"),
             ("seal_pot_level_pct", "seal_leak_ml_min", "seal_replacement"), ()),
    "water": (("water", "moisture", "ماء", "مويه", "رطوبه"), ("oil_water_ppm",), ()),
    "iron": (("iron", "metal", "wear debris", "حديد", "معادن", "برادة"), ("oil_iron_ppm",), ()),
    "particles": (("particle", "contamination", "dirty", "جزيئات", "تلوث", "وسخ"),
                  ("oil_particle_iso",), ()),
    "viscosity": (("viscosity", "لزوجه"), ("oil_viscosity_change_pct",), ()),
    "oil": (("oil", "lab result", "lab test", "laboratory", "sample", "زيت", "مختبر", "عينه"),
            (), ("lab",)),
    "alignment": (("alignment", "aligned", "محاذاه", "استقامه"), ("alignment_offset_mm",), ()),
    "maintenance": (("maintenance", "lubricat", "grease", "work order", "repair",
                     "صيانه", "تزييت", "تشحيم", "شحم", "اصلاح"), (), ("maintenance",)),
    "calibration": (("calibrat", "معايره"), (), ("calibration",)),
    "operators": (("operator", "logbook", "shift log", "مشغل", "المشغلين", "دفتر",
                   "ملاحظات الورديه"), (), ("operator_log",)),
    "inspection": (("inspection", "handheld", "thermal", "الفحوصات", "تفتيش",
                    "الجهاز اليدوي", "حراري"), (), ("inspection",)),
}
GENERIC: dict[str, tuple[str, ...]] = {
    "contradictions": ("contradict", "conflict", "disagree", "mismatch", "تناقض", "تعارض",
                       "ما يتطابق", "متناقض"),
    "missing": ("missing", "gap", "not done", "lacking", "ناقص", "نواقص", "مفقود", "نقص",
                "ما انعمل"),
    "cost": ("cost", "price", "budget", "money", "expensive", "تكلفه", "يكلف", "ميزانيه",
             "فلوس", "سعر", "خساره"),
    "timeline": ("timeline", "sequence", "when", "what happened", "chronolog",
                 "متى", "تسلسل", "قبل التوقف", "الاحداث", "وش صار", "ماذا حدث"),
}
HYPOTHESIS_ALIASES: dict[str, tuple[str, ...]] = {
    "bearing_wear": ("bearing", "محمل", "رولمان", "بيرنق", "بيرنج"),
    "sensor_fault": ("sensor fault", "faulty sensor", "transmitter", "false reading",
                     "عطل الحساس", "عطل في الحساس", "الحساس خربان", "قراءه خاطئه",
                     "خلل الحساس"),
    "seal_failure": ("seal failure", "seal fail", "فشل مانع", "عطل مانع", "مانع التسريب"),
    "cavitation": ("cavitation", "cavitating", "تكهف", "فقاعات"),
    "misalignment": ("misalign", "عدم محاذاه", "عدم المحاذاه", "سوء المحاذاه"),
}
HYPOTHESIS_CUES = ("why", "could", "is it", "possible", "likely", "cause", "what about",
                   "ليش", "لماذا", "هل", "ممكن", "احتمال", "سبب", "وش عن", "ماذا عن", "مو", "ليس")

RECORD_ID = re.compile(r"\b([A-Z]-[A-Z]{3}-\d{4}|WHATIF-\d{3})\b", re.IGNORECASE)
_DIACRITICS = re.compile(r"[ً-ْـ]")
STOPWORDS = {"the", "and", "what", "about", "with", "this", "that", "from", "have", "does",
             "show", "tell", "give", "وش", "ايش", "ماذا", "عن", "في", "على", "من", "هل",
             "عطني", "اعطني", "ابي", "ابغى", "الي", "اللي"}


def normalise(text: str) -> str:
    t = _DIACRITICS.sub("", text.lower())
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ؤ", "و"),
                 ("ئ", "ي")):
        t = t.replace(a, b)
    return f" {t} "


_LATIN = re.compile(r"[a-z]")


def _has(q: str, words: Iterable[str]) -> bool:
    """English aliases must start at a word boundary ('iron' must not match 'environment');
    Arabic aliases match anywhere, because Arabic attaches prefixes such as ال and و."""
    for w in words:
        w = normalise(w).strip()
        if _LATIN.search(w):
            end = r"(?![a-z0-9])" if len(w) <= 3 else ""
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + end, q):
                return True
        elif w in q:
            return True
    return False


# ------------------------------------------------------------- small helpers
def _label(param: str) -> tuple[str, str]:
    return PARAMS.get(param, (param.replace("_", " "), param.replace("_", " ")))


def _fmt(o: Observation) -> str:
    if o.value is None:
        return o.status or "recorded"
    return f"{o.value:g} {o.unit}".strip()


def _when(o: Observation) -> str:
    return o.timestamp.replace("T", " ")[:16]


def _age(o: Observation, end: datetime) -> float:
    return (end - o.ts).total_seconds() / 86400


def _findings_for(ids: set[str], analysis: AnalysisResult) -> list[Finding]:
    seen, out = set(), []
    for f in analysis.all_findings():
        if ids.intersection(f.record_ids) and f.finding_id not in seen:
            seen.add(f.finding_id)
            out.append(f)
    return out


def _hyp_name(config: EngineConfig, hid: str) -> str:
    try:
        return config.hypothesis(hid).name
    except KeyError:
        return hid


def _evidence_lines(findings: list[Finding], config: EngineConfig, limit: int = 6):
    from .advisor import AdvisorItem
    items = []
    verbs = {"support": ("supports", "يدعم"), "refute": ("counts against", "يضعف"),
             "contradiction": ("contradiction", "تناقض"), "missing": ("missing", "ناقص")}
    for f in findings[:limit]:
        en_v, ar_v = verbs.get(f.kind, (f.kind, f.kind))
        hyps = ", ".join(_hyp_name(config, h) for h in f.hypothesis_ids)
        hyps_ar = "، ".join(ar(_hyp_name(config, h)) or _hyp_name(config, h)
                            for h in f.hypothesis_ids)
        status = {"support": "pass", "refute": "info"}.get(f.kind, "fail")
        target_en = f" {hyps}" if hyps and f.kind in ("support", "refute") else ""
        target_ar = f" {hyps_ar}" if hyps_ar and f.kind in ("support", "refute") else ""
        items.append(AdvisorItem(
            f"Used as evidence ({f.finding_id}): {en_v}{target_en} - {f.title}.",
            f"مستخدم كدليل ({f.finding_id}): {ar_v}{target_ar} - {ar(f.title) or f.title}.",
            list(f.record_ids)[:6], status))
    return items


# ------------------------------------------------------------------ answers
def record_answer(rid: str, obs: list[Observation], config: EngineConfig,
                  analysis: AnalysisResult):
    from .advisor import AdvisorAnswer, AdvisorItem
    rec = next((o for o in obs if o.record_id.upper() == rid.upper()), None)
    if rec is None:
        return AdvisorAnswer("record", f"No record {rid}", f"لا يوجد سجل {rid}",
                             [AdvisorItem(f"{rid} is not in this investigation.",
                                          f"السجل {rid} غير موجود في هذا التحقيق.", [], "info")])
    en_p, ar_p = _label(rec.parameter)
    items = [AdvisorItem(
        f"{rec.record_id}: {en_p} = {_fmt(rec)} at {_when(rec)} ({rec.source_type.replace('_', ' ')}, "
        f"{rec.source}).",
        f"{rec.record_id}: {ar_p} = {_fmt(rec)} في {_when(rec)} ({SOURCE_AR.get(rec.source_type, '')}).",
        [rec.record_id], "info")]
    if rec.text:
        items.append(AdvisorItem(f"Record text: \"{rec.text}\"", f"نص السجل: «{rec.text}»",
                                 [], "info"))
    found = _findings_for({rec.record_id}, analysis)
    items += _evidence_lines(found, config)
    if not found:
        items.append(AdvisorItem("This record is not used by any finding.",
                                 "هذا السجل غير مستخدم في أي نتيجة.", [], "info"))
    return AdvisorAnswer("record", f"Record {rec.record_id}", f"السجل {rec.record_id}", items)


def _sensor_summary(param: str, records: list[Observation], config: EngineConfig):
    from .advisor import AdvisorItem
    en_p, ar_p = _label(param)
    vals = [o for o in records if o.value is not None]
    if not vals:
        return []
    first, last = vals[0], vals[-1]
    lo, hi = min(vals, key=lambda o: o.value), max(vals, key=lambda o: o.value)
    unit = first.unit
    items = [AdvisorItem(
        f"{en_p.capitalize()}: {len(vals)} readings, from {first.value:g} to {last.value:g} {unit} "
        f"(range {lo.value:g}-{hi.value:g}).",
        f"{ar_p}: {len(vals)} قراءة، من {first.value:g} إلى {last.value:g} {unit} "
        f"(المدى {lo.value:g}-{hi.value:g}).",
        [first.record_id, last.record_id], "info")]
    limit = config.limits.get(param)
    if limit:
        breaches = [o for o in vals if limit.breached(o.value)]
        sign = ">" if limit.direction == "high" else "<"
        if breaches:
            items.append(AdvisorItem(
                f"Crossed the alarm ({sign} {limit.alarm:g} {unit}) first at {_when(breaches[0])}; "
                f"{len(breaches)} reading(s) in alarm.",
                f"تجاوز حد الإنذار ({sign} {limit.alarm:g} {unit}) أول مرة في {_when(breaches[0])}؛ "
                f"{len(breaches)} قراءة في حالة إنذار.",
                [o.record_id for o in breaches][:6], "fail"))
        else:
            items.append(AdvisorItem(
                f"Stayed within the alarm limit ({sign} {limit.alarm:g} {unit}) the whole time.",
                f"بقي ضمن حد الإنذار ({sign} {limit.alarm:g} {unit}) طوال الفترة.", [], "pass"))
    return items


def _record_lines(records: list[Observation], end: datetime):
    from .advisor import AdvisorItem
    items = []
    for o in sorted(records, key=lambda x: x.ts):
        en_p, ar_p = _label(o.parameter)
        age = _age(o, end)
        when_en = f"{age:.0f} days before the trip" if age >= 2 else _when(o)
        when_ar = f"قبل التوقف بـ {age:.0f} يوم" if age >= 2 else _when(o)
        val = "" if o.value is None else f" = {_fmt(o)}"
        items.append(AdvisorItem(
            f"{o.record_id} - {en_p}{val}, {when_en}. \"{o.text}\"",
            f"{o.record_id} - {ar_p}{val}، {when_ar}.",
            [o.record_id], "info"))
    return items


def topic_answer(topics: list[str], obs: list[Observation], config: EngineConfig,
                 analysis: AnalysisResult):
    from .advisor import AdvisorAnswer, AdvisorItem
    end = max((o.ts for o in obs), default=datetime.now())
    items: list = []
    ids: set[str] = set()
    titles_en, titles_ar = [], []
    for t in topics:
        _, params, sources = TOPICS[t]
        recs = [o for o in obs if o.parameter in params or o.source_type in sources]
        en_t = t.replace("_", " ")
        titles_en.append(en_t)
        titles_ar.append({"vibration": "الاهتزاز", "temperature": "الحرارة", "suction": "السحب",
                          "pressure": "الضغط", "flow": "التدفق", "current": "تيار المحرك",
                          "seal": "مانع التسريب", "water": "الماء في الزيت",
                          "iron": "الحديد في الزيت", "particles": "الجزيئات في الزيت",
                          "viscosity": "لزوجة الزيت", "oil": "تحليل الزيت",
                          "alignment": "المحاذاة", "maintenance": "الصيانة",
                          "calibration": "المعايرة", "operators": "سجلات المشغّلين",
                          "inspection": "الفحوصات الميدانية"}.get(t, en_t))
        if not recs:
            req = [r for h in config.hypotheses for r in h.required
                   if r.parameter in params or r.source_type in sources]
            if req:
                items.append(AdvisorItem(
                    f"No {en_t} records in this investigation, although {req[0].label} is required "
                    f"evidence.",
                    f"لا توجد سجلات عن {titles_ar[-1]} في هذا التحقيق، مع أن "
                    f"«{ar(req[0].label) or req[0].label}» دليل مطلوب.", [], "fail"))
            else:
                items.append(AdvisorItem(f"No {en_t} records in this investigation.",
                                         f"لا توجد سجلات عن {titles_ar[-1]} في هذا التحقيق.",
                                         [], "info"))
            continue
        by_param: dict[str, list[Observation]] = {}
        for o in recs:
            by_param.setdefault(o.parameter, []).append(o)
        for param, rs in by_param.items():
            ids.update(o.record_id for o in rs)
            if rs[0].source_type == "sensor":
                items += _sensor_summary(param, rs, config)
            else:
                items += _record_lines(rs, end)
    items += _evidence_lines(_findings_for(ids, analysis), config)
    return AdvisorAnswer("topic", " / ".join(x.capitalize() for x in titles_en),
                         " / ".join(titles_ar), items[:14],
                         "Built only from this investigation's records.",
                         "مبني فقط من سجلات هذا التحقيق.")


def hypothesis_answer(hid: str, config: EngineConfig, analysis: AnalysisResult):
    from .advisor import AdvisorAnswer, AdvisorItem
    a = analysis.assessment(hid)
    name, name_ar = a.name, ar(a.name) or a.name
    top = analysis.top
    lead = top is not None and top.hypothesis_id == hid
    items = [AdvisorItem(
        f"{name} is ranked #{a.rank} with {a.confidence:.0%} confidence ({a.confidence_label})"
        + ("." if lead else f"; the leading hypothesis is {top.name} ({top.confidence:.0%})."),
        f"{name_ar} في المرتبة {a.rank} بثقة {a.confidence:.0%}"
        + ("." if lead else f"؛ والفرضية الأقوى {ar(top.name) or top.name} ({top.confidence:.0%})."),
        [], "info")]
    for f in a.supporting:
        items.append(AdvisorItem(f"For it: {f.title}.", f"يدعمها: {ar(f.title) or f.title}.",
                                 list(f.record_ids)[:6], "pass"))
    for f in a.refuting:
        items.append(AdvisorItem(f"Against it: {f.title}.", f"ضدها: {ar(f.title) or f.title}.",
                                 list(f.record_ids)[:6], "fail"))
    if not a.supporting:
        items.append(AdvisorItem("None of its supporting rules matched the records.",
                                 "لم تنطبق أي قاعدة داعمة لها على السجلات.", [], "fail"))
    for f in a.missing:
        items.append(AdvisorItem(f"Missing evidence: {f.title} - {f.detail}",
                                 f"دليل ناقص: {ar(f.title) or f.title}.",
                                 list(f.record_ids), "fail"))
    unmatched = [r for r in config.hypothesis(hid).supports
                 if r.label not in {f.title for f in a.supporting}]
    if unmatched and not lead:
        items.append(AdvisorItem(
            "What would make it more likely: " + "; ".join(r.label for r in unmatched[:3]) + ".",
            "ما يرفع احتمالها: " + "؛ ".join(ar(r.label) or r.label for r in unmatched[:3]) + ".",
            [], "info"))
    return AdvisorAnswer("hypothesis", f"About {name}", f"عن {name_ar}", items,
                         "Built only from this investigation's records and rules.",
                         "مبني فقط من سجلات هذا التحقيق وقواعده.")


def generic_answer(kind: str, obs: list[Observation], config: EngineConfig,
                   analysis: AnalysisResult, costs: dict[str, Any]):
    from .advisor import AdvisorAnswer, AdvisorItem
    items: list = []
    if kind == "contradictions":
        for f in analysis.contradictions:
            items.append(AdvisorItem(f"{f.finding_id}: {f.title}. {f.detail}",
                                     f"{f.finding_id}: {ar(f.title) or f.title}.",
                                     list(f.record_ids)[:6], "fail"))
        if not items:
            items.append(AdvisorItem("No contradictions found.", "لا توجد تناقضات.", [], "pass"))
        return AdvisorAnswer(kind, "Contradictions", "التناقضات", items)
    if kind == "missing":
        for f in analysis.missing:
            items.append(AdvisorItem(f"{f.finding_id}: {f.title} - {f.detail}",
                                     f"{f.finding_id}: {ar(f.title) or f.title}.",
                                     list(f.record_ids), "fail"))
        if not items:
            items.append(AdvisorItem("No evidence is missing.", "لا توجد أدلة ناقصة.", [], "pass"))
        return AdvisorAnswer(kind, "Missing evidence", "الأدلة الناقصة", items)
    if kind == "cost":
        sym = costs.get("currency_symbol", "$")
        for a in analysis.assessments[:3]:
            if a.hypothesis_id not in costs.get("profiles", {}):
                continue
            t = estimate(a.hypothesis_id, costs).totals
            items.append(AdvisorItem(
                f"{a.name} ({a.confidence:.0%}): {format_money(t['low'], sym)} - "
                f"{format_money(t['high'], sym)}, base {format_money(t['base'], sym)}.",
                f"{ar(a.name) or a.name} ({a.confidence:.0%}): {format_money(t['low'], sym)} - "
                f"{format_money(t['high'], sym)}، الأساسي {format_money(t['base'], sym)}.",
                [], "info"))
        return AdvisorAnswer(kind, "Cost impact (illustrative)", "أثر التكلفة (توضيحي)", items,
                             "Illustrative figures from config/cost_assumptions.json.",
                             "أرقام توضيحية من ملف افتراضات التكلفة.")
    # timeline
    end = max((o.ts for o in obs), default=datetime.now())
    events: list[tuple[datetime, Any]] = []
    for o in obs:
        if o.source_type != "sensor":
            events.append((o.ts, o))
    for param, limit in config.limits.items():
        hits = sorted((o for o in obs if o.parameter == param and limit.breached(o.value)),
                      key=lambda o: o.ts)
        if hits:
            events.append((hits[0].ts, hits[0]))
    for ts, o in sorted(events, key=lambda e: e[0])[-14:]:
        en_p, ar_p = _label(o.parameter)
        age = _age(o, end)
        prefix_en = f"{age:.0f} days before" if age >= 2 else _when(o)
        prefix_ar = f"قبل التوقف بـ {age:.0f} يوم" if age >= 2 else _when(o)
        if o.source_type == "sensor":
            en, ar_t = f"{en_p} first in alarm ({_fmt(o)})", f"{ar_p} دخل في الإنذار أول مرة ({_fmt(o)})"
            st = "fail"
        else:
            val = "" if o.value is None else f" {_fmt(o)}"
            en, ar_t = f"{en_p}{val}: {o.text}", f"{ar_p}{val}"
            st = "fail" if o.source_type == "event" else "info"
        items.append(AdvisorItem(f"{prefix_en} - {en}", f"{prefix_ar} - {ar_t}", [o.record_id], st))
    return AdvisorAnswer("timeline", "Timeline of key events", "تسلسل الأحداث المهمة", items,
                         "Sensor lines show the first reading that crossed its alarm.",
                         "أسطر الحساسات تبيّن أول قراءة تجاوزت حد الإنذار.")


def search_answer(question: str, obs: list[Observation], config: EngineConfig,
                  analysis: AnalysisResult):
    from .advisor import AdvisorAnswer, AdvisorItem
    q = normalise(question)
    tokens = {w for w in re.findall(r"[\w\-]+", q) if len(w) >= 3 and w not in STOPWORDS}
    if not tokens:
        return None
    scored = []
    for o in obs:
        if o.source_type == "sensor":
            continue
        hay = normalise(" ".join([o.record_id, o.parameter, o.source_type, o.text, o.source,
                                  *_label(o.parameter)]))
        score = sum(1 for t in tokens if t in hay)
        if score:
            scored.append((score, o))
    if not scored:
        return None
    scored.sort(key=lambda s: (-s[0], s[1].timestamp))
    end = max(o.ts for o in obs)
    recs = [o for _, o in scored[:5]]
    items = _record_lines(recs, end)
    items += _evidence_lines(_findings_for({o.record_id for o in recs}, analysis), config, 4)
    return AdvisorAnswer("search", "Records that match your question",
                         "سجلات تطابق سؤالك", items,
                         "Matched by keywords in the records; rephrase for a more specific answer.",
                         "مطابقة بالكلمات في السجلات؛ أعد الصياغة لإجابة أدق.")


# ------------------------------------------------------------------ routing
def route(question: str, obs: Iterable[Observation], config: EngineConfig,
          analysis: AnalysisResult, costs: dict[str, Any]):
    """Return an AdvisorAnswer for entity questions, or None to fall back to intents."""
    obs = list(obs)
    m = RECORD_ID.search(question)
    if m:
        return record_answer(m.group(1).upper(), obs, config, analysis)
    q = normalise(question)
    hyps = [h for h, words in HYPOTHESIS_ALIASES.items()
            if _has(q, words) and any(x.hypothesis_id == h for x in analysis.assessments)]
    topics = [t for t, (words, _, _) in TOPICS.items() if _has(q, words)]
    if hyps and (_has(q, HYPOTHESIS_CUES) or not topics):
        return hypothesis_answer(hyps[0], config, analysis)
    if topics:
        # "oil" plus a specific oil property: answer the specific one only.
        specific = [t for t in topics if t not in ("oil", "pressure")]
        if "suction" in topics and "pressure" in topics:
            topics = [t for t in topics if t != "pressure"]
        if "oil" in topics and specific:
            topics = [t for t in topics if t != "oil"]
        return topic_answer(topics[:3], obs, config, analysis)
    for kind, words in GENERIC.items():
        if _has(q, words):
            return generic_answer(kind, obs, config, analysis, costs)
    return None


def search(question: str, obs: Iterable[Observation], config: EngineConfig,
           analysis: AnalysisResult):
    return search_answer(question, list(obs), config, analysis)
