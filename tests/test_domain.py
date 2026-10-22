import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from plantproof import data_gen
from plantproof.domain import (SCENARIO_DIR, ConfigError, Observation, load_engine_config,
                               load_scenario_index, parse_engine_config,
                               read_observations_csv, write_observations_csv)
from plantproof.domain import HYPOTHESES_PATH


class DomainTests(unittest.TestCase):
    def test_config_loads(self):
        cfg = load_engine_config()
        self.assertEqual({h.id for h in cfg.hypotheses},
                         {"bearing_wear", "sensor_fault", "cavitation", "misalignment"})
        self.assertIn("vibration_mm_s", cfg.limits)

    def test_invalid_config_rejected(self):
        raw = json.loads(HYPOTHESES_PATH.read_text(encoding="utf-8"))
        raw["hypotheses"][0]["supports"][0]["op"] = "~"
        with self.assertRaises(ConfigError):
            parse_engine_config(raw)
        raw = json.loads(HYPOTHESES_PATH.read_text(encoding="utf-8"))
        raw["hypotheses"][1]["id"] = raw["hypotheses"][0]["id"]
        with self.assertRaises(ConfigError):
            parse_engine_config(raw)

    def test_observation_is_immutable(self):
        o = read_observations_csv(SCENARIO_DIR / "scenario_A.csv")[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            o.value = 1.0

    def test_csv_round_trip(self):
        obs = data_gen.generate_scenario("A")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"
            write_observations_csv(obs, p)
            self.assertEqual(read_observations_csv(p), obs)

    def test_generator_is_deterministic_and_matches_committed_csv(self):
        for sid in data_gen.SCENARIOS:
            self.assertEqual(data_gen.generate_scenario(sid), data_gen.generate_scenario(sid))
            committed = read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")
            self.assertEqual(committed, data_gen.generate_scenario(sid),
                             f"Committed scenario_{sid}.csv is out of date; "
                             "run python -m plantproof.data_gen")

    def test_record_ids_unique_and_index_valid(self):
        for meta in load_scenario_index():
            obs = read_observations_csv(SCENARIO_DIR / meta["file"])
            ids = [o.record_id for o in obs]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(o.scenario_id == meta["id"] for o in obs))

    def test_bad_source_type_rejected(self):
        row = data_gen.generate_scenario("A")[0].to_dict() | {"source_type": "rumour"}
        with self.assertRaises(ValueError):
            Observation.from_dict(row)


if __name__ == "__main__":
    unittest.main()
