"""Core, immutable types shared by every Reliability Brain stage.

Nothing here imports the original platform except the frozen ``Observation`` type, which
the adapter copies into ``Record`` before any stage sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class StageStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"                              # the stage raised an error
    BLOCKED = "blocked"                            # a prerequisite failed or is unsupported
    INSUFFICIENT_DATA = "insufficient_data"        # ran, but the data cannot support a result
    VERIFICATION_REJECTED = "verification_rejected"
    AWAITING_EVIDENCE = "awaiting_evidence"        # ran; a conclusion needs more evidence

    @property
    def blocks_dependants(self) -> bool:
        return self in (StageStatus.FAILED, StageStatus.BLOCKED)


class ClaimKind(str, Enum):
    """What kind of statement a claim is. The report keeps these apart."""
    MEASURED = "measured"            # a value read from a record
    FACT = "fact"                    # a property of the data itself (count, date, presence)
    FINDING = "finding"              # an analytical result computed from records
    HYPOTHESIS = "hypothesis"        # a possible explanation, never a conclusion
    ASSUMPTION = "assumption"        # something taken as given, stated openly
    UNCERTAINTY = "uncertainty"      # a known limit of what can be said
    MISSING = "missing"              # information that is needed and absent
    RECOMMENDATION = "recommendation"


class Verification(str, Enum):
    UNCHECKED = "unchecked"
    VERIFIED = "verified"            # evidence exists and re-checks independently
    SUPPORTED = "supported"          # evidence exists; cannot be fully confirmed (e.g. gaps)
    DOWNGRADED = "downgraded"        # confidence lowered by verification
    REJECTED = "rejected"            # evidence missing or contradicts the claim
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class Record:
    """The Brain's own copy of one source record."""
    record_id: str
    case_id: str
    timestamp: str
    asset_id: str
    source_type: str
    parameter: str
    value: float | None
    unit: str
    status: str | None
    subject: str | None
    text: str
    source: str

    @property
    def ts(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


@dataclass(frozen=True)
class RejectedRow:
    """A source row that could not be read; kept so the data-quality stage can report it."""
    row_number: int
    record_id: str
    reason: str


@dataclass(frozen=True)
class Check:
    """A machine-checkable form of a claim, re-evaluated by the verification stage.

    op: '>' '<' '>=' '<=' on ``value`` of the cited records of ``parameter``;
    mode: 'any' (at least one cited record satisfies it), 'all', or 'latest'.
    """
    parameter: str
    op: str
    threshold: float
    mode: str = "any"


@dataclass(frozen=True)
class Claim:
    claim_id: str
    stage_id: str
    kind: ClaimKind
    text_en: str
    text_ar: str = ""
    evidence: tuple[str, ...] = ()          # record IDs
    finding_refs: tuple[str, ...] = ()      # Evidence Engine finding IDs (C-01, M-02, S-…)
    confidence: float | None = None
    check: Check | None = None
    key: bool = False                       # a key claim: its rejection fails verification
    verification: Verification = Verification.UNCHECKED
    verification_note: str = ""


@dataclass(frozen=True)
class Recommendation:
    rec_id: str
    priority: str                # P1 urgent, P2 soon, P3 routine
    category: str                # escalate | data | resolve | diagnose | hold | if_confirmed | review | monitor
    action_en: str
    action_ar: str
    justification: str
    evidence: tuple[str, ...]
    risk_addressed: str
    confidence: str              # High | Medium | Low
    missing_info: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    name: str
    division: str
    status: StageStatus
    summary_en: str = ""
    summary_ar: str = ""
    claims: tuple[Claim, ...] = ()
    data: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    limitations: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    error: str | None = None
    duration_ms: float = 0.0


def frozen_map(d: dict[str, Any]) -> Mapping[str, Any]:
    """Read-only view used for a stage's structured outputs."""
    return MappingProxyType(dict(d))
