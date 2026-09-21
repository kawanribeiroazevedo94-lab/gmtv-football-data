import copy
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "artwork_cache_v2.py"
CACHE_PATH = ROOT / "data" / "artwork-cache-v2.json"
V1_PATH = ROOT / "data" / "artwork-cache.json"

SPEC = importlib.util.spec_from_file_location(
    "gmtv_artwork_cache_v2",
    MODULE_PATH,
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArtworkCacheV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = MODULE.load_cache(CACHE_PATH)
        cls.v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))

    def test_every_v1_entry_is_preserved_in_v2(self):
        self.assertEqual(
            set(self.cache["entries"]),
            set(self.v1),
        )

    def test_no_migrated_legacy_url_is_immediately_publishable(self):
        for entry in self.cache["entries"].values():
            self.assertFalse(entry["publishable"])
            self.assertIsNone(entry["artworkUrl"])
            self.assertIsNone(MODULE.get_publishable_url(entry))

    def test_legacy_urls_are_quarantined_as_candidates(self):
        for key, old in self.v1.items():
            entry = self.cache["entries"][key]
            if old.get("url") and old.get("status") != "rejected":
                self.assertEqual(
                    entry["resolutionStatus"],
                    "pending_review",
                )
                self.assertEqual(
                    entry["candidateUrl"],
                    old["url"],
                )
                self.assertEqual(
                    entry["artworkProvider"],
                    "wikidata",
                )
                self.assertEqual(
                    entry["artworkProperty"],
                    "legacy_unknown",
                )

    def test_rejected_entries_remain_rejected_and_non_retryable(self):
        keys = {
            "team:fulham",
            "team:manchester city",
            "team:manchester united",
            "team:sunderland",
        }
        for key in keys:
            entry = self.cache["entries"][key]
            self.assertEqual(entry["resolutionStatus"], "rejected")
            self.assertEqual(entry["semanticStatus"], "rejected")
            self.assertFalse(entry["publishable"])
            self.assertIsNone(entry["artworkUrl"])
            self.assertIsNone(entry["candidateUrl"])
            self.assertFalse(MODULE.should_retry(entry))

    def test_unresolved_null_is_not_eternal(self):
        unresolved = [
            entry
            for entry in self.cache["entries"].values()
            if entry["resolutionStatus"] == "unresolved"
        ]
        self.assertTrue(unresolved)

        for entry in unresolved:
            retry_at = MODULE.parse_utc(entry["nextReviewAfter"])
            self.assertIsNotNone(retry_at)
            self.assertFalse(
                MODULE.should_retry(
                    entry,
                    retry_at - timedelta(seconds=1),
                )
            )
            self.assertTrue(
                MODULE.should_retry(
                    entry,
                    retry_at,
                )
            )

    def test_pending_review_is_retryable_on_schedule(self):
        pending = [
            entry
            for entry in self.cache["entries"].values()
            if entry["resolutionStatus"] == "pending_review"
        ]
        self.assertTrue(pending)
        for entry in pending:
            retry_at = MODULE.parse_utc(entry["nextReviewAfter"])
            self.assertTrue(
                MODULE.should_retry(entry, retry_at)
            )

    def test_known_registry_entities_receive_gm_ids(self):
        expected = {
            "competition:premier league":
                "competition:premier-league",
            "team:manchester city":
                "club:manchester-city",
            "team:manchester united":
                "club:manchester-united",
            "team:fulham":
                "club:fulham",
            "team:sunderland":
                "club:sunderland",
        }
        for key, gm_id in expected.items():
            self.assertEqual(
                self.cache["entries"][key]["gmId"],
                gm_id,
            )

    def test_rejected_entry_cannot_be_flipped_publishable(self):
        entry = copy.deepcopy(
            self.cache["entries"]["team:manchester city"]
        )
        entry["publishable"] = True
        with self.assertRaises(
            MODULE.ArtworkCacheValidationError
        ):
            MODULE.validate_entry(
                entry["cacheKey"],
                entry,
            )

    def test_unvalidated_candidate_cannot_be_promoted_by_url_only(self):
        pending = next(
            copy.deepcopy(entry)
            for entry in self.cache["entries"].values()
            if entry["resolutionStatus"] == "pending_review"
        )
        pending["artworkUrl"] = pending["candidateUrl"]
        pending["publishable"] = True

        with self.assertRaises(
            MODULE.ArtworkCacheValidationError
        ):
            MODULE.validate_entry(
                pending["cacheKey"],
                pending,
            )

    def test_schema_has_required_provenance_and_validation_fields(self):
        required = {
            "cacheKey",
            "gmId",
            "entityType",
            "name",
            "wikidataQid",
            "resolutionStatus",
            "semanticStatus",
            "fetchStatus",
            "visualStatus",
            "artworkProvider",
            "artworkProperty",
            "artworkUrl",
            "candidateUrl",
            "publishable",
            "attemptCount",
            "lastAttemptAt",
            "nextReviewAfter",
            "rejectedReason",
            "rejectedAt",
            "provenance",
        }
        for entry in self.cache["entries"].values():
            self.assertTrue(required.issubset(entry))


if __name__ == "__main__":
    unittest.main()
