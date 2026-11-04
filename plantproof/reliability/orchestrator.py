"""Runs the eight examination stages in order and records every outcome.

A stage that raises is recorded as FAILED with its error (and logged); stages that depend
on a FAILED or BLOCKED stage are recorded as BLOCKED with the reason. No stage is skipped
silently, and nothing here can raise into the calling application except a bad case ID.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from . import BRAIN_VERSION, adapter
from .context import RunContext
from .registry import (PROFILE_DIR, REGISTRY_PATH, config_hash, find_case, load_profile, load_registry)
from .report import ExaminationReport, build_report
from .stages import (s1_asset_context, s2_data_integrity, s3_health, s4_causal, s5_risk,
                     s6_verification, s7_decisions, s8_knowledge)
from .types import StageResult, StageStatus

log = logging.getLogger("plantproof.reliability")


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    name: str
    division: str
    run: Callable[[RunContext], StageResult]
    depends_on: tuple[str, ...]


PROTOCOL = (
    StageSpec("S1", s1_asset_context.NAME, s1_asset_context.DIVISION, s1_asset_context.run, ()),
    StageSpec("S2", s2_data_integrity.NAME, s2_data_integrity.DIVISION, s2_data_integrity.run, ("S1",)),
    StageSpec("S3", s3_health.NAME, s3_health.DIVISION, s3_health.run, ("S1", "S2")),
    StageSpec("S4", s4_causal.NAME, s4_causal.DIVISION, s4_causal.run, ("S2", "S3")),
    StageSpec("S5", s5_risk.NAME, s5_risk.DIVISION, s5_risk.run, ("S3", "S4")),
    StageSpec("S6", s6_verification.NAME, s6_verification.DIVISION, s6_verification.run, ("S2", "S3", "S4", "S5")),
    StageSpec("S7", s7_decisions.NAME, s7_decisions.DIVISION, s7_decisions.run, ("S5", "S6")),
    StageSpec("S8", s8_knowledge.NAME, s8_knowledge.DIVISION, s8_knowledge.run, ("S4",)),
)


def _blocked(spec: StageSpec, why: str) -> StageResult:
    return StageResult(spec.stage_id, spec.name, spec.division, StageStatus.BLOCKED,
                       f"Not run: {why}.", "لم تُنفّذ هذه المرحلة.", limitations=(why,))


def run_examination(case_id: str, store: Any = None, knowledge: Any = None,
                    now: datetime | None = None, stages=PROTOCOL) -> ExaminationReport:
    """Examine one case. ``store`` is the platform's Store (read only); ``knowledge`` is a
    KnowledgeStore (read only during the run)."""
    t0 = time.perf_counter()
    assets = load_registry()
    asset, case = find_case(case_id, assets)            # a bad case ID is the caller's error
    profile = load_profile(asset.type)
    try:
        data = adapter.load_case(case, store)
    except Exception as exc:                            # unreadable source: report it, do not crash
        log.exception("reliability: cannot load case %s", case_id)
        data = None
        load_error = f"{type(exc).__name__}: {exc}"
    else:
        load_error = None
    ctx = RunContext(asset, case, profile, data, knowledge)
    fp_before = data.fingerprint if data else ""

    for spec in stages:
        if data is None:
            ctx.results[spec.stage_id] = _blocked(spec, f"case data could not be loaded ({load_error})")
            continue
        bad = [d for d in spec.depends_on if d in ctx.results and ctx.results[d].status.blocks_dependants]
        if bad:
            ctx.results[spec.stage_id] = _blocked(
                spec, f"depends on {', '.join(bad)} ({', '.join(ctx.results[d].status.value for d in bad)})")
            continue
        s = time.perf_counter()
        try:
            res = spec.run(ctx)
        except Exception as exc:
            log.error("reliability: stage %s failed on %s: %s", spec.stage_id, case_id, exc)
            res = StageResult(spec.stage_id, spec.name, spec.division, StageStatus.FAILED,
                              f"Stage failed: {type(exc).__name__}: {exc}", "فشلت هذه المرحلة.",
                              error="".join(traceback.format_exception_only(type(exc), exc)).strip())
        ctx.results[spec.stage_id] = _with_duration(res, (time.perf_counter() - s) * 1000)

    fp_after = adapter.fingerprint(data) if data else ""
    cfg_hash = config_hash(REGISTRY_PATH, *sorted(PROFILE_DIR.glob("*.json")), *adapter.ENGINE_CONFIG_FILES)
    return build_report(ctx, fp_before, fp_after, cfg_hash, BRAIN_VERSION,
                        (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                        (time.perf_counter() - t0) * 1000, load_error)


def _with_duration(res: StageResult, ms: float) -> StageResult:
    from dataclasses import replace
    return replace(res, duration_ms=round(ms, 2))


def run_all(store: Any = None, knowledge: Any = None, now: datetime | None = None) -> list[ExaminationReport]:
    """Examine every case in the registry (fleet view)."""
    return [run_examination(c.case_id, store, knowledge, now) for a in load_registry() for c in a.cases]
