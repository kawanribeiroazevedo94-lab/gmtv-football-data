import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from artwork_cache_v2 import load_cache
from entity_registry import load_registry
from feed_v2 import build_feed_v2

REGISTRY_PATH = ROOT / "data" / "entity-registry.json"
CACHE_PATH = ROOT / "data" / "artwork-cache-v2.json"


class ProviderNamespacingV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_data, cls.registry_indexes = load_registry(REGISTRY_PATH)
        cls.cache = load_cache(CACHE_PATH)

    def test_openligadb_ids_and_provenance_survive_v2(self):
        match = {
            "id":"oldb:83185",
            "date":"2026-09-20",
            "kickoff":"10:30",
            "utcDate":"2026-09-20T13:30:00Z",
            "status":"SCHEDULED",
            "competition":{
                "id":4937,"idProvider":"openligadb","code":"BL1",
                "name":"Bundesliga","logo":None,"normalized":"bundesliga",
            },
            "home":{
                "id":6,"idProvider":"openligadb","name":"Example Home",
                "fullName":"Example Home","crest":None,"normalized":"example home",
            },
            "away":{
                "id":7,"idProvider":"openligadb","name":"Example Away",
                "fullName":"Example Away","crest":None,"normalized":"example away",
            },
            "sources":["openligadb"],
            "sourcePriority":70,
            "provenance":{"provider":"openligadb","providerMatchId":83185},
        }
        source = {
            "schema":1,
            "generatedAt":"2026-09-20T12:00:00Z",
            "timezone":"America/Sao_Paulo",
            "window":{"from":"2026-09-20","to":"2026-09-26"},
            "sources":{},
            "days":[{
                "date":"2026-09-20","label":"HOJE","count":1,
                "matches":[copy.deepcopy(match)],
            }],
            "matches":[match],
        }
        result = build_feed_v2(
            source,
            registry_data=self.registry_data,
            registry_indexes=self.registry_indexes,
            artwork_cache_v2=self.cache,
        )
        built = result["matches"][0]
        self.assertEqual(built["competition"]["externalIds"], {"openligadb":"4937"})
        self.assertEqual(built["home"]["externalIds"], {"openligadb":"6"})
        self.assertEqual(built["away"]["externalIds"], {"openligadb":"7"})
        self.assertEqual(built["provenance"]["sourceDetails"]["providerMatchId"], 83185)


if __name__ == "__main__":
    unittest.main()
