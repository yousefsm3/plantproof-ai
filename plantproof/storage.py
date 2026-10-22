"""SQLite storage for observations and investigation history.

PERSISTENCE WARNING
Streamlit Community Cloud does not guarantee that local files survive a
restart, reboot, redeploy or sleep. The SQLite file can be wiped at any time.
- Demo observations are re-seeded automatically from data/scenarios/*.csv.
- Investigation history (investigations, What If runs, Blind Test results,
  handovers) is lost unless exported. Use export_history() / import_history()
  (the History page has buttons for both).

Observations are protected by SQLite triggers: once seeded they cannot be
UPDATEd or DELETEd. Only reset_observations() (drop and re-seed) replaces them.
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

from .domain import (OBS_FIELDS, PROJECT_ROOT, SCENARIO_DIR, Observation,
                     load_scenario_index, read_observations_csv)

HISTORY_KINDS = ("investigation", "whatif", "blind_test", "handover")
EXPORT_FORMAT = "plantproof-history"
EXPORT_VERSION = 1
MAX_IMPORT_ENTRIES = 5000


def default_db_path() -> Path:
    env = os.environ.get("PLANTPROOF_DB")
    return Path(env) if env else PROJECT_ROOT / ".runtime" / "plantproof.db"


_OBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    record_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    asset_id TEXT,
    source_type TEXT NOT NULL,
    parameter TEXT NOT NULL,
    value REAL,
    unit TEXT,
    status TEXT,
    subject TEXT,
    text TEXT,
    source TEXT,
    hypothetical INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_obs_scenario ON observations(scenario_id);
CREATE TRIGGER IF NOT EXISTS obs_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are read-only'); END;
CREATE TRIGGER IF NOT EXISTS obs_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are read-only'); END;
"""

_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    uid TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    title TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_kind ON history(kind, created_at);
"""


class Store:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # A short-lived connection per operation is safe with Streamlit's threads.
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_OBS_SCHEMA + _HISTORY_SCHEMA)

    # ------------------------------------------------------------ observations
    def observation_count(self, scenario_id: str | None = None) -> int:
        with self._conn() as c:
            if scenario_id:
                row = c.execute("SELECT COUNT(*) FROM observations WHERE scenario_id=?",
                                (scenario_id,)).fetchone()
            else:
                row = c.execute("SELECT COUNT(*) FROM observations").fetchone()
        return int(row[0])

    def seed_if_empty(self, scenario_dir: Path = SCENARIO_DIR) -> int:
        if self.observation_count() > 0:
            return 0
        rows = []
        for meta in load_scenario_index(scenario_dir / "index.json"):
            rows += read_observations_csv(scenario_dir / meta["file"])
        with self._conn() as c:
            c.executemany(
                f"INSERT INTO observations ({', '.join(OBS_FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in OBS_FIELDS)})",
                [tuple(int(v) if isinstance(v, bool) else v
                       for v in (getattr(o, f) for f in OBS_FIELDS)) for o in rows])
        return len(rows)

    def observations(self, scenario_id: str) -> tuple[Observation, ...]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM observations WHERE scenario_id=? "
                             "ORDER BY timestamp, record_id", (scenario_id,)).fetchall()
        return tuple(Observation.from_dict(dict(r) | {"hypothetical": bool(r["hypothetical"])})
                     for r in rows)

    def reset_observations(self, scenario_dir: Path = SCENARIO_DIR) -> int:
        """Drop and re-seed the demo observations. History is kept."""
        with self._conn() as c:
            c.executescript("DROP TABLE IF EXISTS observations;")
        self.init_schema()
        return self.seed_if_empty(scenario_dir)

    # ----------------------------------------------------------------- history
    def save(self, kind: str, scenario_id: str, title: str, payload: dict[str, Any]) -> str:
        if kind not in HISTORY_KINDS:
            raise ValueError(f"Unknown history kind: {kind}")
        uid = uuid.uuid4().hex
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._conn() as c:
            c.execute("INSERT INTO history VALUES (?,?,?,?,?,?)",
                      (uid, kind, created, scenario_id, title.strip()[:200] or kind,
                       json.dumps(payload, ensure_ascii=False)))
        return uid

    def list_history(self, kind: str | None = None,
                     scenario_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM history WHERE 1=1", []
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if scenario_id:
            q += " AND scenario_id=?"
            args.append(scenario_id)
        q += " ORDER BY created_at DESC, uid"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    def get(self, uid: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM history WHERE uid=?", (uid,)).fetchone()
        return None if r is None else dict(r) | {"payload": json.loads(r["payload"])}

    def delete(self, uid: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM history WHERE uid=?", (uid,))
        return cur.rowcount > 0

    def clear_history(self) -> int:
        with self._conn() as c:
            cur = c.execute("DELETE FROM history")
        return cur.rowcount

    # ---------------------------------------------------------- export/import
    def export_history(self) -> dict[str, Any]:
        entries = self.list_history()
        return {
            "format": EXPORT_FORMAT,
            "version": EXPORT_VERSION,
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "entries": [{k: e[k] for k in ("uid", "kind", "created_at", "scenario_id",
                                            "title", "payload")} for e in entries],
        }

    def export_history_json(self) -> str:
        return json.dumps(self.export_history(), indent=2, ensure_ascii=False)

    def import_history(self, data: dict[str, Any] | str | bytes) -> dict[str, int]:
        """Import an export file. Existing entries (same uid) are skipped."""
        if isinstance(data, (str, bytes)):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Not a valid JSON file: {exc}") from exc
        if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
            raise ValueError("This is not a PlantProof history export file.")
        if data.get("version") != EXPORT_VERSION:
            raise ValueError(f"Unsupported export version: {data.get('version')}")
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError("Export file has no 'entries' list.")
        if len(entries) > MAX_IMPORT_ENTRIES:
            raise ValueError(f"Too many entries (max {MAX_IMPORT_ENTRIES}).")

        clean = []
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                raise ValueError(f"Entry {i} is not an object.")
            missing = [k for k in ("uid", "kind", "created_at", "scenario_id", "title",
                                   "payload") if k not in e]
            if missing:
                raise ValueError(f"Entry {i} is missing: {', '.join(missing)}")
            if e["kind"] not in HISTORY_KINDS:
                raise ValueError(f"Entry {i} has unknown kind '{e['kind']}'.")
            if not isinstance(e["payload"], dict):
                raise ValueError(f"Entry {i} payload must be an object.")
            clean.append((str(e["uid"])[:64], e["kind"], str(e["created_at"])[:32],
                          str(e["scenario_id"])[:16], str(e["title"])[:200],
                          json.dumps(e["payload"], ensure_ascii=False)))

        inserted = 0
        with self._conn() as c:
            for row in clean:
                cur = c.execute("INSERT OR IGNORE INTO history VALUES (?,?,?,?,?,?)", row)
                inserted += cur.rowcount
        return {"inserted": inserted, "skipped": len(clean) - inserted}
