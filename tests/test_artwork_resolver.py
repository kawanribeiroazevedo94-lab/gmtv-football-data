import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artwork_resolver as MODULE


class ArtworkResolverTests(unittest.TestCase):
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
