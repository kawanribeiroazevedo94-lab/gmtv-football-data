#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "artwork-cache-v2.json"
)

VALID_ENTITY_TYPES = {
    "club",
    "competition",
    "national_team",
    "federation",
    "unknown",
}

VALID_RESOLUTION_STATUSES = {
    "validated",
    "pending_review",
    "unresolved",
    "rejected",
}

VALID_SEMANTIC_STATUSES = {
    "validated",
    "unresolved",
    "rejected",
}

VALID_FETCH_STATUSES = {
    "not_checked",
    "ok",
    "failed",
}

VALID_VISUAL_STATUSES = {
    "not_checked",
    "approved",
    "rejected",
}


class ArtworkCacheValidationError(ValueError):
    pass


def parse_utc(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ArtworkCacheValidationError("timestamp must be a string or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtworkCacheValidationError(
            f"invalid timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise ArtworkCacheValidationError(
            f"timestamp must be timezone-aware: {value!r}"
        )
    return parsed.astimezone(timezone.utc)


def validate_entry(key, entry):
    if not isinstance(key, str) or not key:
        raise ArtworkCacheValidationError("cache key must be non-empty")
    if not isinstance(entry, dict):
        raise ArtworkCacheValidationError(f"entry {key} must be an object")

    required = {
        "cacheKey",
        "gmId",
        "entityType",
        "name",
        "wikidataQid",
        "resolutionStatus",
        "semanticStatus",
        "fetchStatus",
        "visualStatus",
        "artworkProvider",
        "artworkProperty",
        "artworkUrl",
        "candidateUrl",
        "publishable",
        "attemptCount",
        "lastAttemptAt",
        "nextReviewAfter",
        "rejectedReason",
        "rejectedAt",
        "provenance",
    }
    missing = required - set(entry)
    if missing:
        raise ArtworkCacheValidationError(
            f"entry {key} missing fields: {sorted(missing)}"
        )

    if entry["cacheKey"] != key:
        raise ArtworkCacheValidationError(
            f"cacheKey mismatch for {key}"
        )

    if entry["entityType"] not in VALID_ENTITY_TYPES:
        raise ArtworkCacheValidationError(
            f"invalid entityType for {key}"
        )

    if not isinstance(entry["name"], str) or not entry["name"].strip():
        raise ArtworkCacheValidationError(
            f"invalid name for {key}"
        )

    gm_id = entry["gmId"]
    if gm_id is not None and (
        not isinstance(gm_id, str) or not gm_id.strip()
    ):
        raise ArtworkCacheValidationError(
            f"invalid gmId for {key}"
        )

    qid = entry["wikidataQid"]
    if qid is not None and (
        not isinstance(qid, str)
        or not qid.startswith("Q")
        or not qid[1:].isdigit()
    ):
        raise ArtworkCacheValidationError(
            f"invalid wikidataQid for {key}"
        )

    if entry["resolutionStatus"] not in VALID_RESOLUTION_STATUSES:
        raise ArtworkCacheValidationError(
            f"invalid resolutionStatus for {key}"
        )

    if entry["semanticStatus"] not in VALID_SEMANTIC_STATUSES:
        raise ArtworkCacheValidationError(
            f"invalid semanticStatus for {key}"
        )

    if entry["fetchStatus"] not in VALID_FETCH_STATUSES:
        raise ArtworkCacheValidationError(
            f"invalid fetchStatus for {key}"
        )

    if entry["visualStatus"] not in VALID_VISUAL_STATUSES:
        raise ArtworkCacheValidationError(
            f"invalid visualStatus for {key}"
        )

    for field in (
        "artworkProvider",
        "artworkProperty",
        "artworkUrl",
        "candidateUrl",
        "rejectedReason",
    ):
        value = entry[field]
        if value is not None and not isinstance(value, str):
            raise ArtworkCacheValidationError(
                f"{field} must be string or null for {key}"
            )

    if not isinstance(entry["publishable"], bool):
        raise ArtworkCacheValidationError(
            f"publishable must be bool for {key}"
        )

    attempt_count = entry["attemptCount"]
    if (
        not isinstance(attempt_count, int)
        or isinstance(attempt_count, bool)
        or attempt_count < 0
    ):
        raise ArtworkCacheValidationError(
            f"invalid attemptCount for {key}"
        )

    parse_utc(entry["lastAttemptAt"])
    parse_utc(entry["nextReviewAfter"])
    parse_utc(entry["rejectedAt"])

    provenance = entry["provenance"]
    if not isinstance(provenance, dict):
        raise ArtworkCacheValidationError(
            f"provenance must be object for {key}"
        )
    if provenance.get("migratedFrom") != "artwork-cache-v1":
        raise ArtworkCacheValidationError(
            f"invalid migratedFrom for {key}"
        )

    status = entry["resolutionStatus"]

    if status == "validated":
        if entry["semanticStatus"] != "validated":
            raise ArtworkCacheValidationError(
                f"validated artwork without semantic validation for {key}"
            )
        if entry["fetchStatus"] != "ok":
            raise ArtworkCacheValidationError(
                f"validated artwork without fetch validation for {key}"
            )
        if entry["visualStatus"] != "approved":
            raise ArtworkCacheValidationError(
                f"validated artwork without visual approval for {key}"
            )
        if not entry["artworkUrl"]:
            raise ArtworkCacheValidationError(
                f"validated artwork missing URL for {key}"
            )
        if not entry["publishable"]:
            raise ArtworkCacheValidationError(
                f"validated artwork must be publishable for {key}"
            )

    if status in {"pending_review", "unresolved", "rejected"}:
        if entry["publishable"]:
            raise ArtworkCacheValidationError(
                f"non-validated artwork cannot be publishable for {key}"
            )
        if entry["artworkUrl"] is not None:
            raise ArtworkCacheValidationError(
                f"non-validated artwork cannot expose artworkUrl for {key}"
            )

    if status == "rejected":
        if not entry["rejectedReason"]:
            raise ArtworkCacheValidationError(
                f"rejected entry missing reason for {key}"
            )
        if not entry["rejectedAt"]:
            raise ArtworkCacheValidationError(
                f"rejected entry missing rejectedAt for {key}"
            )
        if entry["nextReviewAfter"] is not None:
            raise ArtworkCacheValidationError(
                f"rejected entry must not retry automatically for {key}"
            )

    if status in {"pending_review", "unresolved"}:
        if entry["nextReviewAfter"] is None:
            raise ArtworkCacheValidationError(
                f"retryable entry missing nextReviewAfter for {key}"
            )

    return True


def validate_cache(data):
    if not isinstance(data, dict):
        raise ArtworkCacheValidationError("cache root must be an object")
    if data.get("schema") != 2:
        raise ArtworkCacheValidationError("unsupported cache schema")

    entries = data.get("entries")
    if not isinstance(entries, dict):
        raise ArtworkCacheValidationError("entries must be an object")

    for key, entry in entries.items():
        validate_entry(key, entry)

    return True


def load_cache(path=DEFAULT_CACHE_PATH):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_cache(data)
    return data


def get_publishable_url(entry):
    validate_entry(entry["cacheKey"], entry)
    if entry["resolutionStatus"] != "validated":
        return None
    if not entry["publishable"]:
        return None
    return entry["artworkUrl"]


def should_retry(entry, now=None):
    validate_entry(entry["cacheKey"], entry)

    if entry["resolutionStatus"] == "rejected":
        return False
    if entry["resolutionStatus"] == "validated":
        return False

    review_at = parse_utc(entry["nextReviewAfter"])
    if review_at is None:
        return False

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        raise ArtworkCacheValidationError(
            "retry clock must be timezone-aware"
        )
    else:
        now = now.astimezone(timezone.utc)

    return now >= review_at
