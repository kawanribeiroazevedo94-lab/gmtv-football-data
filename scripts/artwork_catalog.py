"""Reviewed artwork, independent of the current fixture window.

The catalog binds a provider's entity ID to its logo, not a search thumbnail.
Adding an alias requires an unambiguous identity; collisions fail closed.
Network/visual evidence stays in the catalog and is not exposed in the feed.
"""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata


CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "artwork-catalog.json"


def artwork_name(value):
    """Retain SC/FC: Barcelona SC and Barcelona are different clubs."""
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def scoped_team_key(name, competition_name):
    return f"team:{artwork_name(name)}@{artwork_name(competition_name)}"


def validate_catalog(data):
    if data.get("schema") != 1 or not isinstance(data.get("records"), list):
        raise ValueError("Invalid artwork catalog schema")
    index = {}
    ids = set()
    for row in data["records"]:
        record_id = row["id"]
        if record_id in ids:
            raise ValueError(f"Duplicate artwork ID: {record_id}")
        ids.add(record_id)
        if row["kind"] not in {"team", "competition"}:
            raise ValueError(f"Invalid artwork kind: {record_id}")
        if row["entityType"] not in {"club", "national_team", "competition"}:
            raise ValueError(f"Invalid entity type: {record_id}")
        proof = row["verification"]
        if (not row["url"].startswith("https://")
                or proof["httpStatus"] != 200
                or proof["mime"] != "image/png"
                or min(proof["width"], proof["height"]) < 32
                or len(proof["sha256"]) != 64
                or row["reviewStatus"] != "approved"
                or not row["sourceUrl"].startswith("https://")):
            raise ValueError(f"Unverified artwork: {record_id}")
        for name in [row["name"], *row.get("aliases", [])]:
            normalized = artwork_name(name)
            key = f'{row["kind"]}:{normalized}'
            if not key.split(":", 1)[1]:
                raise ValueError(f"Empty artwork alias: {record_id}")
            matches = index.setdefault(key, [])
            if not any(r["id"] == record_id for r in matches):
                matches.append(row)
    return index


@lru_cache(maxsize=1)
def catalog_index():
    return validate_catalog(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def find_catalog_artwork(name, kind, competition_name=None, country_hint=None):
    normalized = artwork_name(name)
    matches = catalog_index().get(f"{kind}:{normalized}", [])
    if kind == "team" and competition_name:
        competition = find_catalog_artwork(competition_name, "competition")
        if competition:
            scoped = [r for r in matches if competition.get("league") in r.get("leagues", [])]
            if len(scoped) == 1:
                return scoped[0]
    if kind == "team" and country_hint:
        scoped = [r for r in matches if r.get("country") == country_hint]
        if len(scoped) == 1:
            return scoped[0]
    return matches[0] if len(matches) == 1 else None


def catalog_entry(row, name, resolver_version):
    proof = row["verification"]
    return {
        "name": name,
        "qid": None,
        "url": row["url"],
        "status": "validated",
        "semanticStatus": "validated",
        "fetchStatus": "ok",
        "visualStatus": "approved",
        "entityType": row["entityType"],
        "provider": row["provider"],
        "property": "provider-logo",
        "sourceFile": None,
        "sourceUrl": row["sourceUrl"],
        "providerEntityId": row["providerEntityId"],
        "catalogId": row["id"],
        "sha256": proof["sha256"],
        "width": proof["width"],
        "height": proof["height"],
        "mime": proof["mime"],
        "resolverVersion": resolver_version,
        "validatedAt": proof["checkedAt"],
        "nextRetryAfter": None,
    }


def prime_catalog(cache, resolver_version):
    # Canonical entries are retained even when no current match references them.
    records = {r["id"]: r for values in catalog_index().values() for r in values}
    for row in records.values():
        normalized = artwork_name(row["name"])
        key = f'{row["kind"]}:{normalized}'
        if find_catalog_artwork(row["name"], row["kind"]) is None:
            continue
        old = cache.get(key) or {}
        if (old.get("status") == "validated" and old.get("url")
                and old.get("semanticStatus") == "validated"
                and old.get("fetchStatus") == "ok"
                and old.get("visualStatus") == "approved"):
            continue
        cache[key] = catalog_entry(row, row["name"], resolver_version)
