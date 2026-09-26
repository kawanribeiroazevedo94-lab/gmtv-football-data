#!/usr/bin/env python3
from __future__ import annotations

import json
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from artwork_cache_v2 import get_publishable_url, validate_cache
from artwork_resolver import NATIONAL_TEAM_NAMES, RESOLVER_VERSION
from entity_registry import load_registry, resolve_entity

ROOT = Path(__file__).resolve().parents[1]
V1_PATH = ROOT / "data" / "artwork-cache.json"
V2_PATH = ROOT / "data" / "artwork-cache-v2.json"
REGISTRY_PATH = ROOT / "data" / "entity-registry.json"


def iso_z(value):
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def entity_type_for_key(key):
    if key.startswith("team:"):
        if key.split(":", 1)[1] in NATIONAL_TEAM_NAMES:
            return "national_team"
        return "club"
    if key.startswith("competition:"):
        return "competition"
    return "unknown"


def registry_gm_id(registry_data, registry_indexes, entity_type, name):
    entity = resolve_entity(
        registry_data,
        registry_indexes,
        entity_type=entity_type,
        name=name,
    )
    return entity.get("gmId") if entity else None


def build_entry(key, legacy, previous, registry_data, registry_indexes, now):
    previous = previous or {}
    entity_type = legacy.get("entityType") or previous.get("entityType") or entity_type_for_key(key)
    name = str(legacy.get("name") or previous.get("name") or key.split(":", 1)[-1]).strip()
    gm_id = (
        registry_gm_id(
            registry_data,
            registry_indexes,
            entity_type,
            name,
        )
        or previous.get("gmId")
    )
    # A competition-scoped crest must not become another team's global default.
    if "@" in key:
        gm_id = None
    migrated_at = (
        (previous.get("provenance") or {}).get("migratedAt")
        or iso_z(now)
    )

    common = {
        "cacheKey": key,
        "gmId": gm_id,
        "entityType": entity_type,
        "name": name,
        "wikidataQid": legacy.get("qid"),
        "resolutionStatus": "unresolved",
        "semanticStatus": "unresolved",
        "fetchStatus": "not_checked",
        "visualStatus": "not_checked",
        "artworkProvider": None,
        "artworkProperty": None,
        "artworkUrl": None,
        "candidateUrl": None,
        "publishable": False,
        "attemptCount": max(1, int(previous.get("attemptCount") or 1)),
        "lastAttemptAt": legacy.get("lastAttemptAt") or legacy.get("validatedAt"),
        "nextReviewAfter": legacy.get("nextRetryAfter") or iso_z(now + timedelta(hours=12)),
        "rejectedReason": None,
        "rejectedAt": None,
        "provenance": {
            "migratedAt": migrated_at,
            "migratedFrom": "artwork-cache-v1",
            "resolverVersion": legacy.get("resolverVersion"),
            "sourceFile": legacy.get("sourceFile"),
            "supersededRejection": legacy.get("supersededRejection"),
            "sourceUrl": legacy.get("sourceUrl"),
            "providerEntityId": legacy.get("providerEntityId"),
            "catalogId": legacy.get("catalogId"),
            "sha256": legacy.get("sha256"),
        },
    }

    url = legacy.get("url")
    if (
        legacy.get("status") == "validated"
        and legacy.get("resolverVersion") == RESOLVER_VERSION
        and legacy.get("semanticStatus") == "validated"
        and legacy.get("fetchStatus") == "ok"
        and legacy.get("visualStatus") == "approved"
        and isinstance(url, str)
        and url.startswith("https://")
    ):
        common.update({
            "resolutionStatus": "validated",
            "semanticStatus": "validated",
            "fetchStatus": "ok",
            "visualStatus": "approved",
            "artworkProvider": legacy.get("provider") or "wikidata-commons",
            "artworkProperty": legacy.get("property") or "P154",
            "artworkUrl": url,
            "candidateUrl": url,
            "publishable": True,
            "lastAttemptAt": legacy.get("validatedAt") or iso_z(now),
            "nextReviewAfter": None,
        })
        return common

    # Rejeição antiga de fotografia não bloqueia um P154 novo; ela fica só na proveniência.
    if legacy.get("status") == "rejected" and legacy.get("resolverVersion") == RESOLVER_VERSION:
        common.update({
            "resolutionStatus": "rejected",
            "semanticStatus": "rejected",
            "fetchStatus": "not_checked",
            "visualStatus": "rejected",
            "artworkProvider": legacy.get("provider"),
            "artworkProperty": legacy.get("property"),
            "nextReviewAfter": None,
            "rejectedReason": legacy.get("rejectedReason") or "resolver_v4_rejected",
            "rejectedAt": legacy.get("rejectedAt") or iso_z(now),
        })
        return common

    # A failed/absent refresh must not destroy an already reviewed image.
    # Explicit current rejections above still revoke it.
    if previous and get_publishable_url(previous):
        retained = copy.deepcopy(previous)
        if legacy.get("lastError"):
            retained.setdefault("provenance", {})["lastRefreshError"] = legacy["lastError"]
        return retained

    return common


def sync_entries(v1, old_entries, registry_data, registry_indexes, now):
    return {
        key: build_entry(key, v1.get(key) or {}, old_entries.get(key),
                         registry_data, registry_indexes, now)
        for key in sorted(set(v1) | set(old_entries))
    }


def main():
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    old_v2 = json.loads(V2_PATH.read_text(encoding="utf-8"))
    registry_data, registry_indexes = load_registry(REGISTRY_PATH)
    old_entries = old_v2.get("entries") or {}
    now = datetime.now(timezone.utc)

    entries = sync_entries(v1, old_entries, registry_data, registry_indexes, now)

    result = {
        "entries": entries,
        "generatedAt": iso_z(now),
        "retryPolicy": old_v2.get(
            "retryPolicy",
            {
                "rejectedAutomaticRetry": False,
                "unresolvedDays": 1,
            },
        ),
        "schema": 2,
    }
    validate_cache(result)
    V2_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        "artwork-cache-v2:",
        len(entries),
        "entries | publishable=",
        sum(1 for value in entries.values() if value.get("publishable")),
    )


if __name__ == "__main__":
    main()
