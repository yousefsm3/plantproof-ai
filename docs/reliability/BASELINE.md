# Phase 0 baseline (before the Reliability Brain)

Recorded on 2026-11-04 on branch `reliability-brain`, created from `main`.

| Item | Value |
| --- | --- |
| Base commit | `d69624a70c32694363ac1cb5df1323813944731e` ("Use the real Yaqen AI logo (network Y) in the brand signature") |
| Python (local) | 3.13; Streamlit Cloud runs 3.12 |
| Runtime dependencies | streamlit 1.65.0, plotly 6.9.0, numpy >=1.26,<3 |
| Tests before Phase 0 | 95, all passing (`python -m unittest discover -s tests -t .`) |
| Tests added in Phase 0 | 7 contract and golden-output tests (`tests/test_contracts.py`) |
| Statement coverage | 92.6% (2,288 of 2,472), measured with `scripts/coverage_report.py` |

## Golden outputs pinned by `tests/test_contracts.py`

| Scenario | Input fingerprint | Leading hypothesis | Contradictions | Missing | Early-warning lead |
| --- | --- | --- | --- | --- | --- |
| A | 9419075f6f336a95 | bearing_wear 0.81 (High) | C-01, C-02 | M-01, M-02 | 12 h |
| B | 3d837dd4efb8c033 | sensor_fault 0.608 (High) | C-01, C-02 | M-01, M-02, M-03 | 0 h |
| C | d5ddc769a3a6e78e | seal_failure 0.90 (High) | C-01 | M-01, M-02 | 19 h |

## Interfaces the Brain is allowed to read

`domain` (types, `load_engine_config`, `load_scenario_index`, `read_observations_csv`),
`evidence_engine.analyse`, `early_warning.detect`, `cost_model.estimate` and
`load_cost_assumptions`, `advisor.next_best_checks`, `fact_check.check`, `whatif.fingerprint`,
and `Store.observations`. All are pinned by the contract tests above.
