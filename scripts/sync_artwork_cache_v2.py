#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from artwork_cache_v2 import validate_cache
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


def make_new_entry(
    key,
    legacy,
    *,
    registry_data,
    registry_indexes,
    migrated_at,
):
    entity_type = entity_type_for_key(key)
    name = str(legacy.get("name") or key.split(":", 1)[-1]).strip()
    qid = legacy.get("qid")
    url = legacy.get("url")
    rejected = legacy.get("status") == "rejected"

    gm_id = registry_gm_id(
        registry_data,
        registry_indexes,
        entity_type,
        name,
    )

    base = {
        "cacheKey": key,
        "gmId": gm_id,
        "entityType": entity_type,
        "name": name,
        "wikidataQid": qid,
        "resolutionStatus": "unresolved",
        "semanticStatus": "unresolved",
        "fetchStatus": "not_checked",
        "visualStatus": "not_checked",
        "artworkProvider": None,
        "artworkProperty": None,
        "artworkUrl": None,
        "candidateUrl": None,
        "publishable": False,
        "attemptCount": 1,
        "lastAttemptAt": None,
        "nextReviewAfter": iso_z(
            migrated_at + timedelta(days=7)
        ),
        "rejectedReason": None,
        "rejectedAt": None,
        "provenance": {
            "migratedAt": iso_z(migrated_at),
            "migratedFrom": "artwork-cache-v1",
        },
    }

    if rejected:
        base.update({
            "resolutionStatus": "rejected",
            "semanticStatus": "rejected",
            "visualStatus": "rejected",
            "artworkProvider": "wikidata" if qid else None,
            "nextReviewAfter": None,
            "rejectedReason": (
                legacy.get("rejectedReason")
                or "legacy_rejected"
            ),
            "rejectedAt": (
                legacy.get("rejectedAt")
                or iso_z(migrated_at)
            ),
            "lastAttemptAt": legacy.get("rejectedAt"),
        })
    elif url:
        base.update({
            "resolutionStatus": "pending_review",
            "artworkProvider": "wikidata",
            "artworkProperty": "legacy_unknown",
            "candidateUrl": url,
            # Candidato novo fica imediatamente elegível
            # para revisão, mas nunca publicável automaticamente.
            "nextReviewAfter": iso_z(migrated_at),
        })

    return base


def refresh_existing(
    current,
    legacy,
    *,
    registry_data,
    registry_indexes,
    now,
):
    entry = copy.deepcopy(current)
    key = entry["cacheKey"]
    entity_type = entity_type_for_key(key)
    name = str(
        legacy.get("name")
        or entry.get("name")
        or key.split(":", 1)[-1]
    ).strip()

    entry["name"] = name
    entry["entityType"] = entity_type
    entry["wikidataQid"] = legacy.get("qid")

    resolved = registry_gm_id(
        registry_data,
        registry_indexes,
        entity_type,
        name,
    )
    if resolved:
        entry["gmId"] = resolved

    # Decisões humanas/forenses já consolidadas têm precedência.
    if entry["resolutionStatus"] in {"rejected", "validated"}:
        return entry

    if legacy.get("status") == "rejected":
        entry.update({
            "resolutionStatus": "rejected",
            "semanticStatus": "rejected",
            "fetchStatus": "not_checked",
            "visualStatus": "rejected",
            "artworkProvider": "wikidata" if legacy.get("qid") else None,
            "artworkProperty": None,
            "artworkUrl": None,
            "candidateUrl": None,
            "publishable": False,
            "nextReviewAfter": None,
            "rejectedReason": (
                legacy.get("rejectedReason")
                or "legacy_rejected"
            ),
            "rejectedAt": (
                legacy.get("rejectedAt")
                or iso_z(now)
            ),
            "lastAttemptAt": legacy.get("rejectedAt"),
        })
        return entry

    url = legacy.get("url")
    if url:
        entry.update({
            "resolutionStatus": "pending_review",
            "fetchStatus": "not_checked",
            "visualStatus": "not_checked",
            "artworkProvider": "wikidata",
            "artworkProperty": "legacy_unknown",
            "artworkUrl": None,
            "candidateUrl": url,
            "publishable": False,
            "rejectedReason": None,
            "rejectedAt": None,
        })
        if not entry.get("nextReviewAfter"):
            entry["nextReviewAfter"] = iso_z(now)
    else:
        entry.update({
            "resolutionStatus": "unresolved",
            "semanticStatus": "unresolved",
            "fetchStatus": "not_checked",
            "visualStatus": "not_checked",
            "artworkUrl": None,
            "candidateUrl": None,
            "publishable": False,
            "rejectedReason": None,
            "rejectedAt": None,
        })
        if not entry.get("nextReviewAfter"):
            entry["nextReviewAfter"] = iso_z(
                now + timedelta(days=7)
            )

    return entry


def main():
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    old_v2 = json.loads(V2_PATH.read_text(encoding="utf-8"))
    registry_data, registry_indexes = load_registry(REGISTRY_PATH)

    old_entries = old_v2.get("entries") or {}
    now = datetime.now(timezone.utc)

    new_entries = {}
    for key in sorted(v1):
        legacy = v1[key]
        if key in old_entries:
            entry = refresh_existing(
                old_entries[key],
                legacy,
                registry_data=registry_data,
                registry_indexes=registry_indexes,
                now=now,
            )
        else:
            entry = make_new_entry(
                key,
                legacy,
                registry_data=registry_data,
                registry_indexes=registry_indexes,
                migrated_at=now,
            )
        new_entries[key] = entry

    changed = new_entries != old_entries

    result = {
        "entries": new_entries,
        "generatedAt": (
            iso_z(now)
            if changed
            else old_v2.get("generatedAt")
        ),
        "retryPolicy": old_v2.get(
            "retryPolicy",
            {
                "rejectedAutomaticRetry": False,
                "unresolvedDays": 7,
            },
        ),
        "schema": 2,
    }

    validate_cache(result)

    V2_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "artwork-cache-v2:",
        len(new_entries),
        "entries | changed=",
        changed,
    )


if __name__ == "__main__":
    main()
