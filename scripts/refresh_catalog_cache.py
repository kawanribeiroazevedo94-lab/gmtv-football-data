"""Refresh artwork of the existing snapshot without changing its fixtures."""
import json
from pathlib import Path

from artwork_cache_v2 import load_cache, get_publishable_url
from artwork_catalog import find_catalog_artwork, catalog_entry, scoped_team_key, artwork_name, prime_catalog
from artwork_resolver import RESOLVER_VERSION
from sync_artwork_cache_v2 import main as sync_cache
from generate_feed_v2 import main as generate_v2
from generate_artwork_catalog import main as generate_catalog

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "data/artwork-cache.json"
    cache = json.loads(path.read_text(encoding="utf-8"))
    for key, row in load_cache()["entries"].items():
        url = get_publishable_url(row)
        old = cache.get(key) or {}
        if url and old.get("status") != "validated":
            cache[key] = dict(name=row["name"], qid=row["wikidataQid"], url=url,
                              status="validated", semanticStatus="validated", fetchStatus="ok",
                              visualStatus="approved", resolverVersion=RESOLVER_VERSION,
                              entityType=row["entityType"], provider=row["artworkProvider"],
                              property=row["artworkProperty"], validatedAt=row["lastAttemptAt"],
                              sourceFile=row["provenance"].get("sourceFile"), nextRetryAfter=None)
    prime_catalog(cache, RESOLVER_VERSION)
    feed_path = ROOT / "data/football-feed.json"
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    for match in feed["matches"]:
        competition = match["competition"]["name"]
        for side, kind, field in [("competition", "competition", "logo"), ("home", "team", "crest"), ("away", "team", "crest")]:
            entity = match[side]
            row = find_catalog_artwork(entity["name"], kind, competition)
            if row:
                key = scoped_team_key(entity["name"], competition) if kind == "team" else f"competition:{artwork_name(entity['name'])}"
                cache[key] = catalog_entry(row, entity["name"], RESOLVER_VERSION)
                entity[field] = row["url"]
    by_id = {m["id"]: m for m in feed["matches"]}
    for day in feed["days"]:
        day["matches"] = [by_id[m["id"]] for m in day["matches"]]
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    feed_path.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sync_cache()
    generate_v2()
    generate_catalog()


if __name__ == "__main__":
    main()
