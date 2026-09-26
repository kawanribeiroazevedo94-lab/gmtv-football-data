import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import artwork_catalog as catalog
import artwork_resolver as resolver
from generate_artwork_catalog import build_public_catalog


class ArtworkCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_has_verified_images_and_unique_provider_ids(self):
        catalog.validate_catalog(self.data)

    def test_competitions_do_not_depend_on_active_fixture_window(self):
        for name in ["Premier League", "Bundesliga", "Campeonato Brasileiro Série A",
                     "Campeonato Brasileiro Série B", "Copa Libertadores", "Copa Sul-Americana",
                     "Copa do Brasil", "Supercopa Rei", "La Liga", "Ligue 1", "Primeira Liga"]:
            with self.subTest(name=name):
                self.assertIsNotNone(catalog.find_catalog_artwork(name, "competition"))

    def test_original_missing_team_names_have_an_identified_crest(self):
        cases = json.loads((ROOT / "tests/fixtures/artwork_names_20260923.json").read_text(encoding="utf-8"))
        for name, competition in cases:
            self.assertIsNotNone(catalog.find_catalog_artwork(name, "team", competition), name)

    def test_homonymous_clubs_and_womens_sides_are_not_confused(self):
        checks = [
            ("Athletic Club", "Brasileirão Série B", "20851"),
            ("Athletic Club", "La Liga", "93"),
            ("Barcelona SC", "Copa Libertadores", "2686"),
            ("Barcelona", "La Liga", "83"),
            ("Barcelona", "UEFA Women's Champions League", "20091"),
            ("Paris FC", "UEFA Women's Champions League", "21640"),
            ("Botafogo-SP", "Brasileirão Série B", "10281"),
            ("Botafogo", "Brasileirão Série A", "6086"),
        ]
        for name, competition, expected in checks:
            with self.subTest(name=name, competition=competition):
                self.assertEqual(catalog.find_catalog_artwork(name, "team", competition)["providerEntityId"], expected)
        self.assertIsNone(catalog.find_catalog_artwork("Athletic Club", "team", "Unknown"))

    def test_club_world_cup_is_not_the_national_teams_world_cup(self):
        clubs = catalog.find_catalog_artwork("FIFA Club World Cup", "competition")
        countries = catalog.find_catalog_artwork("FIFA World Cup", "competition")
        self.assertEqual(clubs["league"], "fifa.cwc")
        self.assertEqual(countries["league"], "fifa.world")
        self.assertNotEqual(clubs["id"], countries["id"])
        self.assertNotEqual(catalog.scoped_team_key("A", "FIFA Club World Cup"),
                            catalog.scoped_team_key("A", "FIFA World Cup"))

    def test_catalog_overrides_old_null_without_network(self):
        cache = {"team:athletic club@brasileirao serie b": {
            "status": "unresolved", "resolverVersion": 4,
            "nextRetryAfter": "2099-01-01T00:00:00Z"}}
        with patch.object(resolver, "http_json", side_effect=AssertionError("unexpected network")):
            url = resolver.resolve_artwork("Athletic Club", "team", cache, competition_name="Brasileirão Série B")
        self.assertTrue(url.startswith("https://"))

    def test_unapproved_catalog_record_cannot_be_published(self):
        data = copy.deepcopy(self.data)
        data["records"][0]["reviewStatus"] = "pending"
        with self.assertRaises(ValueError):
            build_public_catalog(data)

    def test_public_catalog_is_images_only(self):
        public = build_public_catalog(self.data)
        self.assertEqual(set(public), {"schema", "generatedAt", "records"})
        for row in public["records"]:
            self.assertNotIn("verification", row)
            self.assertNotIn("sourceUrl", row)
            self.assertNotIn("matches", row)
            self.assertEqual(row["status"], "validated")

    def cache_entry(self, key, name):
        cache = json.loads((ROOT / "data/artwork-cache-v2.json").read_text(encoding="utf-8"))
        row = copy.deepcopy(next(e for e in cache["entries"].values()
                                 if e["entityType"] == "club" and e["publishable"]))
        row.update(cacheKey=key, name=name, gmId=None, wikidataQid="Q999999999")
        return row

    def test_new_approved_cache_discoveries_reach_public_catalog(self):
        key = "team:clube de teste@premier league"
        entry = self.cache_entry(key, "Clube de Teste")
        alias_key = "team:test club@premier league"
        alias = copy.deepcopy(entry)
        alias.update(cacheKey=alias_key, name="Test Club")
        public = build_public_catalog(self.data, {"entries": {key: entry, alias_key: alias}})
        new = [r for r in public["records"] if r["id"].startswith("cache:")]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["url"], entry["artworkUrl"])
        self.assertIn("Test Club", new[0]["aliases"])
        self.assertIn("eng.1", new[0]["leagues"])

    def test_public_catalog_does_not_promote_http_or_pending_candidates(self):
        key = "team:clube de teste"
        entry = self.cache_entry(key, "Clube de Teste")
        entry["artworkUrl"] = "http://example.org/logo.png"
        self.assertEqual(len(build_public_catalog(self.data, {"entries": {key: entry}})["records"]),
                         len(self.data["records"]))
        entry.update(resolutionStatus="pending_review", artworkUrl=None,
                     candidateUrl="https://example.org/logo.png", publishable=False,
                     visualStatus="not_checked", nextReviewAfter="2026-09-25T00:00:00Z")
        self.assertEqual(len(build_public_catalog(self.data, {"entries": {key: entry}})["records"]),
                         len(self.data["records"]))

    def test_reviewed_catalog_wins_over_old_cache_alias(self):
        key = "team:chelsea"
        entry = self.cache_entry(key, "Chelsea")
        entry["artworkUrl"] = "https://example.org/old.png"
        public = build_public_catalog(self.data, {"entries": {key: entry}})
        self.assertFalse(any(r["url"] == entry["artworkUrl"] for r in public["records"]))


if __name__ == "__main__":
    unittest.main()
