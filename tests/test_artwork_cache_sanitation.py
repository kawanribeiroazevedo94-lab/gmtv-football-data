import importlib.util
import json
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "artwork-cache.json"
MODULE_PATH = ROOT / "scripts" / "update_feed.py"

SPEC = importlib.util.spec_from_file_location("gmtv_update_feed", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)

with patch("zoneinfo.ZoneInfo", return_value=timezone.utc):
    SPEC.loader.exec_module(MODULE)

REJECTED = {
    "team:fulham": "proven_p18_photograph_not_crest",
    "team:manchester city": "proven_p18_stadium_photograph_not_crest",
    "team:manchester united": "proven_p18_match_photograph_not_crest",
    "team:sunderland": "proven_photographic_artwork_not_clean_crest",
}

FORBIDDEN_URL_FRAGMENTS = (
    "Craven_Cottage.JPG",
    "Etihad_Stadium",
    "Manchester_United_v_Tottenham_Hotspur",
    "Stadium_of_Light_sunderland_crest.jpg",
)


def load_cache():
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


class ArtworkCacheSanitationTests(unittest.TestCase):
    def test_proven_bad_entries_are_rejected_and_not_publishable(self):
        cache = load_cache()
        for key, reason in REJECTED.items():
            self.assertIn(key, cache)
            self.assertIsNone(cache[key].get("url"))
            self.assertEqual(cache[key].get("status"), "rejected")
            self.assertEqual(cache[key].get("rejectedReason"), reason)
            self.assertTrue(cache[key].get("rejectedAt"))

    def test_known_bad_photo_urls_no_longer_exist_in_cache(self):
        raw = CACHE_PATH.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_URL_FRAGMENTS:
            self.assertNotIn(fragment, raw)

    def test_rejected_cache_entries_short_circuit_without_rediscovery(self):
        cache = load_cache()
        with patch.object(
            MODULE,
            "wikidata_search",
            side_effect=AssertionError("rejected cache must not rediscover"),
        ), patch.object(
            MODULE,
            "wikidata_logo",
            side_effect=AssertionError("rejected cache must not resolve artwork"),
        ):
            self.assertIsNone(
                MODULE.resolve_artwork("Manchester City FC", "team", cache)
            )
            self.assertIsNone(
                MODULE.resolve_artwork("Manchester United FC", "team", cache)
            )
            self.assertIsNone(
                MODULE.resolve_artwork("Fulham FC", "team", cache)
            )
            self.assertIsNone(
                MODULE.resolve_artwork("Sunderland AFC", "team", cache)
            )

    def test_enrichment_cannot_republish_rejected_club_artwork(self):
        cache = load_cache()
        matches = [
            {
                "competition": {
                    "name": "Premier League",
                    "logo": "https://example.invalid/already-valid.png",
                },
                "home": {
                    "name": "Manchester City FC",
                    "crest": None,
                },
                "away": {
                    "name": "Fulham FC",
                    "crest": None,
                },
            }
        ]

        with patch.object(
            MODULE,
            "wikidata_search",
            side_effect=AssertionError("sanitized entries must stay local"),
        ):
            MODULE.enrich_missing_artwork(matches, cache)

        self.assertIsNone(matches[0]["home"]["crest"])
        self.assertIsNone(matches[0]["away"]["crest"])

    def test_premier_league_entry_is_not_removed_by_semantic_cache_cleanup(self):
        cache = load_cache()
        entry = cache["competition:premier league"]
        self.assertEqual(entry.get("qid"), "Q9448")
        self.assertIn("Pl-logo-light.svg", entry.get("url") or "")

    def test_cache_remains_valid_json_object(self):
        cache = load_cache()
        self.assertIsInstance(cache, dict)
        self.assertGreaterEqual(len(cache), len(REJECTED))


if __name__ == "__main__":
    unittest.main()
