import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artwork_resolver as MODULE


class ArtworkResolverTests(unittest.TestCase):
    def setUp(self):
        # These tests exercise online fallback, independently of catalog data.
        self.catalog = patch.object(MODULE, "find_catalog_artwork", return_value=None)
        self.catalog.start()
        self.addCleanup(self.catalog.stop)

    def test_type_labels_preserve_football_and_club_words(self):
        examples = {
            "association football club": "club",
            "clube de futebol": "club",
            "association football league": "competition",
            "competição de futebol": "competition",
            "national association football team": "national_team",
            "seleção nacional de futebol": "national_team",
            "football federation": "federation",
            "federal republic": "unknown",
        }
        for label, expected in examples.items():
            with self.subTest(label=label):
                self.assertEqual(MODULE._classify_labels([label]), expected)

    def test_search_does_not_pick_ambiguous_or_merely_similar_club(self):
        with (patch.object(MODULE, "http_json", return_value={"search": [
                {"id": "Q1", "label": "United"},
                {"id": "Q2", "label": "United"},
                {"id": "Q3", "label": "Manchester United"},
            ]}), patch.object(MODULE, "wikidata_entity_type", return_value="club")):
            self.assertIsNone(MODULE.wikidata_search("United", "team"))

    def test_unreviewed_commons_search_is_not_automatically_published(self):
        with (patch.object(MODULE, "wikidata_search", return_value="Q1"),
              patch.object(MODULE, "wikidata_logo_filename", return_value=None),
              patch.object(MODULE, "commons_search_logo_file") as search):
            cache = {}
            self.assertIsNone(MODULE.resolve_artwork("Example Club", "team", cache))
            search.assert_not_called()

    def test_429_stops_subsequent_requests_in_same_run(self):
        import urllib.error
        with (patch.object(MODULE, "_network_calls", 0),
              patch.object(MODULE, "_last_request_at", 0.0),
              patch.object(MODULE, "_backoff_until", 0.0),
              patch.object(MODULE.urllib.request, "urlopen", side_effect=
                  urllib.error.HTTPError("https://www.wikidata.org/", 429, "rate limited",
                                         {"Retry-After": "7200"}, None)) as network):
            with self.assertRaises(urllib.error.HTTPError):
                MODULE.http_json("https://www.wikidata.org/w/api.php")
            with self.assertRaisesRegex(RuntimeError, "backoff"):
                MODULE.http_json("https://commons.wikimedia.org/w/api.php")
            self.assertEqual(network.call_count, 1)

    def test_cached_null_is_retried(self):
        cache = {
            "team:real madrid": {
                "name": "Real Madrid",
                "qid": None,
                "url": None,
                "status": "unresolved",
                "resolverVersion": 3,
            }
        }
        with (
            patch.object(MODULE, "wikidata_search", return_value="Q1"),
            patch.object(MODULE, "wikidata_logo_filename", return_value="Real Madrid CF.svg"),
            patch.object(
                MODULE,
                "commons_thumb_info",
                return_value={
                    "url": "https://upload.wikimedia.org/real.png",
                    "width": 256,
                    "height": 256,
                    "mime": "image/png",
                },
            ),
            patch.object(MODULE, "verify_artwork_url", return_value=True),
        ):
            url = MODULE.resolve_artwork("Real Madrid", "team", cache)

        self.assertEqual(url, "https://upload.wikimedia.org/real.png")
        self.assertEqual(cache["team:real madrid"]["status"], "validated")
        self.assertEqual(cache["team:real madrid"]["resolverVersion"], 4)

    def test_old_rejected_photo_does_not_block_new_p154(self):
        cache = {
            "team:manchester city": {
                "name": "Manchester City",
                "qid": "Q50602",
                "url": None,
                "status": "rejected",
                "rejectedReason": "proven_p18_stadium_photograph_not_crest",
            }
        }
        with (
            patch.object(MODULE, "wikidata_search", return_value="Q50602"),
            patch.object(MODULE, "wikidata_logo_filename", return_value="Manchester City FC badge.svg"),
            patch.object(
                MODULE,
                "commons_thumb_info",
                return_value={
                    "url": "https://upload.wikimedia.org/city.png",
                    "width": 256,
                    "height": 256,
                    "mime": "image/png",
                },
            ),
            patch.object(MODULE, "verify_artwork_url", return_value=True),
        ):
            url = MODULE.resolve_artwork("Manchester City", "team", cache)

        self.assertEqual(url, "https://upload.wikimedia.org/city.png")
        self.assertEqual(cache["team:manchester city"]["status"], "validated")
        self.assertEqual(
            cache["team:manchester city"]["supersededRejection"],
            "proven_p18_stadium_photograph_not_crest",
        )

    def test_serie_b_forces_current_curated_file(self):
        cache = {}
        with (
            patch.object(
                MODULE,
                "commons_thumb_info",
                return_value={
                    "url": "https://upload.wikimedia.org/serie-b-2025.png",
                    "width": 256,
                    "height": 256,
                    "mime": "image/png",
                },
            ) as commons,
            patch.object(MODULE, "verify_artwork_url", return_value=True),
        ):
            url = MODULE.resolve_artwork(
                "Brasileirão Série B",
                "competition",
                cache,
            )

        self.assertEqual(url, "https://upload.wikimedia.org/serie-b-2025.png")
        self.assertEqual(
            commons.call_args.args[0],
            "Campeonato Brasileiro Série B logo (2025).svg",
        )

    def test_requested_competition_catalog_is_present(self):
        expected = {
            "Brasileirão Série A",
            "Brasileirão Série B",
            "Copa do Brasil",
            "Supercopa do Brasil",
            "Campeonato Paulista",
            "Campeonato Carioca",
            "Campeonato Mineiro",
            "Campeonato Gaúcho",
            "Copa Libertadores",
            "Copa Sul-Americana",
            "Recopa Sul-Americana",
            "Premier League",
            "La Liga",
            "Serie A",
            "Bundesliga",
            "Ligue 1",
            "Liga Portugal",
            "Eredivisie",
            "UEFA Champions League",
            "UEFA Europa League",
            "UEFA Conference League",
            "UEFA Super Cup",
            "FA Cup",
            "Copa del Rey",
            "Coppa Italia",
            "DFB-Pokal",
            "MLS",
            "Liga MX",
            "Campeonato Argentino",
            "Saudi Pro League",
            "FIFA Club World Cup",
            "FIFA Intercontinental Cup",
            "Copa do Mundo",
            "Copa América",
            "Eurocopa",
            "UEFA Nations League",
        }
        actual = {row[0] for row in MODULE.COMPETITION_CATALOG}
        self.assertTrue(expected.issubset(actual))


if __name__ == "__main__":
    unittest.main()
