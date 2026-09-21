import importlib.util
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_feed.py"
SPEC = importlib.util.spec_from_file_location("gmtv_update_feed", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)

# Os testes desta fase auditam exclusivamente a barreira semântica do Wikidata.
# O Python do Termux pode não possuir uma base IANA de timezone instalada;
# neutralizamos ZoneInfo somente durante o import do módulo para que a ausência
# local de tzdata não mascare regressões do firewall semântico. O source de
# produção permanece inalterado e continua usando ZoneInfo normalmente.
with patch("zoneinfo.ZoneInfo", return_value=timezone.utc):
    SPEC.loader.exec_module(MODULE)


class SemanticArtworkFirewallTests(unittest.TestCase):
    def test_classification_separates_entity_kinds(self):
        self.assertEqual(
            MODULE.classify_wikidata_class_labels(["association football club"]),
            "club",
        )
        self.assertEqual(
            MODULE.classify_wikidata_class_labels(["association football league"]),
            "competition",
        )
        self.assertEqual(
            MODULE.classify_wikidata_class_labels(["national association football team"]),
            "national_team",
        )
        self.assertEqual(
            MODULE.classify_wikidata_class_labels(["football federation"]),
            "federation",
        )
        self.assertEqual(
            MODULE.classify_wikidata_class_labels(["sports organization"]),
            "unknown",
        )

    def test_search_rejects_first_result_when_wrong_entity_type(self):
        search_payload = {
            "search": [
                {"id": "Q_FEDERATION", "label": "Example Football Federation"},
                {"id": "Q_COMPETITION", "label": "Example League"},
            ]
        }

        with patch.object(MODULE, "http_json", return_value=search_payload), patch.object(
            MODULE,
            "wikidata_entity_type",
            side_effect=lambda qid: {
                "Q_FEDERATION": "federation",
                "Q_COMPETITION": "competition",
            }[qid],
        ):
            resolved = MODULE.wikidata_search("Example League", "competition")

        self.assertEqual(resolved, "Q_COMPETITION")

    def test_search_never_falls_back_to_generic_results_zero(self):
        search_payload = {
            "search": [
                {"id": "Q_NATIONAL_TEAM", "label": "Example national team"},
            ]
        }

        with patch.object(MODULE, "http_json", return_value=search_payload), patch.object(
            MODULE,
            "wikidata_entity_type",
            return_value="national_team",
        ):
            resolved = MODULE.wikidata_search("Example League", "competition")

        self.assertIsNone(resolved)

    def test_p18_is_never_used_as_logo_or_crest(self):
        payload = {
            "entities": {
                "Q1": {
                    "claims": {
                        "P18": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": "Stadium photo.jpg"
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }

        with patch.object(MODULE, "http_json", return_value=payload):
            self.assertIsNone(MODULE.wikidata_logo("Q1"))

    def test_p154_remains_eligible_after_entity_validation(self):
        payload = {
            "entities": {
                "Q1": {
                    "claims": {
                        "P154": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": "Official logo.svg"
                                    }
                                }
                            }
                        ],
                        "P18": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": "Stadium photo.jpg"
                                    }
                                }
                            }
                        ],
                    }
                }
            }
        }

        with patch.object(MODULE, "http_json", return_value=payload):
            url = MODULE.wikidata_logo("Q1")

        self.assertIn("Official_logo.svg", url)
        self.assertNotIn("Stadium", url)

    def test_entity_type_uses_structured_p31_not_search_description(self):
        entity_payload = {
            "entities": {
                "Q1": {
                    "claims": {
                        "P31": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": {"id": "Q_CLASS"}
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        classes_payload = {
            "entities": {
                "Q_CLASS": {
                    "labels": {
                        "en": {"value": "national association football team"}
                    }
                }
            }
        }

        with patch.object(
            MODULE,
            "http_json",
            side_effect=[entity_payload, classes_payload],
        ):
            self.assertEqual(MODULE.wikidata_entity_type("Q1"), "national_team")


if __name__ == "__main__":
    unittest.main()
