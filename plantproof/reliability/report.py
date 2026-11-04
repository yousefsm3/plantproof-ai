"""The examination report: one immutable object, with JSON, Markdown, CSV and HTML exports.

The report ID is a hash of the inputs (case, input fingerprint, configuration, Brain
version), so the same inputs always give the same ID and the same content; only
``generated_at`` and timings differ between runs.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from .divisions import DIVISIONS, division_status
from .types import Claim, ClaimKind, StageResult, StageStatus

DISCLAIMER = ("Engineering assessment generated from synthetic demonstration data. It is decision support "
              "for qualified engineers, not a certified diagnosis, and it does not authorise starting, "
              "stopping or modifying equipment.")
DISCLAIMER_AR = ("تقييم هندسي مبني على بيانات افتراضية للعرض. هو دعم لقرار المهندسين المؤهلين وليس تشخيصًا "
                 "معتمدًا، ولا يُجيز تشغيل المعدة أو إيقافها أو تعديلها.")
KIND_LABEL = {ClaimKind.MEASURED: "Measured", ClaimKind.FACT: "Fact", ClaimKind.FINDING: "Finding",
              ClaimKind.HYPOTHESIS: "Hypothesis", ClaimKind.ASSUMPTION: "Assumption",
              ClaimKind.UNCERTAINTY: "Uncertainty", ClaimKind.MISSING: "Missing",
              ClaimKind.RECOMMENDATION: "Recommendation"}


def _plain(o: Any) -> Any:
    if isinstance(o, Enum):
        return o.value
    if is_dataclass(o) and not isinstance(o, type):
        return {f.name: _plain(getattr(o, f.name)) for f in fields(o)}
    if isinstance(o, (dict, MappingProxyType)):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_plain(v) for v in (sorted(o) if isinstance(o, (set, frozenset)) else o)]
    return o


@dataclass(frozen=True)
class ExaminationReport:
    report_id: str
    brain_version: str
    asset_id: str
    asset_name: str
    asset_type: str
    case_id: str
    case_title: str
    source_label: str
    input_fingerprint: str
    fingerprint_after: str
    config_hash: str
    generated_at: str
    duration_ms: float
    stages: tuple[StageResult, ...]
    overall_status: str
    overall_status_ar: str
    condition: str
    grade: str
    risk: str
    leading: str | None
    leading_name: str | None
    leading_confidence: float | None
    leading_label: str | None
    signature: tuple[str, ...]
    final_en: str
    final_ar: str
    load_error: str | None = None

    # ---- access ------------------------------------------------------------------
    @property
    def integrity_ok(self) -> bool:
        return bool(self.input_fingerprint) and self.input_fingerprint == self.fingerprint_after

    def stage(self, stage_id: str) -> StageResult | None:
        return next((s for s in self.stages if s.stage_id == stage_id), None)

    @property
    def verdicts(self) -> dict[str, tuple[str, str]]:
        s6 = self.stage("S6")
        return dict(s6.data.get("verdicts", {})) if s6 else {}

    @property
    def recommendations(self) -> tuple:
        s7 = self.stage("S7")
        return tuple(s7.data.get("recommendations", ())) if s7 else ()

    def claims(self) -> list[Claim]:
        return [c for s in self.stages for c in s.claims]

    def divisions(self) -> list[tuple[str, str, StageStatus, tuple[str, ...], str]]:
        st = {s.stage_id: s.status for s in self.stages}
        return [(en, ar, division_status(st, ids), ids, desc) for en, ar, ids, desc in DIVISIONS]

    def cited_records(self) -> list[str]:
        return sorted({i for c in self.claims() for i in c.evidence})

    def summary_dict(self) -> dict[str, Any]:
        return {"report_id": self.report_id, "overall_status": self.overall_status, "condition": self.condition,
                "grade": self.grade, "risk": self.risk, "leading": self.leading,
                "leading_confidence": self.leading_confidence, "leading_label": self.leading_label,
                "recommendations": [f"{r.priority} {r.action_en}" for r in self.recommendations]}

    # ---- exports -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = _plain(self)
        d["integrity_ok"] = self.integrity_ok
        d["disclaimer"] = DISCLAIMER
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def evidence_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["claim_id", "stage", "kind", "verification", "record_ids", "engine_findings", "statement"])
        v = self.verdicts
        for c in self.claims():
            w.writerow([c.claim_id, c.stage_id, c.kind.value, v.get(c.claim_id, (c.verification.value,))[0],
                        " ".join(c.evidence), " ".join(c.finding_refs), c.text_en])
        return buf.getvalue()

    def sections(self) -> list[tuple[str, str, list[str]]]:
        """The 17 report sections as (title, Arabic title, lines)."""
        s = {x.stage_id: x for x in self.stages}
        v = self.verdicts

        def lines(stage_id: str, kinds=None) -> list[str]:
            st = s.get(stage_id)
            if not st:
                return []
            out = []
            for c in st.claims:
                if kinds and c.kind not in kinds:
                    continue
                ver = v.get(c.claim_id, (c.verification.value, ""))[0]
                ev = f" [records: {', '.join(c.evidence[:8])}{'…' if len(c.evidence) > 8 else ''}]" if c.evidence else ""
                refs = f" [engine: {', '.join(c.finding_refs)}]" if c.finding_refs else ""
                out.append(f"{KIND_LABEL[c.kind]} · {ver} — {c.text_en}{ev}{refs}")
            return out

        s4 = s.get("S4")
        ranking = s4.data.get("ranking", ()) if s4 else ()
        sup = [f"{r['mode_name']}: " + "; ".join(f"{fid} {t} ({', '.join(ids[:5])})" for fid, t, ids in r["supporting"])
               for r in ranking if r["supporting"]]
        con = [f"{r['mode_name']}: " + "; ".join(f"{fid} {t}" for fid, t, _ in r["refuting"])
               for r in ranking if r["refuting"]]
        s2 = s.get("S2")
        con += [f"Contradiction {c}" for c in (s2.data.get("contradictions", ()) if s2 else ())]
        mis = [f"{r['mode_name']}: " + "; ".join(f"{fid} {t}" for fid, t in r["missing"]) for r in ranking if r["missing"]]
        mis += [c.text_en for st in self.stages for c in st.claims if c.kind is ClaimKind.MISSING]
        recs = self.recommendations
        prio = {p: [r.action_en for r in recs if r.priority == p] for p in ("P1", "P2", "P3")}
        tests = [f"{c['title']} (impact {c['impact']:.2f})" for c in (s4.data.get("checks", ()) if s4 else ())]
        tests += [f"{r['mode_name']}: {chk}" for r in ranking[:2] for chk in r["checks"]]
        s6 = s.get("S6")
        return [
            ("1. Asset identification", "تعريف المعدة", lines("S1")),
            ("2. Examination status", "حالة الفحص", [f"Overall: {self.overall_status}"] +
             [f"{x.stage_id} {x.name}: {x.status.value} — {x.summary_en}" for x in self.stages]),
            ("3. Data quality", "جودة البيانات", lines("S2")),
            ("4. Equipment health", "حالة المعدة", lines("S3", (ClaimKind.MEASURED, ClaimKind.FINDING, ClaimKind.MISSING))),
            ("5. Detected anomalies", "الشذوذ المكتشف",
             [c for c in lines("S3") if "learned-baseline" in c or "Anomaly model" in c]),
            ("6. Potential failure mechanisms", "آليات العطل المحتملة", lines("S4", (ClaimKind.UNCERTAINTY,))),
            ("7. Ranked failure hypotheses", "ترتيب فرضيات العطل", lines("S4", (ClaimKind.HYPOTHESIS,))),
            ("8. Supporting evidence", "الأدلة الداعمة", sup or ["None matched."]),
            ("9. Contradicting evidence", "الأدلة المعارضة", con or ["None."]),
            ("10. Missing evidence", "الأدلة الناقصة", mis or ["None."]),
            ("11. Failure risk", "مخاطر العطل", lines("S5")),
            ("12. Confidence and uncertainty", "الثقة وعدم اليقين", (lines("S6") if s6 else []) +
             [c.text_en for st in self.stages for c in st.claims if c.kind is ClaimKind.UNCERTAINTY]),
            ("13. Recommended engineering actions", "الإجراءات الهندسية الموصى بها",
             [f"{r.rec_id} {r.priority} [{r.category}] {r.action_en} Why: {r.justification} Risk: {r.risk_addressed}. "
              f"Confidence: {r.confidence}." + (f" Missing: {'; '.join(r.missing_info)}." if r.missing_info else "") +
              (f" Records: {', '.join(r.evidence[:6])}." if r.evidence else "") for r in recs]),
            ("14. Maintenance priorities", "أولويات الصيانة",
             [f"{p}: " + (" | ".join(a) if a else "none") for p, a in prio.items()]),
            ("15. Additional diagnostic tests", "فحوصات تشخيصية إضافية", tests or ["None identified."]),
            ("16. Final engineering assessment", "التقييم الهندسي النهائي", [self.final_en, DISCLAIMER]),
            ("17. Traceability", "قابلية التتبع", [
                f"Report {self.report_id}; Brain {self.brain_version}; generated {self.generated_at}.",
                f"Case {self.case_id} from {self.source_label}.",
                f"Input fingerprint {self.input_fingerprint}; after the run {self.fingerprint_after} "
                f"({'unchanged' if self.integrity_ok else 'CHANGED'}).",
                f"Configuration hash {self.config_hash}.",
                f"{len(self.cited_records())} distinct records cited: {', '.join(self.cited_records()[:40])}"
                + ("…" if len(self.cited_records()) > 40 else "")]),
        ]

    def to_markdown(self) -> str:
        out = [f"# Reliability Brain report — {self.asset_name}", "",
               f"Case {self.case_id} · report {self.report_id} · {self.generated_at}", "",
               f"> {DISCLAIMER}", ""]
        for title, title_ar, ls in self.sections():
            out += [f"## {title}", f"*{title_ar}*", ""] + [f"- {x}" for x in ls] + [""]
        return "\n".join(out)

    def to_html(self) -> str:
        e = html.escape
        parts = []
        for title, title_ar, ls in self.sections():
            items = "".join(f"<li>{e(x)}</li>" for x in ls)
            parts.append(f"<section><h2>{e(title)} <span class='ar'>{e(title_ar)}</span></h2><ul>{items}</ul></section>")
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reliability Brain report {e(self.case_id)}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1B2226;max-width:960px;margin:32px auto;padding:0 20px;line-height:1.5}}
h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:16px;margin:24px 0 6px;border-bottom:1px solid #D5DDDB;padding-bottom:4px}}
.ar{{color:#6B7B7A;font-weight:400;font-size:13px;direction:rtl}} .meta{{color:#5B6B69;font-size:13px}}
.note{{background:#FFF7E8;border:1px solid #E9D3A6;padding:10px 12px;border-radius:6px;font-size:13px}}
li{{margin:3px 0;font-size:14px}} @media print{{body{{margin:0}}}}
</style></head><body>
<h1>Reliability Brain report — {e(self.asset_name)}</h1>
<div class="meta">Case {e(self.case_id)} · report {e(self.report_id)} · {e(self.generated_at)} · Designed &amp; built by Yaqen AI</div>
<p class="note">{e(DISCLAIMER)}<br><span class="ar">{e(DISCLAIMER_AR)}</span></p>
{''.join(parts)}
</body></html>"""


# ---------------------------------------------------------------------- assembly
def _overall(ctx) -> tuple[str, str]:
    st = {k: r.status for k, r in ctx.results.items()}
    failed = [k for k, v in st.items() if v is StageStatus.FAILED]
    if failed:
        return f"Incomplete: stage {', '.join(failed)} failed", "غير مكتمل: فشلت مرحلة"
    if st.get("S1") is StageStatus.BLOCKED:
        return "Not examined: asset type not supported", "لم يُفحص: نوع المعدة غير مدعوم"
    if any(v is StageStatus.BLOCKED for v in st.values()):
        return "Incomplete: stages blocked", "غير مكتمل: مراحل متوقفة"
    if st.get("S6") is StageStatus.VERIFICATION_REJECTED:
        return "Unverified: key claims rejected", "غير مؤكد: رُفضت ادعاءات أساسية"
    if any(v is StageStatus.INSUFFICIENT_DATA for v in st.values()):
        return "Insufficient data", "البيانات غير كافية"
    if any(v is StageStatus.AWAITING_EVIDENCE for v in st.values()):
        return "Complete, awaiting evidence", "مكتمل، بانتظار أدلة إضافية"
    return "Complete", "مكتمل"


def build_report(ctx, fp_before: str, fp_after: str, cfg_hash: str, version: str, generated_at: str,
                 duration_ms: float, load_error: str | None) -> ExaminationReport:
    from .stages.s8_knowledge import signature
    r = ctx.results
    overall, overall_ar = _overall(ctx)
    condition = r["S3"].data.get("condition", "Unknown") if "S3" in r else "Unknown"
    grade = r["S2"].data.get("grade", "—") if "S2" in r else "—"
    risk = r["S5"].data.get("risk", "Unknown") if "S5" in r else "Unknown"
    lead = None
    if "S4" in r and r["S4"].data.get("leading"):
        lead = next(x for x in r["S4"].data["ranking"] if x["hypothesis_id"] == r["S4"].data["leading"])
    label = None
    if lead:
        label = r["S6"].data.get("label_overrides", {}).get(lead["hypothesis_id"], lead["label"]) if "S6" in r else lead["label"]
    recs = tuple(r["S7"].data.get("recommendations", ())) if "S7" in r else ()
    first = next((x for x in recs if x.priority in ("P1", "P2")), recs[0] if recs else None)

    a = ctx.asset
    if r.get("S1") and r["S1"].status is StageStatus.BLOCKED:
        final = (f"{a.name} ({a.type}) cannot be examined: no examination profile exists for this asset type, "
                 "and pump rules are not applied to other equipment.")
        final_ar = f"لا يمكن فحص {a.asset_id}: لا يوجد ملف فحص لهذا النوع من المعدات."
    elif load_error:
        final = f"The case data could not be loaded ({load_error}); nothing was examined."
        final_ar = "تعذّر تحميل بيانات الحالة."
    else:
        s6 = r.get("S6")
        ver = ("key claims were rejected — the result must not be relied on"
               if s6 and s6.status is StageStatus.VERIFICATION_REJECTED else
               "key claims passed independent verification" if s6 and s6.status is StageStatus.COMPLETED else
               "verification did not run")
        lead_txt = (f"The leading explanation is {lead['mode_name'].lower()} at {lead['adjusted']:.0%} ({label}). "
                    f"This is a hypothesis, not a confirmed diagnosis"
                    + (f"; {len(lead['missing'])} required check(s) are outstanding." if lead["missing"] else ".")
                    if lead else "No failure mechanism is supported by the evidence.")
        final = (f"{a.name}: condition {condition}; data quality {grade}. {lead_txt} Risk {risk}. "
                 f"Verification: {ver}." + (f" First action: {first.action_en}" if first else ""))
        final_ar = (f"{a.asset_id}: الحالة {condition}، جودة البيانات {grade}، مستوى الخطر {risk}. "
                    + (f"التفسير الأرجح {lead['mode_name']} بثقة {lead['adjusted']:.0%}، وهو فرضية وليس تشخيصًا مؤكدًا."
                       if lead else "لا توجد آلية عطل مدعومة بالأدلة."))
    rid = hashlib.sha256(f"{ctx.case.case_id}|{fp_before}|{cfg_hash}|{version}".encode()).hexdigest()[:12]
    profile_name = ctx.profile["name"] if ctx.profile else a.type
    return ExaminationReport(
        rid, version, a.asset_id, a.name, profile_name, ctx.case.case_id, ctx.case.title,
        ctx.data.source_label if ctx.data else "unavailable", fp_before, fp_after, cfg_hash, generated_at,
        round(duration_ms, 1), tuple(r[s.stage_id] for s in _protocol() if s.stage_id in r),
        overall, overall_ar, condition, grade, risk, lead["hypothesis_id"] if lead else None,
        lead["mode_name"] if lead else None, lead["adjusted"] if lead else None, label,
        signature(ctx) if "S3" in r else (), final, final_ar, load_error)


def _protocol():
    from .orchestrator import PROTOCOL
    return PROTOCOL
