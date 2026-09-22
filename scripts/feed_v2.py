#!/usr/bin/env python3
from __future__ import annotations

import copy
from collections import defaultdict

from artwork_cache_v2 import get_publishable_url
from entity_registry import normalize_identity, resolve_entity

SCHEMA_VERSION = 2

STATUS_PRIORITY = {
    "validated": 4,
    "pending_review": 3,
    "unresolved": 2,
    "rejected": 1,
}


class FeedV2ValidationError(ValueError):
    pass


def _observed_provider(match, entity):
    external_id = entity.get("id")
    if external_id is None:
        return None, None

    explicit_provider = str(
        entity.get("idProvider") or ""
    ).strip().lower()
    if explicit_provider:
        return explicit_provider, str(external_id)

    sources = match.get("sources") or []
    if "football-data" in sources:
        return "football-data", str(external_id)

    return None, None


def _cache_indexes(cache_v2):
    entries = cache_v2.get("entries") or {}
    by_gm_id = defaultdict(list)

    for entry in entries.values():
        gm_id = entry.get("gmId")
        if gm_id:
            by_gm_id[gm_id].append(entry)

    for values in by_gm_id.values():
        values.sort(
            key=lambda item: STATUS_PRIORITY.get(
                item.get("resolutionStatus"),
                0,
            ),
            reverse=True,
        )

    return entries, by_gm_id


def _legacy_cache_key(entity_type, name):
    normalized = normalize_identity(name)
    if not normalized:
        return None
    prefix = "competition" if entity_type == "competition" else "team"
    return f"{prefix}:{normalized}"


def _select_artwork_entry(
    *,
    entity_type,
    name,
    gm_id,
    cache_entries,
    cache_by_gm_id,
):
    if gm_id:
        candidates = cache_by_gm_id.get(gm_id) or []
        if candidates:
            return candidates[0]

    key = _legacy_cache_key(entity_type, name)
    if key:
        return cache_entries.get(key)

    return None


def _public_artwork(entry):
    if entry is None:
        return {
            "status": "unresolved",
            "url": None,
            "provider": None,
            "property": None,
            "semanticStatus": "unresolved",
            "fetchStatus": "not_checked",
            "visualStatus": "not_checked",
        }

    return {
        "status": entry.get("resolutionStatus"),
        "url": get_publishable_url(entry),
        "provider": entry.get("artworkProvider"),
        "property": entry.get("artworkProperty"),
        "semanticStatus": entry.get("semanticStatus"),
        "fetchStatus": entry.get("fetchStatus"),
        "visualStatus": entry.get("visualStatus"),
    }


def _entity_v2(
    *,
    match,
    raw,
    entity_type,
    registry_data,
    registry_indexes,
    cache_entries,
    cache_by_gm_id,
):
    display_name = raw.get("name") or raw.get("fullName") or ""

    provider, external_id = _observed_provider(match, raw)

    resolved = resolve_entity(
        registry_data,
        registry_indexes,
        entity_type=entity_type,
        name=display_name,
        provider=provider,
        external_id=external_id,
    )

    gm_id = resolved.get("gmId") if resolved else None

    observed_external_ids = {}
    if provider and external_id is not None:
        observed_external_ids[provider] = external_id

    registered_external_ids = {}
    if resolved:
        registered_external_ids = {
            str(key): str(value)
            for key, value in (resolved.get("externalIds") or {}).items()
        }

    merged_external_ids = dict(registered_external_ids)
    for key, value in observed_external_ids.items():
        current = merged_external_ids.get(key)
        if current is None:
            merged_external_ids[key] = value
        elif current != value:
            resolved = None
            gm_id = None
            merged_external_ids = observed_external_ids
            break

    artwork_entry = _select_artwork_entry(
        entity_type=entity_type,
        name=display_name,
        gm_id=gm_id,
        cache_entries=cache_entries,
        cache_by_gm_id=cache_by_gm_id,
    )

    output = {
        "gmId": gm_id,
        "entityType": entity_type,
        "identityStatus": "resolved" if resolved is not None else "unresolved",
        "canonicalName": resolved.get("canonicalName") if resolved else None,
        "displayName": display_name or None,
        "fullName": raw.get("fullName"),
        "normalized": raw.get("normalized"),
        "country": resolved.get("country") if resolved else None,
        "externalIds": merged_external_ids,
        "wikidataQid": resolved.get("wikidataQid") if resolved else None,
        "validationStatus": (
            resolved.get("validationStatus") if resolved else "unresolved"
        ),
        "confidence": resolved.get("confidence") if resolved else "unknown",
        "resolutionStatus": (
            resolved.get("resolutionStatus") if resolved else "unresolved"
        ),
        "artwork": _public_artwork(artwork_entry),
    }

    if entity_type == "competition":
        output["code"] = raw.get("code")

    return output


def build_match_v2(
    match,
    *,
    registry_data,
    registry_indexes,
    artwork_cache_v2,
):
    cache_entries, cache_by_gm_id = _cache_indexes(artwork_cache_v2)

    return {
        "id": match.get("id"),
        "date": match.get("date"),
        "kickoff": match.get("kickoff"),
        "utcDate": match.get("utcDate"),
        "status": match.get("status"),
        "competition": _entity_v2(
            match=match,
            raw=match.get("competition") or {},
            entity_type="competition",
            registry_data=registry_data,
            registry_indexes=registry_indexes,
            cache_entries=cache_entries,
            cache_by_gm_id=cache_by_gm_id,
        ),
        "home": _entity_v2(
            match=match,
            raw=match.get("home") or {},
            entity_type="club",
            registry_data=registry_data,
            registry_indexes=registry_indexes,
            cache_entries=cache_entries,
            cache_by_gm_id=cache_by_gm_id,
        ),
        "away": _entity_v2(
            match=match,
            raw=match.get("away") or {},
            entity_type="club",
            registry_data=registry_data,
            registry_indexes=registry_indexes,
            cache_entries=cache_entries,
            cache_by_gm_id=cache_by_gm_id,
        ),
        "sources": list(match.get("sources") or []),
        "sourcePriority": match.get("sourcePriority"),
        "provenance": {
            "fixtureSources": list(match.get("sources") or []),
            "sourcePriority": match.get("sourcePriority"),
            "sourceDetails": copy.deepcopy(
                match.get("provenance") or {}
            ),
        },
    }


def build_feed_v2(
    feed_v1,
    *,
    registry_data,
    registry_indexes,
    artwork_cache_v2,
):
    if feed_v1.get("schema") != 1:
        raise FeedV2ValidationError("source feed must use schema 1")

    source_snapshot = copy.deepcopy(feed_v1)

    matches = [
        build_match_v2(
            match,
            registry_data=registry_data,
            registry_indexes=registry_indexes,
            artwork_cache_v2=artwork_cache_v2,
        )
        for match in feed_v1.get("matches") or []
    ]

    by_id = {
        match.get("id"): match
        for match in matches
        if match.get("id")
    }

    days = []
    for day in feed_v1.get("days") or []:
        day_matches = []
        for source_match in day.get("matches") or []:
            match_id = source_match.get("id")
            built = by_id.get(match_id)
            if built is None:
                built = build_match_v2(
                    source_match,
                    registry_data=registry_data,
                    registry_indexes=registry_indexes,
                    artwork_cache_v2=artwork_cache_v2,
                )
            day_matches.append(copy.deepcopy(built))

        days.append(
            {
                "date": day.get("date"),
                "label": day.get("label"),
                "count": len(day_matches),
                "matches": day_matches,
            }
        )

    result = {
        "schema": SCHEMA_VERSION,
        "generatedAt": feed_v1.get("generatedAt"),
        "timezone": feed_v1.get("timezone"),
        "window": copy.deepcopy(feed_v1.get("window") or {}),
        "sources": copy.deepcopy(feed_v1.get("sources") or {}),
        "contracts": {
            "identityRegistrySchema": registry_data.get("schema"),
            "artworkCacheSchema": artwork_cache_v2.get("schema"),
        },
        "days": days,
        "matches": matches,
    }

    if feed_v1 != source_snapshot:
        raise FeedV2ValidationError("schema 1 source was mutated")

    validate_feed_v2(result)
    return result


def validate_feed_v2(feed):
    if not isinstance(feed, dict):
        raise FeedV2ValidationError("feed root must be an object")
    if feed.get("schema") != 2:
        raise FeedV2ValidationError("feed schema must be 2")

    matches = feed.get("matches")
    days = feed.get("days")

    if not isinstance(matches, list):
        raise FeedV2ValidationError("matches must be a list")
    if not isinstance(days, list):
        raise FeedV2ValidationError("days must be a list")

    seen = set()
    for match in matches:
        match_id = match.get("id")
        if not match_id:
            raise FeedV2ValidationError("match without id")
        if match_id in seen:
            raise FeedV2ValidationError(f"duplicate match id: {match_id}")
        seen.add(match_id)

        for role, expected_type in (
            ("competition", "competition"),
            ("home", "club"),
            ("away", "club"),
        ):
            entity = match.get(role)
            if not isinstance(entity, dict):
                raise FeedV2ValidationError(
                    f"invalid {role} in {match_id}"
                )
            if entity.get("entityType") != expected_type:
                raise FeedV2ValidationError(
                    f"wrong entity type for {role} in {match_id}"
                )

            identity_status = entity.get("identityStatus")
            if identity_status not in {"resolved", "unresolved"}:
                raise FeedV2ValidationError(
                    f"invalid identityStatus in {match_id}"
                )
            if identity_status == "resolved" and not entity.get("gmId"):
                raise FeedV2ValidationError(
                    f"resolved entity without gmId in {match_id}"
                )

            if not isinstance(entity.get("externalIds"), dict):
                raise FeedV2ValidationError(
                    f"externalIds must be object in {match_id}"
                )

            artwork = entity.get("artwork")
            if not isinstance(artwork, dict):
                raise FeedV2ValidationError(
                    f"artwork must be object in {match_id}"
                )

            if (
                artwork.get("url") is not None
                and artwork.get("status") != "validated"
            ):
                raise FeedV2ValidationError(
                    f"unvalidated artwork URL in {match_id}"
                )

            forbidden = {
                "candidateUrl",
                "nextReviewAfter",
                "rejectedReason",
                "rejectedAt",
            }
            if forbidden & set(artwork):
                raise FeedV2ValidationError(
                    f"private cache fields leaked in {match_id}"
                )

    for day in days:
        day_matches = day.get("matches")
        if not isinstance(day_matches, list):
            raise FeedV2ValidationError("day matches must be a list")
        if day.get("count") != len(day_matches):
            raise FeedV2ValidationError(
                f"day count mismatch: {day.get('date')}"
            )
        for match in day_matches:
            if match.get("id") not in seen:
                raise FeedV2ValidationError(
                    "day references unknown match"
                )

    return True
