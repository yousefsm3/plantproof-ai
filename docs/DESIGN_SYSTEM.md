# PlantProof AI design system

Implemented in `ui_theme.py` (tokens, stylesheet, chart style) and `.streamlit/config.toml`
(Streamlit dark base theme). Every page uses the same stylesheet.

## Principles

1. Colour carries meaning. Red appears only for a genuine critical condition (live alarm,
   Critical risk, failed verification, conflicting records). Brand colours never signal status.
2. Hierarchy before detail. Each page leads with the few facts that decide the next action;
   supporting detail sits behind expanders, tabs or a "Full details" button.
3. Evidence is visible. Record IDs, units and the basis of every number are shown or one
   click away. No decorative charts and no invented values.
4. Bilingual by default. English first, Arabic gloss in a smaller, quieter style; Arabic
   sentences render right-to-left.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| bg | #0E1315 | app background |
| surface / raised / sunken | #151C1F / #1B2427 / #11181A | cards / hover and selected / inputs, canvases |
| border / border_strong | #27333A / #3A4950 | separators / control outlines |
| text / text2 / muted | #E6ECEB / #A9B8B6 / #74858A | primary / secondary / Arabic gloss, captions |
| brand / brand_deep | #4DA383 / #2E7D66 | Yaqen identity, primary buttons, leading explanation |
| ok | #3FAE7C | verified, healthy, nothing open |
| warn | #E0A43C | warning, uncertain, awaiting evidence, missing evidence |
| crit | #E5483A | critical condition only |
| info | #5FA3C7 | information, data series |
| neutral | #8A9A98 | ordinary, blocked, not applicable |
| copper | #C08048 | AI Advisor entry point (identity only) |

Spacing scale 4 / 8 / 12 / 16 / 24 px; radius 8 px; borders 1 px; status accents 3 px.

## Components

| Component | Class / key | Rule |
| --- | --- | --- |
| KPI tile | `.pp-tile` + tone | label (EN + small AR), value, one-line note |
| Banner | `.pp-banner` + tone (+ `live`) | page status; `live` pulses only for a live alarm |
| Stage step | `.pp-step` + tone | one per examination stage, status chip, duration |
| Chip | `.pp-chip` + tone | short status words |
| Sidebar entry points | `pp_ops_side`, `pp_rb_side`, `pp_advisor_side` | each special view has one distinct button |
| Panel switch | `pp_ops_tab*` | segmented buttons; selected = brand underline |
| Charts | `ui_theme.style_fig` | dark plot, grid #26323A, axis titles with units |

## Responsive behaviour

Streamlit columns stack below 640 px. Tile and step grids use `auto-fit` and fall to two
columns on phones. The floating advisor button shrinks on small screens. The UI preview
workflow checks every page at 1440, 820 and 390 px for horizontal overflow and captures
screenshots.
