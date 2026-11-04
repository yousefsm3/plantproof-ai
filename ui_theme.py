"""PlantProof AI design system: tokens and the one stylesheet every page uses.

Documented in docs/DESIGN_SYSTEM.md. Colour carries meaning only:
  green  = verified / healthy        amber = warning / uncertain / needs evidence
  red    = genuine critical condition steel = information        neutral = ordinary
Brand accents (Yaqen green, copper) are used for identity elements, never for status.
"""

from __future__ import annotations

TOKENS = {
    # surfaces
    "bg": "#0E1315", "surface": "#151C1F", "raised": "#1B2427", "sunken": "#11181A",
    "border": "#27333A", "border_strong": "#3A4950",
    # text
    "text": "#E6ECEB", "text2": "#A9B8B6", "muted": "#74858A",
    # brand
    "brand": "#4DA383", "brand_deep": "#2E7D66", "copper": "#C08048",
    # meaning
    "ok": "#3FAE7C", "warn": "#E0A43C", "crit": "#E5483A", "info": "#5FA3C7", "neutral": "#8A9A98",
    "ok_bg": "#13271F", "warn_bg": "#2A2213", "crit_bg": "#2C1412", "info_bg": "#122230",
}
STATUS_TONE = {   # examination and condition states -> meaning colour
    "completed": "ok", "verified": "ok", "Normal": "ok", "Low": "ok", "A": "ok",
    "awaiting_evidence": "warn", "insufficient_data": "warn", "supported": "info", "downgraded": "warn",
    "Degraded": "warn", "Medium": "warn", "B": "info", "C": "warn", "Undetermined": "warn",
    "Alarm (unconfirmed)": "warn", "pending": "neutral", "not_applicable": "neutral", "Unknown": "neutral",
    "blocked": "neutral", "failed": "crit", "verification_rejected": "crit", "rejected": "crit",
    "Alarm": "crit", "High": "crit", "Critical": "crit", "D": "crit",
}
CHART = {"paper": "rgba(0,0,0,0)", "plot": "#151C1F", "grid": "#26323A", "axis": "#3A4950",
         "font": "#C9D4D2", "series": ["#5FA3C7", "#4DA383", "#C08048", "#9B8AC4"]}


def tone(value: str) -> str:
    return STATUS_TONE.get(value, "neutral")


def stylesheet(bg_uri: str) -> str:
    t = TOKENS
    return f"""
<style>
:root {{
  --pp-bg:{t['bg']}; --pp-surface:{t['surface']}; --pp-raised:{t['raised']}; --pp-sunken:{t['sunken']};
  --pp-border:{t['border']}; --pp-border-strong:{t['border_strong']};
  --pp-text:{t['text']}; --pp-text2:{t['text2']}; --pp-muted:{t['muted']};
  --pp-brand:{t['brand']}; --pp-brand-deep:{t['brand_deep']}; --pp-copper:{t['copper']};
  --pp-ok:{t['ok']}; --pp-warn:{t['warn']}; --pp-crit:{t['crit']}; --pp-info:{t['info']}; --pp-neutral:{t['neutral']};
  --pp-ok-bg:{t['ok_bg']}; --pp-warn-bg:{t['warn_bg']}; --pp-crit-bg:{t['crit_bg']}; --pp-info-bg:{t['info_bg']};
  --pp-r:8px; --pp-s1:4px; --pp-s2:8px; --pp-s3:12px; --pp-s4:16px; --pp-s5:24px;
}}
/* ---------- shell ---------- */
[data-testid="stAppViewContainer"] {{
  background-color: var(--pp-bg);
  background-image: url("{bg_uri}"), radial-gradient(1200px 600px at 70% -10%, #17262A 0%, var(--pp-bg) 60%);
  background-repeat: no-repeat, no-repeat; background-position: right -60px bottom -40px, 0 0;
  background-size: min(1100px, 95vw) auto, cover; background-attachment: fixed;
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: #0B1012; border-right: 1px solid var(--pp-border); }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; max-width: 1360px; }}
[data-testid="stToolbarActions"], .stAppDeployButton, [data-testid="stAppDeployButton"] {{ display: none !important; }}
/* ---------- type ---------- */
h1, h2, h3, h4 {{ color: var(--pp-text) !important; letter-spacing: .1px; }}
[data-testid="stHeading"] h1 {{ font-size: 1.7rem; font-weight: 700; }}
[data-testid="stHeading"] h3 {{ font-size: 1.08rem; font-weight: 650; padding-bottom: 4px;
  border-bottom: 1px solid var(--pp-border); }}
[data-testid="stCaptionContainer"] {{ color: var(--pp-text2); }}
code {{ color: #BFD7D0 !important; background: var(--pp-sunken) !important; }}
/* ---------- cards and containers ---------- */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"], [data-testid="stForm"],
[data-testid="stTabs"], [data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{
  background: var(--pp-surface) !important; border: 1px solid var(--pp-border) !important;
  border-radius: var(--pp-r) !important; box-shadow: none !important;
}}
[data-testid="stPlotlyChart"], [data-testid="stTabs"] {{ padding: 6px 8px; }}
[data-testid="stExpander"] summary:hover {{ color: var(--pp-brand); }}
[data-testid="stMetric"] {{ background: var(--pp-surface); border: 1px solid var(--pp-border);
  border-left: 3px solid var(--pp-neutral); border-radius: var(--pp-r); padding: 10px 14px; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{ color: var(--pp-text2) !important; font-weight: 600; }}
[data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] div, [data-testid="stMetricLabel"] label {{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{ white-space: normal !important;
  overflow: visible !important; text-overflow: clip !important; font-size: 1.45rem; line-height: 1.25;
  color: var(--pp-text); }}
.st-key-pp_kpi_records [data-testid="stMetric"] {{ border-left-color: var(--pp-info); }}
.st-key-pp_kpi_contra [data-testid="stMetric"] {{ border-left-color: var(--pp-crit); }}
.st-key-pp_kpi_miss [data-testid="stMetric"] {{ border-left-color: var(--pp-warn); }}
.st-key-pp_kpi_lead [data-testid="stMetric"] {{ border-left-color: var(--pp-brand); }}
[class*="st-key-pp_contra"] {{ border-left: 3px solid var(--pp-crit) !important; }}
[class*="st-key-pp_miss"] {{ border-left: 3px solid var(--pp-warn) !important; }}
[class*="st-key-pp_fc_ok"] {{ border-left: 3px solid var(--pp-ok) !important; }}
[class*="st-key-pp_fc_bad"] {{ border-left: 3px solid var(--pp-crit) !important; }}
[class*="st-key-pp_fc_none"] {{ border-left: 3px solid var(--pp-neutral) !important; }}
.st-key-pp_keypoints {{ border-left: 3px solid var(--pp-brand) !important; }}
/* ---------- controls ---------- */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
  background: var(--pp-raised) !important; border: 1px solid var(--pp-border-strong) !important;
  color: var(--pp-text) !important; font-weight: 600 !important; }}
[data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--pp-brand) !important; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: var(--pp-brand-deep) !important; border: 1px solid var(--pp-brand) !important;
  color: #fff !important; font-weight: 650 !important; }}
/* sidebar entry points: one distinct button each */
.st-key-pp_ops_side button, .st-key-pp_advisor_side button, .st-key-pp_rb_side button {{
  width: 100%; justify-content: flex-start; padding: 10px 14px !important; margin: 2px 0;
  font-weight: 700 !important; border-radius: var(--pp-r) !important; }}
.st-key-pp_ops_side button {{ background: var(--pp-crit-bg) !important; border: 1px solid #7A2A22 !important; }}
.st-key-pp_ops_side button * {{ color: #FFD9D4 !important; }}
.st-key-pp_ops_side button:hover {{ border-color: var(--pp-crit) !important; }}
.st-key-pp_rb_side button {{ background: var(--pp-info-bg) !important; border: 1px solid #2D5570 !important; }}
.st-key-pp_rb_side button * {{ color: #D5EAF6 !important; }}
.st-key-pp_advisor_side button {{ background: #2A1E14 !important; border: 1px solid #6B4A2C !important; }}
.st-key-pp_advisor_side button * {{ color: #F1D9C2 !important; }}
.st-key-pp_fab {{ position: fixed; right: 24px; bottom: 76px; z-index: 1000; width: auto !important; }}
.st-key-pp_fab button {{ border-radius: 999px !important; padding: 10px 18px !important;
  background: #2A1E14 !important; border: 1px solid var(--pp-copper) !important;
  box-shadow: 0 6px 20px rgba(0,0,0,.45) !important; }}
.st-key-pp_fab button * {{ color: #F1D9C2 !important; }}
.st-key-pp_alarm_go {{ display: none !important; }}
[class*="st-key-pp_ops_tab"] button {{ width: 100%; min-height: 58px; background: var(--pp-surface) !important;
  border: 1px solid var(--pp-border) !important; }}
[class*="st-key-pp_ops_tab"] button * {{ color: var(--pp-text2) !important; }}
[class*="st-key-pp_ops_tab_on"] button {{ background: var(--pp-raised) !important; border-color: var(--pp-brand) !important;
  box-shadow: inset 0 -2px 0 var(--pp-brand); }}
[class*="st-key-pp_ops_tab_on"] button * {{ color: var(--pp-text) !important; }}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) {{ display: none; }}
[data-testid="stMarkdownContainer"]:has(.pp-tiles), [data-testid="stMarkdownContainer"]:has(.pp-banner),
[data-testid="stMarkdownContainer"]:has(.pp-steps) {{ background: transparent !important; padding: 0 !important; }}
/* ---------- shared components ---------- */
.pp-tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 4px 0 12px; }}
.pp-tile {{ background: var(--pp-surface); border: 1px solid var(--pp-border); border-left: 3px solid var(--pp-neutral);
  border-radius: var(--pp-r); padding: 10px 12px; min-width: 0; }}
.pp-tile.ok {{ border-left-color: var(--pp-ok); }} .pp-tile.warn {{ border-left-color: var(--pp-warn); }}
.pp-tile.crit {{ border-left-color: var(--pp-crit); background: linear-gradient(180deg, var(--pp-crit-bg), var(--pp-surface)); }}
.pp-tile.info {{ border-left-color: var(--pp-info); }} .pp-tile.brand {{ border-left-color: var(--pp-brand); }}
.pp-tl {{ color: var(--pp-text2); font-size: .8rem; font-weight: 600; line-height: 1.3; }}
.pp-tl span, .pp-tn span {{ color: var(--pp-muted); font-weight: 400; font-size: .92em; }}
.pp-tv {{ color: var(--pp-text); font-size: 1.5rem; font-weight: 750; line-height: 1.2; margin: 3px 0;
  overflow-wrap: anywhere; }}
.pp-tv.sm {{ font-size: 1.1rem; }}
.pp-tn {{ color: var(--pp-text2); font-size: .8rem; line-height: 1.35; }}
.pp-chip {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .74rem; font-weight: 700;
  border: 1px solid currentColor; line-height: 1.6; white-space: nowrap; }}
.pp-chip.ok {{ color: var(--pp-ok); }} .pp-chip.warn {{ color: var(--pp-warn); }} .pp-chip.crit {{ color: var(--pp-crit); }}
.pp-chip.info {{ color: var(--pp-info); }} .pp-chip.neutral {{ color: var(--pp-neutral); }}
.pp-banner {{ border: 1px solid var(--pp-border); border-left: 4px solid var(--pp-neutral); border-radius: var(--pp-r);
  padding: 14px 16px; background: var(--pp-surface); margin-bottom: 12px; }}
.pp-banner.crit {{ border-color: #7A2A22; border-left-color: var(--pp-crit); background: var(--pp-crit-bg); }}
.pp-banner.warn {{ border-color: #6B5320; border-left-color: var(--pp-warn); background: var(--pp-warn-bg); }}
.pp-banner.ok {{ border-color: #24513C; border-left-color: var(--pp-ok); background: var(--pp-ok-bg); }}
.pp-banner.info {{ border-color: #2D5570; border-left-color: var(--pp-info); background: var(--pp-info-bg); }}
.pp-banner .t {{ font-size: 1.15rem; font-weight: 750; color: var(--pp-text); }}
.pp-banner .s {{ color: var(--pp-text2); font-size: .9rem; margin-top: 4px; }}
.pp-banner .a {{ color: var(--pp-muted); font-size: .82rem; margin-top: 2px; direction: rtl; text-align: left; }}
.pp-banner.live {{ animation: pplive 1.2s ease-in-out infinite alternate; }}
@keyframes pplive {{ from {{ box-shadow: 0 0 0 0 rgba(229,72,58,0); }} to {{ box-shadow: 0 0 0 4px rgba(229,72,58,.35); }} }}
.pp-steps {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 6px 0 14px; }}
.pp-step {{ background: var(--pp-surface); border: 1px solid var(--pp-border); border-top: 3px solid var(--pp-neutral);
  border-radius: var(--pp-r); padding: 8px 10px; min-width: 0; }}
.pp-step.ok {{ border-top-color: var(--pp-ok); }} .pp-step.warn {{ border-top-color: var(--pp-warn); }}
.pp-step.crit {{ border-top-color: var(--pp-crit); }} .pp-step.neutral {{ border-top-color: var(--pp-neutral); }}
.pp-step .n {{ color: var(--pp-muted); font-size: .72rem; font-weight: 700; letter-spacing: .4px; }}
.pp-step .h {{ color: var(--pp-text); font-size: .86rem; font-weight: 650; line-height: 1.3; margin: 2px 0 4px; }}
.pp-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82em; color: #BFD7D0; }}
.pp-ar {{ font-size: .78em; opacity: .7; font-weight: 400; margin-inline-start: .45em; }}
.pp-rtl {{ direction: rtl; text-align: right; unicode-bidi: isolate; color: var(--pp-muted);
  font-size: .86rem; line-height: 1.6; margin: -6px 0 8px 0; }}
.pp-rtl-title {{ font-size: .95rem; font-weight: 600; margin-top: -10px; }}
.pp-rtl-note {{ font-size: .78rem; }}
.pp-name {{ font-size: 1.2rem; font-weight: 750; color: var(--pp-text); letter-spacing: .2px; }}
.pp-name span {{ color: var(--pp-brand); }}
/* brand signature */
[data-testid="stMarkdownContainer"]:has(.pp-sign) {{ background: transparent !important; padding: 0 !important; }}
.pp-sign {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin: 40px 0 10px;
  color: var(--pp-text2); }}
.pp-sign-mark {{ width: 36px; height: 36px; flex: none; filter: drop-shadow(0 0 6px rgba(77,163,131,.35)); }}
.pp-sign-t {{ font-size: .95rem; letter-spacing: .3px; font-weight: 500;
  background: linear-gradient(100deg, currentColor 0%, currentColor 40%, #7FD6B6 50%, currentColor 60%, currentColor 100%);
  background-size: 250% 100%; -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; animation: ppshine 3.5s linear infinite; }}
.pp-sign-t b {{ font-weight: 800; }}
.pp-sign-ar {{ font-size: .74rem; opacity: .7; direction: rtl; text-align: left; }}
.pp-sign-li {{ display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
  border-radius: 6px; border: 1.5px solid currentColor; color: inherit !important; font-weight: 800;
  font-size: .85rem; text-decoration: none !important; opacity: .85; }}
.pp-sign-li:hover {{ opacity: 1; color: #5FA8E6 !important; }}
@keyframes ppshine {{ from {{ background-position: 100% 0; }} to {{ background-position: -150% 0; }} }}
/* ---------- responsive ---------- */
@media (max-width: 900px) {{
  [data-testid="stMainBlockContainer"] {{ padding-left: 1rem; padding-right: 1rem; }}
  .pp-tv {{ font-size: 1.25rem; }}
  .st-key-pp_fab {{ right: 12px; bottom: 64px; }}
}}
@media (max-width: 640px) {{
  [data-testid="stHeading"] h1 {{ font-size: 1.35rem; }}
  .pp-tiles {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .pp-steps {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .st-key-pp_fab button {{ padding: 8px 12px !important; font-size: .8rem; }}
}}
</style>
"""


def style_fig(fig, height: int = 300, x_title: str | None = None, y_title: str | None = None,
              legend: bool = False):
    """Apply the dark chart style. Titles carry units."""
    c = CHART
    fig.update_layout(paper_bgcolor=c["paper"], plot_bgcolor=c["plot"], height=height,
                      margin=dict(l=10, r=10, t=16, b=10), font=dict(color=c["font"], size=12),
                      showlegend=legend, legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(gridcolor=c["grid"], linecolor=c["axis"], zerolinecolor=c["grid"])
    fig.update_yaxes(gridcolor=c["grid"], linecolor=c["axis"], zerolinecolor=c["grid"])
    if x_title is not None:
        fig.update_xaxes(title=x_title)
    if y_title is not None:
        fig.update_yaxes(title=y_title)
    return fig
