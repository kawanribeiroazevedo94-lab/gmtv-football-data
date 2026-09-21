import importlib.util
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "update_feed.py"

SPEC = importlib.util.spec_from_file_location("gmtv_update_feed", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)

with patch("zoneinfo.ZoneInfo", return_value=timezone.utc):
    SPEC.loader.exec_module(MODULE)


def team(name, team_id=None):
    return {
        "id": team_id,
        "name": name,
        "fullName": name,
        "normalized": MODULE.normalize(name),
    }


def competition(name="Premier League", code="PL", competition_id=None):
    return {
        "id": competition_id,
        "code": code,
        "name": name,
        "normalized": MODULE.normalize(name),
    }


def match(
    home,
    away,
    *,
    date="2026-09-21",
    kickoff="16:00",
    competition_name="Premier League",
    competition_code="PL",
    competition_id=None,
):
    return {
        "date": date,
        "kickoff": kickoff,
        "competition": competition(
            competition_name,
            competition_code,
            competition_id,
        ),
        "home": team(home),
        "away": team(away),
    }


class TeamAliasTests(unittest.TestCase):
    def assertAlias(self, left, right):
        self.assertTrue(
            MODULE.team_identity_match(team(left), team(right)),
            f"{left!r} deveria equivaler a {right!r}",
        )

    def assertNotAlias(self, left, right):
        self.assertFalse(
            MODULE.team_identity_match(team(left), team(right)),
            f"{left!r} NÃO deveria equivaler a {right!r}",
        )

    def test_required_positive_aliases(self):
        self.assertAlias("Man City", "Manchester City FC")
        self.assertAlias("Man United", "Manchester United FC")
        self.assertAlias("Bayern München", "Bayern Munich")
        self.assertAlias("Internazionale", "Inter Milan")
        self.assertAlias("Atlético-MG", "Atlético Mineiro")

    def test_dangerous_substring_false_positives_are_rejected(self):
        self.assertNotAlias("Manchester City", "Manchester United")
        self.assertNotAlias("Inter", "Internacional")
        self.assertNotAlias("United", "Manchester United")
        self.assertNotAlias("City", "Manchester City")

    def test_external_ids_win_when_both_are_present(self):
        left = team("Same Name", team_id=100)
        right = team("Same Name", team_id=200)
        self.assertFalse(MODULE.team_identity_match(left, right))

        right["id"] = 100
        self.assertTrue(MODULE.team_identity_match(left, right))


class MatchDedupTests(unittest.TestCase):
    def test_aliases_deduplicate_same_context(self):
        existing = [
            match(
                "Manchester City FC",
                "Sunderland AFC",
                kickoff="16:00",
            )
        ]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            kickoff="16:15",
        )
        self.assertIs(existing[0], MODULE.find_equivalent(existing, candidate))

    def test_different_competition_does_not_deduplicate(self):
        existing = [
            match(
                "Manchester City FC",
                "Sunderland AFC",
                competition_code="PL",
            )
        ]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            competition_name="FA Cup",
            competition_code="FAC",
        )
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))

    def test_different_date_does_not_deduplicate(self):
        existing = [match("Manchester City FC", "Sunderland AFC")]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            date="2026-09-22",
        )
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))

    def test_home_and_away_are_not_swappable(self):
        existing = [match("Manchester City FC", "Sunderland AFC")]
        candidate = match("Sunderland AFC", "Man City")
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))

    def test_kickoff_inside_tolerance_deduplicates(self):
        existing = [
            match(
                "Manchester City FC",
                "Sunderland AFC",
                kickoff="16:00",
            )
        ]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            kickoff="17:30",
        )
        self.assertIs(existing[0], MODULE.find_equivalent(existing, candidate))

    def test_kickoff_outside_tolerance_does_not_deduplicate(self):
        existing = [
            match(
                "Manchester City FC",
                "Sunderland AFC",
                kickoff="16:00",
            )
        ]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            kickoff="17:31",
        )
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))

    def test_missing_kickoff_does_not_deduplicate(self):
        existing = [
            match(
                "Manchester City FC",
                "Sunderland AFC",
                kickoff="16:00",
            )
        ]
        candidate = match(
            "Man City",
            "Sunderland AFC",
            kickoff=None,
        )
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))

    def test_ambiguous_inter_does_not_merge_with_internacional(self):
        existing = [
            match(
                "Internacional",
                "Grêmio",
                competition_name="Campeonato Brasileiro Série A",
                competition_code="BSA",
            )
        ]
        candidate = match(
            "Inter",
            "Grêmio",
            competition_name="Campeonato Brasileiro Série A",
            competition_code="BSA",
        )
        self.assertIsNone(MODULE.find_equivalent(existing, candidate))


if __name__ == "__main__":
    unittest.main()
