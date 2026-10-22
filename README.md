# PlantProof AI

Evidence-first investigation of industrial incidents, built with Python and Streamlit.

PlantProof AI checks plant records for **contradictions** and **missing evidence**, ranks
configurable **root-cause hypotheses**, and links every finding to the **source record IDs**
behind it. All analysis is transparent and rule-based: no LLM, no external AI service, no paid
API and no API keys.

Every label in the dashboard shows a light-grey Arabic gloss next to the English text
(`plantproof/translations.py`). Engine-generated detail sentences stay in English.

The visual identity (logo, colours, equipment line art) is original to this project. PlantProof AI
is a concept prototype for the energy sector and is not affiliated with or endorsed by any company.

> **Synthetic data only.** Every record in this repository is fictional. This repository is
> public: it contains no credentials, API keys, passwords, personal data or secrets, and must
> never contain any.

## Features

| Page | What it does |
|---|---|
| Overview | KPIs, sensor trends with alarm limits, hypothesis confidence, open contradictions and evidence gaps |
| Evidence | Hypothesis ranking with the full scoring working, supporting/refuting/missing evidence, contradiction details, record tracing, raw records, save investigation |
| Advisor | Rule-based engineering assistant (English or Arabic questions): what to check first (ranked by simulated impact), restart-readiness checklist, why the leader leads, action plan. No external AI |
| What If | Presets or custom changes (ignore record types, override a value, scale a sensor, add hypothetical evidence). Runs on a copy; a fingerprint check proves the originals are unchanged |
| Blind Test | Scores the engine, or your own analysis, against separately stored reference answers (100-point scale) |
| Cost | Low / base / high repair cost with visible formulas and editable assumptions, plus a confidence-weighted expected cost |
| History | Saved investigations, What If runs, Blind Test results and handovers, with **JSON export/import** |
| Handover | Template-based shift handover with Markdown and JSON downloads |

## Important: storage is not permanent on Streamlit Community Cloud

History is stored in a local SQLite file (`.runtime/plantproof.db`). On Streamlit Community
Cloud, local files are **not guaranteed to persist**. They can be wiped when the app restarts,
reboots, redeploys or wakes from sleep.

- Demo observations are rebuilt automatically from `data/scenarios/`.
- Saved investigations, What If runs, Blind Test results and handovers are **lost** unless you
  export them (History → Download history) and import them again later.
- The app shows this warning in the sidebar and on the History page.
- To make history permanent later, replace `plantproof/storage.py` with a hosted database
  backend. No other file needs to change.

## Blind Test transparency

Reference answers live in `data/reference_answers.json`. Only `plantproof/blind_test.py` reads
that file; the evidence engine never does, and a unit test enforces this. However, **this
repository is public, so anyone can read the answers**. The separation demonstrates the
method; it is not a secret.

## Project structure

```
app.py                      Streamlit dashboard (display only)
plantproof/
  domain.py                 data classes, CSV I/O, config loading and validation
  data_gen.py               deterministic synthetic data generator
  evidence_engine.py        contradictions, missing evidence, hypothesis scoring
  whatif.py                 simulations on copies + fingerprint proof
  blind_test.py             scoring against reference answers
  cost_model.py             low/base/high cost simulator
  handover.py               shift handover summaries
  advisor.py                rule-based engineering advisor
  translations.py           Arabic glosses for the UI
  storage.py                SQLite storage, history export/import
config/                     hypotheses.json, cost_assumptions.json
assets/                     original logo and equipment line art (SVG)
data/                       synthetic scenarios + reference answers
tests/                      unit tests + fake-Streamlit smoke test
.streamlit/config.toml      theme
requirements.txt            pinned dependencies
```

Everything in `plantproof/` uses only the Python standard library, so all logic can be tested
without Streamlit installed.

## How confidence is calculated

```
support_ratio    = max(0, matched supporting weight - matched refuting weight) / total supporting weight
coverage         = required evidence present / required evidence total
coverage_factor  = 0.5 + 0.5 * coverage
contested_factor = max(0.7, 0.9 ^ contradictions touching supporting records)
confidence       = support_ratio * coverage_factor * contested_factor
```

Thresholds, weights and rules are in `config/hypotheses.json`.

## Running the tests

```
python -m unittest discover -s tests -t .
```

The core tests need only Python 3.11+. The smoke test runs `app.py` against a fake Streamlit;
it catches Python errors in the UI code but cannot check real Streamlit rendering.

## Deploying on Streamlit Community Cloud

1. Put these files in a **public** GitHub repository (see the iPad steps below).
2. Sign in at https://share.streamlit.io with GitHub and choose **Create app → Deploy a public app from GitHub**.
3. Repository: your repo. Branch: `main`. Main file path: `app.py`.
4. Open **Advanced settings** and choose **Python 3.12**. No secrets are needed.
5. Click **Deploy**. The first build takes a few minutes.

If the app shows an error, open **Manage app** (bottom right) to read the logs.

## Uploading from an iPad (no computer needed)

GitHub's web uploader puts files into the folder you are currently viewing, and the iPad file
picker cannot upload folders. So create each folder first, then upload into it.

1. Download `plantproof-ai.zip` and tap it in the Files app to unzip it.
2. On github.com (Safari), create a **public** repository named `plantproof-ai`.
3. **Root files:** in the repo, tap **Add file → Upload files**, select `app.py`,
   `requirements.txt` and `README.md`, then **Commit changes**.
4. For each folder below: tap **Add file → Create new file**, type the first file's path
   (the `/` creates the folder), paste its contents, commit. Then open that folder and use
   **Upload files** for the rest.

| Folder | Create this file first | Then upload into the folder |
|---|---|---|
| `plantproof/` | `plantproof/__init__.py` | the other 8 `.py` files |
| `config/` | `config/README.md` | `hypotheses.json`, `cost_assumptions.json` |
| `data/` | `data/README.md` | `reference_answers.json` |
| `data/scenarios/` | `data/scenarios/README.md` | `index.json`, `scenario_A.csv`, `scenario_B.csv` |
| `tests/` | `tests/__init__.py` | the `test_*.py` files and `fake_streamlit.py` |

5. **Hidden files** (names starting with a dot may not show in the Files app). Create them with
   **Add file → Create new file** and paste their contents:
   - `.streamlit/config.toml` (optional theme)
   - `.gitignore` (stops database files being committed)
6. Check the repository shows the structure above, then deploy.

## Live demo script (about 4 minutes)

1. **Overview, Scenario A.** "P-301 tripped. PlantProof read 202 records: two contradictions,
   two evidence gaps, and bearing wear leads at 81%." Point at the red markers on the
   vibration chart.
2. **Evidence.** Open the bearing wear card: supporting rules, weights, and record IDs. Use
   **Trace a record** on `A-OPS-0004`: the operator wrote "running normally" while vibration
   and bearing temperature were in alarm.
3. **What If.** Preset "Oil analysis comes back clean". Bearing wear drops; then show the
   green fingerprint check: the original data was never touched.
4. **Switch to Scenario B.** Same trip, different story: the handheld reading disagrees with
   the online sensor and its calibration is two years old. Sensor fault now leads.
5. **Blind Test.** Run it: 100/100 on both scenarios. Then score your own guess in the second
   tab to show the scorer is fair.
6. **Cost.** Sensor fault costs about £4.4k (base) against about £25k for bearing wear. That
   is why evidence matters before restart.
7. **Handover.** Generate it, download the Markdown, save it. Finish on **History → Download
   history** and explain the storage warning.

Open the app about 10 minutes before presenting: free apps sleep after a period without visits.

## Limitations

- Rules are hand-written for one asset type (a centrifugal pump) and two synthetic scenarios.
- Contradiction detection covers "normal" claims against sensor alarms and cross-checked
  measurements; it does not interpret free text.
- Cost figures are illustrative, not engineering estimates.
- History storage is temporary on Streamlit Community Cloud (export it).
- The smoke test uses a fake Streamlit, so real rendering is only verified on deployment.

## Regenerating the demo data

```
python -m plantproof.data_gen
```

Output is deterministic (fixed seeds); the tests fail if the committed CSVs drift.
