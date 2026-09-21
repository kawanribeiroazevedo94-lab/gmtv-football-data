#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from artwork_cache_v2 import load_cache
from entity_registry import load_registry
from feed_v2 import build_feed_v2, validate_feed_v2

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "football-feed.json"
TARGET = ROOT / "data" / "football-feed-v2.json"
REGISTRY = ROOT / "data" / "entity-registry.json"
ARTWORK_CACHE = ROOT / "data" / "artwork-cache-v2.json"


def main():
    feed_v1 = json.loads(SOURCE.read_text(encoding="utf-8"))
    registry_data, registry_indexes = load_registry(REGISTRY)
    artwork_cache = load_cache(ARTWORK_CACHE)

    feed_v2 = build_feed_v2(
        feed_v1,
        registry_data=registry_data,
        registry_indexes=registry_indexes,
        artwork_cache_v2=artwork_cache,
    )
    validate_feed_v2(feed_v2)

    TARGET.write_text(
        json.dumps(
            feed_v2,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "feed v2 gerado: "
        f"{len(feed_v2['matches'])} partidas | "
        f"{len(feed_v2['days'])} dias"
    )


if __name__ == "__main__":
    main()
