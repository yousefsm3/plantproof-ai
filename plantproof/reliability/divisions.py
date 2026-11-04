"""The six intelligence divisions and the eight examination stages they own."""

from __future__ import annotations

from .types import StageStatus

DIVISIONS = (
    ("Asset Intelligence", "ذكاء المعدات", ("S1", "S3"),
     "What the equipment is, what data exists for it, and its present condition."),
    ("Trust & Verification", "الثقة والتحقق", ("S2", "S6"),
     "Whether the data can be trusted, and whether the Brain's own claims hold up."),
    ("Causal Reasoning", "الاستدلال السببي", ("S4",),
     "Which failure mechanisms the evidence supports, contradicts or leaves open."),
    ("Failure Risk", "مخاطر العطل", ("S5",),
     "How severe a failure would be and how strong the evidence for it is."),
    ("Decision Intelligence", "ذكاء القرار", ("S7",),
     "What to do next, in priority order, with the evidence for each step."),
    ("Knowledge Engine", "محرك المعرفة", ("S8",),
     "What earlier, confirmed investigations add; unconfirmed ones stay unresolved."),
)

# severity order used to summarise a division from its stages (worst first)
_WORST = (StageStatus.FAILED, StageStatus.BLOCKED, StageStatus.VERIFICATION_REJECTED,
          StageStatus.INSUFFICIENT_DATA, StageStatus.AWAITING_EVIDENCE, StageStatus.PENDING,
          StageStatus.COMPLETED)


def division_status(stages: dict[str, StageStatus], stage_ids: tuple[str, ...]) -> StageStatus:
    present = [stages[s] for s in stage_ids if s in stages]
    if not present:
        return StageStatus.PENDING
    return min(present, key=_WORST.index)
