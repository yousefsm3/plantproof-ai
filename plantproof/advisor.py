"""Rule-based engineering advisor (no LLM, no external calls).

Every answer is computed from the engine's analysis and What If simulations,
so each recommendation can be traced to source record IDs.

Capabilities:
  next_best_checks  - which missing evidence or contradiction to resolve first,
                      ranked by the biggest change its tested outcomes could make
                      (a simple "value of information" estimate using What If runs)
  restart_readiness - evidence checklist before a restart decision
  explain_leader    - why the leading hypothesis leads
  action_plan       - ordered actions with cost range
  answer            - routes a free-text question (English or Arabic) to the above
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .cost_model import estimate, format_money
from .domain import AnalysisResult, EngineConfig, Observation
from .evidence_engine import analyse
from .translations import ar
from .whatif import EVIDENCE_TEMPLATES, WhatIfChange, apply_changes

DISCLAIMER_EN = ("Decision support only. Restart only under your site's procedures, "
                 "permits and authorisation.")
DISCLAIMER_AR = "هذا دعم للقرار فقط. لا تُعِد التشغيل إلا وفق إجراءات موقعك وتصاريحه وموافقاته."


@dataclass
class AdvisorItem:
    en: str
    ar: str
    record_ids: list[str] = field(default_factory=list)
    status: str | None = None          # pass | fail | info


@dataclass
class AdvisorAnswer:
    intent: str
    title_en: str
    title_ar: str
    items: list[AdvisorItem]
    note_en: str = ""
    note_ar: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"intent": self.intent, "title_en": self.title_en, "title_ar": self.title_ar,
                "items": [i.__dict__ for i in self.items],
                "note_en": self.note_en, "note_ar": self.note_ar}


def _name_ar(name: str) -> str:
    return ar(name) or name


# ------------------------------------------------------------------ next checks
def _candidate_values(config: EngineConfig, source_type: str, parameter: str) -> list[float]:
    """Plausible test results: one value on each side of every rule threshold."""
    values: set[float] = set()
    for h in config.hypotheses:
        for rule in h.supports + h.refutes:
            for c in rule.conditions:
                if c.source_type == source_type and c.parameter == parameter:
                    t = c.threshold
                    if c.op in (">", ">="):
                        values.add(round(t * 1.3 if t > 0 else t + 1, 3))
                    elif c.op in ("<", "<="):
                        values.add(round(t * 0.6, 3))
                    else:
                        values.add(t)
    return sorted(values)


def _simulate(observations, config, changes) -> AnalysisResult:
    return analyse(apply_changes(observations, changes), config)


def next_best_checks(observations: Iterable[Observation], config: EngineConfig,
                     analysis: AnalysisResult) -> list[dict[str, Any]]:
    obs = tuple(observations)
    leader = analysis.top
    if leader is None:
        return []
    out = []

    def outcome(changes, label_en, label_ar):
        res = _simulate(obs, config, changes)
        new_top = res.top
        delta = res.assessment(leader.hypothesis_id).confidence - leader.confidence
        flip = new_top is not None and new_top.hypothesis_id != leader.hypothesis_id
        return {"label_en": label_en, "label_ar": label_ar, "delta": round(delta, 3),
                "new_leader": new_top.name if new_top else "-",
                "new_confidence": new_top.confidence if new_top else 0.0,
                "flip": flip, "impact": round(abs(delta) + (0.5 if flip else 0.0), 3)}

    # 1) missing or out-of-date evidence
    for m in analysis.missing:
        source_type, parameter = m.key.split(":", 1)
        values = _candidate_values(config, source_type, parameter)
        outcomes = []
        if values:
            for v in values:
                ch = [WhatIfChange("add_record", {"parameter": parameter,
                                                  "source_type": source_type, "value": v})]
                unit = EVIDENCE_TEMPLATES.get(parameter, {}).get("unit", "")
                outcomes.append(outcome(ch, f"if it reads {v:g} {unit}".strip(),
                                        f"إذا كانت القراءة {v:g} {unit}".strip()))
        else:
            ch = [WhatIfChange("add_record", {"parameter": parameter, "source_type": source_type})]
            outcomes.append(outcome(ch, "if a current record is obtained",
                                    "إذا تم الحصول على سجل حديث"))
        best = max(outcomes, key=lambda o: o["impact"])
        out.append({"kind": "missing", "key": m.key, "finding_id": m.finding_id,
                    "title": m.title, "title_ar": ar(m.title) or m.title,
                    "record_ids": list(m.record_ids), "impact": best["impact"],
                    "outcomes": outcomes})

    # 2) contradictions: what if the conflicting claim/check record is wrong?
    for c in analysis.contradictions:
        ch = [WhatIfChange("exclude_records", {"record_ids": [c.key]})]
        o = outcome(ch, f"if record {c.key} proves wrong", f"إذا ثبت أن السجل {c.key} خاطئ")
        out.append({"kind": "contradiction", "key": c.key, "finding_id": c.finding_id,
                    "title": c.title, "title_ar": ar(c.title) or c.title,
                    "record_ids": list(c.record_ids), "impact": o["impact"],
                    "outcomes": [o]})

    # Contradictions first when impact ties: they are safety-relevant.
    out.sort(key=lambda x: (-x["impact"], x["kind"] != "contradiction", x["finding_id"]))
    return out


def _checks_answer(observations, config, analysis) -> AdvisorAnswer:
    checks = next_best_checks(observations, config, analysis)
    items = []
    for i, c in enumerate(checks, start=1):
        o = max(c["outcomes"], key=lambda x: x["impact"])
        if o["impact"] == 0:
            eff_en = "no tested result would change the current conclusion (lower priority)."
            eff_ar = "لا توجد نتيجة مختبَرة تغيّر الاستنتاج الحالي (أولوية أقل)."
        elif o["flip"]:
            eff_en = (f"{o['label_en']}, the leading hypothesis would change to "
                      f"{o['new_leader']} ({o['new_confidence']:.0%}).")
            eff_ar = (f"{o['label_ar']}، ستتغير الفرضية الأقوى إلى "
                      f"{_name_ar(o['new_leader'])} ({o['new_confidence']:.0%}).")
        else:
            eff_en = (f"{o['label_en']}, confidence in the current leader would move by "
                      f"{o['delta']:+.0%}.")
            eff_ar = f"{o['label_ar']}، ستتغير ثقة الفرضية الحالية بمقدار {o['delta']:+.0%}."
        verb_en = "Resolve" if c["kind"] == "contradiction" else "Collect"
        verb_ar = "حُلّ" if c["kind"] == "contradiction" else "اجمع"
        items.append(AdvisorItem(
            f"{i}. {verb_en} {c['finding_id']} - {c['title']} (impact {c['impact']:.2f}): {eff_en}",
            f"{i}. {verb_ar} {c['finding_id']} - {c['title_ar']}: {eff_ar}",
            c["record_ids"], "info"))
    if not items:
        items.append(AdvisorItem("No open evidence gaps or contradictions.",
                                 "لا توجد فجوات أدلة أو تناقضات مفتوحة.", status="pass"))
    return AdvisorAnswer(
        "checks", "What to check first", "ماذا أفحص أولًا", items,
        "Impact = the biggest change any tested result of that check could make to the "
        "current conclusion (simulated with What If; original data untouched). +0.5 if the "
        "leading hypothesis would change.",
        "الأثر = أكبر تغيير يمكن أن تُحدثه أي نتيجة مختبَرة لهذا الفحص في الاستنتاج الحالي "
        "(محاكاة ماذا لو بدون المساس بالبيانات الأصلية)، ويُضاف 0.5 إذا تغيرت الفرضية الأقوى.")


# -------------------------------------------------------------- restart check
def restart_readiness(analysis: AnalysisResult, config: EngineConfig) -> AdvisorAnswer:
    top = analysis.top
    items: list[AdvisorItem] = []
    n_c = len(analysis.contradictions)
    items.append(AdvisorItem(
        "No unresolved contradictions" if n_c == 0 else f"{n_c} contradiction(s) still unresolved",
        "لا توجد تناقضات معلّقة" if n_c == 0 else f"يوجد {n_c} تناقض لم يُحل بعد",
        [c.key for c in analysis.contradictions], "pass" if n_c == 0 else "fail"))
    if top is not None:
        miss = top.missing
        items.append(AdvisorItem(
            f"All evidence required for {top.name} is present" if not miss else
            f"{len(miss)} required evidence item(s) missing for {top.name}",
            f"كل الأدلة المطلوبة لـ{_name_ar(top.name)} موجودة" if not miss else
            f"ينقص {len(miss)} دليل مطلوب لـ{_name_ar(top.name)}",
            [rid for m in miss for rid in m.record_ids], "pass" if not miss else "fail"))
        ok = top.confidence >= config.high_threshold
        items.append(AdvisorItem(
            f"Leading confidence {top.confidence:.0%} "
            f"{'meets' if ok else 'is below'} the {config.high_threshold:.0%} threshold",
            f"ثقة الفرضية الأقوى {top.confidence:.0%} "
            f"{'تحقق' if ok else 'أقل من'} الحد {config.high_threshold:.0%}",
            top.record_ids[:6], "pass" if ok else "fail"))
        second = analysis.assessments[1] if len(analysis.assessments) > 1 else None
        gap = top.confidence - (second.confidence if second else 0.0)
        clear = gap >= 0.25
        items.append(AdvisorItem(
            f"Margin over the next hypothesis: {gap:.0%} "
            f"({'clear' if clear else 'not clear enough, need 25%'})",
            f"الفارق عن الفرضية التالية: {gap:.0%} "
            f"({'واضح' if clear else 'غير كافٍ، المطلوب 25%'})",
            [], "pass" if clear else "fail"))
    fails = sum(1 for i in items if i.status == "fail")
    if fails == 0:
        title_en, title_ar = ("Evidence supports a restart decision",
                              "الأدلة تدعم اتخاذ قرار إعادة التشغيل")
    else:
        title_en = f"Not ready: {fails} item(s) to close before deciding"
        title_ar = f"غير جاهز: يجب إغلاق {fails} بند قبل القرار"
    return AdvisorAnswer("restart", title_en, title_ar, items, DISCLAIMER_EN, DISCLAIMER_AR)


# ------------------------------------------------------------------- explain
def explain_leader(analysis: AnalysisResult, config: EngineConfig) -> AdvisorAnswer:
    top = analysis.top
    if top is None:
        return AdvisorAnswer("explain", "No hypothesis to explain", "لا توجد فرضية للشرح", [])
    items = [AdvisorItem(
        f"{top.name} leads with {top.confidence:.0%} ({top.confidence_label}).",
        f"{_name_ar(top.name)} في المقدمة بثقة {top.confidence:.0%}.", [], "info")]
    for f in top.supporting:
        items.append(AdvisorItem(f"Supports: {f.title}. {f.detail}",
                                 f"يدعمها: {ar(f.title) or f.title}", list(f.record_ids), "pass"))
    for f in top.refuting:
        items.append(AdvisorItem(f"Against: {f.title}. {f.detail}",
                                 f"ضدها: {ar(f.title) or f.title}", list(f.record_ids), "fail"))
    for f in top.missing:
        items.append(AdvisorItem(f"Missing: {f.title} - {f.detail}",
                                 f"ناقص: {ar(f.title) or f.title}", list(f.record_ids), "fail"))
    items.append(AdvisorItem(
        f"Score: support ratio {top.support_ratio:.0%} × coverage factor "
        f"{config.coverage_floor + (1 - config.coverage_floor) * top.coverage:.2f} × "
        f"contested factor {top.contested_factor:.2f} = {top.confidence:.0%}.",
        f"الحساب: نسبة الدعم × معامل التغطية × معامل التعارض = {top.confidence:.0%}.",
        [], "info"))
    second = analysis.assessments[1] if len(analysis.assessments) > 1 else None
    if second is not None:
        items.append(AdvisorItem(
            f"Next: {second.name} at {second.confidence:.0%}.",
            f"التالية: {_name_ar(second.name)} بثقة {second.confidence:.0%}.", [], "info"))
    return AdvisorAnswer("explain", f"Why {top.name} leads",
                         f"لماذا {_name_ar(top.name)} في المقدمة", items)


# ---------------------------------------------------------------- action plan
def action_plan(observations, config: EngineConfig, analysis: AnalysisResult,
                costs: dict[str, Any]) -> AdvisorAnswer:
    items: list[AdvisorItem] = []
    step = 0
    for c in next_best_checks(observations, config, analysis):
        step += 1
        verb_en = "Resolve" if c["kind"] == "contradiction" else "Collect"
        verb_ar = "حُلّ" if c["kind"] == "contradiction" else "اجمع"
        items.append(AdvisorItem(f"{step}. {verb_en} {c['finding_id']}: {c['title']}",
                                 f"{step}. {verb_ar} {c['finding_id']}: {c['title_ar']}",
                                 c["record_ids"], "info"))
    top = analysis.top
    if top is not None and top.confidence_label != "Low":
        for a in top.recommended_actions:
            step += 1
            items.append(AdvisorItem(f"{step}. If {top.name} is confirmed: {a}",
                                     f"{step}. إذا تأكدت {_name_ar(top.name)}: {ar(a) or a}",
                                     [], "info"))
        if top.hypothesis_id in costs.get("profiles", {}):
            t = estimate(top.hypothesis_id, costs).totals
            sym = costs.get("currency_symbol", "£")
            items.append(AdvisorItem(
                f"Budget range if confirmed: {format_money(t['low'], sym)} - "
                f"{format_money(t['high'], sym)} (base {format_money(t['base'], sym)}).",
                f"الميزانية المتوقعة إذا تأكد السبب: {format_money(t['low'], sym)} - "
                f"{format_money(t['high'], sym)}.", [], "info"))
    return AdvisorAnswer("plan", "Recommended action plan", "خطة العمل المقترحة", items,
                         DISCLAIMER_EN, DISCLAIMER_AR)


# ------------------------------------------------------------------- routing
INTENTS = {
    "checks": ("first", "check", "next", "priority", "inspect", "test",
               "أفحص", "افحص", "أول", "اول", "أولوية", "فحص", "الأهم"),
    "restart": ("restart", "safe", "start", "ready", "run again",
                "تشغيل", "آمن", "امن", "جاهز", "أشغل", "اشغل"),
    "explain": ("why", "explain", "reason", "leading", "لماذا", "ليش", "ليه", "اشرح", "سبب"),
    "plan": ("plan", "action", "do", "steps", "what now", "خطة", "إجراء", "اجراء", "خطوات",
             "وش اسوي", "ماذا أفعل"),
}

SUGGESTED = (
    ("What should I check first?", "ماذا أفحص أولًا؟", "checks"),
    ("Is it safe to restart?", "هل إعادة التشغيل آمنة؟", "restart"),
    ("Why is this hypothesis leading?", "لماذا هذه الفرضية في المقدمة؟", "explain"),
    ("What is the action plan?", "ما خطة العمل؟", "plan"),
)


def detect_intent(question: str) -> str | None:
    q = question.strip().lower()
    if not q:
        return None
    scores = {k: sum(1 for w in words if w in q) for k, words in INTENTS.items()}
    # On a tie prefer the broader answer: a plan already includes the checks.
    order = ("plan", "restart", "explain", "checks")
    best = max(order, key=lambda k: (scores[k], -order.index(k)))
    return best if scores[best] > 0 else None


def answer(question: str, observations, config: EngineConfig, analysis: AnalysisResult,
           costs: dict[str, Any]) -> AdvisorAnswer:
    intent = detect_intent(question)
    if intent == "checks":
        return _checks_answer(observations, config, analysis)
    if intent == "restart":
        return restart_readiness(analysis, config)
    if intent == "explain":
        return explain_leader(analysis, config)
    if intent == "plan":
        return action_plan(observations, config, analysis, costs)
    return AdvisorAnswer(
        "help", "I can answer these questions", "أستطيع الإجابة عن هذه الأسئلة",
        [AdvisorItem(en, ar_, status="info") for en, ar_, _ in SUGGESTED],
        "The advisor is rule-based: it only answers from this investigation's evidence.",
        "المساعد مبني على القواعد: يجيب فقط من أدلة هذا التحقيق.")
