"""Reliability Brain — a staged, evidence-grounded equipment examination.

An isolated package: nothing in the original platform imports it, and it only reads the
platform through ``adapter.py``. Remove this folder (and its one registration in app.py)
and PlantProof AI runs exactly as before.

Public API:
    run_examination(case_id, store=None, knowledge=None) -> ExaminationReport
    run_all(store=None, knowledge=None) -> list[ExaminationReport]
    load_registry() -> tuple[Asset, ...]
    KnowledgeStore
"""

BRAIN_VERSION = "1.0.0"

from .knowledge import KnowledgeStore  # noqa: E402
from .orchestrator import PROTOCOL, run_all, run_examination  # noqa: E402
from .registry import load_registry, supported_types  # noqa: E402

__all__ = ["BRAIN_VERSION", "KnowledgeStore", "PROTOCOL", "run_all", "run_examination",
           "load_registry", "supported_types"]
