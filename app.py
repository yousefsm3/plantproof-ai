"""PlantProof AI - Streamlit dashboard.

This file only DISPLAYS results. All analysis lives in the plantproof/ package
(plain Python, unit-tested). Run locally with:  streamlit run app.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st

from plantproof import __version__, blind_test, cost_model, handover, whatif
from plantproof.domain import (SOURCE_TYPES, AnalysisResult, ConfigError, EngineConfig,
                               Finding, Observation, load_engine_config,
                               load_scenario_index)
from plantproof.evidence_engine import analyse
from plantproof.storage import Store

st.set_page_config(page_title="PlantProof AI", page_icon="🏭", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = ("Overview", "Evidence", "What If", "Blind Test", "Cost", "History", "Handover")
PAGE_ICONS = {"Overview": "📊", "Evidence": "🔎", "What If": "🧪", "Blind Test": "🎯",
              "Cost": "💷", "History": "🗂️", "Handover": "🔁"}
PARAM_LABELS = {"vibration_mm_s": "Vibration (mm/s)", "bearing_temp_c": "Bearing temp (°C)",
                "discharge_pressure_bar": "Discharge pressure (bar)",
                "motor_current_a": "Motor current (A)"}
LABEL_COLORS = {"High": "#0F766E", "Medium": "#D97706", "Low": "#94A3B8"}
PERSISTENCE_SHORT = ("Saved history may be lost when the app restarts or redeploys. "
                     "Export it from the History page to keep a copy.")
PERSISTENCE_FULL = (
    "**Storage notice.** History is stored in a local SQLite file. On Streamlit "
    "Community Cloud, local files are **not guaranteed to persist**: they can be wiped "
    "when the app restarts, reboots, redeploys or wakes from sleep. Demo data is rebuilt "
    "automatically, but saved investigations, What If runs, Blind Test results and "
    "handovers are lost unless you **export** them below and **import** them again later."
)


# --------------------------------------------------------------------------- setup
@st.cache_resource(show_spinner=False)
def get_store() -> Store:
    store = Store()
    store.seed_if_empty()
    return store


@st.cache_resource(show_spinner=False)
def get_config() -> EngineConfig:
    return load_engine_config()


@st.cache_resource(show_spinner=False)
def get_costs() -> dict:
    return cost_model.load_cost_assumptions()


@st.cache_resource(show_spinner=False)
def get_index() -> list[dict]:
    return load_scenario_index()


@dataclass
class Ctx:
    store: Store
    cfg: EngineConfig
    costs: dict
    meta: dict
    sid: str
    obs: tuple[Observation, ...]
    result: AnalysisResult


def pct(x: float) -> str:
    return f"{x:.0%}"


def money(x: float, ctx: Ctx) -> str:
    return cost_model.format_money(x, ctx.costs["currency_symbol"])


def ids_text(ids, limit: int = 10) -> str:
    ids = list(ids)
    if not ids:
        return "—"
    extra = f" … +{len(ids) - limit} more" if len(ids) > limit else ""
    return ", ".join(ids[:limit]) + extra


def records_table(obs) -> list[dict]:
    return [{"Record ID": o.record_id, "Time": o.timestamp.replace("T", " "),
             "Type": o.source_type.replace("_", " "), "Parameter": o.parameter,
             "Value": o.value, "Unit": o.unit, "Status": o.status or "",
             "Source": o.source, "Text": o.text} for o in obs]


def show_finding(f: Finding) -> None:
    st.markdown(f"**{f.finding_id} · {f.title}**  \n{f.detail}")
    st.caption(f"Source records: {ids_text(f.record_ids)}")


def session_get(key: str, sid: str):
    """Return a per-scenario session value, or None if it belongs to another scenario."""
    item = st.session_state.get(key)
    if item and item[0] == sid:
        return item[1]
    return None


# -------------------------------------------------------------------------- charts
def confidence_chart(assessments) -> go.Figure:
    items = list(reversed(assessments))
    fig = go.Figure(go.Bar(
        x=[a.confidence for a in items], y=[a.name for a in items], orientation="h",
        marker_color=[LABEL_COLORS[a.confidence_label] for a in items],
        text=[f"{a.confidence:.0%} · {a.confidence_label}" for a in items],
        textposition="auto", hovertemplate="%{y}: %{x:.0%}<extra></extra>"))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(range=[0, 1], tickformat=".0%", title="Confidence"))
    return fig


def trend_chart(obs, param: str, ctx: Ctx, highlight: set[str]) -> go.Figure:
    series = [o for o in obs if o.source_type == "sensor" and o.parameter == param]
    fig = go.Figure(go.Scatter(
        x=[o.timestamp for o in series], y=[o.value for o in series], mode="lines+markers",
        name=PARAM_LABELS.get(param, param), line=dict(color="#0F766E", width=2),
        marker=dict(size=4), customdata=[o.record_id for o in series],
        hovertemplate="%{customdata}<br>%{x}<br>%{y}<extra></extra>"))
    hot = [o for o in series if o.record_id in highlight]
    if hot:
        fig.add_trace(go.Scatter(
            x=[o.timestamp for o in hot], y=[o.value for o in hot], mode="markers",
            name="Linked to a contradiction", marker=dict(color="#DC2626", size=9),
            customdata=[o.record_id for o in hot],
            hovertemplate="%{customdata}<br>%{y}<extra></extra>"))
    limit = ctx.cfg.limits.get(param)
    if limit:
        fig.add_hline(y=limit.alarm, line_dash="dash", line_color="#DC2626",
                      annotation_text=f"Alarm {limit.alarm:g}", annotation_position="top left")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=bool(hot),
                      legend=dict(orientation="h", y=-0.2),
                      yaxis_title=PARAM_LABELS.get(param, param))
    return fig


def comparison_chart(rows) -> go.Figure:
    names = [r["hypothesis"] for r in rows]
    fig = go.Figure([
        go.Bar(name="Baseline", x=names, y=[r["baseline_confidence"] for r in rows],
               marker_color="#94A3B8"),
        go.Bar(name="What If", x=names, y=[r["scenario_confidence"] for r in rows],
               marker_color="#0F766E"),
    ])
    fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(range=[0, 1], tickformat=".0%", title="Confidence"),
                      legend=dict(orientation="h", y=1.1))
    return fig


def cost_chart(est: cost_model.CostEstimate) -> go.Figure:
    cases = ["Low", "Base", "High"]
    colors = ["#0F766E", "#5EAAA8", "#D97706"]
    fig = go.Figure([
        go.Bar(name=line.component, x=cases, y=[line.low, line.base, line.high],
               marker_color=colors[i % len(colors)])
        for i, line in enumerate(est.lines)
    ])
    fig.update_layout(barmode="stack", height=320, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis_title=f"Cost ({est.currency_symbol})",
                      legend=dict(orientation="h", y=1.1))
    return fig


# --------------------------------------------------------------------------- pages
def page_overview(ctx: Ctx) -> None:
    r, top = ctx.result, ctx.result.top
    st.title(f"🏭 {ctx.meta['asset_name']}")
    st.caption(f"{ctx.meta['title']} · analysis window {r.window_start.replace('T', ' ')} "
               f"→ {r.window_end.replace('T', ' ')}")
    st.info(ctx.meta["summary"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records analysed", r.record_count)
    c2.metric("Contradictions", len(r.contradictions),
              help="Records that conflict with each other. Resolve before restart.")
    c3.metric("Missing evidence", len(r.missing),
              help="Evidence a hypothesis needs that is absent or out of date.")
    if top:
        c4.metric("Leading hypothesis", top.name, f"{pct(top.confidence)} · {top.confidence_label}",
                  delta_color="off")

    if top:
        est = cost_model.estimate(top.hypothesis_id, ctx.costs)
        t = est.totals
        st.markdown(f"**Estimated cost impact if {top.name.lower()} is confirmed:** "
                    f"{money(t['low'], ctx)} – {money(t['high'], ctx)} "
                    f"(base {money(t['base'], ctx)}). Illustrative figures; see the Cost page.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Sensor trends")
        highlight = {rid for c in r.contradictions for rid in c.record_ids}
        params = [p for p in PARAM_LABELS if any(o.parameter == p for o in ctx.obs)]
        tabs = st.tabs([PARAM_LABELS[p] for p in params])
        for tab, p in zip(tabs, params):
            with tab:
                st.plotly_chart(trend_chart(ctx.obs, p, ctx, highlight), key=f"trend_{p}")
    with right:
        st.subheader("Hypothesis confidence")
        st.plotly_chart(confidence_chart(r.assessments), key="overview_conf")
        st.caption("Rule-based and explainable. See the Evidence page for the working.")

    a, b = st.columns(2)
    with a:
        st.subheader("⚠️ Contradictions")
        if not r.contradictions:
            st.success("No contradictions detected.")
        for f in r.contradictions:
            with st.container(border=True):
                show_finding(f)
    with b:
        st.subheader("🧩 Missing evidence")
        if not r.missing:
            st.success("All required evidence is present.")
        for f in r.missing:
            with st.container(border=True):
                hyps = ", ".join(ctx.cfg.hypothesis(h).name for h in f.hypothesis_ids)
                st.markdown(f"**{f.finding_id} · {f.title}**  \n{f.detail}")
                st.caption(f"Needed to test: {hyps}")


def page_evidence(ctx: Ctx) -> None:
    r = ctx.result
    st.title("🔎 Evidence engine")
    st.caption("Every conclusion below links to the source record IDs it is based on.")

    st.subheader("Hypothesis ranking")
    st.dataframe([{
        "Rank": a.rank, "Hypothesis": a.name, "Confidence": pct(a.confidence),
        "Level": a.confidence_label, "Support ratio": pct(a.support_ratio),
        "Evidence coverage": pct(a.coverage), "Contested factor": a.contested_factor,
    } for a in r.assessments], hide_index=True)

    with st.expander("How confidence is calculated"):
        cfg = ctx.cfg
        st.markdown(
            f"""
- **Support ratio** = max(0, matched supporting weight − matched refuting weight) ÷ total supporting weight
- **Coverage** = required evidence present ÷ required evidence total
- **Coverage factor** = {cfg.coverage_floor:g} + {1 - cfg.coverage_floor:g} × coverage
- **Contested factor** = max({cfg.min_contested_factor:g}, {cfg.contested_penalty:g} ^ number of contradictions touching supporting records)
- **Confidence** = support ratio × coverage factor × contested factor
- Levels: High ≥ {pct(cfg.high_threshold)}, Medium ≥ {pct(cfg.medium_threshold)}, otherwise Low.

Rules, weights and thresholds live in `config/hypotheses.json`.
""")

    for a in r.assessments:
        with st.expander(f"#{a.rank} {a.name} — {pct(a.confidence)} ({a.confidence_label})",
                         expanded=a.rank == 1):
            st.caption(ctx.cfg.hypothesis(a.hypothesis_id).description)
            m1, m2, m3 = st.columns(3)
            m1.metric("Support ratio", pct(a.support_ratio),
                      f"{a.support_score:g} of {a.support_possible:g} pts, −{a.refute_score:g} refuting",
                      delta_color="off")
            m2.metric("Evidence coverage", pct(a.coverage))
            m3.metric("Contested factor", f"{a.contested_factor:.2f}")
            st.markdown("**Supporting evidence**")
            for f in a.supporting or []:
                show_finding(f)
            if not a.supporting:
                st.caption("No supporting rule matched.")
            st.markdown("**Refuting evidence**")
            for f in a.refuting:
                show_finding(f)
            if not a.refuting:
                st.caption("No refuting rule matched.")
            if a.missing:
                st.markdown("**Missing evidence**")
                for f in a.missing:
                    st.markdown(f"- {f.title}: {f.detail}")
            st.markdown("**Recommended actions if confirmed**")
            st.markdown("\n".join(f"- {x}" for x in a.recommended_actions) or "—")

    st.subheader("Contradictions")
    if not r.contradictions:
        st.success("No contradictions detected.")
    for f in r.contradictions:
        with st.container(border=True):
            show_finding(f)

    st.subheader("Trace a record")
    referenced = sorted({rid for f in r.all_findings() for rid in f.record_ids})
    by_id = {o.record_id: o for o in ctx.obs}
    if referenced:
        rid = st.selectbox("Record ID used by a finding", referenced, key=f"trace_record_{ctx.sid}")
        rec = by_id.get(rid)
        if rec:
            st.dataframe(records_table([rec]), hide_index=True)
            used_by = r.findings_for_record(rid)
            st.markdown("**Used by:** " + ", ".join(f"{f.finding_id} ({f.title})" for f in used_by))

    st.subheader("All source records")
    present = [s for s in SOURCE_TYPES if any(o.source_type == s for o in ctx.obs)]
    chosen = st.multiselect("Record types", present,
                            default=[s for s in present if s != "sensor"], key="ev_types")
    st.dataframe(records_table([o for o in ctx.obs if o.source_type in chosen]), hide_index=True)

    st.subheader("Save this investigation")
    with st.form("save_investigation"):
        title = st.text_input("Title", value=f"P-301 trip investigation ({ctx.sid})")
        role = st.text_input("Analyst role", placeholder="e.g. Reliability engineer",
                             help="Use a role, not a personal name - this demo is public.")
        notes = st.text_area("Notes", max_chars=2000)
        if st.form_submit_button("Save investigation", type="primary"):
            top = r.top
            ctx.store.save("investigation", ctx.sid, title, {
                "analyst_role": role, "notes": notes,
                "leading_hypothesis": top.name if top else None,
                "confidence": top.confidence if top else None,
                "analysis": r.to_dict(),
            })
            st.success("Investigation saved to History. Remember to export history to keep it.")


def _whatif_presets(sid: str) -> dict[str, list[whatif.WhatIfChange]]:
    C = whatif.WhatIfChange
    return {
        "Alignment check finds a 0.32 mm offset": [
            C("add_record", {"parameter": "alignment_offset_mm", "value": 0.32})],
        "Alignment check within tolerance (0.03 mm)": [
            C("add_record", {"parameter": "alignment_offset_mm", "value": 0.03})],
        "Oil analysis comes back clean (15 ppm iron)": [
            C("override_value", {"record_id": f"{sid}-LAB-0001", "value": 15.0})],
        "New sensor calibration certificate issued today": [
            C("add_record", {"parameter": "vib_sensor_cal"})],
        "Handheld check at trip time reads 3.0 mm/s": [
            C("add_record", {"parameter": "handheld_vibration_mm_s", "value": 3.0})],
        "Ignore all operator logs": [C("exclude_source", {"source_type": "operator_log"})],
    }


def page_whatif(ctx: Ctx) -> None:
    st.title("🧪 What If simulations")
    st.caption("Changes are applied to a copy of the data. Original observations are never "
               "modified - each run proves this with a fingerprint check.")

    presets = _whatif_presets(ctx.sid)
    choice = st.selectbox("Start from a preset", ["Custom"] + list(presets), key="wi_preset")
    changes: list[whatif.WhatIfChange] = []

    if choice != "Custom":
        changes = presets[choice]
        st.markdown("**Changes:** " + "; ".join(c.describe() for c in changes))
    else:
        present = [s for s in SOURCE_TYPES if any(o.source_type == s for o in ctx.obs)]
        excl = st.multiselect("Ignore these record types", present, key="wi_excl")
        for s in excl:
            changes.append(whatif.WhatIfChange("exclude_source", {"source_type": s}))

        valued = [o for o in ctx.obs if o.value is not None]
        if st.checkbox("Override one record's value", key="wi_ovr_on"):
            non_sensor = [o.record_id for o in valued if o.source_type != "sensor"]
            ids = non_sensor + [o.record_id for o in valued if o.source_type == "sensor"]
            rid = st.selectbox("Record", ids, key=f"wi_ovr_id_{ctx.sid}")
            current = next(o for o in valued if o.record_id == rid)
            st.caption(f"Current value: {current.value:g} {current.unit} · {current.text}")
            val = st.number_input("New value", value=float(current.value), key=f"wi_ovr_val_{ctx.sid}_{rid}")
            changes.append(whatif.WhatIfChange("override_value", {"record_id": rid, "value": val}))

        if st.checkbox("Scale a sensor parameter", key="wi_scale_on"):
            params = sorted({o.parameter for o in ctx.obs if o.source_type == "sensor"})
            p = st.selectbox("Parameter", params, format_func=lambda x: PARAM_LABELS.get(x, x),
                             key="wi_scale_p")
            factor = st.slider("Multiply all readings by", 0.5, 1.5, 1.0, 0.05, key="wi_scale_f")
            changes.append(whatif.WhatIfChange("scale_parameter", {"parameter": p, "factor": factor}))

        if st.checkbox("Add hypothetical evidence", key="wi_add_on"):
            tpls = whatif.EVIDENCE_TEMPLATES
            p = st.selectbox("Evidence", list(tpls), format_func=lambda x: tpls[x]["label"],
                             key="wi_add_p")
            params = {"parameter": p}
            if tpls[p]["default"] is not None:
                params["value"] = st.number_input("Value", value=float(tpls[p]["default"]),
                                                  key="wi_add_v")
            changes.append(whatif.WhatIfChange("add_record", params))

    if st.button("Run simulation", type="primary", disabled=not changes, key="wi_run"):
        try:
            res = whatif.run_whatif(ctx.obs, ctx.cfg, changes)
            st.session_state["whatif_result"] = (ctx.sid, res)
        except ValueError as exc:
            st.error(f"Could not run the simulation: {exc}")

    res = session_get("whatif_result", ctx.sid)
    if res is None:
        st.info("Choose a preset or build custom changes, then run the simulation.")
        return

    st.divider()
    st.success(res.summary())
    st.markdown("**Applied:** " + "; ".join(c.describe() for c in res.changes))
    ok = res.originals_unchanged and whatif.fingerprint(ctx.store.observations(ctx.sid)) \
        == res.fingerprint_before
    f1, f2 = st.columns(2)
    f1.metric("Original data fingerprint (before → after)",
              f"{res.fingerprint_before[:8]} → {res.fingerprint_after[:8]}")
    if ok:
        f2.success("✅ Original observations unchanged (memory and database checked).")
    else:
        f2.error("Original observations changed - please report this bug.")

    rows = res.comparison()
    st.plotly_chart(comparison_chart(rows), key="wi_chart")
    st.dataframe([{"Hypothesis": x["hypothesis"], "Baseline": pct(x["baseline_confidence"]),
                   "What If": pct(x["scenario_confidence"]),
                   "Change": f"{x['delta']:+.0%}", "Rank": f"{x['baseline_rank']} → {x['scenario_rank']}"}
                  for x in rows], hide_index=True)
    sc = res.set_changes()
    cols = st.columns(4)
    for col, (k, label) in zip(cols, [("contradictions_resolved", "Contradictions resolved"),
                                      ("contradictions_new", "New contradictions"),
                                      ("missing_resolved", "Evidence gaps closed"),
                                      ("missing_new", "New evidence gaps")]):
        col.metric(label, len(sc[k]))
        if sc[k]:
            col.caption(", ".join(sc[k]))

    if st.button("Save this run to History", key="wi_save"):
        ctx.store.save("whatif", ctx.sid, res.summary(), res.to_dict())
        st.success("What If run saved.")


def _show_score(score: blind_test.BlindTestScore, ctx: Ctx, key: str) -> None:
    m1, m2 = st.columns(2)
    m1.metric("Blind Test score", f"{score.total:g} / 100")
    m2.metric("Grade", score.grade)
    st.progress(min(1.0, score.total / 100))
    st.dataframe([{"Component": c.name, "Points": f"{c.points:g} / {c.max_points:g}",
                   "Detail": c.detail} for c in score.components], hide_index=True)
    with st.expander("Reveal reference answers"):
        ref = score.reference
        st.markdown(f"**Root cause:** {ctx.cfg.hypothesis(ref.root_cause).name}")
        st.markdown(f"**Expected contradictions:** {', '.join(sorted(ref.expected_contradictions))}")
        st.markdown(f"**Expected missing evidence:** {', '.join(sorted(ref.expected_missing))}")
        st.markdown(f"**Rationale:** {ref.rationale}")
        for c in score.components[1:]:
            if c.false_positives or c.false_negatives:
                st.caption(f"{c.name}: extra {c.false_positives or '—'}, "
                           f"missed {c.false_negatives or '—'}")
    if st.button("Save result to History", key=f"bt_save_{key}"):
        ctx.store.save("blind_test", ctx.sid,
                       f"Blind Test ({score.submission.source}): {score.total:g}/100",
                       score.to_dict())
        st.success("Blind Test result saved.")


def page_blind_test(ctx: Ctx) -> None:
    st.title("🎯 Blind Test")
    st.caption("Scores an analysis against reference answers stored separately in "
               "data/reference_answers.json. The evidence engine never reads that file "
               "(a unit test enforces this).")
    st.warning("Transparency note: this repository is public, so anyone can read the "
               "reference answers. The separation shows the method; it is not a secret.")
    try:
        ref = blind_test.load_reference(ctx.sid)
    except KeyError:
        st.info("No reference answers for this scenario.")
        return

    tab_engine, tab_analyst = st.tabs(["Score the engine", "Score your own analysis"])
    with tab_engine:
        st.markdown("Runs the engine's current analysis through the scorer.")
        if st.button("Run Blind Test", type="primary", key="bt_run"):
            sub = blind_test.submission_from_analysis(ctx.result)
            st.session_state["bt_engine"] = (ctx.sid, blind_test.score(sub, ref))
        score = session_get("bt_engine", ctx.sid)
        if score:
            _show_score(score, ctx, "engine")

    with tab_analyst:
        st.markdown("Make your own call from the Evidence page, then see how you score.")
        hyps = [h.id for h in ctx.cfg.hypotheses]
        names = {h.id: h.name for h in ctx.cfg.hypotheses}
        claims = [o for o in ctx.obs if o.source_type in ("operator_log", "inspection")]
        catalogue = ctx.cfg.required_evidence_catalogue()
        with st.form("analyst_bt"):
            first = st.selectbox("Most likely root cause", hyps, format_func=names.get)
            second = st.selectbox("Second most likely", hyps, index=1, format_func=names.get)
            contra = st.multiselect(
                "Records involved in contradictions", [o.record_id for o in claims],
                format_func=lambda rid: f"{rid} — "
                + next(o.text for o in claims if o.record_id == rid)[:60])
            miss = st.multiselect("Evidence that is missing or out of date", list(catalogue),
                                  format_func=catalogue.get)
            submitted = st.form_submit_button("Score my analysis", type="primary")
        if submitted:
            ranking = [first] + ([second] if second != first else [])
            sub = blind_test.Submission(ranking, set(contra), set(miss), source="analyst")
            st.session_state["bt_analyst"] = (ctx.sid, blind_test.score(sub, ref))
        score = session_get("bt_analyst", ctx.sid)
        if score:
            _show_score(score, ctx, "analyst")


def page_cost(ctx: Ctx) -> None:
    st.title("💷 Cost impact simulator")
    st.caption("Low / base / high totals with every assumption and formula visible. "
               "All figures are illustrative synthetic values.")
    hyps = [a.hypothesis_id for a in ctx.result.assessments]
    names = {a.hypothesis_id: f"{a.name} ({pct(a.confidence)})" for a in ctx.result.assessments}
    hid = st.selectbox("Cost the repair for", hyps, format_func=names.get, key="cost_h")

    base_assumptions = ctx.costs
    prof = base_assumptions["profiles"][hid]
    overrides: dict[str, dict[str, float]] = {}
    with st.expander("Adjust assumptions (this session only)"):
        fields = [("downtime_hours", "Downtime (hours)", prof["downtime_hours"]),
                  ("labour_hours", "Labour (hours)", prof["labour_hours"]),
                  ("parts", "Parts (£)", prof["parts"]),
                  ("lost_margin_per_hour", "Lost margin (£/hour)",
                   base_assumptions["lost_margin_per_hour"]),
                  ("labour_rate_per_hour", "Labour rate (£/hour)",
                   base_assumptions["labour_rate_per_hour"])]
        for key, label, rng in fields:
            st.markdown(f"**{label}**")
            cols = st.columns(3)
            overrides[key] = {
                case: cols[i].number_input(case.title(), min_value=0.0, value=float(rng[case]),
                                           key=f"cost_{hid}_{key}_{case}")
                for i, case in enumerate(cost_model.CASES)
            }
    try:
        assumptions = cost_model.with_overrides(base_assumptions, hid, overrides)
    except ConfigError as exc:
        st.error(f"Invalid assumptions: {exc}. Using the default values instead.")
        assumptions = base_assumptions

    est = cost_model.estimate(hid, assumptions)
    t = est.totals
    st.markdown(f"**Repair scope:** {est.description}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Low", money(t["low"], ctx))
    c2.metric("Base", money(t["base"], ctx))
    c3.metric("High", money(t["high"], ctx))

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(cost_chart(est), key="cost_chart")
    with right:
        st.markdown("**Breakdown**")
        st.dataframe([{"Component": line.component, "Formula": line.formula,
                       "Low": money(line.low, ctx), "Base": money(line.base, ctx),
                       "High": money(line.high, ctx)} for line in est.lines], hide_index=True)
        st.markdown("**Inputs used**")
        st.dataframe([{"Input": k.replace("_", " "), "Low": v["low"], "Base": v["base"],
                       "High": v["high"]} for k, v in est.inputs.items()], hide_index=True)

    st.subheader("Confidence-weighted base cost")
    w = cost_model.weighted_estimate(ctx.result.assessments, assumptions)
    if w is None:
        st.info("All hypotheses have zero confidence, so no weighted estimate is possible.")
    else:
        st.metric("Expected base cost across hypotheses", money(w["value"], ctx))
        st.dataframe([{"Hypothesis": x["hypothesis"], "Confidence": pct(x["confidence"]),
                       "Weight": pct(x["weight"]), "Base total": money(x["base_total"], ctx),
                       "Contribution": money(x["contribution"], ctx)} for x in w["rows"]],
                     hide_index=True)
        st.caption("Weight = hypothesis confidence ÷ sum of all confidences. "
                   "Expected cost = Σ weight × base total.")


def page_history(ctx: Ctx) -> None:
    st.title("🗂️ Investigation history")
    st.warning(PERSISTENCE_FULL)

    entries_all = ctx.store.list_history()
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**Export history**")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        st.download_button(f"⬇️ Download history ({len(entries_all)} entries, JSON)",
                           data=ctx.store.export_history_json(),
                           file_name=f"plantproof_history_{stamp}.json",
                           mime="application/json", key="hist_export")
    with e2:
        st.markdown("**Import history**")
        upload = st.file_uploader("PlantProof history JSON", type=["json"], key="hist_upload")
        if upload is not None and st.button("Import file", key="hist_import"):
            try:
                res = ctx.store.import_history(upload.getvalue())
                st.success(f"Imported {res['inserted']} entries "
                           f"({res['skipped']} already present).")
            except ValueError as exc:
                st.error(str(exc))

    show_all = st.checkbox("Show all scenarios", key="hist_all")
    labels = {"investigation": "Investigations", "whatif": "What If runs",
              "blind_test": "Blind Tests", "handover": "Handovers"}
    tabs = st.tabs(list(labels.values()))
    for tab, kind in zip(tabs, labels):
        with tab:
            items = ctx.store.list_history(kind, None if show_all else ctx.sid)
            if not items:
                st.caption("Nothing saved yet.")
            for item in items:
                with st.expander(f"{item['title']} · {item['created_at']} · scenario "
                                 f"{item['scenario_id']}"):
                    p = item["payload"]
                    if kind == "investigation":
                        st.markdown(f"**Leading hypothesis:** {p.get('leading_hypothesis')} "
                                    f"({pct(p.get('confidence') or 0)})  \n"
                                    f"**Analyst role:** {p.get('analyst_role') or '—'}  \n"
                                    f"**Notes:** {p.get('notes') or '—'}")
                    elif kind == "whatif":
                        st.markdown(f"**Changes:** {'; '.join(p.get('change_descriptions', []))}  \n"
                                    f"**Result:** {p.get('summary')}")
                    elif kind == "blind_test":
                        st.markdown(f"**Score:** {p.get('total')} / 100 ({p.get('grade')})")
                    elif kind == "handover":
                        st.markdown(p.get("markdown", ""))
                    st.json(p, expanded=False)
                    if st.button("Delete", key=f"del_{item['uid']}"):
                        ctx.store.delete(item["uid"])
                        st.rerun()

    with st.expander("Danger zone"):
        confirm = st.checkbox("I understand this cannot be undone", key="hist_confirm")
        d1, d2 = st.columns(2)
        if d1.button("Clear all history", disabled=not confirm, key="hist_clear"):
            n = ctx.store.clear_history()
            st.success(f"Deleted {n} entries.")
        if d2.button("Reset demo observations", disabled=not confirm, key="hist_reset"):
            n = ctx.store.reset_observations()
            for k in ("whatif_result", "bt_engine", "bt_analyst", "handover_doc"):
                st.session_state.pop(k, None)
            st.success(f"Re-seeded {n} demo records. History kept.")


def page_handover(ctx: Ctx) -> None:
    st.title("🔁 Shift handover")
    st.caption("Built from engine findings and your notes - no AI text generation. "
               "Use role names, not personal names: this demo is public.")
    last_whatif = session_get("whatif_result", ctx.sid)
    with st.form("handover_form"):
        shift = st.selectbox("Shift", ["Day shift (06:00–18:00)", "Night shift (18:00–06:00)"])
        c1, c2 = st.columns(2)
        outgoing = c1.text_input("Outgoing (role)", placeholder="e.g. Day shift lead")
        incoming = c2.text_input("Incoming (role)", placeholder="e.g. Night shift lead")
        include_cost = st.checkbox("Include cost impact for the leading hypothesis", value=True)
        include_wi = st.checkbox("Include latest What If result", value=last_whatif is not None,
                                 disabled=last_whatif is None)
        notes = st.text_area("Notes for the incoming shift", max_chars=handover.MAX_NOTES)
        go_ = st.form_submit_button("Generate handover", type="primary")
    if go_:
        top = ctx.result.top
        est = cost_model.estimate(top.hypothesis_id, ctx.costs) if (include_cost and top) else None
        wi_notes = [last_whatif.summary()] if (include_wi and last_whatif) else []
        doc = handover.build_handover(ctx.result, ctx.meta, shift=shift, outgoing=outgoing,
                                      incoming=incoming, notes=notes, cost=est,
                                      whatif_notes=wi_notes)
        st.session_state["handover_doc"] = (ctx.sid, doc)

    doc = session_get("handover_doc", ctx.sid)
    if doc:
        md = doc.to_markdown()
        with st.container(border=True):
            st.markdown(md)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Markdown report", md, file_name=f"handover_{ctx.sid}_{stamp}.md",
                           mime="text/markdown", key="ho_md")
        d2.download_button("⬇️ JSON data", doc.to_json(),
                           file_name=f"handover_{ctx.sid}_{stamp}.json",
                           mime="application/json", key="ho_json")
        if d3.button("Save to History", key="ho_save"):
            ctx.store.save("handover", ctx.sid, f"Handover · {doc.shift}",
                           doc.to_dict() | {"markdown": md})
            st.success("Handover saved.")

    previous = ctx.store.list_history("handover", ctx.sid)
    if previous:
        st.subheader("Previous handovers")
        for item in previous[:10]:
            with st.expander(f"{item['title']} · {item['created_at']}"):
                st.markdown(item["payload"].get("markdown", ""))


# ---------------------------------------------------------------------------- main
def main() -> None:
    try:
        store, cfg, costs, index = get_store(), get_config(), get_costs(), get_index()
    except (ConfigError, OSError, ValueError) as exc:
        st.error(f"PlantProof AI could not start: {exc}")
        st.stop()
        return

    st.sidebar.title("🏭 PlantProof AI")
    st.sidebar.caption("Evidence-first investigations for plant incidents")
    page = st.sidebar.radio("Navigate", PAGES, key="page",
                            format_func=lambda p: f"{PAGE_ICONS[p]} {p}")
    titles = {s["id"]: s["title"] for s in index}
    sid = st.sidebar.selectbox("Scenario", list(titles), format_func=titles.get, key="scenario")
    st.sidebar.divider()
    st.sidebar.warning(PERSISTENCE_SHORT, icon="💾")
    st.sidebar.caption(f"v{__version__} · Synthetic demo data only · Rule-based analysis, "
                       "no external AI or API keys.")

    meta = next(s for s in index if s["id"] == sid)
    obs = store.observations(sid)
    if not obs:
        store.reset_observations()
        obs = store.observations(sid)
    ctx = Ctx(store, cfg, costs, meta, sid, obs, analyse(obs, cfg, sid))

    {"Overview": page_overview, "Evidence": page_evidence, "What If": page_whatif,
     "Blind Test": page_blind_test, "Cost": page_cost, "History": page_history,
     "Handover": page_handover}[page](ctx)


main()
