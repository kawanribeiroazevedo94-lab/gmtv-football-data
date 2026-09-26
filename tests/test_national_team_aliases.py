import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import artwork_catalog as catalog
from generate_artwork_catalog import build_public_catalog


class NationalTeamAliasTests(unittest.TestCase):
    def test_portuguese_provider_names_resolve_to_the_same_national_team_id(self):
        cases = json.loads((ROOT / "tests/fixtures/national_team_names_pt_br.json").read_text(encoding="utf-8"))
        data = json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))
        public = build_public_catalog(data)
        public_index = {}
        for row in public["records"]:
            for name in [row["name"], *row["aliases"]]:
                public_index.setdefault((row["kind"], catalog.artwork_name(name)), set()).add(row["id"])
        self.assertEqual(len(cases), 86)
        for case in cases:
            with self.subTest(name=case["alias"]):
                row = catalog.find_catalog_artwork(case["alias"], "team")
                self.assertIsNotNone(row)
                self.assertEqual(row["id"], case["id"])
                self.assertEqual(row["entityType"], "national_team")
                self.assertEqual(public_index[("team", catalog.artwork_name(case["alias"]))], {case["id"]})


if __name__ == "__main__":
    unittest.main()
