import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from artwork_cache_v2 import load_cache
from entity_registry import load_registry
from feed_v2 import build_feed_v2, validate_feed_v2

REGISTRY_PATH = ROOT / "data" / "entity-registry.json"
CACHE_PATH = ROOT / "data" / "artwork-cache-v2.json"
V2_PATH = ROOT / "data" / "football-feed-v2.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "update-football-feed.yml"


def synthetic_feed():
    match = {
        "id": "fd:fixture-1",
        "date": "2026-09-21",
        "kickoff": "16:00",
        "utcDate": "2026-09-21T19:00:00Z",
        "status": "SCHEDULED",
        "competition": {
            "id": 2021,
            "code": "PL",
            "name": "Premier League",
            "logo": "https://legacy.invalid/pl.png",
            "normalized": "premier league",
        },
        "home": {
            "id": 65,
            "name": "Man City",
            "fullName": "Manchester City FC",
            "crest": "https://legacy.invalid/city.png",
            "normalized": "man city",
        },
        "away": {
            "id": 999999,
            "name": "Example Unknown",
            "fullName": "Example Unknown FC",
            "crest": None,
            "normalized": "example unknown",
        },
        "sources": ["football-data"],
        "sourcePriority": 100,
    }
    return {
        "schema": 1,
        "generatedAt": "2026-09-21T12:00:00Z",
        "timezone": "America/Sao_Paulo",
        "window": {
            "from": "2026-09-21",
            "to": "2026-09-27",
        },
        "sources": {},
        "days": [
            {
                "date": "2026-09-21",
                "label": "HOJE",
                "count": 1,
                "matches": [copy.deepcopy(match)],
            }
        ],
        "matches": [match],
    }


class FeedV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_data, cls.registry_indexes = load_registry(
            REGISTRY_PATH
        )
        cls.cache = load_cache(CACHE_PATH)

    def build(self, feed=None, cache=None):
        return build_feed_v2(
            feed or synthetic_feed(),
            registry_data=self.registry_data,
            registry_indexes=self.registry_indexes,
            artwork_cache_v2=cache or self.cache,
        )

    def test_schema1_input_is_not_mutated(self):
        source = synthetic_feed()
        original = copy.deepcopy(source)
        self.build(source)
        self.assertEqual(source, original)

    def test_aliases_resolve_to_stable_gm_ids(self):
        result = self.build()
        match = result["matches"][0]
        self.assertEqual(
            match["competition"]["gmId"],
            "competition:premier-league",
        )
        self.assertEqual(
            match["home"]["gmId"],
            "club:manchester-city",
        )
        self.assertIsNone(match["away"]["gmId"])

    def test_external_ids_are_namespaced_by_provider(self):
        match = self.build()["matches"][0]
        self.assertEqual(
            match["competition"]["externalIds"],
            {"football-data": "2021"},
        )
        self.assertEqual(
            match["home"]["externalIds"],
            {"football-data": "65"},
        )
        self.assertEqual(
            match["away"]["externalIds"],
            {"football-data": "999999"},
        )

    def test_legacy_feed_artwork_is_not_reused(self):
        result = self.build()
        match = result["matches"][0]
        self.assertIsNone(
            match["competition"]["artwork"]["url"]
        )
        self.assertIsNone(match["home"]["artwork"]["url"])
        dumped = json.dumps(result)
        self.assertNotIn("https://legacy.invalid/", dumped)

    def test_cache_candidate_urls_never_leak_to_public_feed(self):
        result = self.build()
        dumped = json.dumps(result)
        self.assertNotIn("candidateUrl", dumped)
        for entry in self.cache["entries"].values():
            candidate = entry.get("candidateUrl")
            if candidate:
                self.assertNotIn(candidate, dumped)

    def test_only_validated_artwork_can_publish_url(self):
        cache = copy.deepcopy(self.cache)
        entry = cache["entries"]["competition:premier league"]
        entry["resolutionStatus"] = "validated"
        entry["semanticStatus"] = "validated"
        entry["fetchStatus"] = "ok"
        entry["visualStatus"] = "approved"
        entry["artworkUrl"] = "https://cdn.example/pl.svg"
        entry["candidateUrl"] = None
        entry["publishable"] = True
        entry["nextReviewAfter"] = None

        result = self.build(cache=cache)
        artwork = result["matches"][0]["competition"]["artwork"]
        self.assertEqual(artwork["status"], "validated")
        self.assertEqual(
            artwork["url"],
            "https://cdn.example/pl.svg",
        )

    def test_generated_local_feed_v2_validates(self):
        data = json.loads(V2_PATH.read_text(encoding="utf-8"))
        self.assertTrue(validate_feed_v2(data))
        self.assertEqual(data["schema"], 2)

    def test_day_counts_match_embedded_matches(self):
        result = self.build()
        self.assertEqual(
            result["days"][0]["count"],
            len(result["days"][0]["matches"]),
        )
        self.assertEqual(
            result["days"][0]["matches"][0]["id"],
            result["matches"][0]["id"],
        )

    def test_workflow_generates_validates_and_commits_v2(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "python scripts/generate_feed_v2.py",
            workflow,
        )
        self.assertIn(
            "data/football-feed-v2.json",
            workflow,
        )
        self.assertIn("validate_feed_v2", workflow)


if __name__ == "__main__":
    unittest.main()
