"""AI fact check: verify an AI-written (or any) report sentence by sentence against the records.

Any text - a draft from ChatGPT, a colleague's note, a handover - is split into sentences.
Each sentence is checked against this investigation's records:

- supported      a record confirms it (record IDs shown)
- contradicted   a record says otherwise (record IDs shown)
- no_evidence    nothing in the records confirms or refutes it, so it must not be trusted

Claims understood (English and Arabic): record IDs, sensor and lab readings described as
high / low / normal, quoted numbers for a reading, seal leakage, and statements that a
hypothesis is (or is not) the cause. Everything else is reported as "no evidence" rather
than guessed. No language model is used, so the checker itself cannot invent anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .advisor_qa import PARAMS, RECORD_ID, _has, normalise
from .domain import AnalysisResult, EngineConfig, Observation
from .translations import ar as tr

SUPPORTED, CONTRADICTED, NO_EVIDENCE = "supported", "contradicted", "no_evidence"


@dataclass
class SentenceCheck:
    sentence: str
    verdict: str
    reasons: list[tuple[str, str]] = field(default_factory=list)   # (English, Arabic)
    record_ids: list[str] = field(default_factory=list)


# parameter -> aliases; more specific parameters first so "handheld vibration" wins
CLAIM_PARAMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("handheld_vibration_mm_s", ("handheld", "الجهاز اليدوي", "اليدوي")),
    ("vibration_mm_s", ("vibration", "vibrat", "اهتزاز")),
    ("bearing_temp_c", ("bearing temp", "temperature", "حراره المحمل", "حراره", "سخونه")),
    ("seal_pot_level_pct", ("seal pot", "seal level", "خزان مانع", "مستوى مانع", "خزان")),
    ("seal_leak_ml_min", ("leak", "تسريب", "تهريب", "يسرب")),
    ("suction_pressure_bar", ("suction", "سحب")),
    ("discharge_pressure_bar", ("discharge", "تصريف")),
    ("flow_m3h", ("flow", "تدفق")),
    ("motor_current_a", ("motor current", "current", "تيار")),
    ("oil_water_ppm", ("water", "moisture", "ماء", "مويه", "رطوبه")),
    ("oil_iron_ppm", ("iron", "metal", "wear debris", "حديد", "معادن", "برادة")),
    ("oil_particle_iso", ("particle", "contamination", "cleanliness", "جزيئات", "تلوث", "نظافه")),
    ("oil_viscosity_change_pct", ("viscosity", "لزوج")),
    ("alignment_offset_mm", ("alignment", "aligned", "محاذاه")),
)
EXCLUSIVE = {"handheld_vibration_mm_s": "vibration_mm_s", "seal_pot_level_pct": "seal_leak_ml_min"}

# (abnormal-if-above, normal-if-at-or-below) for non-sensor readings
BANDS = {
    "handheld_vibration_mm_s": (7.1, 4.5), "seal_leak_ml_min": (5.0, 1.0),
    "oil_water_ppm": (500.0, 200.0), "oil_iron_ppm": (50.0, 25.0),
    "oil_particle_iso": (18.0, 16.0), "oil_viscosity_change_pct": (10.0, 5.0),
    "alignment_offset_mm": (0.1, 0.05),
}
HIGH_WORDS = ("high", "elevated", "rising", "rose", "increased", "above", "excessive", "spike",
              "عالي", "مرتفع", "ارتفع", "زاد", "زياده", "فوق", "كثير")
LOW_WORDS = ("low", "dropped", "drop", "fell", "falling", "decreased", "below", "lost",
             "منخفض", "انخفض", "نزل", "نقص", "تحت", "قليل")
CHANGE_WORDS = ("rising", "rose", "increased", "increasing", "climbed", "dropped", "fell",
                "falling", "decreased", "decreasing", "ارتفع", "زاد", "انخفض", "نزل", "نقص", "يرتفع",
                "ينزل", "ينخفض")
NORMAL_WORDS = ("normal", "fine", "ok", "okay", "stable", "clean", "healthy", "within",
                "acceptable", "good", "طبيعي", "سليم", "مستقر", "نظيف", "ضمن", "تمام", "زين", "جيد")
NEGATIONS = ("not", "no", "never", "without", "isn't", "wasn't", "doesn't", "none",
             "ليس", "مو", "ما", "لا", "غير", "بدون", "مافي", "ما فيه", "لايوجد")
LEAK_PRESENT = ("leak", "leaking", "leaks", "تسريب", "يسرب", "تهريب", "يهرب")

CLAIM_HYPOTHESES = {
    "bearing_wear": ("bearing wear", "bearing failure", "worn bearing", "bearing damage",
                     "تاكل المحمل", "تلف المحمل", "عطل المحمل", "تاكل في المحمل"),
    "sensor_fault": ("sensor fault", "faulty sensor", "sensor is faulty", "false reading",
                     "sensor error", "عطل الحساس", "خلل الحساس", "الحساس خربان", "عطل في الحساس",
                     "قراءه خاطئه"),
    "seal_failure": ("seal failure", "seal failed", "failed seal", "seal damage",
                     "فشل مانع", "عطل مانع", "تلف مانع", "عطل في مانع"),
    "cavitation": ("cavitation", "cavitating", "تكهف"),
    "misalignment": ("misalign", "عدم المحاذاه", "عدم محاذاه", "سوء المحاذاه"),
}
HYP_NEGATIONS = ("not", "ruled out", "rule out", "unlikely", "rather than", "excluded",
                 "isn't", "no sign", "ليس", "مو", "غير", "مستبعد", "استبعاد", "ما هو", "مب")

NUMBER = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)(?![\w-])")
_SPLIT = re.compile(r"(?<=[.!?؟؛])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip(" -•*\t") for p in _SPLIT.split(text or "")]
    return [p for p in parts if len(p) >= 4]


_AR = "ء-ي"   # Arabic letters


def _word_has(q: str, words, whole: bool = False) -> bool:
    """English words match as whole words ('no' must not match 'normal'). Arabic words may
    take a و / ب / ال prefix and any suffix; with whole=True (negations) they must stand
    alone, so 'ما' does not match 'ماء' or 'مانع'."""
    for w in words:
        n = normalise(w).strip()
        if re.search(r"[a-z]", n):
            if re.search(r"(?<![a-z0-9'])" + re.escape(n) + r"(?![a-z0-9'])", q):
                return True
        elif whole:
            if re.search(rf"(?<![{_AR}])" + re.escape(n) + rf"(?![{_AR}])", q):
                return True
        elif re.search(rf"(?<![{_AR}])(?:وال|بال|ال|و|ب)?" + re.escape(n), q):
            return True
    return False


def _params_in(q: str) -> list[str]:
    q = q.replace("مانع التسريب", "مانع").replace("mechanical seal", "seal")
    found = [p for p, aliases in CLAIM_PARAMS if _has(q, aliases)]
    for strong, weak in EXCLUSIVE.items():
        if strong in found and weak in found:
            if strong == "handheld_vibration_mm_s" or not _has(q, LEAK_PRESENT):
                found.remove(weak)
    return found


def _claimed_state(q: str, param: str) -> str | None:
    neg = _word_has(q, NEGATIONS, whole=True)
    if _word_has(q, NORMAL_WORDS):
        return "abnormal" if neg else "normal"
    if _word_has(q, HIGH_WORDS):
        return "normal" if neg else "high"
    if _word_has(q, LOW_WORDS):
        return "normal" if neg else "low"
    if param == "seal_leak_ml_min" and _has(q, LEAK_PRESENT):
        return "normal" if neg else "high"
    return None


def _baseline_shift(series: list[Observation], pct: float = 0.15) -> tuple[str, list[Observation]]:
    """For a sensor without an alarm limit: compare the last 6 h with the first 18 h."""
    vals = [o.value for o in series]
    base = sum(vals[:18]) / max(1, len(vals[:18]))
    tail = series[-6:]
    late = sum(o.value for o in tail) / len(tail)
    change = (late - base) / base if base else 0
    if change > pct:
        return "high", tail
    if change < -pct:
        return "low", tail
    return "normal", tail


def _actual_state(param: str, obs: list[Observation], cfg: EngineConfig):
    """Return (state, direction, evidence records) or None if there is no such record."""
    series = sorted((o for o in obs if o.parameter == param and o.value is not None),
                    key=lambda o: o.timestamp)
    if not series:
        return None
    limit = cfg.limits.get(param)
    if series[0].source_type == "sensor":
        if limit:
            high = limit.direction == "high"
            bad = [o for o in series if (o.value > limit.alarm if high else o.value < limit.alarm)]
            if bad:
                return ("high" if high else "low"), limit.direction, bad[:6]
            return "normal", limit.direction, series[-3:]
        state, ev = _baseline_shift(series)
        return state, None, ev
    if param in BANDS:
        top, ok = BANDS[param]
        latest = series[-1]
        if latest.value > top:
            return "high", "high", [latest]
        if latest.value <= ok:
            return "normal", "high", [latest]
        return "borderline", "high", [latest]
    return None


STATE_AR = {"high": "مرتفع", "low": "منخفض", "normal": "طبيعي", "abnormal": "غير طبيعي"}


def _labels(param: str) -> tuple[str, str]:
    return PARAMS.get(param, (param.replace("_", " "), param.replace("_", " ")))


def _check_param(q: str, param: str, obs: list[Observation], cfg: EngineConfig):
    """Return (verdict, (reason_en, reason_ar), record_ids) or None if not checkable."""
    actual = _actual_state(param, obs, cfg)
    if actual is None:
        return None
    state, _direction, ev = actual
    ids = [o.record_id for o in ev]
    en, ar = _labels(param)
    claimed = _claimed_state(q, param)
    nums = [float(n) for n in NUMBER.findall(q)]
    if nums and not claimed:
        values = [o for o in obs if o.parameter == param and o.value is not None]
        for n in nums:
            close = [o for o in values if abs(o.value - n) <= max(0.05 * abs(o.value), 0.05)]
            if close:
                o = close[0]
                return SUPPORTED, (f"{en} = {o.value:g} in {o.record_id}",
                                   f"{ar} = {o.value:g} في السجل {o.record_id}"), [o.record_id]
        o = min(values, key=lambda x: min(abs(x.value - n) for n in nums))
        return CONTRADICTED, (f"no {en} record has that value (nearest: {o.value:g} in {o.record_id})",
                              f"لا يوجد سجل لـ{ar} بهذه القيمة (الأقرب {o.value:g} في {o.record_id})"), \
            [o.record_id]
    if claimed is None or state == "borderline":
        return None
    if claimed == "abnormal":
        claimed = state if state in ("high", "low") else "abnormal"
    shown = ", ".join(f"{o.value:g}" for o in ev[:3])
    if (state == "normal" and claimed in ("high", "low") and ev[0].source_type == "sensor"
            and _word_has(q, CHANGE_WORDS)):
        series = sorted((o for o in obs if o.parameter == param and o.value is not None),
                        key=lambda o: o.timestamp)
        shift, tail = _baseline_shift(series, pct=0.08)
        if shift == claimed:
            start = sum(o.value for o in series[:18]) / len(series[:18])
            return SUPPORTED, (
                f"{en} moved from about {start:.3g} to {tail[-1].value:g}, but stayed within its alarm limit",
                f"{ar} تغيّر من حوالي {start:.3g} إلى {tail[-1].value:g} لكنه بقي ضمن حد الإنذار"), \
                [o.record_id for o in tail[-3:]]
    if claimed == state:
        return SUPPORTED, (f"{en} is {state} ({shown})", f"{ar} {STATE_AR[state]} ({shown})"), ids
    return CONTRADICTED, (f"records show {en} is {state}, not {claimed} ({shown})",
                          f"السجلات تبيّن أن {ar} {STATE_AR[state]} وليس {STATE_AR[claimed]} ({shown})"), ids


def _check_hypothesis(q: str, result: AnalysisResult, cfg: EngineConfig):
    out = []
    for hid, aliases in CLAIM_HYPOTHESES.items():
        if not _has(q, aliases):
            continue
        a = next((x for x in result.assessments if x.hypothesis_id == hid), None)
        if a is None:
            continue
        negated = _word_has(q, HYP_NEGATIONS, whole=True)
        likely = a.confidence >= cfg.medium_threshold
        verdict = SUPPORTED if likely != negated else CONTRADICTED
        lead = a.rank == 1
        out.append((verdict, (
            f"{a.name}: engine confidence {a.confidence:.0%}" + (" (leading hypothesis)" if lead else ""),
            f"{tr(a.name) or a.name}: ثقة المحرك {a.confidence:.0%}" + (" (الفرضية الأقوى)" if lead else "")),
            a.record_ids[:6]))
    return out


def check_sentence(sentence: str, obs: list[Observation], result: AnalysisResult,
                   cfg: EngineConfig) -> SentenceCheck:
    q = normalise(sentence)
    known = {o.record_id: o for o in obs}
    outcomes = []
    missing_ids = False
    flagged = {f.record_ids[0]: f for f in result.contradictions if f.record_ids}
    for rid in RECORD_ID.findall(sentence):
        rid = rid.upper()
        if rid not in known:
            missing_ids = True
            outcomes.append((CONTRADICTED, (f"record {rid} does not exist",
                                            f"السجل {rid} غير موجود"), []))
        elif rid in flagged:
            f = flagged[rid]
            outcomes.append((CONTRADICTED, (
                f"{rid} is itself contradicted by other records: {f.title}",
                f"السجل {rid} نفسه تناقضه سجلات أخرى: {tr(f.title) or f.title}"),
                list(f.record_ids[:6])))
    outcomes += _check_hypothesis(q, result, cfg)
    if not missing_ids:
        for p in _params_in(q):
            res = _check_param(q, p, obs, cfg)
            if res:
                outcomes.append(res)
    if not outcomes:
        cited = [r.upper() for r in RECORD_ID.findall(sentence) if r.upper() in known]
        if cited:
            return SentenceCheck(sentence, SUPPORTED, [("cited records exist", "السجلات المذكورة موجودة")],
                                 cited)
        return SentenceCheck(sentence, NO_EVIDENCE, [
            ("no record in this investigation confirms or refutes this",
             "لا يوجد سجل في هذا التحقيق يؤكد هذا أو ينفيه")])
    verdict = CONTRADICTED if any(v == CONTRADICTED for v, _r, _i in outcomes) else SUPPORTED
    ids: list[str] = []
    for _v, _r, i in outcomes:
        ids += [x for x in i if x not in ids]
    return SentenceCheck(sentence, verdict, [r for _v, r, _i in outcomes], ids)


def check(text: str, obs, result: AnalysisResult, cfg: EngineConfig) -> list[SentenceCheck]:
    obs = list(obs)
    return [check_sentence(s, obs, result, cfg) for s in split_sentences(text)]


def summary(checks: list[SentenceCheck]) -> dict[str, int]:
    return {k: sum(c.verdict == k for c in checks) for k in (SUPPORTED, CONTRADICTED, NO_EVIDENCE)}


# Example drafts written like a confident AI assistant, each with deliberate mistakes.
SAMPLE_DRAFTS_AR = {
    "A": ("توقفت المضخة P-301 بسبب تآكل المحمل. الاهتزاز المباشر كان عالي قبل التوقف. "
          "الحديد في الزيت طبيعي، يعني الزيت سليم. "
          "سجل المشغّل A-OPS-0004 يؤكد إن المضخة كانت شغالة بشكل طبيعي. "
          "ضغط السحب كان مستقر. المحمل تغيّر الشهر الماضي عن طريق المورّد. "
          "السبب الرئيسي هو التكهف."),
    "B": ("حساس الاهتزاز المباشر أظهر اهتزاز عالي قبل التوقف. "
          "فحص الجهاز اليدوي كان عالي بعد، وهذا يؤكد إن المشكلة ميكانيكية. "
          "حرارة المحمل كانت طبيعية. يبدو إنه عطل في الحساس. "
          "الحديد في الزيت مرتفع. تمت معايرة الحساس في السجل B-CAL-0099."),
    "C": ("توقفت المضخة بسبب فشل مانع التسريب. مستوى خزان مانع التسريب نزل تحت حد الإنذار. "
          "ما فيه تسريب وقت الفحص. الماء في الزيت كان 900. "
          "الاهتزاز كان عالي وهو سبب التوقف. ضغط السحب طبيعي. "
          "مانع التسريب ركّبه مقاول خبير."),
}
SAMPLE_DRAFTS = {
    "A": ("Pump P-301 tripped because of bearing wear. Online vibration was high before the trip. "
          "The oil iron level was normal, so the oil is healthy. "
          "The operator log A-OPS-0004 confirms the pump was running normally. "
          "Suction pressure was stable. The bearing was replaced last month by the vendor. "
          "The root cause is cavitation."),
    "B": ("The online vibration sensor showed high vibration before the trip. "
          "The handheld vibration check was also high, which confirms a mechanical problem. "
          "Bearing temperature was normal. This looks like a sensor fault. "
          "Iron in the oil is high. The transmitter was recalibrated in record B-CAL-0099."),
    "C": ("Pump P-301 tripped because of a seal failure. The seal pot level dropped below the alarm. "
          "There was no leak at inspection. Water in the oil was 900 ppm. "
          "Vibration was high and caused the trip. Suction pressure was normal. "
          "The seal was installed by an experienced contractor."),
}
