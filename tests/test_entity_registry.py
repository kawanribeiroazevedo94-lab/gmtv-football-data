import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "entity_registry.py"
REGISTRY_PATH = ROOT / "data" / "entity-registry.json"

SPEC = importlib.util.spec_from_file_location("gmtv_entity_registry", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def synthetic_entity(gm_id, entity_type, name, external_ids=None, qid=None):
    return {
        "gmId": gm_id,
        "entityType": entity_type,
        "canonicalName": name,
        "aliases": [],
        "country": None,
        "externalIds": external_ids or {},
        "wikidataQid": qid,
        "validationStatus": "validated",
        "validatedAt": "2026-09-21",
        "confidence": "high",
        "resolutionStatus": "resolved",
    }


class RegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.indexes = MODULE.load_registry(REGISTRY_PATH)

    def test_registry_schema_and_required_fields(self):
        self.assertEqual(self.data["schema"], 1)
        self.assertGreaterEqual(len(self.data["entities"]), 12)
        required = {
            "gmId", "entityType", "canonicalName", "aliases", "country",
            "externalIds", "wikidataQid", "validationStatus", "validatedAt",
            "confidence", "resolutionStatus",
        }
        for entity in self.data["entities"]:
            self.assertTrue(required.issubset(entity.keys()))

    def test_seeded_aliases_resolve_to_stable_gm_ids(self):
        cases = {
            "Man City": "club:manchester-city",
            "Manchester City FC": "club:manchester-city",
            "Man United": "club:manchester-united",
            "Manchester United FC": "club:manchester-united",
            "Bayern München": "club:bayern-munich",
            "Bayern Munich": "club:bayern-munich",
            "Internazionale": "club:internazionale-milano",
            "Inter Milan": "club:internazionale-milano",
            "Atlético-MG": "club:atletico-mineiro",
            "Atlético Mineiro": "club:atletico-mineiro",
        }
        for name, expected in cases.items():
            self.assertEqual(
                MODULE.resolve_gm_id(
                    self.data, self.indexes, entity_type="club", name=name
                ),
                expected,
            )

    def test_ambiguous_substrings_are_not_accepted_as_aliases(self):
        for name in ("Inter", "United", "City", "Internacional"):
            self.assertIsNone(
                MODULE.resolve_gm_id(
                    self.data, self.indexes, entity_type="club", name=name
                )
            )

    def test_brazilian_a_b_cbf_and_national_team_are_independent(self):
        expected = {
            ("competition", "Brasileirão Série A"): "competition:brasileirao-serie-a",
            ("competition", "Brasileirão Série B"): "competition:brasileirao-serie-b",
            ("federation", "CBF"): "federation:cbf",
            ("national_team", "Seleção Brasileira"): "national-team:brazil",
        }
        resolved = []
        for (entity_type, name), gm_id in expected.items():
            value = MODULE.resolve_gm_id(
                self.data, self.indexes, entity_type=entity_type, name=name
            )
            self.assertEqual(value, gm_id)
            resolved.append(value)
        self.assertEqual(len(set(resolved)), 4)

    def test_entity_type_is_part_of_identity(self):
        self.assertIsNone(MODULE.resolve_gm_id(
            self.data, self.indexes, entity_type="competition", name="CBF"
        ))
        self.assertIsNone(MODULE.resolve_gm_id(
            self.data, self.indexes, entity_type="competition", name="Seleção Brasileira"
        ))
        self.assertIsNone(MODULE.resolve_gm_id(
            self.data, self.indexes, entity_type="national_team", name="Brasileirão Série A"
        ))

    def test_known_qids_from_audited_cache_resolve_by_type(self):
        expected = {
            ("club", "Q50602"): "club:manchester-city",
            ("club", "Q18656"): "club:manchester-united",
            ("club", "Q18708"): "club:fulham",
            ("club", "Q18739"): "club:sunderland",
            ("competition", "Q9448"): "competition:premier-league",
        }
        for (entity_type, qid), gm_id in expected.items():
            self.assertEqual(
                MODULE.resolve_gm_id(
                    self.data, self.indexes,
                    entity_type=entity_type, wikidata_qid=qid
                ),
                gm_id,
            )

    def test_external_ids_are_namespaced_by_provider_and_type(self):
        data = {
            "schema": 1,
            "entities": [
                synthetic_entity(
                    "club:alpha", "club", "Alpha",
                    {"provider-a": 123, "provider-b": 999}
                ),
                synthetic_entity(
                    "club:beta", "club", "Beta",
                    {"provider-b": 123}
                ),
                synthetic_entity(
                    "competition:alpha", "competition", "Alpha Competition",
                    {"provider-a": 123}
                ),
            ],
        }
        indexes = MODULE.validate_registry(data)
        self.assertEqual(
            MODULE.resolve_gm_id(
                data, indexes, entity_type="club",
                provider="provider-a", external_id=123
            ),
            "club:alpha",
        )
        self.assertEqual(
            MODULE.resolve_gm_id(
                data, indexes, entity_type="club",
                provider="provider-b", external_id=123
            ),
            "club:beta",
        )
        self.assertEqual(
            MODULE.resolve_gm_id(
                data, indexes, entity_type="competition",
                provider="provider-a", external_id=123
            ),
            "competition:alpha",
        )

    def test_conflicting_signals_fail_closed(self):
        data = {
            "schema": 1,
            "entities": [
                synthetic_entity(
                    "club:alpha", "club", "Alpha", {"provider-a": 1}, "Q101"
                ),
                synthetic_entity(
                    "club:beta", "club", "Beta", {"provider-a": 2}, "Q102"
                ),
            ],
        }
        indexes = MODULE.validate_registry(data)
        self.assertIsNone(
            MODULE.resolve_entity(
                data, indexes, entity_type="club",
                provider="provider-a", external_id=1, wikidata_qid="Q102"
            )
        )

    def test_duplicate_alias_in_same_type_is_rejected(self):
        data = copy.deepcopy(self.data)
        duplicate = synthetic_entity("club:fake-city", "club", "Man City")
        data["entities"].append(duplicate)
        with self.assertRaises(MODULE.RegistryValidationError):
            MODULE.validate_registry(data)

    def test_duplicate_external_id_same_provider_and_type_is_rejected(self):
        data = {
            "schema": 1,
            "entities": [
                synthetic_entity("club:alpha", "club", "Alpha", {"provider-a": 77}),
                synthetic_entity("club:beta", "club", "Beta", {"provider-a": 77}),
            ],
        }
        with self.assertRaises(MODULE.RegistryValidationError):
            MODULE.validate_registry(data)


if __name__ == "__main__":
    unittest.main()
