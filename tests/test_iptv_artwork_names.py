import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import artwork_catalog as catalog
from generate_artwork_catalog import build_public_catalog


class IptvArtworkNamesTests(unittest.TestCase):
    def test_all_names_visible_in_the_fourteen_iptv_matches_select_the_correct_id(self):
        cases = json.loads((ROOT / "tests/fixtures/iptv_names_20260926.json").read_text(encoding="utf-8"))
        public = build_public_catalog(json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8")))
        self.assertEqual(len(cases), 14)
        for match in cases:
            for side in ("home", "away"):
                expected = match[side]
                with self.subTest(name=expected["name"]):
                    row = catalog.find_catalog_artwork(expected["name"], "team", "Jogos do dia")
                    self.assertIsNotNone(row)
                    self.assertEqual(row["id"], expected["catalogId"])
                    matches = [r for r in public["records"] if r["kind"] == "team" and
                               catalog.artwork_name(expected["name"]) in
                               {catalog.artwork_name(n) for n in [r["name"], *r["aliases"]]}]
                    self.assertEqual({r["id"] for r in matches}, {expected["catalogId"]})
                    self.assertEqual(matches[0]["url"], row["url"])

    def test_reviewed_aliases_do_not_enable_fuzzy_matching(self):
        for name in ("MACED", "SUISA", "OPER", "EUAA", "PER"):
            with self.subTest(name=name):
                self.assertIsNone(catalog.find_catalog_artwork(name, "team", "Jogos do dia"))


if __name__ == "__main__":
    unittest.main()
