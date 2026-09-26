import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from artwork_cache_v2 import validate_entry
from entity_registry import load_registry
from sync_artwork_cache_v2 import build_entry, sync_entries


class ArtworkSyncTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.indexes = load_registry(ROOT / "data/entity-registry.json")
        self.now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        self.key = "competition:premier league"
        self.good = dict(name="Premier League", status="validated", resolverVersion=4,
                         url="https://example.invalid/approved.png", semanticStatus="validated",
                         fetchStatus="ok", visualStatus="approved", validatedAt="2026-09-23T00:00:00Z")
        self.previous = self.build(self.good)

    def build(self, legacy, previous=None):
        return build_entry(self.key, legacy, previous, self.registry, self.indexes, self.now)

    def test_http_failure_does_not_erase_previous_validated_logo(self):
        for legacy in ({}, {"status": "unresolved", "lastError": "HTTP Error 429"}):
            result = self.build(legacy, self.previous)
            self.assertTrue(validate_entry(self.key, result))
            self.assertEqual(result["artworkUrl"], self.good["url"])
            self.assertTrue(result["publishable"])

    def test_explicit_current_rejection_revokes_previous_logo(self):
        result = self.build({"status": "rejected", "resolverVersion": 4,
                             "rejectedReason": "wrong entity"}, self.previous)
        self.assertTrue(validate_entry(self.key, result))
        self.assertFalse(result["publishable"])
        self.assertIsNone(result["artworkUrl"])

    def test_missing_validation_gate_cannot_be_promoted(self):
        for field in ("semanticStatus", "fetchStatus", "visualStatus"):
            candidate = copy.deepcopy(self.good)
            candidate.pop(field)
            self.assertFalse(self.build(candidate)["publishable"])

    def test_v2_only_entry_is_preserved_by_next_sync(self):
        result = sync_entries({}, {self.key: self.previous}, self.registry, self.indexes, self.now)
        self.assertEqual(result[self.key], self.previous)

    def test_retry_date_is_not_postponed_on_every_sync(self):
        result = self.build({"status": "unresolved", "nextRetryAfter": "2026-09-23T01:00:00Z"})
        self.assertEqual(result["nextReviewAfter"], "2026-09-23T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
