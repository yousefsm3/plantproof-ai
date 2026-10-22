import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from plantproof.domain import SCENARIO_DIR, read_observations_csv
from plantproof.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.store.seed_if_empty()

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_matches_csv_and_is_idempotent(self):
        for sid in ("A", "B"):
            self.assertEqual(list(self.store.observations(sid)),
                             read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv"))
        self.assertEqual(self.store.seed_if_empty(), 0)

    def test_observations_are_read_only(self):
        with sqlite3.connect(self.store.db_path) as c:
            with self.assertRaises(sqlite3.DatabaseError):
                c.execute("UPDATE observations SET value = 0 WHERE record_id = 'A-LAB-0001'")
            with self.assertRaises(sqlite3.DatabaseError):
                c.execute("DELETE FROM observations")
        self.assertEqual(self.store.observation_count("A"), 202)

    def test_history_crud(self):
        uid = self.store.save("investigation", "A", "Test", {"notes": "hello"})
        self.assertEqual(self.store.get(uid)["payload"]["notes"], "hello")
        self.assertEqual(len(self.store.list_history("investigation", "A")), 1)
        self.assertEqual(self.store.list_history("investigation", "B"), [])
        self.assertTrue(self.store.delete(uid))
        self.assertIsNone(self.store.get(uid))
        with self.assertRaises(ValueError):
            self.store.save("gossip", "A", "x", {})

    def test_export_import_round_trip(self):
        self.store.save("investigation", "A", "Inv", {"n": 1})
        self.store.save("handover", "B", "Hand", {"markdown": "# hi"})
        exported = self.store.export_history_json()
        other = Store(Path(self.tmp.name) / "other.db")
        self.assertEqual(other.import_history(exported), {"inserted": 2, "skipped": 0})
        self.assertEqual(other.import_history(exported), {"inserted": 0, "skipped": 2})
        self.assertEqual(json.loads(other.export_history_json())["entries"],
                         json.loads(exported)["entries"])

    def test_import_rejects_bad_files(self):
        for bad in ("not json", json.dumps({"format": "other"}),
                    json.dumps({"format": "plantproof-history", "version": 99, "entries": []}),
                    json.dumps({"format": "plantproof-history", "version": 1,
                                "entries": [{"uid": "x"}]}),
                    json.dumps({"format": "plantproof-history", "version": 1,
                                "entries": [{"uid": "x", "kind": "evil", "created_at": "",
                                             "scenario_id": "A", "title": "", "payload": {}}]})):
            with self.assertRaises(ValueError):
                self.store.import_history(bad)

    def test_reset_keeps_history(self):
        self.store.save("whatif", "A", "Run", {})
        self.assertEqual(self.store.reset_observations(), 403)
        self.assertEqual(len(self.store.list_history()), 1)


if __name__ == "__main__":
    unittest.main()
