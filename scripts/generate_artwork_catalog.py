"""Publish reviewed images for IPTV matches; never create fixtures."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from artwork_catalog import artwork_name, find_catalog_artwork, validate_catalog
from artwork_cache_v2 import get_publishable_url, load_cache

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/artwork-catalog.json"
PUBLIC = ROOT / "data/football-artwork.json"


def build_public_catalog(data, cache=None):
    validate_catalog(data)
    fields = ("id", "name", "kind", "entityType", "aliases", "url", "league", "leagues", "country")
    result = {
        "schema": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "records": [dict({field: row.get(field) for field in fields}, status="validated")
                    for row in data["records"]],
    }
    covered = {(row["kind"], artwork_name(name)) for row in result["records"]
               for name in [row["name"], *(row.get("aliases") or [])]}
    additions = {}
    for key, entry in (cache or {}).get("entries", {}).items():
        url = get_publishable_url(entry)
        kind = "competition" if entry["entityType"] == "competition" else "team"
        if (not url or not url.startswith("https://")
                or (kind, artwork_name(entry["name"])) in covered
                or entry["entityType"] not in {"competition", "club", "national_team"}
                or not urlparse(url).path.lower().endswith(".png")):
            continue
        identity = entry.get("wikidataQid") or key
        record_id = f"cache:{kind}:{identity}"
        row = additions.setdefault(record_id, dict(
            id=record_id, name=entry["name"], kind=kind, entityType=entry["entityType"],
            aliases=[], url=url, league=None, leagues=[], country=None, status="validated",
        ))
        if artwork_name(entry["name"]) != artwork_name(row["name"]):
            if entry["name"] not in row["aliases"]:
                row["aliases"].append(entry["name"])
        if "@" in key:
            competition = find_catalog_artwork(key.split("@", 1)[1], "competition")
            if competition:
                league = competition.get("league")
                if league and league not in row["leagues"]:
                    row["leagues"].append(league)
                row["country"] = competition.get("country")
    result["records"].extend(additions.values())
    return result


def main():
    result = build_public_catalog(json.loads(SOURCE.read_text(encoding="utf-8")),
                                  load_cache(ROOT / "data/artwork-cache-v2.json"))
    PUBLIC.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("football-artwork:", len(result["records"]), "images; no fixtures or IPTV credentials")


if __name__ == "__main__":
    main()
