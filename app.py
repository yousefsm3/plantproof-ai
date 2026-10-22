"""PlantProof AI - Streamlit dashboard.

This file only DISPLAYS results. All analysis lives in the plantproof/ package
(plain Python, unit-tested). Run locally with:  streamlit run app.py

UI labels show English followed by a light-grey Arabic gloss
(see plantproof/translations.py).
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from plantproof import __version__, advisor, blind_test, cost_model, handover, whatif
from plantproof.domain import (SOURCE_TYPES, AnalysisResult, ConfigError, EngineConfig,
                               Finding, Observation, load_engine_config,
                               load_scenario_index)
from plantproof.evidence_engine import analyse
from plantproof.storage import Store
from plantproof.translations import ar, bi, bi_plain

st.set_page_config(page_title="PlantProof AI", page_icon=":material/hub:", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = ("Overview", "Evidence", "Advisor", "What If", "Blind Test", "Cost", "History",
         "Handover")
PAGE_ICONS = {"Overview": ":material/dashboard:", "Evidence": ":material/manage_search:",
              "Advisor": ":material/psychology:",
              "What If": ":material/science:", "Blind Test": ":material/fact_check:",
              "Cost": ":material/payments:", "History": ":material/history:",
              "Handover": ":material/sync_alt:"}
PARAM_LABELS = {"vibration_mm_s": "Vibration (mm/s)", "bearing_temp_c": "Bearing temp (°C)",
                "discharge_pressure_bar": "Discharge pressure (bar)",
                "motor_current_a": "Motor current (A)"}
SOURCE_AR = {"sensor": "حساس", "operator_log": "سجل مشغّل", "inspection": "فحص",
             "lab": "مختبر", "calibration": "معايرة", "maintenance": "صيانة", "event": "حدث"}
CASE_AR = {"low": "منخفض", "base": "أساسي", "high": "مرتفع"}
LABEL_COLORS = {"High": "#145A55", "Medium": "#C8844A", "Low": "#B9CCC9"}
PETROL, STEEL, COPPER, ALERT = "#145A55", "#7FA9A3", "#C8844A", "#B42318"
ASSETS = Path(__file__).resolve().parent / "assets"
DISCLAIMER = ("Concept prototype for the energy sector. Not affiliated with or endorsed by "
              "any company.")
DISCLAIMER_AR = "نموذج أولي لقطاع الطاقة، غير تابع لأي شركة ولا معتمد منها."
PERSISTENCE_SHORT = ("Saved history may be lost when the app restarts or redeploys. "
                     "Export it from the History page to keep a copy.")
PERSISTENCE_FULL = (
    "**Storage notice** :small[:gray[تنبيه التخزين]]  \n"
    "History is stored in a local SQLite file. On Streamlit Community Cloud, local files are "
    "**not guaranteed to persist**: they can be wiped when the app restarts, reboots, "
    "redeploys or wakes from sleep. Demo data is rebuilt automatically, but saved "
    "investigations, What If runs, Blind Test results and handovers are lost unless you "
    "**export** them below and **import** them again later.  \n"
    ":small[:gray[قد يُحذف السجل عند إعادة تشغيل التطبيق أو تحديثه أو استيقاظه من السكون. "
    "نزّله من هنا واستورده لاحقًا.]]"
)
HANDOVER_HEADINGS = ("Status", "Leading hypothesis", "Contradictions to resolve",
                     "Missing evidence", "Actions for incoming shift",
                     "Cost impact (illustrative)", "What If notes", "Analyst notes")


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


def gray(text: str) -> str:
    """Light-grey Arabic line for st.markdown / st.caption."""
    return f":small[:gray[{text}]]" if text else ""


def with_ar(text: str) -> str:
    """English sentence followed by its Arabic gloss on a new line (markdown)."""
    gloss = ar(text)
    return f"{text}  \n:small[:gray[{gloss}]]" if gloss else text


def source_plain(s: str) -> str:
    return f"{s.replace('_', ' ')} · {SOURCE_AR.get(s, '')}"


def ids_text(ids, limit: int = 10) -> str:
    ids = list(ids)
    if not ids:
        return "—"
    extra = f" … +{len(ids) - limit} more" if len(ids) > limit else ""
    return ", ".join(ids[:limit]) + extra


def records_table(obs) -> list[dict]:
    return [{"Record ID · رقم السجل": o.record_id,
             "Time · الوقت": o.timestamp.replace("T", " "),
             "Type · النوع": source_plain(o.source_type),
             "Parameter · المتغير": o.parameter, "Value · القيمة": o.value,
             "Unit · الوحدة": o.unit, "Status · الحالة": o.status or "",
             "Source · المصدر": o.source, "Text · النص": o.text} for o in obs]


def show_finding(f: Finding) -> None:
    st.markdown(f"**{f.finding_id} · {f.title}** {gray(ar(f.title))}  \n{f.detail}")
    st.caption(f"{bi('Source records')}: {ids_text(f.record_ids)}")


def session_get(key: str, sid: str):
    """Return a per-scenario session value, or None if it belongs to another scenario."""
    item = st.session_state.get(key)
    if item and item[0] == sid:
        return item[1]
    return None


def page_header(icon: str, title: str, caption: str = "") -> None:
    st.title(f"{icon} {bi(title)}")
    if caption:
        st.caption(with_ar(caption))


# ------------------------------------------------------------------------ branding
@st.cache_resource(show_spinner=False)
def svg_data_uri(name: str, recolor: tuple[str, str] | None = None,
                 opacity: tuple[str, str] | None = None) -> str:
    """Read an SVG from assets/ (original artwork) and return it as a data URI."""
    svg = (ASSETS / name).read_text(encoding="utf-8")
    if recolor:
        svg = svg.replace(*recolor)
    if opacity:
        svg = svg.replace(*opacity)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def inject_theme() -> None:
    """Industrial look: faint equipment drawing behind the app, card-style metrics."""
    bg = svg_data_uri("equipment.svg")
    st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{
  background-color: #CBD3D3;
  background-image: url("{bg}"),
    repeating-linear-gradient(135deg, rgba(255,255,255,0.06) 0 2px, rgba(0,0,0,0.03) 2px 4px),
    linear-gradient(180deg, #E2E7E7 0%, #CDD5D5 55%, #BAC5C5 100%);
  background-repeat: no-repeat, repeat, no-repeat;
  background-position: right -40px bottom -20px, 0 0, 0 0;
  background-size: min(1250px, 100vw) auto, auto, cover;
  background-attachment: fixed;
}}
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #EBEFEF 0%, #D7DEDE 100%);
  border-right: 1px solid #B6C2C2;
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMetric"] {{
  background: #EEF6F4; border: 1px solid #CFE3DE;
  border-left: 5px solid {PETROL}; border-radius: 10px; padding: 10px 14px;
}}
/* ---- unified, readable content on top of the equipment background ---- */
h1, h2, h3 {{ color: #0B2E2D !important; }}
[data-testid="stHeading"] h3 {{
  display: inline-block; background: #E3F1EE; padding: 4px 14px;
  border-radius: 8px; border-left: 4px solid {COPPER};
}}
[data-testid="stHeading"] h1 {{
  display: inline-block; background: rgba(255,255,255,0.9); padding: 2px 14px; border-radius: 10px;
}}
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {{
  background: rgba(255,255,255,0.9); border-radius: 8px; padding: 2px 8px;
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
button [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stMetric"] [data-testid="stMarkdownContainer"],
[data-testid="stTooltipContent"] [data-testid="stMarkdownContainer"],
label [data-testid="stMarkdownContainer"] {{ background: transparent; padding: 0; }}
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: #F1F7F6; border-radius: 12px; box-shadow: 0 2px 10px rgba(11,46,45,0.08);
}}
[class*="st-key-pp_contra"] {{ background: #FDEDEB !important; border: 1px solid #F3C4BD !important;
  border-left: 6px solid {ALERT} !important; }}
[class*="st-key-pp_miss"] {{ background: #FCF1E6 !important; border: 1px solid #EED3B8 !important;
  border-left: 6px solid {COPPER} !important; }}
.st-key-pp_kpi_records [data-testid="stMetric"] {{ background: #E6F2EF; border-left-color: {PETROL}; }}
.st-key-pp_kpi_contra [data-testid="stMetric"] {{ background: #FDEDEB; border-color: #F3C4BD;
  border-left-color: {ALERT}; }}
.st-key-pp_kpi_miss [data-testid="stMetric"] {{ background: #FCF1E6; border-color: #EED3B8;
  border-left-color: {COPPER}; }}
.st-key-pp_kpi_lead [data-testid="stMetric"] {{ background: #DDEFE9; border-color: #B9DCD3;
  border-left-color: #0B2E2D; }}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"],
[data-testid="stExpander"] [data-testid="stMarkdownContainer"],
[data-testid="stExpander"] [data-testid="stCaptionContainer"],
[data-testid="stTabs"] [data-testid="stMarkdownContainer"],
[data-testid="stForm"] [data-testid="stMarkdownContainer"] {{ background: transparent; padding: 0; }}
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stExpander"],
[data-testid="stTabs"], [data-testid="stForm"] {{
  background: #F6FAF9; border: 1px solid #D3E5E1; border-radius: 12px;
  box-shadow: 0 2px 10px rgba(11,46,45,0.07);
}}
[data-testid="stPlotlyChart"], [data-testid="stTabs"] {{ padding: 8px 10px; }}
[data-testid="stMetricLabel"] {{ color: {PETROL}; font-weight: 600; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
  font-size: 1.55rem; line-height: 1.25; color: #0B2E2D;
}}
.pp-ar {{ font-size: .78em; opacity: .6; font-weight: 400; margin-inline-start: .45em; }}
.pp-rtl {{ direction: rtl; text-align: right; unicode-bidi: isolate; color: #6B7B7A;
  font-size: .86rem; line-height: 1.6; margin: -6px 0 8px 0; }}
.pp-rtl-title {{ font-size: .95rem; font-weight: 600; margin-top: -10px; }}
.pp-rtl-note {{ font-size: .78rem; }}
.pp-name {{ font-size: 1.25rem; font-weight: 700; color: #0B2E2D; letter-spacing: .2px; }}
.pp-name span {{ color: {COPPER}; }}
</style>
""", unsafe_allow_html=True)


def sidebar_brand() -> None:
    """Logo as a small brand mark in the top corner; the platform name only in the sidebar."""
    try:
        st.logo(str(ASSETS / "logo.svg"), size="large")
    except Exception:  # an older Streamlit without st.logo: the name below still shows
        pass
    st.sidebar.markdown('<div class="pp-name">PlantProof <span>AI</span></div>',
                        unsafe_allow_html=True)


# -------------------------------------------------------------------------- charts
def confidence_chart(assessments) -> go.Figure:
    items = list(reversed(assessments))
    fig = go.Figure(go.Bar(
        x=[a.confidence for a in items], y=[bi_plain(a.name) for a in items], orientation="h",
        marker_color=[LABEL_COLORS[a.confidence_label] for a in items],
        text=[f"{a.confidence:.0%} · {a.confidence_label}" for a in items],
        textposition="auto", hovertemplate="%{y}: %{x:.0%}<extra></extra>"))
    fig.update_layout(paper_bgcolor="#F6FAF9", plot_bgcolor="#FFFFFF", height=280, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(range=[0, 1], tickformat=".0%", title=bi_plain("Confidence")))
    return fig


def trend_chart(obs, param: str, ctx: Ctx, highlight: set[str]) -> go.Figure:
    series = [o for o in obs if o.source_type == "sensor" and o.parameter == param]
    label = bi_plain(PARAM_LABELS.get(param, param))
    fig = go.Figure(go.Scatter(
        x=[o.timestamp for o in series], y=[o.value for o in series], mode="lines+markers",
        name=label, line=dict(color=PETROL, width=2),
        marker=dict(size=4), customdata=[o.record_id for o in series],
        hovertemplate="%{customdata}<br>%{x}<br>%{y}<extra></extra>"))
    hot = [o for o in series if o.record_id in highlight]
    if hot:
        fig.add_trace(go.Scatter(
            x=[o.timestamp for o in hot], y=[o.value for o in hot], mode="markers",
            name=bi_plain("Linked to a contradiction"), marker=dict(color=ALERT, size=9),
            customdata=[o.record_id for o in hot],
            hovertemplate="%{customdata}<br>%{y}<extra></extra>"))
    limit = ctx.cfg.limits.get(param)
    if limit:
        fig.add_hline(y=limit.alarm, line_dash="dash", line_color=ALERT,
                      annotation_text=f"Alarm · حد الإنذار {limit.alarm:g}",
                      annotation_position="top left")
    fig.update_layout(paper_bgcolor="#F6FAF9", plot_bgcolor="#FFFFFF", height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=bool(hot),
                      legend=dict(orientation="h", y=-0.2), yaxis_title=label)
    return fig


def comparison_chart(rows) -> go.Figure:
    names = [bi_plain(r["hypothesis"]) for r in rows]
    fig = go.Figure([
        go.Bar(name=bi_plain("Baseline"), x=names, y=[r["baseline_confidence"] for r in rows],
               marker_color="#B9CCC9"),
        go.Bar(name=bi_plain("What If"), x=names, y=[r["scenario_confidence"] for r in rows],
               marker_color=PETROL),
    ])
    fig.update_layout(paper_bgcolor="#F6FAF9", plot_bgcolor="#FFFFFF", barmode="group", height=340, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(range=[0, 1], tickformat=".0%", title=bi_plain("Confidence")),
                      legend=dict(orientation="h", y=1.1))
    return fig


def cost_chart(est: cost_model.CostEstimate) -> go.Figure:
    cases = [f"{c.title()} · {CASE_AR[c]}" for c in cost_model.CASES]
    colors = [PETROL, STEEL, COPPER]
    fig = go.Figure([
        go.Bar(name=bi_plain(line.component), x=cases, y=[line.low, line.base, line.high],
               marker_color=colors[i % len(colors)])
        for i, line in enumerate(est.lines)
    ])
    fig.update_layout(paper_bgcolor="#F6FAF9", plot_bgcolor="#FFFFFF", barmode="stack", height=320, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis_title=f"Cost · التكلفة ({est.currency_symbol})",
                      legend=dict(orientation="h", y=1.1))
    return fig


# --------------------------------------------------------------------------- pages
def page_overview(ctx: Ctx) -> None:
    r, top = ctx.result, ctx.result.top
    st.title(f":material/factory: {bi(ctx.meta['asset_name'])}")
    st.caption(f"{bi(ctx.meta['title'])} · {bi('analysis window')} "
               f"{r.window_start.replace('T', ' ')} → {r.window_end.replace('T', ' ')}")
    st.info(ctx.meta["summary"] + "  \n:small[:gray[توقفت المضخة P-301 بسبب إنذار اهتزاز عالٍ وتوقف "
            "الخط 3. حدّد السبب قبل إعادة التشغيل.]]")

    c1, c2, c3, c4 = st.columns(4)
    with c1.container(key="pp_kpi_records"):
        st.metric(bi("Records analysed"), r.record_count)
    with c2.container(key="pp_kpi_contra"):
        st.metric(bi("Contradictions"), len(r.contradictions),
                  help=with_ar("Records that conflict with each other. Resolve before restart."))
    with c3.container(key="pp_kpi_miss"):
        st.metric(bi("Missing evidence"), len(r.missing),
                  help=with_ar("Evidence a hypothesis needs that is absent or out of date."))
    if top:
        with c4.container(key="pp_kpi_lead"):
            st.metric(bi("Leading hypothesis"), top.name,
                      f"{pct(top.confidence)} · {top.confidence_label} · {ar(top.name)}",
                      delta_color="off")

    if top:
        t = cost_model.estimate(top.hypothesis_id, ctx.costs).totals
        st.markdown(f"**{bi('Estimated cost impact if confirmed')}** ({top.name}): "
                    f"{money(t['low'], ctx)} – {money(t['high'], ctx)} "
                    f"(base {money(t['base'], ctx)}). Illustrative figures; see the Cost page.  \n"
                    + gray("أرقام توضيحية، التفاصيل في صفحة التكلفة."))

    left, right = st.columns([3, 2])
    with left:
        st.subheader(bi("Sensor trends"))
        highlight = {rid for c in r.contradictions for rid in c.record_ids}
        params = [p for p in PARAM_LABELS if any(o.parameter == p for o in ctx.obs)]
        tabs = st.tabs([bi(PARAM_LABELS[p]) for p in params])
        for tab, p in zip(tabs, params):
            with tab:
                st.plotly_chart(trend_chart(ctx.obs, p, ctx, highlight), key=f"trend_{p}")
    with right:
        st.subheader(bi("Hypothesis confidence"))
        st.plotly_chart(confidence_chart(r.assessments), key="overview_conf")
        st.caption(with_ar("Rule-based and explainable. See the Evidence page for the working."))

    a, b = st.columns(2)
    with a:
        st.subheader(f":material/report: {bi('Contradictions')}")
        if not r.contradictions:
            st.success(with_ar("No contradictions detected."))
        for f in r.contradictions:
            with st.container(border=True, key=f"pp_contra_ov_{f.finding_id}"):
                show_finding(f)
    with b:
        st.subheader(f":material/pending_actions: {bi('Missing evidence')}")
        if not r.missing:
            st.success(with_ar("All required evidence is present."))
        for f in r.missing:
            with st.container(border=True, key=f"pp_miss_ov_{f.finding_id}"):
                hyps = ", ".join(ctx.cfg.hypothesis(h).name for h in f.hypothesis_ids)
                hyps_ar = "، ".join(ar(ctx.cfg.hypothesis(h).name) for h in f.hypothesis_ids)
                st.markdown(f"**{f.finding_id} · {f.title}** {gray(ar(f.title))}  \n{f.detail}")
                st.caption(f"{bi('Needed to test')}: {hyps} {gray(hyps_ar)}")


def page_evidence(ctx: Ctx) -> None:
    r = ctx.result
    page_header(PAGE_ICONS["Evidence"], "Evidence engine",
                "Every conclusion below links to the source record IDs it is based on.")

    st.subheader(bi("Hypothesis ranking"))
    st.dataframe([{
        "Rank · الترتيب": a.rank, "Hypothesis · الفرضية": bi_plain(a.name),
        "Confidence · الثقة": pct(a.confidence),
        "Level · المستوى": bi_plain(a.confidence_label),
        "Support ratio · نسبة الدعم": pct(a.support_ratio),
        "Evidence coverage · تغطية الأدلة": pct(a.coverage),
        "Contested factor · معامل التعارض": a.contested_factor,
    } for a in r.assessments], hide_index=True)

    with st.expander(bi("How confidence is calculated")):
        cfg = ctx.cfg
        st.markdown(
            f"""
- **Support ratio** :small[:gray[نسبة الدعم]] = max(0, matched supporting weight − matched refuting weight) ÷ total supporting weight
- **Coverage** :small[:gray[التغطية]] = required evidence present ÷ required evidence total
- **Coverage factor** :small[:gray[معامل التغطية]] = {cfg.coverage_floor:g} + {1 - cfg.coverage_floor:g} × coverage
- **Contested factor** :small[:gray[معامل التعارض]] = max({cfg.min_contested_factor:g}, {cfg.contested_penalty:g} ^ number of contradictions touching supporting records)
- **Confidence** :small[:gray[الثقة]] = support ratio × coverage factor × contested factor
- Levels :small[:gray[المستويات]]: High :small[:gray[عالية]] ≥ {pct(cfg.high_threshold)}, Medium :small[:gray[متوسطة]] ≥ {pct(cfg.medium_threshold)}, otherwise Low :small[:gray[منخفضة]].

Rules, weights and thresholds live in `config/hypotheses.json`.
:small[:gray[القواعد والأوزان والحدود موجودة في ملف الإعدادات config/hypotheses.json.]]
""")

    for a in r.assessments:
        with st.expander(f"#{a.rank} {bi(a.name)} — {pct(a.confidence)} ({bi(a.confidence_label)})",
                         expanded=a.rank == 1):
            st.caption(ctx.cfg.hypothesis(a.hypothesis_id).description)
            m1, m2, m3 = st.columns(3)
            m1.metric(bi("Support ratio"), pct(a.support_ratio),
                      f"{a.support_score:g} of {a.support_possible:g} pts, −{a.refute_score:g} refuting",
                      delta_color="off")
            m2.metric(bi("Evidence coverage"), pct(a.coverage))
            m3.metric(bi("Contested factor"), f"{a.contested_factor:.2f}")
            st.markdown(f"**{bi('Supporting evidence')}**")
            for f in a.supporting:
                show_finding(f)
            if not a.supporting:
                st.caption(with_ar("No supporting rule matched."))
            st.markdown(f"**{bi('Refuting evidence')}**")
            for f in a.refuting:
                show_finding(f)
            if not a.refuting:
                st.caption(with_ar("No refuting rule matched."))
            if a.missing:
                st.markdown(f"**{bi('Missing evidence')}**")
                for f in a.missing:
                    st.markdown(f"- {f.title} {gray(ar(f.title))}: {f.detail}")
            st.markdown(f"**{bi('Recommended actions if confirmed')}**")
            st.markdown("\n".join(f"- {x} {gray(ar(x))}" for x in a.recommended_actions) or "—")

    st.subheader(bi("Contradictions"))
    if not r.contradictions:
        st.success(with_ar("No contradictions detected."))
    for f in r.contradictions:
        with st.container(border=True, key=f"pp_contra_ev_{f.finding_id}"):
            show_finding(f)

    st.subheader(bi("Trace a record"))
    referenced = sorted({rid for f in r.all_findings() for rid in f.record_ids})
    by_id = {o.record_id: o for o in ctx.obs}
    if referenced:
        rid = st.selectbox(bi("Record ID used by a finding"), referenced,
                           key=f"trace_record_{ctx.sid}")
        rec = by_id.get(rid)
        if rec:
            st.dataframe(records_table([rec]), hide_index=True)
            used_by = r.findings_for_record(rid)
            st.markdown(f"**{bi('Used by')}:** "
                        + ", ".join(f"{f.finding_id} ({f.title})" for f in used_by))

    st.subheader(bi("All source records"))
    present = [s for s in SOURCE_TYPES if any(o.source_type == s for o in ctx.obs)]
    chosen = st.multiselect(bi("Record types"), present, format_func=source_plain,
                            default=[s for s in present if s != "sensor"], key="ev_types")
    st.dataframe(records_table([o for o in ctx.obs if o.source_type in chosen]), hide_index=True)

    st.subheader(bi("Save this investigation"))
    with st.form("save_investigation"):
        title = st.text_input(bi("Title"), value=f"P-301 trip investigation ({ctx.sid})")
        role = st.text_input(bi("Analyst role"), placeholder="e.g. Reliability engineer",
                             help=with_ar("Use a role, not a personal name - this demo is public."))
        notes = st.text_area(bi("Notes"), max_chars=2000)
        if st.form_submit_button(bi("Save investigation"), type="primary"):
            top = r.top
            ctx.store.save("investigation", ctx.sid, title, {
                "analyst_role": role, "notes": notes,
                "leading_hypothesis": top.name if top else None,
                "confidence": top.confidence if top else None,
                "analysis": r.to_dict(),
            })
            st.success(with_ar("Investigation saved to History. Remember to export history to keep it."))


STATUS_ICON = {"pass": ":green[:material/check_circle:]", "fail": ":red[:material/cancel:]",
               "info": ":gray[:material/arrow_right:]"}


def rtl(text: str, cls: str = "pp-rtl") -> None:
    """Arabic line rendered right-to-left so mixed IDs and numbers keep their order."""
    st.markdown(f'<div dir="rtl" class="{cls}">{html.escape(text)}</div>',
                unsafe_allow_html=True)


def _render_answer(ans: advisor.AdvisorAnswer) -> None:
    st.markdown(f"**{ans.title_en}**")
    rtl(ans.title_ar, "pp-rtl pp-rtl-title")
    for item in ans.items:
        icon = STATUS_ICON.get(item.status or "info", "")
        st.markdown(f"{icon} {item.en}")
        rtl(item.ar)
        if item.record_ids:
            st.caption(f"{bi('Source records')}: {ids_text(item.record_ids, 8)}")
    if ans.note_en:
        st.caption(ans.note_en)
        rtl(ans.note_ar, "pp-rtl pp-rtl-note")


def page_advisor(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["Advisor"], "Engineering advisor",
                "Rule-based assistant: every answer comes from this investigation's evidence "
                "and What If simulations. No external AI.")
    chat = session_get("advisor_chat", ctx.sid) or []

    st.markdown(f"**{bi('Suggested questions')}**")
    cols = st.columns(len(advisor.SUGGESTED))
    asked = None
    for col, (en, ar_text, intent) in zip(cols, advisor.SUGGESTED):
        if col.button(f"{en} :small[:gray[{ar_text}]]", key=f"adv_{intent}"):
            asked = en
    typed = st.chat_input("Ask about this investigation · اسأل عن هذا التحقيق", key="adv_input")
    if typed:
        asked = typed.strip()[:300]
    if asked:
        ans = advisor.answer(asked, ctx.obs, ctx.cfg, ctx.result, ctx.costs)
        chat = chat + [(asked, ans)]
        st.session_state["advisor_chat"] = (ctx.sid, chat)

    if not chat:
        st.info(with_ar("Ask a question about this investigation, then use the suggested "
                        "questions or type your own."))
        return
    for q, ans in chat:
        with st.chat_message("user", avatar=":material/engineering:"):
            st.markdown(q)
        with st.chat_message("assistant", avatar=":material/psychology:"):
            _render_answer(ans)
    if st.button(bi("Clear conversation"), key="adv_clear"):
        st.session_state.pop("advisor_chat", None)
        st.rerun()


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
    page_header(PAGE_ICONS["What If"], "What If simulations",
                "Changes are applied to a copy of the data. Original observations are never "
                "modified - each run proves this with a fingerprint check.")

    presets = _whatif_presets(ctx.sid)
    choice = st.selectbox(bi("Start from a preset"), ["Custom"] + list(presets),
                          format_func=bi_plain, key="wi_preset")
    changes: list[whatif.WhatIfChange] = []

    if choice != "Custom":
        changes = presets[choice]
        st.markdown(f"**{bi('Changes')}:** " + "; ".join(c.describe() for c in changes))
    else:
        present = [s for s in SOURCE_TYPES if any(o.source_type == s for o in ctx.obs)]
        excl = st.multiselect(bi("Ignore these record types"), present,
                              format_func=source_plain, key="wi_excl")
        for s in excl:
            changes.append(whatif.WhatIfChange("exclude_source", {"source_type": s}))

        valued = [o for o in ctx.obs if o.value is not None]
        if st.checkbox(bi("Override one record's value"), key="wi_ovr_on"):
            non_sensor = [o.record_id for o in valued if o.source_type != "sensor"]
            ids = non_sensor + [o.record_id for o in valued if o.source_type == "sensor"]
            rid = st.selectbox(bi("Record"), ids, key=f"wi_ovr_id_{ctx.sid}")
            current = next(o for o in valued if o.record_id == rid)
            st.caption(f"Current value · القيمة الحالية: {current.value:g} {current.unit} · {current.text}")
            val = st.number_input(bi("New value"), value=float(current.value),
                                  key=f"wi_ovr_val_{ctx.sid}_{rid}")
            changes.append(whatif.WhatIfChange("override_value", {"record_id": rid, "value": val}))

        if st.checkbox(bi("Scale a sensor parameter"), key="wi_scale_on"):
            params = sorted({o.parameter for o in ctx.obs if o.source_type == "sensor"})
            p = st.selectbox(bi("Parameter"), params,
                             format_func=lambda x: bi_plain(PARAM_LABELS.get(x, x)),
                             key="wi_scale_p")
            factor = st.slider(bi("Multiply all readings by"), 0.5, 1.5, 1.0, 0.05,
                               key="wi_scale_f")
            changes.append(whatif.WhatIfChange("scale_parameter", {"parameter": p, "factor": factor}))

        if st.checkbox(bi("Add hypothetical evidence"), key="wi_add_on"):
            tpls = whatif.EVIDENCE_TEMPLATES
            p = st.selectbox(bi("Evidence"), list(tpls),
                             format_func=lambda x: bi_plain(tpls[x]["label"]), key="wi_add_p")
            params = {"parameter": p}
            if tpls[p]["default"] is not None:
                params["value"] = st.number_input(bi("Value"), value=float(tpls[p]["default"]),
                                                  key="wi_add_v")
            changes.append(whatif.WhatIfChange("add_record", params))

    if st.button(bi("Run simulation"), type="primary", disabled=not changes, key="wi_run"):
        try:
            res = whatif.run_whatif(ctx.obs, ctx.cfg, changes)
            st.session_state["whatif_result"] = (ctx.sid, res)
        except ValueError as exc:
            st.error(f"Could not run the simulation · تعذّر تشغيل المحاكاة: {exc}")

    res = session_get("whatif_result", ctx.sid)
    if res is None:
        st.info(with_ar("Choose a preset or build custom changes, then run the simulation."))
        return

    st.divider()
    bt, stp = res.baseline.top, res.scenario.top
    summary_ar = ""
    if bt and stp:
        summary_ar = (f"الفرضية الأقوى لم تتغير: {ar(stp.name)} ({bt.confidence:.0%} ← {stp.confidence:.0%})"
                      if bt.hypothesis_id == stp.hypothesis_id else
                      f"الفرضية الأقوى تغيرت من {ar(bt.name)} ({bt.confidence:.0%}) "
                      f"إلى {ar(stp.name)} ({stp.confidence:.0%})")
    st.success(f"{res.summary()}  \n{gray(summary_ar)}")
    st.markdown(f"**{bi('Applied')}:** " + "; ".join(c.describe() for c in res.changes))
    ok = res.originals_unchanged and whatif.fingerprint(ctx.store.observations(ctx.sid)) \
        == res.fingerprint_before
    f1, f2 = st.columns(2)
    f1.metric(bi("Original data fingerprint (before → after)"),
              f"{res.fingerprint_before[:8]} → {res.fingerprint_after[:8]}")
    if ok:
        f2.success(":material/verified: " + with_ar("Original observations unchanged (memory and database checked)."))
    else:
        f2.error("Original observations changed - please report this bug. "
                 "البيانات الأصلية تغيرت، يرجى الإبلاغ عن هذا الخطأ.")

    rows = res.comparison()
    st.plotly_chart(comparison_chart(rows), key="wi_chart")
    st.dataframe([{"Hypothesis · الفرضية": bi_plain(x["hypothesis"]),
                   "Baseline · الأصل": pct(x["baseline_confidence"]),
                   "What If · ماذا لو": pct(x["scenario_confidence"]),
                   "Change · التغيير": f"{x['delta']:+.0%}",
                   "Rank · الترتيب": f"{x['baseline_rank']} → {x['scenario_rank']}"}
                  for x in rows], hide_index=True)
    sc = res.set_changes()
    cols = st.columns(4)
    for col, (k, label) in zip(cols, [("contradictions_resolved", "Contradictions resolved"),
                                      ("contradictions_new", "New contradictions"),
                                      ("missing_resolved", "Evidence gaps closed"),
                                      ("missing_new", "New evidence gaps")]):
        col.metric(bi(label), len(sc[k]))
        if sc[k]:
            col.caption(", ".join(sc[k]))

    if st.button(bi("Save this run to History"), key="wi_save"):
        ctx.store.save("whatif", ctx.sid, res.summary(), res.to_dict())
        st.success(with_ar("What If run saved."))


def _show_score(score: blind_test.BlindTestScore, ctx: Ctx, key: str) -> None:
    m1, m2 = st.columns(2)
    m1.metric(bi("Blind Test score"), f"{score.total:g} / 100")
    m2.metric(bi("Grade"), score.grade, ar(score.grade), delta_color="off")
    st.progress(min(1.0, score.total / 100))
    names_ar = {"Root cause": "السبب الجذري", "Contradictions": "التناقضات",
                "Missing evidence": "الأدلة المفقودة"}
    st.dataframe([{"Component · العنصر": f"{c.name} · {names_ar.get(c.name, '')}",
                   "Points · النقاط": f"{c.points:g} / {c.max_points:g}",
                   "Detail · التفاصيل": c.detail} for c in score.components], hide_index=True)
    with st.expander(bi("Reveal reference answers")):
        ref = score.reference
        root = ctx.cfg.hypothesis(ref.root_cause).name
        st.markdown(f"**{bi('Root cause')}:** {root} {gray(ar(root))}")
        st.markdown(f"**{bi('Expected contradictions')}:** "
                    f"{', '.join(sorted(ref.expected_contradictions))}")
        st.markdown(f"**{bi('Expected missing evidence')}:** "
                    f"{', '.join(sorted(ref.expected_missing))}")
        st.markdown(f"**{bi('Rationale')}:** {ref.rationale}")
        for c in score.components[1:]:
            if c.false_positives or c.false_negatives:
                st.caption(f"{c.name}: extra {c.false_positives or '—'}, "
                           f"missed {c.false_negatives or '—'}")
    if st.button(bi("Save result to History"), key=f"bt_save_{key}"):
        ctx.store.save("blind_test", ctx.sid,
                       f"Blind Test ({score.submission.source}): {score.total:g}/100",
                       score.to_dict())
        st.success(with_ar("Blind Test result saved."))


def page_blind_test(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["Blind Test"], "Blind Test",
                "Scores an analysis against reference answers stored separately in "
                "data/reference_answers.json. The evidence engine never reads that file "
                "(a unit test enforces this).")
    st.warning(with_ar("Transparency note: this repository is public, so anyone can read the "
                       "reference answers. The separation shows the method; it is not a secret."))
    try:
        ref = blind_test.load_reference(ctx.sid)
    except KeyError:
        st.info("No reference answers for this scenario · لا توجد إجابات مرجعية لهذا السيناريو.")
        return

    tab_engine, tab_analyst = st.tabs([bi("Score the engine"), bi("Score your own analysis")])
    with tab_engine:
        st.markdown(with_ar("Runs the engine's current analysis through the scorer."))
        if st.button(bi("Run Blind Test"), type="primary", key="bt_run"):
            sub = blind_test.submission_from_analysis(ctx.result)
            st.session_state["bt_engine"] = (ctx.sid, blind_test.score(sub, ref))
        score = session_get("bt_engine", ctx.sid)
        if score:
            _show_score(score, ctx, "engine")

    with tab_analyst:
        st.markdown(with_ar("Make your own call from the Evidence page, then see how you score."))
        hyps = [h.id for h in ctx.cfg.hypotheses]
        names = {h.id: bi_plain(h.name) for h in ctx.cfg.hypotheses}
        claims = [o for o in ctx.obs if o.source_type in ("operator_log", "inspection")]
        catalogue = ctx.cfg.required_evidence_catalogue()
        with st.form("analyst_bt"):
            first = st.selectbox(bi("Most likely root cause"), hyps, format_func=names.get)
            second = st.selectbox(bi("Second most likely"), hyps, index=1, format_func=names.get)
            contra = st.multiselect(
                bi("Records involved in contradictions"), [o.record_id for o in claims],
                format_func=lambda rid: f"{rid} — "
                + next(o.text for o in claims if o.record_id == rid)[:60])
            miss = st.multiselect(bi("Evidence that is missing or out of date"), list(catalogue),
                                  format_func=lambda k: bi_plain(catalogue[k]))
            submitted = st.form_submit_button(bi("Score my analysis"), type="primary")
        if submitted:
            ranking = [first] + ([second] if second != first else [])
            sub = blind_test.Submission(ranking, set(contra), set(miss), source="analyst")
            st.session_state["bt_analyst"] = (ctx.sid, blind_test.score(sub, ref))
        score = session_get("bt_analyst", ctx.sid)
        if score:
            _show_score(score, ctx, "analyst")


def page_cost(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["Cost"], "Cost impact simulator",
                "Low / base / high totals with every assumption and formula visible. "
                "All figures are illustrative synthetic values.")
    hyps = [a.hypothesis_id for a in ctx.result.assessments]
    names = {a.hypothesis_id: f"{bi_plain(a.name)} ({pct(a.confidence)})"
             for a in ctx.result.assessments}
    hid = st.selectbox(bi("Cost the repair for"), hyps, format_func=names.get, key="cost_h")

    base_assumptions = ctx.costs
    prof = base_assumptions["profiles"][hid]
    overrides: dict[str, dict[str, float]] = {}
    with st.expander(bi("Adjust assumptions (this session only)")):
        fields = [("downtime_hours", "Downtime (hours)", prof["downtime_hours"]),
                  ("labour_hours", "Labour (hours)", prof["labour_hours"]),
                  ("parts", "Parts (£)", prof["parts"]),
                  ("lost_margin_per_hour", "Lost margin (£/hour)",
                   base_assumptions["lost_margin_per_hour"]),
                  ("labour_rate_per_hour", "Labour rate (£/hour)",
                   base_assumptions["labour_rate_per_hour"])]
        for key, label, rng in fields:
            st.markdown(f"**{bi(label)}**")
            cols = st.columns(3)
            overrides[key] = {
                case: cols[i].number_input(f"{case.title()} :small[:gray[{CASE_AR[case]}]]",
                                           min_value=0.0, value=float(rng[case]),
                                           key=f"cost_{hid}_{key}_{case}")
                for i, case in enumerate(cost_model.CASES)
            }
    try:
        assumptions = cost_model.with_overrides(base_assumptions, hid, overrides)
    except ConfigError as exc:
        st.error(f"Invalid assumptions · افتراضات غير صحيحة: {exc}. Using the default values instead.")
        assumptions = base_assumptions

    est = cost_model.estimate(hid, assumptions)
    t = est.totals
    st.markdown(f"**{bi('Repair scope')}:** {est.description}")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Low :small[:gray[{CASE_AR['low']}]]", money(t["low"], ctx))
    c2.metric(f"Base :small[:gray[{CASE_AR['base']}]]", money(t["base"], ctx))
    c3.metric(f"High :small[:gray[{CASE_AR['high']}]]", money(t["high"], ctx))

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(cost_chart(est), key="cost_chart")
    with right:
        st.markdown(f"**{bi('Breakdown')}**")
        st.dataframe([{"Component · العنصر": bi_plain(line.component),
                       "Formula · المعادلة": line.formula,
                       "Low · منخفض": money(line.low, ctx), "Base · أساسي": money(line.base, ctx),
                       "High · مرتفع": money(line.high, ctx)} for line in est.lines],
                     hide_index=True)
        st.markdown(f"**{bi('Inputs used')}**")
        st.dataframe([{"Input · المدخل": k.replace("_", " "), "Low · منخفض": v["low"],
                       "Base · أساسي": v["base"], "High · مرتفع": v["high"]}
                      for k, v in est.inputs.items()], hide_index=True)

    st.subheader(bi("Confidence-weighted base cost"))
    w = cost_model.weighted_estimate(ctx.result.assessments, assumptions)
    if w is None:
        st.info("All hypotheses have zero confidence, so no weighted estimate is possible. "
                "كل الفرضيات ثقتها صفر، فلا يمكن حساب تقدير موزون.")
    else:
        st.metric(bi("Expected base cost across hypotheses"), money(w["value"], ctx))
        st.dataframe([{"Hypothesis · الفرضية": bi_plain(x["hypothesis"]),
                       "Confidence · الثقة": pct(x["confidence"]),
                       "Weight · الوزن": pct(x["weight"]),
                       "Base total · الإجمالي الأساسي": money(x["base_total"], ctx),
                       "Contribution · المساهمة": money(x["contribution"], ctx)}
                      for x in w["rows"]], hide_index=True)
        st.caption("Weight = hypothesis confidence ÷ sum of all confidences. "
                   "Expected cost = Σ weight × base total.  \n"
                   + gray("الوزن = ثقة الفرضية ÷ مجموع الثقة. التكلفة المتوقعة = مجموع (الوزن × الإجمالي الأساسي)."))


def page_history(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["History"], "Investigation history")
    st.warning(PERSISTENCE_FULL)

    entries_all = ctx.store.list_history()
    e1, e2 = st.columns(2)
    with e1:
        st.markdown(f"**{bi('Export history')}**")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        st.download_button(f":material/download: Download history · تنزيل السجل ({len(entries_all)} entries, JSON)",
                           data=ctx.store.export_history_json(),
                           file_name=f"plantproof_history_{stamp}.json",
                           mime="application/json", key="hist_export")
    with e2:
        st.markdown(f"**{bi('Import history')}**")
        upload = st.file_uploader("PlantProof history JSON :small[:gray[ملف السجل]]", type=["json"],
                                  key="hist_upload")
        if upload is not None and st.button(bi("Import file"), key="hist_import"):
            try:
                res = ctx.store.import_history(upload.getvalue())
                st.success(f"Imported {res['inserted']} entries ({res['skipped']} already present). "
                           f"{gray('تم الاستيراد.')}")
            except ValueError as exc:
                st.error(str(exc))

    show_all = st.checkbox(bi("Show all scenarios"), key="hist_all")
    labels = {"investigation": "Investigations", "whatif": "What If runs",
              "blind_test": "Blind Tests", "handover": "Handovers"}
    tabs = st.tabs([bi(v) for v in labels.values()])
    for tab, kind in zip(tabs, labels):
        with tab:
            items = ctx.store.list_history(kind, None if show_all else ctx.sid)
            if not items:
                st.caption(with_ar("Nothing saved yet."))
            for item in items:
                with st.expander(f"{item['title']} · {item['created_at']} · scenario "
                                 f"{item['scenario_id']}"):
                    p = item["payload"]
                    if kind == "investigation":
                        st.markdown(f"**{bi('Leading hypothesis')}:** {p.get('leading_hypothesis')} "
                                    f"({pct(p.get('confidence') or 0)})  \n"
                                    f"**{bi('Analyst role')}:** {p.get('analyst_role') or '—'}  \n"
                                    f"**{bi('Notes')}:** {p.get('notes') or '—'}")
                    elif kind == "whatif":
                        st.markdown(f"**{bi('Changes')}:** "
                                    f"{'; '.join(p.get('change_descriptions', []))}  \n"
                                    f"**Result :small[:gray[النتيجة]]:** {p.get('summary')}")
                    elif kind == "blind_test":
                        st.markdown(f"**Score :small[:gray[النتيجة]]:** {p.get('total')} / 100 "
                                    f"({p.get('grade')})")
                    elif kind == "handover":
                        st.markdown(p.get("markdown", ""))
                    st.json(p, expanded=False)
                    if st.button(bi("Delete"), key=f"del_{item['uid']}"):
                        ctx.store.delete(item["uid"])
                        st.rerun()

    with st.expander(bi("Danger zone")):
        confirm = st.checkbox(bi("I understand this cannot be undone"), key="hist_confirm")
        d1, d2 = st.columns(2)
        if d1.button(bi("Clear all history"), disabled=not confirm, key="hist_clear"):
            n = ctx.store.clear_history()
            st.success(f"Deleted {n} entries · حُذفت {n} عناصر.")
        if d2.button(bi("Reset demo observations"), disabled=not confirm, key="hist_reset"):
            n = ctx.store.reset_observations()
            for k in ("whatif_result", "bt_engine", "bt_analyst", "handover_doc"):
                st.session_state.pop(k, None)
            st.success(f"Re-seeded {n} demo records. History kept. "
                       f"{gray('أُعيد تحميل بيانات العرض، والسجل محفوظ.')}")


def _bilingual_report(md: str) -> str:
    """Add grey Arabic to the report's section headings (on-screen preview only)."""
    for h in HANDOVER_HEADINGS:
        md = md.replace(f"\n## {h}\n", f"\n## {h} :small[:gray[{ar(h)}]]\n")
    return md


def page_handover(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["Handover"], "Shift handover",
                "Built from engine findings and your notes - no AI text generation. "
                "Use role names, not personal names: this demo is public.")
    last_whatif = session_get("whatif_result", ctx.sid)
    with st.form("handover_form"):
        shift = st.selectbox(bi("Shift"), ["Day shift (06:00–18:00)", "Night shift (18:00–06:00)"],
                             format_func=bi_plain)
        c1, c2 = st.columns(2)
        outgoing = c1.text_input(bi("Outgoing (role)"), placeholder="e.g. Day shift lead")
        incoming = c2.text_input(bi("Incoming (role)"), placeholder="e.g. Night shift lead")
        include_cost = st.checkbox(bi("Include cost impact for the leading hypothesis"), value=True)
        include_wi = st.checkbox(bi("Include latest What If result"),
                                 value=last_whatif is not None, disabled=last_whatif is None)
        notes = st.text_area(bi("Notes for the incoming shift"), max_chars=handover.MAX_NOTES)
        go_ = st.form_submit_button(bi("Generate handover"), type="primary")
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
            st.markdown(_bilingual_report(md))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        d1, d2, d3 = st.columns(3)
        d1.download_button(f":material/download: {bi('Markdown report')}", md,
                           file_name=f"handover_{ctx.sid}_{stamp}.md",
                           mime="text/markdown", key="ho_md")
        d2.download_button(f":material/download: {bi('JSON data')}", doc.to_json(),
                           file_name=f"handover_{ctx.sid}_{stamp}.json",
                           mime="application/json", key="ho_json")
        if d3.button(bi("Save to History"), key="ho_save"):
            ctx.store.save("handover", ctx.sid, f"Handover · {doc.shift}",
                           doc.to_dict() | {"markdown": md})
            st.success(with_ar("Handover saved."))

    previous = ctx.store.list_history("handover", ctx.sid)
    if previous:
        st.subheader(bi("Previous handovers"))
        for item in previous[:10]:
            with st.expander(f"{item['title']} · {item['created_at']}"):
                st.markdown(_bilingual_report(item["payload"].get("markdown", "")))


# ---------------------------------------------------------------------------- main
def main() -> None:
    try:
        store, cfg, costs, index = get_store(), get_config(), get_costs(), get_index()
    except (ConfigError, OSError, ValueError) as exc:
        st.error(f"PlantProof AI could not start: {exc}")
        st.stop()
        return

    inject_theme()
    sidebar_brand()
    st.sidebar.caption(with_ar("Evidence-first investigations for plant incidents"))
    page = st.sidebar.radio(bi("Navigate"), PAGES, key="page",
                            format_func=lambda p: f"{PAGE_ICONS[p]} {bi(p)}")
    titles = {s["id"]: s["title"] for s in index}
    sid = st.sidebar.selectbox(bi("Scenario"), list(titles),
                               format_func=lambda k: bi_plain(titles[k]), key="scenario")
    st.sidebar.divider()
    st.sidebar.warning(with_ar(PERSISTENCE_SHORT), icon=":material/save:")
    st.sidebar.caption(f"v{__version__} · "
                       + with_ar("Synthetic demo data only · Rule-based analysis, "
                                 "no external AI or API keys."))
    st.sidebar.caption(f"{DISCLAIMER}  \n{gray(DISCLAIMER_AR)}")

    meta = next(s for s in index if s["id"] == sid)
    obs = store.observations(sid)
    if not obs:
        store.reset_observations()
        obs = store.observations(sid)
    ctx = Ctx(store, cfg, costs, meta, sid, obs, analyse(obs, cfg, sid))

    {"Overview": page_overview, "Evidence": page_evidence, "Advisor": page_advisor,
     "What If": page_whatif,
     "Blind Test": page_blind_test, "Cost": page_cost, "History": page_history,
     "Handover": page_handover}[page](ctx)


main()
