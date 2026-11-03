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


def _drop_stale_plantproof_modules() -> None:
    """After a redeploy, Streamlit re-runs app.py but can keep old plantproof modules in
    memory, so new functions look missing. If the package source changed, forget the old
    modules and caches so the imports below load the new code."""
    import hashlib
    import sys

    src = Path(__file__).parent / "plantproof"
    digest = hashlib.sha256(b"".join(f.read_bytes() for f in sorted(src.glob("*.py")))).hexdigest()
    pkg = sys.modules.get("plantproof")
    if pkg is not None and getattr(pkg, "_source_digest", None) == digest:
        return
    for name in [m for m in sys.modules if m == "plantproof" or m.startswith("plantproof.")]:
        del sys.modules[name]
    st.cache_resource.clear()
    st.cache_data.clear()
    import plantproof
    plantproof._source_digest = digest


_drop_stale_plantproof_modules()

from plantproof import (__version__, advisor, blind_test, cost_model, early_warning, fact_check,
                        handover, whatif)
from plantproof.domain import (SOURCE_TYPES, AnalysisResult, ConfigError, EngineConfig,
                               Finding, Observation, load_engine_config,
                               load_scenario_index)
from plantproof.evidence_engine import analyse
from plantproof.storage import Store
from plantproof.translations import ar, bi, bi_plain

st.set_page_config(page_title="PlantProof AI", page_icon=":material/hub:", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = ("Overview", "AI Early Warning", "Evidence", "AI Fact Check", "Live Sensor", "What If",
         "Blind Test", "Cost", "History", "Handover")
ADVISOR = "Advisor"   # opened from its own highlighted button, not from the page list
OPS = "Operations Room"   # also opened from its own red button (and by the live alarm)
PAGE_ICONS = {"Overview": ":material/dashboard:", "Evidence": ":material/manage_search:",
              "Advisor": ":material/psychology:",
              "What If": ":material/science:", "Blind Test": ":material/fact_check:",
              "Cost": ":material/payments:", "History": ":material/history:",
              "Handover": ":material/sync_alt:", "AI Early Warning": ":material/monitor_heart:",
              "AI Fact Check": ":material/verified:", "Live Sensor": ":material/sensors:",
              "Operations Room": ":material/crisis_alert:"}
LINKEDIN_URL = "https://www.linkedin.com/company/146908832/"   # Yaqen AI public company page
APP_URL = "https://plantproof-ai.streamlit.app"
PARAM_LABELS = {"vibration_mm_s": "Vibration (mm/s)", "bearing_temp_c": "Bearing temp (°C)",
                "seal_pot_level_pct": "Seal pot level (%)",
                "suction_pressure_bar": "Suction pressure (bar)",
                "discharge_pressure_bar": "Discharge pressure (bar)",
                "flow_m3h": "Flow (m³/h)",
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
    store.sync_demo_data()
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
/* ---- AI Advisor: its own copper button, in the sidebar and floating ---- */
.st-key-pp_advisor_side button, .st-key-pp_fab button {{
  background: linear-gradient(135deg, #B8743A 0%, #8F5326 100%) !important;
  color: #FFFFFF !important; border: none !important; font-weight: 700 !important;
  box-shadow: 0 6px 16px rgba(143,83,38,0.35) !important;
}}
.st-key-pp_advisor_side button {{ width: 100%; padding: 10px 14px !important; margin: 6px 0 10px; }}
.st-key-pp_advisor_side button:hover, .st-key-pp_fab button:hover {{ filter: brightness(1.08); }}
.st-key-pp_advisor_side button *, .st-key-pp_fab button * {{ color: #FFFFFF !important; }}
.st-key-pp_fab {{
  position: fixed; right: 28px; bottom: 84px; z-index: 1000; width: auto !important;
}}
.st-key-pp_fab button {{ border-radius: 999px !important; padding: 12px 20px !important; }}
.pp-rtl {{ direction: rtl; text-align: right; unicode-bidi: isolate; color: #6B7B7A;
  font-size: .86rem; line-height: 1.6; margin: -6px 0 8px 0; }}
.pp-rtl-title {{ font-size: .95rem; font-weight: 600; margin-top: -10px; }}
.pp-rtl-note {{ font-size: .78rem; }}
/* ---- clear, solid cards, inputs and buttons (readable on top of the background) ---- */
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stExpander"],
[data-testid="stTabs"], [data-testid="stForm"] {{
  background: #FFFFFF !important; border: 1.5px solid #9DB5B0 !important;
  box-shadow: 0 4px 14px rgba(11,46,45,0.16) !important;
}}
[data-testid="stAlert"] {{ border: 1.5px solid #9DB5B0; border-radius: 10px; }}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
[data-baseweb="base-input"], [data-testid="stNumberInputContainer"] {{
  background: #FFFFFF !important; border: 1.5px solid #6F8F8A !important; border-radius: 8px !important;
}}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="base-input"] input {{
  background: #FFFFFF !important; color: #0B2E2D !important;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {{ border-color: {PETROL} !important;
  box-shadow: 0 0 0 2px rgba(20,90,85,0.25) !important; }}
[data-testid="stCheckbox"] label span:first-child {{ border: 1.5px solid #6F8F8A; }}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
  background: #FFFFFF !important; border: 1.5px solid {PETROL} !important; color: #0B2E2D !important;
  font-weight: 600 !important;
}}
[data-testid="stBaseButton-secondary"]:hover {{ background: #E6F2EF !important; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  border: 1.5px solid #0B2E2D !important; font-weight: 600 !important;
  box-shadow: 0 3px 8px rgba(11,46,45,0.25) !important;
}}
/* hide the GitHub / Fork / edit icons Streamlit Cloud adds to the top bar */
[data-testid="stToolbarActions"], .stAppDeployButton, [data-testid="stAppDeployButton"] {{
  display: none !important; }}
[class*="st-key-pp_fc_ok"] {{ border-left: 6px solid #1E7B4F !important; background: #F1FAF5 !important; }}
[class*="st-key-pp_fc_bad"] {{ border-left: 6px solid {ALERT} !important; background: #FDEDEB !important; }}
[class*="st-key-pp_fc_none"] {{ border-left: 6px solid #8A9B97 !important; background: #F4F6F6 !important; }}
[data-testid="stMarkdownContainer"]:has(.pp-sign) {{ background: transparent !important; padding: 0 !important; }}
.pp-sign {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin: 40px 0 10px;
  color: #0B2E2D; opacity: .92; }}
.pp-sign-mark {{ width: 40px; height: 40px; flex: none; filter: drop-shadow(0 0 6px rgba(77,163,131,.4)); }}
.pp-sign-t {{ font-size: .95rem; letter-spacing: .3px; font-weight: 500;
  background: linear-gradient(100deg, currentColor 0%, currentColor 40%, #4DA383 50%, currentColor 60%, currentColor 100%);
  background-size: 250% 100%; -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; animation: ppshine 3.5s linear infinite; }}
.pp-sign-t b {{ font-weight: 800; }}
.pp-sign-ar {{ font-size: .74rem; opacity: .65; direction: rtl; text-align: left; }}
.pp-sign-li {{ display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border-radius: 6px; border: 1.5px solid currentColor; color: inherit !important; font-weight: 800;
  font-size: .85rem; text-decoration: none !important; opacity: .8; transition: all .2s; }}
.pp-sign-li:hover {{ opacity: 1; color: #0A66C2 !important; border-color: #0A66C2; }}
@keyframes ppshine {{ from {{ background-position: 100% 0; }} to {{ background-position: -150% 0; }} }}
.st-key-pp_alarm_go {{ display: none !important; }}
.st-key-pp_ops_side button {{ width: 100%; padding: 12px 14px !important; margin: 6px 0 2px;
  background: linear-gradient(135deg, #D0342C 0%, #7A160F 100%) !important; border: 1px solid #FF8A7A !important;
  box-shadow: 0 6px 18px rgba(180,35,24,.45) !important; font-weight: 800 !important; letter-spacing: .3px; }}
.st-key-pp_ops_side button * {{ color: #FFFFFF !important; }}
.st-key-pp_ops_side button:hover {{ filter: brightness(1.1); }}
.st-key-pp_ops_alarm {{ background: #FDEDEB !important; border: 2px solid {ALERT} !important;
  border-left: 8px solid {ALERT} !important; }}
.st-key-pp_ops_alarm h3 {{ color: {ALERT} !important; }}
.st-key-pp_ops_top {{ border-left: 6px solid {PETROL} !important; background: #F1F8F6 !important; }}
.st-key-pp_keypoints {{ border-left: 6px solid {COPPER} !important; }}
.pp-name {{ font-size: 1.25rem; font-weight: 700; color: #0B2E2D; letter-spacing: .2px; }}
.pp-name span {{ color: {COPPER}; }}
</style>
""", unsafe_allow_html=True)


def report_html(doc: handover.Handover) -> str:
    """Branded HTML handover report with the project logo embedded."""
    logo = (ASSETS / "logo.svg").read_text(encoding="utf-8")
    logo = logo[logo.index("<svg"):]
    return doc.to_html(logo_svg=logo)


def open_advisor() -> None:
    st.session_state["view"] = ADVISOR
    st.session_state["page"] = None   # clear the list so any page click leaves this view


def close_advisor() -> None:
    st.session_state["view"] = None


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
def headlines(findings, key: str, empty: str) -> None:
    """One short line per finding; the full detail opens on click."""
    if not findings:
        st.success(with_ar(empty))
        return
    for f in findings:
        with st.expander(f"{f.title} {gray(ar(f.title))}"):
            st.markdown(f.detail)
            st.caption(f"{bi('Source records')}: {ids_text(f.record_ids)}")


def why_line(a) -> tuple[str, str]:
    """The strongest supporting reason for a hypothesis, as one short line."""
    if a.supporting:
        f = a.supporting[0]
        return f.title, ar(f.title)
    if a.refuting:
        f = a.refuting[0]
        return f"Against: {f.title}", f"ضدها: {ar(f.title) or f.title}"
    return "No matching evidence", "لا توجد أدلة مطابقة"


def page_overview(ctx: Ctx) -> None:
    r, top = ctx.result, ctx.result.top
    st.title(f":material/factory: {bi(ctx.meta['asset_name'])}")
    st.caption(f"{bi(ctx.meta['title'])} · {bi('analysis window')} "
               f"{r.window_start.replace('T', ' ')} → {r.window_end.replace('T', ' ')}")
    st.info(with_ar(ctx.meta["summary"]))

    c1, c2, c3, c4 = st.columns(4)
    with c1.container(key="pp_kpi_records"):
        st.metric(bi("Records analysed"), r.record_count)
    with c2.container(key="pp_kpi_contra"):
        st.metric(bi("Contradictions"), len(r.contradictions))
    with c3.container(key="pp_kpi_miss"):
        st.metric(bi("Missing evidence"), len(r.missing))
    if top:
        with c4.container(key="pp_kpi_lead"):
            st.metric(bi("Leading hypothesis"), top.name,
                      f"{pct(top.confidence)} · {ar(top.name)}", delta_color="off")

    # ---- key points: one line each
    ew = early_warning.detect(list(ctx.obs), ctx.cfg.limits)
    pts = []
    if top:
        en, ar_ = why_line(top)
        pts.append((f"**Most likely cause:** {top.name} ({pct(top.confidence)}), mainly because: {en}.",
                    f"السبب الأرجح: {ar(top.name)} ({pct(top.confidence)})، والسبب الأهم: {ar_}."))
    if ew and ew.warned_before_alarm:
        pts.append((f"**AI early warning:** unusual behaviour flagged {ew.lead_hours:g} h before the first alarm.",
                    f"الإنذار المبكر: النموذج لاحظ سلوكًا غير طبيعي قبل أول إنذار بـ {ew.lead_hours:g} ساعة."))
    if r.contradictions:
        pts.append((f"**{len(r.contradictions)} records disagree** with each other: resolve before restart.",
                    f"{len(r.contradictions)} سجلات متناقضة: لازم تُحل قبل إعادة التشغيل."))
    if r.missing:
        pts.append((f"**{len(r.missing)} checks are missing:** "
                    + ", ".join(f.title.replace("Missing: ", "") for f in r.missing) + ".",
                    f"{len(r.missing)} فحوصات ناقصة."))
    if top:
        t = cost_model.estimate(top.hypothesis_id, ctx.costs).totals
        pts.append((f"**Cost if confirmed:** about {money(t['base'], ctx)} "
                    f"(range {money(t['low'], ctx)} – {money(t['high'], ctx)}).",
                    f"التكلفة إذا تأكد السبب: حوالي {money(t['base'], ctx)}."))
    with st.container(border=True, key="pp_keypoints"):
        st.markdown(f"#### :material/bolt: {bi('Key points')}")
        st.markdown("\n".join(f"- {en}  \n  {gray(ar_)}" for en, ar_ in pts))

    # ---- details on demand
    a, b = st.columns(2)
    with a:
        st.markdown(f"**:material/report: {bi('Contradictions')}** {gray('اضغط للتفاصيل')}")
        headlines(r.contradictions, "ov_c", "No contradictions detected.")
    with b:
        st.markdown(f"**:material/pending_actions: {bi('Missing evidence')}** {gray('اضغط للتفاصيل')}")
        headlines(r.missing, "ov_m", "All required evidence is present.")

    with st.expander(f":material/show_chart: {bi('Sensor trends')}"):
        highlight = {rid for c in r.contradictions for rid in c.record_ids}
        params = [p for p in PARAM_LABELS if any(o.parameter == p for o in ctx.obs)]
        tabs = st.tabs([bi(PARAM_LABELS[p]) for p in params])
        for tab, p in zip(tabs, params):
            with tab:
                st.plotly_chart(trend_chart(ctx.obs, p, ctx, highlight), key=f"trend_{p}")
    with st.expander(f":material/bar_chart: {bi('Hypothesis confidence')}"):
        st.plotly_chart(confidence_chart(r.assessments), key="overview_conf")
        st.caption(with_ar("Rule-based and explainable. See the Evidence page for the working."))


def page_evidence(ctx: Ctx) -> None:
    r = ctx.result
    page_header(PAGE_ICONS["Evidence"], "Evidence engine",
                "Every conclusion below links to the source record IDs it is based on.")

    st.subheader(bi("Hypothesis ranking"))
    st.caption(gray("كل فرضية بسطر واحد. اضغط عليها للتفاصيل."))

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
        why_en, why_ar = why_line(a)
        with st.expander(f"#{a.rank} {bi(a.name)} — **{pct(a.confidence)}** · {why_en} {gray(why_ar)}"):
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
    headlines(r.contradictions, "ev_c", "No contradictions detected.")

    with st.expander(f":material/search: {bi('Trace a record')}"):
        _trace_and_records(ctx)
    with st.expander(f":material/save: {bi('Save this investigation')}"):
        _save_investigation(ctx)


def _trace_and_records(ctx: Ctx) -> None:
    r = ctx.result
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

    st.markdown(f"**{bi('All source records')}**")
    present = [s for s in SOURCE_TYPES if any(o.source_type == s for o in ctx.obs)]
    chosen = st.multiselect(bi("Record types"), present, format_func=source_plain,
                            default=[s for s in present if s != "sensor"], key="ev_types")
    st.dataframe(records_table([o for o in ctx.obs if o.source_type in chosen]), hide_index=True)


def _save_investigation(ctx: Ctx) -> None:
    r = ctx.result
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
                "Ask anything about this investigation, in English or Arabic. Every answer is "
                "built from its records and cites their IDs. No external AI.")
    chat = session_get("advisor_chat", ctx.sid) or []
    # Drop answers created by an older version of the advisor (e.g. after a redeploy).
    chat = [(q, a) for q, a in chat if hasattr(a, "attachment") and hasattr(a, "items")]

    st.markdown(f"**{bi('Suggested questions')}**")
    cols = st.columns(len(advisor.SUGGESTED))
    asked = None
    for col, (en, ar_text, intent) in zip(cols, advisor.SUGGESTED):
        if col.button(f"{en} :small[:gray[{ar_text}]]", key=f"adv_{intent}"):
            asked = en
    st.markdown(f"**{bi('Or ask about anything in the records')}**")
    ex_cols = st.columns(len(advisor.EXAMPLES))
    for i, (col, (en, ar_text)) in enumerate(zip(ex_cols, advisor.EXAMPLES)):
        if col.button(f"{en} :small[:gray[{ar_text}]]", key=f"adv_ex_{i}"):
            asked = ar_text
    typed = st.chat_input("Ask anything, e.g. is the oil ok? · اسأل أي سؤال، مثل: هل الزيت سليم؟",
                          key="adv_input")
    if typed:
        asked = typed.strip()[:300]
    if asked:
        saved = ctx.store.list_history("handover", ctx.sid)
        ans = advisor.answer(asked, ctx.obs, ctx.cfg, ctx.result, ctx.costs, ctx.meta,
                             saved[0] if saved else None)
        chat = chat + [(asked, ans)]
        st.session_state["advisor_chat"] = (ctx.sid, chat)

    if not chat:
        st.info(with_ar("Ask a question about this investigation, then use the suggested "
                        "questions or type your own."))
        return
    for n, (q, ans) in enumerate(chat):
        with st.chat_message("user", avatar=":material/engineering:"):
            st.markdown(q)
        with st.chat_message("assistant", avatar=":material/psychology:"):
            _render_answer(ans)
            doc = getattr(ans, "attachment", None)  # answers saved before an update lack it
            if isinstance(doc, handover.Handover):
                md = doc.to_markdown()
                with st.expander(bi("Shift handover"), expanded=True):
                    st.markdown(_bilingual_report(md))
                h1, h2 = st.columns(2)
                if h1.button(bi("Save to History"), key=f"adv_ho_save_{n}"):
                    ctx.store.save("handover", ctx.sid, "Handover · Advisor",
                                   doc.to_dict() | {"markdown": md})
                    st.success(with_ar("Handover saved."))
                h2.download_button(f":material/download: {bi('Handover report')}",
                                   report_html(doc),
                                   file_name=f"handover_{ctx.sid}_advisor_{n}.html",
                                   mime="text/html", key=f"adv_ho_html_{n}")
    if st.button(bi("Clear conversation"), key="adv_clear"):
        st.session_state.pop("advisor_chat", None)
        st.rerun()


# ------------------------------------------------------------- AI early warning
def ew_chart(ew: early_warning.EarlyWarning) -> go.Figure:
    xs = [h.timestamp for h in ew.hours]
    fig = go.Figure(go.Scatter(
        x=xs, y=[h.score for h in ew.hours], mode="lines+markers", line=dict(color=PETROL, width=2.5),
        marker=dict(size=5, color=[ALERT if h.score > ew.threshold else PETROL for h in ew.hours]),
        name=bi_plain("Anomaly score"), hovertemplate="%{x}<br>%{y}<extra></extra>"))
    fig.add_hline(y=ew.threshold, line_dash="dash", line_color=COPPER,
                  annotation_text=f"Learned threshold · الحد المتعلَّم {ew.threshold:g}",
                  annotation_position="top left")
    fig.add_vrect(x0=xs[0], x1=xs[ew.train_hours - 1], fillcolor="#DDEFE9", opacity=0.5,
                  line_width=0)
    fig.add_annotation(x=xs[0], y=1, yref="paper", showarrow=False, xanchor="left",
                       text="Learning normal · تعلّم الطبيعي", font=dict(color=PETROL))
    if ew.first_warning:
        fig.add_vline(x=ew.first_warning.timestamp, line_color=COPPER, line_width=2)
        fig.add_annotation(x=ew.first_warning.timestamp, y=1, yref="paper", showarrow=False,
                           text="AI warning · إنذار مبكر", xanchor="right", font=dict(color=COPPER))
    if ew.first_alarm:
        fig.add_vline(x=ew.first_alarm[0], line_color=ALERT, line_width=2, line_dash="dot")
        fig.add_annotation(x=ew.first_alarm[0], y=0.9, yref="paper", showarrow=False,
                           text="First alarm · أول إنذار", xanchor="left", font=dict(color=ALERT))
    fig.update_layout(paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", height=360,
                      margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                      yaxis_title=bi_plain("Anomaly score"))
    return fig


def _driver_text(drivers) -> tuple[str, str]:
    en, ar_ = [], []
    for p, z in drivers:
        lab = PARAM_LABELS.get(p, p).split(" (")[0]
        word, word_ar = ("above", "أعلى") if z > 0 else ("below", "أقل")
        en.append(f"{lab} {abs(z):g}× its normal spread {word} normal")
        ar_.append(f"{ar(PARAM_LABELS.get(p, p)) or lab} {word_ar} من الطبيعي بـ {abs(z):g} ضعف تذبذبه المعتاد")
    return "; ".join(en), "، ".join(ar_)


def page_early_warning(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["AI Early Warning"], "AI Early Warning",
                "A machine-learning model learns how this pump normally behaves, then flags "
                "unusual hours before any alarm limit is crossed. It runs inside the app: no "
                "external AI service.")
    ew = early_warning.detect(list(ctx.obs), ctx.cfg.limits)
    if ew is None:
        st.warning(with_ar("Not enough hourly sensor data to train the model."))
        return
    fw, fa = ew.first_warning, ew.first_alarm
    c1, c2, c3 = st.columns(3)
    with c1.container(key="pp_kpi_lead"):
        st.metric(bi("First AI warning"), fw.timestamp.replace("T", " ")[5:16] if fw else "—")
    with c2.container(key="pp_kpi_contra"):
        st.metric(bi("First alarm"), fa[0].replace("T", " ")[5:16] if fa else "—")
    with c3.container(key="pp_kpi_records"):
        lead = ew.lead_hours
        st.metric(bi("Warning lead time"),
                  f"{lead:g} h" if lead and lead > 0 else ("Same hour" if lead == 0 else "—"))
    if ew.warned_before_alarm:
        st.success(f"The model raised a warning **{ew.lead_hours:g} hours before** the first alarm "
                   f"({fa[2]}).  \n" + gray(f"النموذج نبّه قبل أول إنذار بـ {ew.lead_hours:g} ساعة."))
    st.plotly_chart(ew_chart(ew), key="ew_chart")

    if fw:
        en, ar_ = _driver_text(fw.drivers)
        st.subheader(bi("What the model noticed first"))
        st.markdown(f"**{fw.timestamp.replace('T', ' ')[:16]}**: {en}.  \n{gray(ar_)}")
        st.caption(f"{bi('Source records')}: {ids_text(fw.record_ids)}")
        flagged = [h for h in ew.hours if h.flagged]
        movers = {p for h in flagged for p, _z in h.drivers}
        if len(movers) == 1 and fw and (fa is None or ew.lead_hours == 0):
            st.info(with_ar("Only one sensor changed while every other sensor stayed normal. A real "
                            "mechanical fault usually moves more than one sensor, so this pattern "
                            "points to checking the instrument itself."))
        with st.expander(bi("Flagged hours")):
            st.dataframe([{"Time · الوقت": h.timestamp.replace("T", " ")[:16],
                           "Score · الدرجة": h.score,
                           "Main drivers · الأسباب": ", ".join(f"{p} ({z:+g})" for p, z in h.drivers),
                           "Records · السجلات": ids_text(h.record_ids, 4)} for h in flagged],
                         hide_index=True)
    else:
        st.info(with_ar("No unusual behaviour detected in this window."))

    with st.expander(bi("How the model works")):
        st.markdown(with_ar(
            "1. It learns the normal level and spread of every sensor, and how the sensors move "
            "together, from the first 18 hours.") + "  \n" + with_ar(
            "2. Each hour gets an anomaly score: how far the whole set of readings is from what it "
            "learned (Mahalanobis distance).") + "  \n" + with_ar(
            "3. The alert threshold is learned from the healthy hours, with a safety margin. An "
            "hour is flagged when it and the next hour are above it.") + "  \n" + with_ar(
            "4. The sensors that drive the score are shown with their record IDs, so every warning "
            "can be checked."))
        st.dataframe([{"Sensor · الحساس": bi_plain(PARAM_LABELS.get(p, p)), "Normal mean · المتوسط": m,
                       "Normal spread · التذبذب": sd} for p, (m, sd) in ew.baseline.items()],
                     hide_index=True)


# ---------------------------------------------------------------- AI fact check
VERDICT_STYLE = {
    fact_check.SUPPORTED: (":material/check_circle:", "Supported by records", "pp_fc_ok"),
    fact_check.CONTRADICTED: (":material/cancel:", "Contradicted by records", "pp_fc_bad"),
    fact_check.NO_EVIDENCE: (":material/help:", "No evidence in the records", "pp_fc_none"),
}


def page_fact_check(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["AI Fact Check"], "AI Fact Check",
                "Paste a report written by any AI tool (or a person). Every sentence is checked "
                "against this investigation's records: green is backed by a record, red is "
                "contradicted, grey has no evidence and should not be trusted.")
    lang = st.radio(bi("Example draft"), ["Arabic", "English"], horizontal=True, key="fc_lang",
                    format_func=bi_plain)
    drafts = fact_check.SAMPLE_DRAFTS_AR if lang == "Arabic" else fact_check.SAMPLE_DRAFTS
    sample = drafts.get(ctx.sid, "")
    key = f"fc_text_{ctx.sid}_{lang}"
    text = st.text_area(bi("Report to check"), value=sample, height=170, key=key)
    if not st.button(f":material/fact_check: {bi('Check every sentence')}", type="primary",
                     key="fc_run") and not st.session_state.get("fc_done"):
        st.caption(with_ar("The example is written like a confident AI assistant, with some "
                           "mistakes hidden in it."))
        return
    st.session_state["fc_done"] = True
    checks = fact_check.check(text, ctx.obs, ctx.result, ctx.cfg)
    if not checks:
        st.warning(with_ar("Nothing to check yet."))
        return
    n = fact_check.summary(checks)
    c1, c2, c3 = st.columns(3)
    with c1.container(key="pp_kpi_records"):
        st.metric(bi("Supported by records"), n[fact_check.SUPPORTED])
    with c2.container(key="pp_kpi_contra"):
        st.metric(bi("Contradicted by records"), n[fact_check.CONTRADICTED])
    with c3.container(key="pp_kpi_miss"):
        st.metric(bi("No evidence in the records"), n[fact_check.NO_EVIDENCE])
    for i, c in enumerate(checks):
        icon, label, cls = VERDICT_STYLE[c.verdict]
        with st.container(border=True, key=f"{cls}_{i}"):
            st.markdown(f"{icon} **{bi(label)}**  \n> {c.sentence}")
            for en, ar_ in c.reasons:
                st.markdown(f"- {en}  \n  {gray(ar_)}")
            if c.record_ids:
                st.caption(f"{bi('Source records')}: {ids_text(c.record_ids, 6)}")


# ------------------------------------------------------------------ live sensor
def page_live_sensor(ctx: Ctx) -> None:
    page_header(PAGE_ICONS["Live Sensor"], "Live Sensor",
                "Turn a phone into a vibration sensor for this screen. Put it flat on a running "
                "machine (a fan or a washing machine), let the model learn normal for 10 seconds, "
                "then change how the machine runs and watch the screen detect it.")
    st.markdown(with_ar("1. Keep this page open on the iPad or laptop: it shows a code and a QR.")
                + "  \n" + with_ar("2. Scan the QR with the phone camera and press Start sending.")
                + "  \n" + with_ar("3. Put the phone on the machine. The screen learns, then alerts "
                                    "when the vibration changes."))
    pair = str(st.query_params.get("pair", "")) if hasattr(st, "query_params") else ""
    live_monitor(pair if pair.isdigit() and len(pair) == 6 else "", "full", 820)


def live_monitor(pair: str, mode: str, height: int) -> None:
    body = ((ASSETS / "live_sensor.html").read_text(encoding="utf-8")
            .replace("__APP_URL__", APP_URL).replace("__PAIR__", pair).replace("__MODE__", mode))
    import streamlit.components.v1 as components
    components.html(body, height=height, scrolling=True)


# -------------------------------------------------------------- operations room
def open_ops_room() -> None:
    st.session_state["view"] = OPS
    st.session_state["page"] = None


def go_ops_room() -> None:
    """Called by the live sensor's red alarm bar (it clicks a hidden button)."""
    st.session_state["view"] = OPS
    st.session_state["page"] = None
    st.session_state["pp_live_alarm"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def ack_alarm() -> None:
    st.session_state.pop("pp_live_alarm", None)


OPS_PANELS = (("hyp", ":material/psychology_alt:", "Hypotheses", "Evidence"),
              ("cost", ":material/payments:", "Cost", "Cost"),
              ("contra", ":material/report:", "Conflicts", "Evidence"),
              ("miss", ":material/pending_actions:", "Gaps", "Evidence"),
              ("ew", ":material/monitor_heart:", "Early warning", "AI Early Warning"))


def go_page(name: str) -> None:
    st.session_state["view"] = None
    st.session_state["page"] = name


def set_ops_panel(panel: str) -> None:
    st.session_state["ops_panel"] = None if st.session_state.get("ops_panel") == panel else panel


def ops_css() -> None:
    """War-room look, only on this page."""
    st.markdown(f"""<style>
[data-testid="stAppViewContainer"] {{ background: radial-gradient(1200px 500px at 50% -10%, #3A0B08 0%, #170605 55%, #0D0303 100%) !important; }}
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] h4 {{ color: #FFE9E6 !important; }}
[data-testid="stMain"] [data-testid="stHeading"] h1 {{ background: transparent !important; }}
.st-key-pp_ops_head {{ background: linear-gradient(90deg, #7A160F, #B42318) !important; border: 1px solid #FF6B5A !important;
  box-shadow: 0 0 0 1px #3A0B08, 0 10px 30px rgba(180,35,24,.45) !important; }}
.st-key-pp_ops_head.pp-live, .st-key-pp_ops_head:has(.pp-alarm-on) {{ animation: ppglow 1.2s ease-in-out infinite alternate; }}
@keyframes ppglow {{ from {{ box-shadow: 0 0 0 0 rgba(255,80,60,.0), 0 10px 30px rgba(180,35,24,.45); }}
                     to   {{ box-shadow: 0 0 0 6px rgba(255,80,60,.35), 0 10px 30px rgba(180,35,24,.6); }} }}
.st-key-pp_ops_head * {{ color: #FFFFFF !important; background: transparent !important; }}
[class*="st-key-pp_ops_kpi"] [data-testid="stMetric"] {{ background: #1E0807 !important; border: 1px solid #5A1A14 !important;
  border-left: 5px solid #E5483A !important; }}
[class*="st-key-pp_ops_kpi"] [data-testid="stMetricLabel"], [class*="st-key-pp_ops_kpi"] [data-testid="stMetricLabel"] * {{ color: #FFB4A8 !important; }}
[class*="st-key-pp_ops_kpi"] [data-testid="stMetricValue"], [class*="st-key-pp_ops_kpi"] [data-testid="stMetricValue"] * {{ color: #FFFFFF !important; }}
[class*="st-key-pp_ops_kpi"] [data-testid="stMetricDelta"] * {{ color: #FFB4A8 !important; }}
[class*="st-key-pp_ops_card"] {{ background: #FFFFFF !important; border: 1px solid #5A1A14 !important;
  border-top: 5px solid #B42318 !important; }}
[class*="st-key-pp_ops_tab"] button {{ background: #2A0B09 !important; color: #FFE9E6 !important;
  border: 1px solid #7A2A22 !important; width: 100%; font-weight: 700 !important; }}
[class*="st-key-pp_ops_tab"] button * {{ color: #FFE9E6 !important; }}
[class*="st-key-pp_ops_tab_on"] button {{ background: #B42318 !important; border-color: #FF8A7A !important; }}
.st-key-pp_ops_case_low [data-testid="stMetric"] {{ border-left-color: #1E7B4F !important; }}
.st-key-pp_ops_case_base [data-testid="stMetric"] {{ border-left-color: #C8844A !important; }}
.st-key-pp_ops_case_high [data-testid="stMetric"] {{ border-left-color: #B42318 !important; }}
[data-testid="stMain"] .pp-sign {{ color: #FFE9E6; }}
.pp-tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 4px 0 10px; }}
.pp-tile {{ background: #1E0807; border: 1px solid #5A1A14; border-left: 5px solid #E5483A; border-radius: 10px;
  padding: 10px 12px; }}
.pp-tile.hot {{ background: linear-gradient(135deg, #5C110B, #2A0807); border-color: #FF6B5A; }}
.pp-tile.case-low {{ border-left-color: #2FA36B; }} .pp-tile.case-base {{ border-left-color: #E0A060; }}
.pp-tile.case-high {{ border-left-color: #FF4D3D; }}
.pp-tl {{ color: #FFB4A8; font-size: .82rem; font-weight: 600; line-height: 1.3; }}
.pp-tl span, .pp-tn span {{ color: #C98C84; font-size: .78em; font-weight: 400; }}
.pp-tv {{ color: #FFFFFF; font-size: 1.7rem; font-weight: 800; line-height: 1.25; margin: 2px 0; }}
.pp-tn {{ color: #F3D3CE; font-size: .8rem; line-height: 1.35; }}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) {{ display: none; }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"]:has(.pp-tiles) {{ background: transparent !important; padding: 0 !important; }}
[class*="st-key-pp_ops_tab"] button {{ min-height: 64px; }}
</style>""", unsafe_allow_html=True)


def ops_tile(label: str, value: str, note: str = "", note_ar: str = "", tone: str = "") -> str:
    """One dark KPI tile (HTML): English label with small Arabic, big value, short note."""
    e = html.escape
    return (f'<div class="pp-tile {tone}"><div class="pp-tl">{e(label)} <span>{e(ar(label))}</span></div>'
            f'<div class="pp-tv">{e(value)}</div>'
            f'<div class="pp-tn">{e(note)} <span>{e(note_ar)}</span></div></div>')


def tiles(items: list[str]) -> None:
    st.markdown(f'<div class="pp-tiles">{"".join(items)}</div>', unsafe_allow_html=True)


def _ops_panel(ctx: Ctx, panel: str) -> None:
    r, top = ctx.result, ctx.result.top
    if panel == "hyp":
        tiles([ops_tile(a.name, pct(a.confidence), why_line(a)[0], why_line(a)[1],
                        "hot" if a.rank == 1 else "") for a in r.assessments[:3]])
    elif panel == "cost" and top:
        est = cost_model.estimate(top.hypothesis_id, ctx.costs).totals
        st.caption(f"{bi('If the leading cause is confirmed')}: {top.name} {gray(ar(top.name))}")
        notes = {"low": ("Best case", "أفضل حالة"), "base": ("Most likely", "الأرجح"),
                 "high": ("Worst case", "أسوأ حالة")}
        tiles([ops_tile(case.title(), money(est[case], ctx), *notes[case], f"case-{case}")
               for case in cost_model.CASES])
    elif panel == "contra":
        headlines(r.contradictions, "ops_c", "No contradictions detected.")
    elif panel == "miss":
        headlines(r.missing, "ops_m", "All required evidence is present.")
    elif panel == "ew":
        ew = early_warning.detect(list(ctx.obs), ctx.cfg.limits)
        if ew and ew.first_warning:
            tiles([ops_tile("First AI warning", ew.first_warning.timestamp.replace("T", " ")[5:16]),
                   ops_tile("First alarm", ew.first_alarm[0].replace("T", " ")[5:16] if ew.first_alarm else "—"),
                   ops_tile("Warning lead time", f"{ew.lead_hours:g} h" if ew.lead_hours else "Same hour",
                            tone="hot")])
        else:
            st.info(with_ar("No unusual behaviour detected in this window."))
    target = next(t for k, _i, _n, t in OPS_PANELS if k == panel)
    st.button(f":material/open_in_new: {bi('Full details')}", key=f"pp_ops_go_{panel}",
              on_click=go_page, args=(target,))


def _ops_advisor(ctx: Ctx) -> None:
    with st.container(border=True, key="pp_ops_card_ai"):
        st.markdown(f"**{PAGE_ICONS[ADVISOR]} {bi('AI Advisor')}**")
        with st.form("ops_ask", clear_on_submit=True, border=False):
            q = st.text_input(bi("Ask"), placeholder="e.g. Is the oil OK? · مثال: هل الزيت سليم؟",
                              label_visibility="collapsed")
            sent = st.form_submit_button(bi("Ask"))
        if sent and q and q.strip():
            saved = ctx.store.list_history("handover", ctx.sid)
            st.session_state["ops_answer"] = (ctx.sid, q.strip()[:300], advisor.answer(
                q.strip()[:300], ctx.obs, ctx.cfg, ctx.result, ctx.costs, ctx.meta,
                saved[0] if saved else None))
        last = st.session_state.get("ops_answer")
        if last and last[0] == ctx.sid:
            _sid, q, ans = last
            st.caption(f":material/person: {q}")
            st.markdown(f"**{ans.title_en}**  \n{gray(ans.title_ar)}")
            for item in ans.items[:3]:
                st.markdown(f"- {item.en}  \n  {gray(item.ar)}")
            if len(ans.items) > 3:
                st.button(bi("Open the full answer"), key="pp_ops_more", on_click=open_advisor)


def page_ops_room(ctx: Ctx) -> None:
    r, top = ctx.result, ctx.result.top
    ops_css()
    alarm = st.session_state.get("pp_live_alarm")
    with st.container(border=True, key="pp_ops_head"):
        h1, h2 = st.columns([4, 1])
        with h1:
            if alarm:
                st.markdown(f"## :material/crisis_alert: LIVE ALARM · {ctx.meta['asset_name']}")
                st.markdown(f"Abnormal vibration detected by the live sensor at **{alarm}**. "
                            f"Line 3 at risk.  \n"
                            f":small[إنذار مباشر: الحساس اكتشف اهتزازًا غير طبيعي الساعة {alarm}.]")
            else:
                st.markdown(f"## :material/crisis_alert: {bi('Operations Room')} · {ctx.meta['asset_name']}")
                st.markdown(f"{ctx.meta['summary']}  \n:small[{ar(ctx.meta['summary'])}]")
        with h2:
            if alarm:
                st.button(f":material/done: {bi('Acknowledge')}", key="pp_ack", on_click=ack_alarm)

    ew = early_warning.detect(list(ctx.obs), ctx.cfg.limits)
    est = cost_model.estimate(top.hypothesis_id, ctx.costs).totals if top else None
    tiles([
        ops_tile("Leading hypothesis", pct(top.confidence) if top else "—",
                 top.name if top else "", ar(top.name) if top else "", "hot"),
        ops_tile("AI early warning", f"{ew.lead_hours:g} h" if ew and ew.warned_before_alarm else "—",
                 "before the first alarm", "قبل أول إنذار"),
        ops_tile("Contradictions", str(len(r.contradictions)), "records disagree", "سجلات متعارضة"),
        ops_tile("Missing evidence", str(len(r.missing)), "checks not done", "فحوصات ناقصة"),
        ops_tile("Cost if confirmed", money(est["base"], ctx) if est else "—", "most likely", "الأرجح"),
    ])

    left, right = st.columns([2, 1])
    with left:
        panel = st.session_state.get("ops_panel", "hyp")
        for col, (key, icon, name, _t) in zip(st.columns(len(OPS_PANELS)), OPS_PANELS):
            on = "_on" if panel == key else ""
            with col.container(key=f"pp_ops_tab{on}_{key}"):
                st.button(f"{icon} {name} :small[{ar(name)}]", key=f"pp_ops_btn_{key}",
                          on_click=set_ops_panel, args=(key,))
        if panel:
            with st.container(border=True, key="pp_ops_card_panel"):
                _ops_panel(ctx, panel)
        with st.container(border=True, key="pp_ops_card_actions"):
            a, b = st.columns(2)
            with a:
                st.markdown(f"**:material/task_alt: {bi('Do this now')}**")
                if top:
                    st.markdown("\n".join(f"{n}. {x}  \n   {gray(ar(x))}"
                                          for n, x in enumerate(top.recommended_actions, 1)))
            with b:
                st.markdown(f"**:material/block: {bi('Before restart')}**")
                items = r.contradictions + r.missing
                st.markdown("\n".join(f"- {f.title}  \n  {gray(ar(f.title))}" for f in items)
                            or with_ar("Nothing blocking a restart."))
    with right:
        _ops_advisor(ctx)
        with st.container(border=True, key="pp_ops_card_live"):
            st.markdown(f"**:material/sensors: {bi('Live monitor')}**")
            live_monitor("", "ops", 430)


# ------------------------------------------------------------------- branding
YAQEN_MARK = ('<svg class="pp-sign-mark" viewBox="215 130 720 795" aria-hidden="true">'
              '<g stroke="currentColor" stroke-width="56" stroke-linecap="round">'
              '<line x1="325" y1="242" x2="575" y2="540"/><line x1="823" y1="242" x2="575" y2="540"/>'
              '<line x1="575" y1="540" x2="575" y2="813"/></g>'
              '<g fill="currentColor"><circle cx="325" cy="242" r="91"/><circle cx="823" cy="242" r="91"/>'
              '<circle cx="575" cy="813" r="91"/></g>'
              '<circle cx="575" cy="540" r="115" fill="#4DA383"/></svg>')


def yaqen_footer() -> None:
    """Brand signature at the bottom of every page: no box, just the mark, a shimmer and a link."""
    link = ""
    if LINKEDIN_URL:
        link = (f'<a class="pp-sign-li" href="{html.escape(LINKEDIN_URL)}" target="_blank" '
                f'rel="noopener" title="Yaqen AI on LinkedIn">in</a>')
    st.markdown(
        f'<div class="pp-sign">{YAQEN_MARK}'
        f'<div><div class="pp-sign-t">Designed &amp; built by <b>Yaqen AI</b></div>'
        f'<div class="pp-sign-ar">صُممت وطُوّرت بواسطة يقين للذكاء الاصطناعي</div></div>{link}</div>',
        unsafe_allow_html=True)


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
        d1.download_button(f":material/download: {bi('Handover report')}", report_html(doc),
                           file_name=f"handover_{ctx.sid}_{stamp}.html",
                           mime="text/html", key="ho_html")
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
    st.sidebar.button(f"{PAGE_ICONS[OPS]} Operations Room :small[غرفة العمليات]", key="pp_ops_side",
                      on_click=open_ops_room, type="primary")
    st.sidebar.button(f"{PAGE_ICONS[ADVISOR]} AI Advisor · المساعد الذكي", key="pp_advisor_side",
                      on_click=open_advisor, type="primary")
    try:   # a phone that scanned the pairing QR opens straight on the Live Sensor page
        if st.query_params.get("pair") and not st.session_state.get("pp_pair_opened"):
            st.session_state["pp_pair_opened"] = True
            st.session_state["page"] = "Live Sensor"
    except Exception:
        pass
    nav = st.sidebar.radio(bi("Navigate"), PAGES, key="page", on_change=close_advisor,
                           format_func=lambda p: f"{PAGE_ICONS[p]} {bi(p)}")
    view = st.session_state.get("view")
    page = view if view in (ADVISOR, OPS) else (nav or "Overview")
    titles = {s["id"]: s["title"] for s in index}
    sid = st.sidebar.selectbox(bi("Scenario"), list(titles),
                               format_func=lambda k: bi_plain(titles[k]), key="scenario")
    with st.sidebar.expander(bi("About this demo")):
        st.warning(with_ar(PERSISTENCE_SHORT), icon=":material/save:")
        st.caption(f"v{__version__} · "
                   + with_ar("Synthetic demo data only · Rule-based analysis, "
                             "no external AI or API keys."))
        st.caption(f"{DISCLAIMER}  \n{gray(DISCLAIMER_AR)}")

    meta = next(s for s in index if s["id"] == sid)
    obs = store.observations(sid)
    if not obs:
        store.reset_observations()
        obs = store.observations(sid)
    ctx = Ctx(store, cfg, costs, meta, sid, obs, analyse(obs, cfg, sid))

    with st.container(key="pp_alarm_go"):       # clicked by the live sensor's red alarm bar
        st.button("Live alarm", key="pp_alarm_btn", on_click=go_ops_room)
    if page not in (ADVISOR, OPS):
        with st.container(key="pp_fab"):
            st.button(f"{PAGE_ICONS[ADVISOR]} Ask the AI Advisor · اسأل المساعد",
                      key="pp_advisor_fab", on_click=open_advisor)
    {"Overview": page_overview, "Evidence": page_evidence, "Advisor": page_advisor,
     "What If": page_whatif,
     "Blind Test": page_blind_test, "Cost": page_cost, "History": page_history,
     "Handover": page_handover, "AI Early Warning": page_early_warning,
     "AI Fact Check": page_fact_check, "Live Sensor": page_live_sensor,
     "Operations Room": page_ops_room}[page](ctx)
    yaqen_footer()


main()
