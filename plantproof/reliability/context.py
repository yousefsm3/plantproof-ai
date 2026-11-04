"""Run context shared by the stages of one examination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import adapter
from .registry import Asset, Case
from .types import Claim, ClaimKind, Record, StageResult


@dataclass
class RunContext:
    asset: Asset
    case: Case
    profile: dict[str, Any] | None
    data: adapter.CaseData | None
    knowledge: Any = None                       # KnowledgeStore or None
    results: dict[str, StageResult] = field(default_factory=dict)
    _cache: dict[tuple, Any] = field(default_factory=dict)

    # ---- records -------------------------------------------------------------
    @property
    def records(self) -> tuple[Record, ...]:
        return self.data.records if self.data else ()

    def usable_ids(self) -> frozenset[str] | None:
        """Record IDs the data-integrity stage accepted (None before that stage ran)."""
        s2 = self.results.get("S2")
        if s2 is None or "usable_ids" not in s2.data:
            return None
        return frozenset(s2.data["usable_ids"])

    def usable_records(self) -> tuple[Record, ...]:
        ids = self.usable_ids()
        return self.records if ids is None else tuple(r for r in self.records if r.record_id in ids)

    def sensor_series(self, param: str) -> list[Record]:
        return sorted((r for r in self.usable_records()
                       if r.source_type == "sensor" and r.parameter == param and r.value is not None),
                      key=lambda r: (r.timestamp, r.record_id))

    # ---- engine outputs, computed once per record set ------------------------------
    def _memo(self, kind: str, fn, ids: Iterable[str] | None):
        key = (kind, None if ids is None else frozenset(ids))
        if key not in self._cache:
            self._cache[key] = fn(self.data, None if ids is None else key[1])
        return self._cache[key]

    def engine(self, ids: Iterable[str] | None = None) -> adapter.EngineView:
        return self._memo("engine", adapter.engine_view, ids)

    def warning(self, ids: Iterable[str] | None = None) -> adapter.WarningView:
        return self._memo("warning", adapter.warning_view, ids)

    def checks(self, ids: Iterable[str] | None = None) -> tuple[dict, ...]:
        return self._memo("checks", adapter.next_checks, ids)

    # ---- profile helpers -------------------------------------------------------
    def label(self, param: str) -> str:
        if self.profile:
            if param in self.profile["sensors"]:
                return self.profile["sensors"][param]["label"]
            if param in self.profile["condition_bands"]:
                return self.profile["condition_bands"][param]["label"]
        return param.replace("_", " ")


class ClaimBuilder:
    """Numbers claims within a stage: S3-01, S3-02, …"""

    def __init__(self, stage_id: str):
        self.stage_id, self.n, self.items = stage_id, 0, []

    def add(self, kind: ClaimKind, text_en: str, text_ar: str = "", **kw) -> Claim:
        self.n += 1
        c = Claim(f"{self.stage_id}-{self.n:02d}", self.stage_id, kind, text_en, text_ar, **kw)
        self.items.append(c)
        return c

    def all(self) -> tuple[Claim, ...]:
        return tuple(self.items)
