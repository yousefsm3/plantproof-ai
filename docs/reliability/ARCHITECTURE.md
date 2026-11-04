# Reliability Brain — architecture and examination protocol

The Reliability Brain is an isolated package (`plantproof/reliability/`) that examines one
equipment case in eight ordered stages and produces a traceable engineering report. It does
not replace any PlantProof feature: it reads their results through one adapter and adds what
they do not do — data-integrity grading, sensor trust, confidence adjustment, mechanism
coverage, risk triage, self-verification, prioritised decisions and investigation memory.

## Package layout

```
plantproof/reliability/
  __init__.py        public API, BRAIN_VERSION
  types.py           frozen types: Record, Claim, Check, StageResult, Recommendation, enums
  registry.py        asset registry + examination profiles (config/reliability/)
  adapter.py         the ONLY bridge to the original platform (read-only)
  context.py         per-run context, memoised engine calls, claim numbering
  orchestrator.py    PROTOCOL, run_examination(), run_all()
  divisions.py       six divisions and their stages
  report.py          ExaminationReport, 17 sections, JSON/Markdown/CSV/HTML
  knowledge.py       KnowledgeStore: own SQLite file, rb_ tables
  fixtures.py        deterministic generator for the Brain-only synthetic assets
  stages/s1..s8      one module per stage
reliability_ui.py    Streamlit workspace (loaded only when the flag is on)
config/reliability/  assets.json, profiles/centrifugal_pump.json
data/reliability/    P-302, P-303, K-101 fixtures; known_answers.json
```

## Isolation rules (all enforced by tests)

| Rule | How it is enforced |
| --- | --- |
| No original module imports the Brain | AST test over `plantproof/*.py` (`IsolationAndImmutabilityTests`) |
| The adapter uses only public names | AST test on `adapter.py` |
| Original data, config and store unchanged | file-bytes, fingerprint and store-count tests |
| Inputs copied into frozen Brain types | `Record` is frozen; stage outputs are read-only mappings |
| Own storage | `KnowledgeStore` writes only `rb_investigations`, `rb_outcomes` in `PLANTPROOF_RB_DB` (default `.runtime/reliability.db`) |
| Own session keys | all start with `rb_` |
| Feature flag | `PLANTPROOF_RELIABILITY=1` (env or root-level Streamlit secret); off = the Brain module is never imported |
| Removable | delete `plantproof/reliability/`, `reliability_ui.py`, `config/reliability/`, `data/reliability/` and the `RB` entries in `app.py`; the original 95 tests and contract tests still pass |

## Examination protocol

| Stage | Division | Purpose | Key outputs | Can end as |
| --- | --- | --- | --- | --- |
| S1 Asset identity and context | Asset Intelligence | Identify the asset, its profile, records, parameters; list unknown specifications | supported, sensors present/absent, unknown specs, events | completed, blocked (unsupported type), insufficient data |
| S2 Data integrity and evidence | Trust & Verification | Eight checks (D1–D8): unreadable rows, duplicate IDs, conflicting and repeated readings, implausible values, series completeness, traceability, sensor trust (calibration, independent cross-checks) | grade A–D, confidence cap, usable record IDs, per-sensor trust | completed, insufficient data |
| S3 Equipment health | Asset Intelligence | Baseline, latest, deviation, trend and alarm status per sensor; lab/inspection bands; learned-baseline anomaly (existing model) | per-parameter status, overall condition, anomaly | completed, insufficient data |
| S4 Failure mechanisms and causes | Causal Reasoning | Re-run the existing Evidence Engine on usable records; adjust confidence; compare typical indicators; name unscored mechanisms; rank discriminating checks | ranking with formula, leading explanation, checks | completed, awaiting evidence |
| S5 Failure risk and degradation | Failure Risk | Severity (consequence × criticality) × evidence strength → risk; trend; early warning; illustrative cost; explicit no-probability and no-RUL statements | risk, basis, trend, exposure | completed, insufficient data |
| S6 Independent verification | Trust & Verification | Re-check every claim of S1–S5 (record existence, finding existence, numeric re-evaluation, evidence presence, label justification, contradictions addressed, independent fact check) | verdict per claim, label overrides | completed, verification rejected |
| S7 Engineering decisions | Decision Intelligence | Prioritised recommendations (P1–P3) with justification, evidence, risk addressed, confidence, missing information | recommendations | completed |
| S8 Knowledge and memory | Knowledge Engine | Earlier investigations; confirmed vs unresolved; similar confirmed cases | previous, similar, knowledge counts | completed |

Dependencies: a stage whose prerequisite is FAILED or BLOCKED is recorded as BLOCKED with the
reason. A stage that raises is recorded as FAILED with its error and logged. Nothing is
skipped silently.

## Evidence and confidence rules

* Every claim is typed: measured, fact, finding, hypothesis, assumption, uncertainty, missing,
  recommendation. The report keeps them apart.
* A claim cites record IDs and/or Evidence Engine finding IDs. Claims with a `Check`
  (parameter, operator, threshold, mode) are re-evaluated by S6 against the cited records.
* Adjusted confidence = engine confidence × data-quality cap (A 1.0, B 0.9, C 0.75, D 0.5)
  × sensor-trust factor (0.7 when a non-instrument hypothesis relies on a disputed sensor).
* Levels use the engine thresholds (High ≥ 0.6, Medium ≥ 0.3). S6 downgrades High to
  Medium while required evidence is missing. Hypotheses are never marked verified.
* Confidence is evidence strength, never a probability. No failure probability and no
  remaining useful life are produced.
* Only a person-recorded outcome (confirmed or ruled out) turns a mechanism into knowledge.

## Multi-asset extension

An asset type is supported only when `config/reliability/profiles/<type>.json` exists. A
profile defines sensors and plausibility ranges, condition bands, calibrations, cross-check
pairs, failure modes (with consequence, indicators, discriminating checks) and spec fields.
To add electric motors, for example: write `profiles/electric_motor.json`, register motor
assets in `assets.json`, add known-answer cases and tests. Until then motors are reported as
not supported, as the K-101 compressor is today. Engine hypotheses come from the existing
`config/hypotheses.json`, which is pump-specific; a new type needs its own rule set before
its mechanisms can be scored.

## Deferred (not implemented)

| Item | Why deferred |
| --- | --- |
| Durable storage, authentication, private broker (Phase 6) | Only needed for real data; not justified for the synthetic demo. See SECURITY_AND_LIMITATIONS.md. |
| Profiles for motors, compressors, valves | Need validated rules and test cases first |
| Spectral vibration analysis | No spectral data in the records |
| Probabilistic risk, remaining useful life | No validated run-to-failure data |
| Optional language-model narrative | Would need strict grounding through S6; the core works without it |
