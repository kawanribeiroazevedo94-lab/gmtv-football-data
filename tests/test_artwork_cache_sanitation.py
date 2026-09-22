import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "artwork-cache.json"

FORBIDDEN_URL_FRAGMENTS = (
    "Craven_Cottage.JPG",
    "Etihad_Stadium",
    "Manchester_United_v_Tottenham_Hotspur",
    "Stadium_of_Light_sunderland_crest.jpg",
    "BrasileiraoB2014-",
)


def load_cache():
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


class ArtworkCacheSanitationTests(unittest.TestCase):
    def test_known_bad_photo_and_old_serie_b_urls_are_absent(self):
        raw = CACHE_PATH.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_URL_FRAGMENTS:
            self.assertNotIn(fragment, raw)

    def test_validated_entries_are_https_and_versioned(self):
        cache = load_cache()
        for key, entry in cache.items():
            if entry.get("status") == "validated":
                self.assertEqual(entry.get("resolverVersion"), 4, key)
                self.assertTrue((entry.get("url") or "").startswith("https://"), key)
                self.assertEqual(entry.get("semanticStatus"), "validated", key)
                self.assertEqual(entry.get("fetchStatus"), "ok", key)
                self.assertEqual(entry.get("visualStatus"), "approved", key)

    def test_cache_remains_valid_json_object(self):
        cache = load_cache()
        self.assertIsInstance(cache, dict)
        self.assertGreater(len(cache), 0)


if __name__ == "__main__":
    unittest.main()
