import copy
import importlib.util
import json
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "artwork_cache_v2.py"
CACHE_PATH = ROOT / "data" / "artwork-cache-v2.json"
V1_PATH = ROOT / "data" / "artwork-cache.json"

SPEC = importlib.util.spec_from_file_location("gmtv_artwork_cache_v2", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArtworkCacheV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = MODULE.load_cache(CACHE_PATH)
        cls.v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))

    def test_every_v1_entry_is_preserved_in_v2(self):
        self.assertEqual(set(self.cache["entries"]), set(self.v1))

    def test_only_resolver_v4_validated_artwork_is_publishable(self):
        for key, old in self.v1.items():
            entry = self.cache["entries"][key]
            expected = bool(
                old.get("status") == "validated"
                and old.get("resolverVersion") == 4
                and old.get("url")
            )
            self.assertEqual(entry["publishable"], expected, key)
            if expected:
                self.assertEqual(entry["resolutionStatus"], "validated")
                self.assertEqual(entry["artworkUrl"], old["url"])
                self.assertEqual(MODULE.get_publishable_url(entry), old["url"])
            else:
                self.assertIsNone(entry["artworkUrl"])
                self.assertIsNone(MODULE.get_publishable_url(entry))

    def test_unresolved_entries_remain_retryable(self):
        unresolved = [
            entry
            for entry in self.cache["entries"].values()
            if entry["resolutionStatus"] == "unresolved"
        ]
        for entry in unresolved:
            retry_at = MODULE.parse_utc(entry["nextReviewAfter"])
            self.assertIsNotNone(retry_at)
            self.assertFalse(MODULE.should_retry(entry, retry_at - timedelta(seconds=1)))
            self.assertTrue(MODULE.should_retry(entry, retry_at))

    def test_known_registry_entities_keep_gm_ids(self):
        expected = {
            "competition:premier league": "competition:premier-league",
            "team:manchester city": "club:manchester-city",
            "team:manchester united": "club:manchester-united",
            "team:fulham": "club:fulham",
            "team:sunderland": "club:sunderland",
        }
        for key, gm_id in expected.items():
            if key in self.cache["entries"]:
                self.assertEqual(self.cache["entries"][key]["gmId"], gm_id)

    def test_nonvalidated_entry_cannot_be_flipped_publishable(self):
        target = next(
            copy.deepcopy(entry)
            for entry in self.cache["entries"].values()
            if entry["resolutionStatus"] != "validated"
        )
        target["artworkUrl"] = "https://example.invalid/logo.png"
        target["publishable"] = True
        with self.assertRaises(MODULE.ArtworkCacheValidationError):
            MODULE.validate_entry(target["cacheKey"], target)

    def test_schema_has_required_fields(self):
        required = {
            "cacheKey", "gmId", "entityType", "name", "wikidataQid",
            "resolutionStatus", "semanticStatus", "fetchStatus", "visualStatus",
            "artworkProvider", "artworkProperty", "artworkUrl", "candidateUrl",
            "publishable", "attemptCount", "lastAttemptAt", "nextReviewAfter",
            "rejectedReason", "rejectedAt", "provenance",
        }
        for entry in self.cache["entries"].values():
            self.assertTrue(required.issubset(entry))


if __name__ == "__main__":
    unittest.main()
