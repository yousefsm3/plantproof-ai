# Delivery report — Reliability Brain and platform quality

Branch `reliability-brain`, based on `main` at `d69624a`. Not merged and not deployed: merging
updates the public demo, so it waits for the owner's approval.

## Results at a glance

| Item | Result | How it was checked |
| --- | --- | --- |
| Original 95 tests | All pass, unchanged assertions | `python -m unittest discover -s tests -t .` locally and in CI |
| Total tests | 140, all pass | same; 7 contract, 35 Brain, 3 new smoke tests added |
| Statement coverage | 92.0% overall (3,714 of 4,039); Brain modules 89–99% | `scripts/coverage_report.py` (stdlib tracer, ±2 points) |
| Real browser, flag off | 11 pages open without errors at 1440, 820 and 390 px; no horizontal overflow reported | `ui-preview` workflow, real Streamlit 1.65 |
| Real browser, flag on | 12 pages incl. Reliability Brain open without errors at all three widths | same |
| Original data immutability | Scenario files, configs and the platform store unchanged; fingerprints equal before and after every Brain run | `IsolationAndImmutabilityTests` |
| Isolation | No original module imports the Brain; adapter uses public names only | AST tests |
| Feature flag | Off: Brain never imported, no button, view refused. On: page, button and Ops Room summary | smoke tests + CI matrix |
| Failure containment | A crashing stage blocks only its dependants; a broken Brain module leaves the platform working | `OrchestrationTests`, `test_broken_brain_never_breaks_the_platform` |

## Known-answer cases

| Case | Status | Condition | Data | Risk | Leading explanation | Engineering reason |
| --- | --- | --- | --- | --- | --- | --- |
| P-301/A | Complete | Alarm | A | Critical | Bearing degradation 81% (High) | Vibration, temperature, oil debris and overdue lubrication agree |
| P-301/B | Complete, awaiting evidence | Alarm (unconfirmed) | B | High | Vibration instrument fault 55% (Medium) | Only the transmitter is high; handheld disagrees; calibration two years old |
| P-301/C | Complete | Alarm | A | Critical | Mechanical seal failure 90% (High) | Seal pot falling, leak seen, water in oil, recent seal change |
| P-302/routine | Complete | Normal | A | Low | none supported | Everything at baseline; monitoring only |
| P-303/poor-data | Insufficient data | Degraded | D | Undetermined | none supported | Gaps, duplicates, conflicts, impossible values, no calibration |
| K-101/routine | Not examined | — | — | — | — | No profile for compressors; pump rules not applied |

## Changed files and why

| File | Change | Why |
| --- | --- | --- |
| `app.py` | Theme moved to `ui_theme`; charts restyled; Overview tiles; Ops Room hierarchy; flag-gated Brain page, button and summary; page errors contained and logged | Platform quality directive; Brain registration |
| `.streamlit/config.toml` | Dark base theme | Design system |
| `assets/live_sensor.html` | Dark styling, version 1.4 | Visual consistency (logic unchanged) |
| `plantproof/translations.py` | Arabic for new UI text | Bilingual UI |
| `README.md` | Brain section, verification tooling | Documentation |
| `tests/fake_streamlit.py` | Stop/rerun signals derive from BaseException, as in Streamlit | Page error containment must not swallow reruns; no assertion changed |
| `tests/test_app_smoke.py` | Flag off/on and broken-Brain tests | New behaviour |
| `tests/test_translations.py` | Also checks `reliability_ui.py` | Wider coverage, no assertion weakened |
| `scripts/check_pages.py` | Accepts any sensor widget 1.x | Version bump |
| New: `plantproof/reliability/**`, `reliability_ui.py`, `ui_theme.py`, `config/reliability/**`, `data/reliability/**`, `docs/**`, `tests/test_contracts.py`, `tests/test_rb_brain.py`, `scripts/coverage_report.py`, `scripts/ui_preview.py`, `.github/workflows/ui-preview.yml` | Brain, design system, tests, tooling | Mission scope |

Unchanged: every module in `plantproof/` that existed before, `config/hypotheses.json`,
`config/cost_assumptions.json`, `data/scenarios/*`, `data/reference_answers.json`.

## Implemented versus deferred

| Implemented | Deferred (reason) |
| --- | --- |
| 8-stage protocol, 6 divisions, orchestration with all statuses | Durable storage, login, private broker (only needed for real data) |
| Data-integrity grading and confidence cap | Profiles for motors, compressors, valves (need validated rules) |
| Sensor trust from calibration and cross-checks | Spectral vibration analysis (no spectral data) |
| Self-verification incl. independent fact check | Probabilistic risk and remaining useful life (no validated data) |
| Prioritised, evidence-linked recommendations | Optional language-model narrative (core works without it) |
| Knowledge store with human-confirmed outcomes | Language switching (UI is bilingual side by side instead) |
| Fleet view, asset registry, unsupported-type handling | PDF export (HTML report prints to PDF from the browser) |
| Reports: JSON, Markdown, CSV, printable HTML | |
| Design system, dark theme, Ops Room hierarchy, Brain workspace | |

## Readiness

Professional demo with synthetic data: yes. Controlled pilot or production: no — see
`SECURITY_AND_LIMITATIONS.md`.
