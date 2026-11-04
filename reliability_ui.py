"""Reliability Brain workspace (Streamlit). Loaded by app.py only when
PLANTPROOF_RELIABILITY=1. Every value shown comes from an ExaminationReport; nothing here
computes engineering results itself.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

import streamlit as st

import ui_theme
from plantproof.reliability import KnowledgeStore, load_registry, run_all, run_examination
from plantproof.reliability import adapter, registry
from plantproof.reliability.report import DISCLAIMER, DISCLAIMER_AR
from plantproof.reliability.stages.s5_risk import MATRIX
from plantproof.reliability.types import ClaimKind
from plantproof.translations import ar, bi, bi_plain

STATUS_EN = {"completed": "Completed", "failed": "Failed", "blocked": "Blocked",
             "insufficient_data": "Insufficient evidence", "verification_rejected": "Verification failed",
             "awaiting_evidence": "Awaiting evidence", "pending": "Pending"}
STATUS_AR = {"completed": "مكتملة", "failed": "فشلت", "blocked": "متوقفة", "insufficient_data": "أدلة غير كافية",
             "verification_rejected": "فشل التحقق", "awaiting_evidence": "بانتظار أدلة", "pending": "قيد الانتظار"}
KIND_AR = {"measured": "مقاس", "fact": "حقيقة", "finding": "نتيجة تحليل", "hypothesis": "فرضية",
           "assumption": "افتراض", "uncertainty": "عدم يقين", "missing": "ناقص", "recommendation": "توصية"}
VER_AR = {"verified": "مؤكد", "supported": "مدعوم", "downgraded": "خُفّضت ثقته", "rejected": "مرفوض",
          "not_applicable": "غير منطبق", "unchecked": "لم يُفحص"}
PRIO_AR = {"P1": "عاجل", "P2": "قريبًا", "P3": "روتيني"}


@st.cache_resource(show_spinner=False)
def knowledge_store() -> KnowledgeStore:
    return KnowledgeStore()


def gray(t: str) -> str:
    return f":small[:gray[{t}]]" if t else ""


def chip(text: str, tone: str) -> str:
    return f'<span class="pp-chip {tone}">{html.escape(text)}</span>'


def tile(label: str, value: str, note: str = "", note_ar: str = "", tone: str = "neutral", small=False) -> str:
    e = html.escape
    return (f'<div class="pp-tile {tone}"><div class="pp-tl">{e(label)} <span>{e(ar(label))}</span></div>'
            f'<div class="pp-tv{" sm" if small else ""}">{e(value)}</div>'
            f'<div class="pp-tn">{e(note)} <span>{e(note_ar)}</span></div></div>')


def html_block(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def case_for_scenario(sid: str) -> str:
    return f"P-301/{sid}"


def examine(case_id: str, store) -> "object":
    """Run the examination now: it takes tens of milliseconds, so results are never stale."""
    return run_examination(case_id, store=store, knowledge=knowledge_store())


# ------------------------------------------------------------------ ops room summary
def ops_summary(store, sid: str):
    """Read-only Brain summary for the Operations Room (Phase 7)."""
    r = examine(case_for_scenario(sid), store)
    v = r.stage("S6").data.get("counts", {}) if r.stage("S6") else {}
    outstanding = sum(len(x["missing"]) for x in (r.stage("S4").data.get("ranking", ())[:1] if r.stage("S4") else ()))
    first = next(iter(r.recommendations), None)
    return r, v, outstanding, first


# ------------------------------------------------------------------ page
def render(store, default_sid: str) -> None:
    st.title(f":material/biotech: {bi('Reliability Brain')}")
    st.caption(f"A staged engineering examination: eight stages in six divisions, every conclusion traced to "
               f"records and checked by the Brain itself.  \n"
               f"{gray('فحص هندسي على مراحل: ثماني مراحل في ستة أقسام، وكل استنتاج مربوط بسجلاته ويُراجع ذاتيًا.')}")
    assets = load_registry()
    cases = [(c.case_id, a, c) for a in assets for c in a.cases]
    ids = [c[0] for c in cases]
    default = case_for_scenario(default_sid)
    if "rb_case" not in st.session_state and default in ids:
        st.session_state["rb_case"] = default
    labels = {cid: f"{a.asset_id} · {c.title} ({a.type.replace('_', ' ')})" for cid, a, c in cases}
    case_id = st.selectbox(bi("Asset and case"), ids, format_func=lambda k: labels[k], key="rb_case")
    try:
        r = examine(case_id, store)
    except registry.RegistryError as exc:
        st.error(f"Cannot examine {case_id}: {exc}")
        return
    _summary(r)
    tabs = st.tabs([bi_plain(x) for x in ("Stages", "Hypotheses", "Risk", "Verification", "Decisions",
                                          "Evidence", "Fleet", "Knowledge", "Export")])
    with tabs[0]:
        _stages(r)
    with tabs[1]:
        _hypotheses(r)
    with tabs[2]:
        _risk(r)
    with tabs[3]:
        _verification(r)
    with tabs[4]:
        _decisions(r)
    with tabs[5]:
        _evidence(r)
    with tabs[6]:
        _fleet(store)
    with tabs[7]:
        _knowledge(r)
    with tabs[8]:
        _export(r)
    st.caption(f"{DISCLAIMER}  \n{gray(DISCLAIMER_AR)}")


def _summary(r) -> None:
    tone = ("neutral" if r.overall_status.startswith("Not examined") else
            "crit" if r.risk == "Critical" or r.overall_status.startswith(("Unverified", "Incomplete")) else
            "warn" if r.risk in ("High", "Undetermined") or "awaiting" in r.overall_status.lower()
            or r.overall_status == "Insufficient data" else "ok")
    html_block(f'<div class="pp-banner {tone}"><div class="t">{html.escape(r.overall_status)} · '
               f'{html.escape(r.asset_name)}</div><div class="s">{html.escape(r.final_en)}</div>'
               f'<div class="a">{html.escape(r.overall_status_ar)} — {html.escape(r.final_ar)}</div></div>')
    s6 = r.stage("S6")
    counts = s6.data.get("counts", {}) if s6 and s6.data else {}
    lead = (f"{r.leading_confidence:.0%}" if r.leading_confidence is not None else "None supported")
    html_block('<div class="pp-tiles">' + "".join([
        tile("Condition", r.condition, "observed state", "الحالة المرصودة", ui_theme.tone(r.condition), small=True),
        tile("Data quality", r.grade, "integrity grade", "درجة سلامة البيانات", ui_theme.tone(r.grade)),
        tile("Risk", r.risk, "severity × evidence", "الشدة × الأدلة", ui_theme.tone(r.risk), small=True),
        tile("Leading explanation", lead, (r.leading_name or "no mechanism") + (f" · {r.leading_label}" if r.leading_label else ""),
             "فرضية وليست تشخيصًا", "brand" if r.leading else "neutral"),
        tile("Verified claims", f"{counts.get('verified', 0)}",
             f"{counts.get('rejected', 0)} rejected · {counts.get('downgraded', 0)} downgraded",
             "مؤكد / مرفوض", "crit" if counts.get("rejected") else "ok" if counts else "neutral"),
        tile("Source data", "Unchanged" if r.integrity_ok else ("—" if not r.input_fingerprint else "CHANGED"),
             f"fingerprint {r.input_fingerprint or '—'}", "البصمة قبل وبعد", "ok" if r.integrity_ok else "neutral",
             small=True),
    ]) + "</div>")
    st.markdown(f"**{bi('Examination progress')}** {gray('اضغط تبويب المراحل للتفاصيل')}")
    steps = []
    for s in r.stages:
        t = ui_theme.tone(s.status.value)
        steps.append(f'<div class="pp-step {t}"><div class="n">{s.stage_id} · {html.escape(s.division.upper())}</div>'
                     f'<div class="h">{html.escape(s.name)}</div>{chip(STATUS_EN[s.status.value], t)} '
                     f'<span class="pp-tn">{s.duration_ms:.0f} ms</span></div>')
    html_block('<div class="pp-steps">' + "".join(steps) + "</div>")
    divs = []
    for en, a_, status, sids, desc in r.divisions():
        t = ui_theme.tone(status.value)
        divs.append(f'<div class="pp-tile {t}"><div class="pp-tl">{html.escape(en)} <span>{html.escape(a_)}</span></div>'
                    f'<div style="margin:4px 0">{chip(STATUS_EN[status.value], t)} '
                    f'<span class="pp-tn">{", ".join(sids)}</span></div><div class="pp-tn">{html.escape(desc)}</div></div>')
    with st.expander(f":material/account_tree: {bi('Intelligence divisions')}"):
        html_block('<div class="pp-tiles">' + "".join(divs) + "</div>")


def _claims_table(r, stage) -> list[dict]:
    v = r.verdicts
    rows = []
    for c in stage.claims:
        ver = v.get(c.claim_id, (c.verification.value, ""))
        rows.append({"ID": c.claim_id, "Type · النوع": f"{c.kind.value} · {KIND_AR[c.kind.value]}",
                     "Verification · التحقق": f"{ver[0]} · {VER_AR.get(ver[0], '')}",
                     "Statement · العبارة": c.text_en,
                     "Records · السجلات": ", ".join(c.evidence[:8]) + ("…" if len(c.evidence) > 8 else ""),
                     "Check note · ملاحظة التحقق": ver[1] if len(ver) > 1 else ""})
    return rows


def _stages(r) -> None:
    for s in r.stages:
        t = ui_theme.tone(s.status.value)
        icon = {"ok": ":green[:material/check_circle:]", "warn": ":orange[:material/error:]",
                "crit": ":red[:material/cancel:]"}.get(t, ":gray[:material/radio_button_unchecked:]")
        with st.expander(f"{icon} **{s.stage_id} · {s.name}** — {STATUS_EN[s.status.value]} "
                         f"{gray(STATUS_AR[s.status.value])}"):
            st.markdown(f"{s.summary_en}  \n{gray(s.summary_ar)}")
            st.caption(f"Division: {s.division} · inputs: {', '.join(s.inputs) or '—'} · {s.duration_ms:.1f} ms")
            if s.error:
                st.error(f"Stage error: {s.error}")
            if s.claims:
                st.dataframe(_claims_table(r, s), hide_index=True)
            for lim in s.limitations:
                st.markdown(f":gray[:material/info: Limitation: {lim}]")


def _hypotheses(r) -> None:
    s4 = r.stage("S4")
    if not s4 or not s4.data.get("ranking"):
        st.info(f"No hypotheses were assessed ({s4.status.value if s4 else 'not run'}).  \n"
                f"{gray('لم تُقيَّم فرضيات.')}")
        return
    over = r.stage("S6").data.get("label_overrides", {}) if r.stage("S6") else {}
    st.dataframe([{
        "#": x["rank"], "Mechanism · الآلية": f"{x['mode_name']} · {ar(x['name']) or ''}",
        "Engine · المحرك": f"{x['engine_confidence']:.0%}", "Data cap · سقف البيانات": f"{x['data_cap']:.0%}",
        "Sensor trust · ثقة الحساس": f"×{x['trust_factor']:.1f}", "Confidence · الثقة": f"{x['adjusted']:.0%}",
        "Level · المستوى": over.get(x["hypothesis_id"], x["label"]),
        "Coverage · التغطية": f"{x['coverage']:.0%}",
        "Missing · ناقص": "; ".join(t for _, t in x["missing"]) or "—"} for x in s4.data["ranking"]],
        hide_index=True)
    st.caption("Confidence = engine confidence × data-quality cap × sensor-trust factor. It is evidence "
               "strength, not a probability of failure.  \n"
               + gray("الثقة = ثقة المحرك × سقف جودة البيانات × عامل ثقة الحساس، وهي قوة دليل وليست احتمال عطل."))
    for x in s4.data["ranking"][:3]:
        with st.expander(f"#{x['rank']} {x['mode_name']} — {x['adjusted']:.0%}"):
            st.markdown("**" + bi("Supporting evidence") + "**")
            st.markdown("\n".join(f"- {fid} {t} · `{', '.join(ids[:6])}`" for fid, t, ids in x["supporting"]) or "—")
            st.markdown("**" + bi("Refuting evidence") + "**")
            st.markdown("\n".join(f"- {fid} {t}" for fid, t, _ in x["refuting"]) or "—")
            st.markdown("**" + bi("Missing evidence") + "**")
            st.markdown("\n".join(f"- {fid} {t}" for fid, t in x["missing"]) or "—")
            st.markdown("**" + bi("Typical indicators") + "** " + gray("مؤشرات نموذجية، ليست دليلًا"))
            st.markdown("\n".join(f"- {k}: {v}" for k, v in x["symptoms"].items()) or "—")
            st.markdown("**" + bi("Distinguishing checks") + "**")
            st.markdown("\n".join(f"- {c}" for c in x["checks"]) or "—")
    na = [c for c in s4.claims if c.kind is ClaimKind.UNCERTAINTY]
    if na:
        st.markdown("**" + bi("Mechanisms not scored") + "**")
        st.markdown("\n".join(f"- {c.text_en}" for c in na))


def _risk(r) -> None:
    s5 = r.stage("S5")
    if not s5 or not s5.data:
        st.info("Risk was not assessed.")
        return
    d = s5.data
    exp = d.get("exposure")
    html_block('<div class="pp-tiles">' + "".join([
        tile("Risk", d.get("risk", "—"), d.get("basis", ""), "", ui_theme.tone(d.get("risk", "")), small=True),
        tile("Severity", d.get("severity") or "—", "consequence class", "فئة العواقب", "neutral", small=True),
        tile("Evidence strength", d.get("strength") or "—", "not a probability", "ليست احتمالًا", "neutral", small=True),
        tile("Indicator trend", d.get("trend") or "—", "last 12 h", "آخر 12 ساعة",
             "warn" if d.get("trend") == "worsening" else "neutral", small=True),
        tile("Cost exposure", f"${exp['base']:,.0f}" if exp else "—",
             f"${exp['low']:,.0f}–${exp['high']:,.0f}, illustrative" if exp else "no supported mechanism",
             "توضيحية", "neutral", small=True),
    ]) + "</div>")
    st.markdown(f"**{bi('Risk matrix')}** {gray('الشدة × قوة الدليل')}")
    rows = []
    for sev in ("High", "Medium", "Low"):
        row = {"Severity · الشدة": sev}
        for strength in ("Strong", "Moderate"):
            val = MATRIX[(sev, strength)]
            here = d.get("severity") == sev and d.get("strength") == strength
            row[f"{strength} evidence"] = f"▶ {val} ◀" if here else val
        rows.append(row)
    st.dataframe(rows, hide_index=True)
    st.caption("Weak evidence never raises risk above Medium; an unexplained alarm is rated Medium.")
    for c in s5.claims:
        if c.kind is ClaimKind.UNCERTAINTY:
            st.markdown(f":orange[:material/help:] {c.text_en}  \n{gray(c.text_ar)}")


def _verification(r) -> None:
    s6 = r.stage("S6")
    if not s6 or not s6.data:
        st.info("Verification did not run.")
        return
    c = s6.data["counts"]
    html_block('<div class="pp-tiles">' + "".join([
        tile("Verified", str(c["verified"]), "re-checked on records", "أُعيد فحصها على السجلات", "ok"),
        tile("Supported", str(c["supported"]), "evidence exists", "لها أدلة", "info"),
        tile("Downgraded", str(c["downgraded"]), "confidence lowered", "خُفّضت ثقتها", "warn" if c["downgraded"] else "neutral"),
        tile("Rejected", str(c["rejected"]), "do not rely on these", "لا يُعتمد عليها", "crit" if c["rejected"] else "neutral"),
    ]) + "</div>")
    v = r.verdicts
    flagged = [(cid, ver, note) for cid, (ver, note) in v.items() if ver in ("rejected", "downgraded")]
    flagged += [(c2.claim_id, c2.verification.value, c2.text_en) for c2 in s6.claims if c2.verification.value == "rejected"]
    if flagged:
        st.markdown("**" + bi("Rejected or downgraded") + "**")
        st.dataframe([{"Claim": a, "Result": b, "Reason": n} for a, b, n in flagged], hide_index=True)
    else:
        st.success("No claim was rejected or downgraded.  \n" + gray("لم يُرفض أو يُخفّض أي ادعاء."))
    if s6.data.get("fact_check"):
        st.markdown("**" + bi("Independent fact check") + "** " + gray("مدقق المنصة المستقل"))
        st.dataframe([{"Claim": a, "Sentence": b, "Result": c2, "Reason": d}
                      for a, b, c2, d in s6.data["fact_check"]], hide_index=True)
    for lim in s6.limitations:
        st.caption(f":material/info: {lim}")


def _decisions(r) -> None:
    recs = r.recommendations
    if not recs:
        st.info("No recommendations: the examination did not reach the decision stage.  \n"
                + gray("لا توجد توصيات لأن الفحص لم يصل لمرحلة القرار."))
        return
    for x in recs:
        tone = {"P1": "crit", "P2": "warn", "P3": "info"}[x.priority]
        miss = f"<div class='pp-tn'>Still missing: {html.escape('; '.join(x.missing_info))}</div>" if x.missing_info else ""
        recs_ids = f"<div class='pp-tn pp-mono'>{html.escape(', '.join(x.evidence[:8]))}</div>" if x.evidence else ""
        html_block(f'<div class="pp-banner {tone}" style="padding:10px 14px">'
                   f'<div>{chip(x.priority + " · " + PRIO_AR[x.priority], tone)} {chip(x.category, "neutral")} '
                   f'{chip("confidence " + x.confidence, "neutral")}</div>'
                   f'<div class="t" style="font-size:1rem;margin-top:6px">{html.escape(x.action_en)}</div>'
                   f'<div class="a">{html.escape(x.action_ar)}</div>'
                   f'<div class="s">Why: {html.escape(x.justification)}</div>'
                   f'<div class="pp-tn">Risk addressed: {html.escape(x.risk_addressed or "—")}</div>{miss}{recs_ids}</div>')
    st.caption(":material/gavel: Decision support only. Recommendations do not authorise starting, stopping or "
               "modifying equipment.  \n" + gray("دعم قرار فقط، ولا تُجيز التشغيل أو الإيقاف."))


def _evidence(r) -> None:
    cited = r.cited_records()
    if not cited:
        st.info("No records were cited.")
        return
    rid = st.selectbox(bi("Record"), cited, key="rb_record")
    try:
        _a, case = registry.find_case(r.case_id, load_registry())
        recs = {x.record_id: x for x in adapter.load_case(case).records}
    except Exception as exc:          # show the problem; never hide it
        st.error(f"Could not load the source records: {exc}")
        return
    rec = recs.get(rid)
    if rec:
        st.dataframe([{"Record": rec.record_id, "Time": rec.timestamp.replace("T", " "), "Type": rec.source_type,
                       "Parameter": rec.parameter, "Value": rec.value, "Unit": rec.unit, "Status": rec.status or "",
                       "Source": rec.source, "Text": rec.text}], hide_index=True)
    using = [c for c in r.claims() if rid in c.evidence]
    st.markdown(f"**{bi('Claims citing this record')}** ({len(using)})")
    st.dataframe([{"ID": c.claim_id, "Type": c.kind.value, "Statement": c.text_en} for c in using], hide_index=True)


@st.cache_data(show_spinner=False, ttl=60)
def _fleet_rows(_store, stamp: str) -> list[dict]:
    rows = []
    for x in run_all(store=_store):
        rows.append({"Asset · المعدة": x.asset_id, "Case · الحالة": x.case_title, "Type": x.asset_type,
                     "Status · الوضع": x.overall_status, "Condition": x.condition, "Data": x.grade,
                     "Risk · الخطر": x.risk, "Leading · الأرجح": x.leading_name or "—",
                     "P1 actions": sum(r.priority == "P1" for r in x.recommendations)})
    return rows


def _fleet(store) -> None:
    st.caption("Every registered case, examined with the same protocol. Asset types without an examination "
               "profile are reported as not supported.  \n" + gray("كل الحالات المسجلة بنفس بروتوكول الفحص."))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    st.dataframe(_fleet_rows(store, stamp), hide_index=True)
    st.caption(f"Supported asset types: {', '.join(registry.supported_types())}.")


def _knowledge(r) -> None:
    ks = knowledge_store()
    st.caption("Saving keeps a record of this examination. A mechanism becomes knowledge only when a person records "
               "a confirmed or ruled-out outcome. Stored in the Brain's own file; may be wiped when the app restarts."
               "  \n" + gray("المعرفة لا تُبنى إلا من نتائج يؤكدها شخص."))
    if st.button(f":material/save: {bi('Save this examination')}", key="rb_save"):
        try:
            uid = ks.save_investigation(r)
            st.success(f"Saved as investigation {uid}.  \n" + gray("تم الحفظ."))
        except Exception as exc:
            st.error(f"Could not save: {exc}")
    saved = ks.list_investigations(r.asset_id)
    if not saved:
        st.info("No saved examinations for this asset yet.  \n" + gray("لا توجد فحوصات محفوظة لهذه المعدة."))
    else:
        st.dataframe([{"ID": i["uid"], "Case": i["case_id"], "Saved": i["created_at"].replace("T", " "),
                       "Leading": i["leading"] or "—", "Risk": i["risk"],
                       "Outcomes": ", ".join(f"{o['mechanism']}: {o['outcome']}" for o in i["outcomes"]) or "none"}
                      for i in saved], hide_index=True)
        prof = registry.load_profile("centrifugal_pump") or {"failure_modes": []}
        with st.form("rb_outcome", border=True):
            st.markdown(f"**{bi('Record an inspection outcome')}**")
            inv = st.selectbox(bi("Investigation"), [i["uid"] for i in saved], key="rb_out_inv")
            mech = st.selectbox(bi("Mechanism"), [m["id"] for m in prof["failure_modes"]], key="rb_out_mech")
            outcome = st.selectbox(bi("Outcome"), ["confirmed", "ruled_out"], key="rb_out_res")
            role = st.text_input(bi("Your role"), placeholder="e.g. Reliability engineer", key="rb_out_role")
            note = st.text_input(bi("What was found"), key="rb_out_note")
            if st.form_submit_button(bi("Record outcome")):
                try:
                    ks.record_outcome(inv, mech, outcome, role or "", note or "")
                    st.success("Outcome recorded.  \n" + gray("تم تسجيل النتيجة."))
                except ValueError as exc:
                    st.warning(str(exc))
    know = ks.knowledge()
    if know:
        st.markdown(f"**{bi('Confirmed knowledge')}**")
        st.dataframe([{"Mechanism": m, "Confirmed": len(k["confirmed"]), "Ruled out": len(k["ruled_out"]),
                       "From investigations": ", ".join(x["investigation"] for x in k["confirmed"] + k["ruled_out"])}
                      for m, k in know.items()], hide_index=True)


def _export(r) -> None:
    st.caption("Exports keep record IDs, verification results, fingerprints and the configuration hash.  \n"
               + gray("التصدير يحتفظ بأرقام السجلات ونتائج التحقق والبصمات."))
    base = r.case_id.replace("/", "_")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button(":material/description: Report (HTML, printable to PDF)", r.to_html(), f"{base}_report.html", mime="text/html", key="rb_dl_html")
    c2.download_button(":material/article: Markdown", r.to_markdown(), f"{base}_report.md", mime="text/markdown",
                       key="rb_dl_md")
    c3.download_button(":material/data_object: JSON", r.to_json(), f"{base}_report.json", mime="application/json",
                       key="rb_dl_json")
    c4.download_button(":material/table: Evidence (CSV)", r.evidence_csv(), f"{base}_evidence.csv", mime="text/csv",
                       key="rb_dl_csv")
    st.markdown(f"**{bi('Report sections')}**")
    for title, title_ar, lines in r.sections():
        with st.expander(f"{title} {gray(title_ar)}"):
            st.markdown("\n".join(f"- {x}" for x in lines) or "—")
