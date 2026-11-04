"""Knowledge Engine storage: the Brain's own SQLite file with ``rb_`` tables.

It never touches the platform's database. An investigation saved here is only a record of
what the Brain concluded; a mechanism becomes knowledge only when a person records a
confirmed (or ruled-out) outcome against it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..domain import PROJECT_ROOT

OUTCOMES = ("confirmed", "ruled_out")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS rb_investigations (
    uid TEXT PRIMARY KEY, created_at TEXT NOT NULL, asset_id TEXT NOT NULL, case_id TEXT NOT NULL,
    report_id TEXT NOT NULL UNIQUE, input_fingerprint TEXT NOT NULL, config_hash TEXT NOT NULL,
    brain_version TEXT NOT NULL, leading TEXT, leading_confidence REAL, risk TEXT, condition TEXT,
    signature TEXT NOT NULL, summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rb_outcomes (
    uid TEXT PRIMARY KEY, investigation_uid TEXT NOT NULL REFERENCES rb_investigations(uid),
    created_at TEXT NOT NULL, mechanism TEXT NOT NULL, outcome TEXT NOT NULL,
    recorded_by_role TEXT NOT NULL, note TEXT NOT NULL, evidence TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rb_inv_asset ON rb_investigations(asset_id, created_at);
"""


def default_path() -> Path:
    env = os.environ.get("PLANTPROOF_RB_DB")
    return Path(env) if env else PROJECT_ROOT / ".runtime" / "reliability.db"


class KnowledgeStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- investigations ------------------------------------------------------
    def save_investigation(self, report: Any) -> str:
        """Save a report summary; saving the same report twice returns the first record."""
        with self._conn() as c:
            row = c.execute("SELECT uid FROM rb_investigations WHERE report_id=?", (report.report_id,)).fetchone()
            if row:
                return row["uid"]
            uid = uuid.uuid4().hex[:12]
            c.execute("INSERT INTO rb_investigations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                uid, datetime.now(timezone.utc).isoformat(timespec="seconds"), report.asset_id, report.case_id,
                report.report_id, report.input_fingerprint, report.config_hash, report.brain_version,
                report.leading, report.leading_confidence, report.risk, report.condition,
                json.dumps(sorted(report.signature)), json.dumps(report.summary_dict())))
            return uid

    def list_investigations(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM rb_investigations", ()
        if asset_id:
            q, args = q + " WHERE asset_id=?", (asset_id,)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q + " ORDER BY created_at DESC, uid", args)]
        for r in rows:
            r["signature"] = json.loads(r["signature"])
            r["summary"] = json.loads(r["summary"])
            r["outcomes"] = self.outcomes(r["uid"])
        return rows

    def get(self, uid: str) -> dict[str, Any] | None:
        return next((r for r in self.list_investigations() if r["uid"] == uid), None)

    # ---- outcomes: the only route into knowledge ------------------------------
    def record_outcome(self, investigation_uid: str, mechanism: str, outcome: str, recorded_by_role: str,
                       note: str = "", evidence: tuple[str, ...] = ()) -> str:
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}")
        if not recorded_by_role.strip():
            raise ValueError("an outcome needs the role of the person recording it")
        if not mechanism.strip():
            raise ValueError("an outcome needs a mechanism")
        with self._conn() as c:
            if not c.execute("SELECT 1 FROM rb_investigations WHERE uid=?", (investigation_uid,)).fetchone():
                raise ValueError(f"unknown investigation '{investigation_uid}'")
            uid = uuid.uuid4().hex[:12]
            c.execute("INSERT INTO rb_outcomes VALUES (?,?,?,?,?,?,?,?)", (
                uid, investigation_uid, datetime.now(timezone.utc).isoformat(timespec="seconds"), mechanism,
                outcome, recorded_by_role.strip()[:80], note.strip()[:1000], json.dumps(list(evidence))))
            return uid

    def outcomes(self, investigation_uid: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM rb_outcomes WHERE investigation_uid=? ORDER BY created_at, uid", (investigation_uid,))]
        for r in rows:
            r["evidence"] = json.loads(r["evidence"])
        return rows

    def knowledge(self) -> dict[str, dict[str, Any]]:
        """mechanism -> confirmed and ruled-out cases, each traceable to its investigation."""
        out: dict[str, dict[str, Any]] = {}
        for inv in self.list_investigations():
            for o in inv["outcomes"]:
                k = out.setdefault(o["mechanism"], {"confirmed": [], "ruled_out": []})
                k[o["outcome"]].append({"investigation": inv["uid"], "asset_id": inv["asset_id"],
                                        "case_id": inv["case_id"], "signature": inv["signature"],
                                        "note": o["note"], "recorded_by_role": o["recorded_by_role"]})
        return out

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM rb_outcomes")
            c.execute("DELETE FROM rb_investigations")


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Side-by-side difference of two saved investigations."""
    sa, sb = set(a["signature"]), set(b["signature"])
    return {"same_asset": a["asset_id"] == b["asset_id"],
            "leading": (a["leading"], b["leading"]),
            "confidence": (a["leading_confidence"], b["leading_confidence"]),
            "risk": (a["risk"], b["risk"]),
            "shared_indicators": sorted(sa & sb), "only_first": sorted(sa - sb), "only_second": sorted(sb - sa)}
