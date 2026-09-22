import importlib.util
import unittest
from datetime import date, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "free_sources.py"
SPEC = importlib.util.spec_from_file_location("free_sources", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fake_zone(name):
    mapping = {
        "America/Sao_Paulo": timezone(timedelta(hours=-3)),
        "Europe/Paris": timezone(timedelta(hours=2)),
    }
    return mapping[name]


class OpenLigaDBSourceTests(unittest.TestCase):
    def test_openligadb_keeps_provider_namespaces(self):
        competition = {"providerId":4937,"shortcut":"bl1","name":"Bundesliga","code":"BL1"}
        raw = {
            "matchID":83185,
            "matchDateTimeUTC":"2026-09-20T13:30:00Z",
            "matchIsFinished":False,
            "team1":{"teamId":6,"teamName":"Bayer 04 Leverkusen"},
            "team2":{"teamId":163,"teamName":"RB Leipzig"},
        }
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            parsed = MODULE.make_openligadb_match(raw, competition)
        self.assertEqual(parsed["competition"]["idProvider"], "openligadb")
        self.assertEqual(parsed["home"]["idProvider"], "openligadb")
        self.assertEqual(parsed["away"]["idProvider"], "openligadb")

    def test_openligadb_does_not_publish_provider_artwork(self):
        competition = {"providerId":4937,"shortcut":"bl1","name":"Bundesliga","code":"BL1"}
        raw = {
            "matchID":1,
            "matchDateTimeUTC":"2026-09-20T13:30:00Z",
            "matchIsFinished":False,
            "team1":{"teamId":10,"teamName":"Home","teamIconUrl":"https://random.example/home.png"},
            "team2":{"teamId":20,"teamName":"Away","teamIconUrl":"https://random.example/away.png"},
        }
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            parsed = MODULE.make_openligadb_match(raw, competition)
        self.assertIsNone(parsed["home"]["crest"])
        self.assertIsNone(parsed["away"]["crest"])
        self.assertIsNone(parsed["competition"]["logo"])

    def test_openligadb_utc_converts_to_app_timezone(self):
        competition = {"providerId":4937,"shortcut":"bl1","name":"Bundesliga","code":"BL1"}
        raw = {
            "matchID":83185,
            "matchDateTimeUTC":"2026-09-20T13:30:00Z",
            "matchIsFinished":False,
            "team1":{"teamId":6,"teamName":"Home"},
            "team2":{"teamId":7,"teamName":"Away"},
        }
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            parsed = MODULE.make_openligadb_match(raw, competition)
        self.assertEqual(parsed["date"], "2026-09-20")
        self.assertEqual(parsed["kickoff"], "10:30")


class WikimediaParserTests(unittest.TestCase):
    COMPETITION = {
        "key":"uwcl",
        "name":"UEFA Women's Champions League",
        "code":"UWCL",
        "timezone":"Europe/Paris",
    }

    def test_parses_start_date_template_and_converts_timezone(self):
        text = r'''{{Football box
|date = {{Start date|2026|9|22|df=y}}
|time = 18:45
|team1 = [[FC Bayern Munich (women)|Bayern Munich]]
|score = v
|team2 = [[Manchester City W.F.C.|Manchester City]]
}}'''
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            matches = MODULE.parse_wikimedia_matches(
                text,
                self.COMPETITION,
                date(2026,9,22),
                date(2026,9,28),
                provenance={"page":"Example","pageId":123,"revisionId":456,"revisionTimestamp":"2026-09-21T08:39:55Z"},
            )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["date"], "2026-09-22")
        self.assertEqual(matches[0]["kickoff"], "13:45")
        self.assertEqual(matches[0]["home"]["name"], "Bayern Munich")
        self.assertEqual(matches[0]["away"]["name"], "Manchester City")
        self.assertEqual(matches[0]["provenance"]["revisionId"], 456)

    def test_parses_plain_text_date(self):
        text = r'''{{football box
|date = 23 September 2026
|time = 21:00
|team1 = [[FC Barcelona Femení|Barcelona]]
|score = v
|team2 = [[Paris FC (women)|Paris FC]]
}}'''
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            matches = MODULE.parse_wikimedia_matches(text,self.COMPETITION,date(2026,9,22),date(2026,9,28))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["date"], "2026-09-23")
        self.assertEqual(matches[0]["kickoff"], "16:00")

    def test_missing_time_fails_closed(self):
        text = r'''{{Football box
|date = 22 September 2026
|team1 = Bayern Munich
|score = v
|team2 = Manchester City
}}'''
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            matches = MODULE.parse_wikimedia_matches(text,self.COMPETITION,date(2026,9,22),date(2026,9,28))
        self.assertEqual(matches, [])

    def test_outside_window_is_not_published(self):
        text = r'''{{Football box
|date = 30 September 2026
|time = 18:45
|team1 = Roma
|score = v
|team2 = Barcelona
}}'''
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            matches = MODULE.parse_wikimedia_matches(text,self.COMPETITION,date(2026,9,22),date(2026,9,28))
        self.assertEqual(matches, [])


class SeasonTests(unittest.TestCase):
    def test_wikipedia_season_label(self):
        self.assertEqual(MODULE.wikipedia_season_label(date(2026,9,22)), "2026–27")
        self.assertEqual(MODULE.wikipedia_season_label(date(2027,3,1)), "2026–27")


class BSDSourceTests(unittest.TestCase):
    def test_bsd_serie_b_event_is_namespaced_and_localized(self):
        raw = {
            "id": 101360,
            "league_id": 34,
            "season_id": 52,
            "event_date": "2026-09-22T22:30:00Z",
            "home_team": "Criciúma",
            "home_team_id": 929,
            "away_team": "Operário-PR",
            "away_team_id": 828,
        }
        with patch.object(MODULE, "ZoneInfo", side_effect=fake_zone):
            match = MODULE.make_bsd_match(raw)

        self.assertIsNotNone(match)
        self.assertEqual(match["date"], "2026-09-22")
        self.assertEqual(match["kickoff"], "19:30")
        self.assertEqual(match["competition"]["code"], "BSB")
        self.assertEqual(match["competition"]["idProvider"], "bsd")
        self.assertEqual(match["home"]["id"], 929)
        self.assertEqual(match["away"]["id"], 828)
        self.assertIsNone(match["competition"]["logo"])
        self.assertIsNone(match["home"]["crest"])
        self.assertIsNone(match["away"]["crest"])

    def test_bsd_unknown_league_fails_closed(self):
        raw = {
            "id": 1,
            "league_id": 999999,
            "event_date": "2026-09-22T22:30:00Z",
            "home_team": "A",
            "away_team": "B",
        }
        self.assertIsNone(MODULE.make_bsd_match(raw))


if __name__ == "__main__":
    unittest.main()
