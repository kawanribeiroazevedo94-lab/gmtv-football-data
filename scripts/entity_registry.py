#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "entity-registry.json"

ENTITY_TYPES = {"club", "competition", "national_team", "federation", "unknown"}
VALIDATION_STATUSES = {"validated", "unresolved", "rejected"}
RESOLUTION_STATUSES = {"resolved", "partial", "unresolved"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}

GM_ID_PREFIXES = {
    "club": "club:",
    "competition": "competition:",
    "national_team": "national-team:",
    "federation": "federation:",
    "unknown": "unknown:",
}

DROP_WORDS = {
    "fc", "afc", "cf", "sc", "ac", "ec", "se", "ca", "cr", "fbc",
    "club", "clube", "football", "futebol", "calcio", "de", "do", "da", "the",
}


class RegistryValidationError(ValueError):
    pass


def normalize_identity(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in DROP_WORDS]
    return " ".join(tokens).strip()


def _external_id_key(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_registry(data):
    if not isinstance(data, dict):
        raise RegistryValidationError("registry root must be an object")
    if data.get("schema") != 1:
        raise RegistryValidationError("unsupported registry schema")

    entities = data.get("entities")
    if not isinstance(entities, list):
        raise RegistryValidationError("entities must be a list")

    gm_ids = set()
    alias_index = {}
    external_index = {}
    qid_index = {}

    for position, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise RegistryValidationError(f"entity at index {position} must be an object")

        gm_id = entity.get("gmId")
        entity_type = entity.get("entityType")
        canonical_name = entity.get("canonicalName")
        aliases = entity.get("aliases")
        country = entity.get("country")
        external_ids = entity.get("externalIds")
        qid = entity.get("wikidataQid")
        validation_status = entity.get("validationStatus")
        validated_at = entity.get("validatedAt")
        confidence = entity.get("confidence")
        resolution_status = entity.get("resolutionStatus")

        if not isinstance(gm_id, str) or not gm_id.strip():
            raise RegistryValidationError(f"invalid gmId at index {position}")
        if gm_id in gm_ids:
            raise RegistryValidationError(f"duplicate gmId: {gm_id}")
        gm_ids.add(gm_id)

        if entity_type not in ENTITY_TYPES:
            raise RegistryValidationError(f"invalid entityType for {gm_id}: {entity_type!r}")
        if not gm_id.startswith(GM_ID_PREFIXES[entity_type]):
            raise RegistryValidationError(f"gmId prefix/type mismatch: {gm_id}")

        if not isinstance(canonical_name, str) or not canonical_name.strip():
            raise RegistryValidationError(f"invalid canonicalName for {gm_id}")

        if not isinstance(aliases, list) or any(
            not isinstance(alias, str) or not alias.strip() for alias in aliases
        ):
            raise RegistryValidationError(f"invalid aliases for {gm_id}")

        if country is not None and (not isinstance(country, str) or not country.strip()):
            raise RegistryValidationError(f"invalid country for {gm_id}")

        if not isinstance(external_ids, dict):
            raise RegistryValidationError(f"externalIds must be an object for {gm_id}")

        if qid is not None and not re.fullmatch(r"Q[1-9][0-9]*", str(qid)):
            raise RegistryValidationError(f"invalid wikidataQid for {gm_id}: {qid!r}")

        if validation_status not in VALIDATION_STATUSES:
            raise RegistryValidationError(f"invalid validationStatus for {gm_id}")

        if not isinstance(validated_at, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", validated_at
        ):
            raise RegistryValidationError(f"invalid validatedAt for {gm_id}")

        if confidence not in CONFIDENCE_LEVELS:
            raise RegistryValidationError(f"invalid confidence for {gm_id}")

        if resolution_status not in RESOLUTION_STATUSES:
            raise RegistryValidationError(f"invalid resolutionStatus for {gm_id}")

        for candidate_name in [canonical_name, *aliases]:
            normalized = normalize_identity(candidate_name)
            if not normalized:
                raise RegistryValidationError(f"empty normalized alias for {gm_id}")
            key = (entity_type, normalized)
            current = alias_index.get(key)
            if current is not None and current != gm_id:
                raise RegistryValidationError(
                    f"alias collision for {entity_type}:{normalized}: {current} vs {gm_id}"
                )
            alias_index[key] = gm_id

        for provider, external_id in external_ids.items():
            if not isinstance(provider, str) or not provider.strip():
                raise RegistryValidationError(f"invalid provider for {gm_id}")
            normalized_external_id = _external_id_key(external_id)
            if normalized_external_id is None:
                raise RegistryValidationError(f"invalid external id for {gm_id}:{provider}")
            key = (entity_type, provider.strip().lower(), normalized_external_id)
            current = external_index.get(key)
            if current is not None and current != gm_id:
                raise RegistryValidationError(
                    f"external id collision for {key}: {current} vs {gm_id}"
                )
            external_index[key] = gm_id

        if qid:
            key = (entity_type, qid)
            current = qid_index.get(key)
            if current is not None and current != gm_id:
                raise RegistryValidationError(f"Wikidata QID collision for {key}")
            qid_index[key] = gm_id

    return {
        "byGmId": {entity["gmId"]: entity for entity in entities},
        "byAlias": alias_index,
        "byExternalId": external_index,
        "byWikidataQid": qid_index,
    }


def load_registry(path=DEFAULT_REGISTRY_PATH):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    indexes = validate_registry(data)
    return data, indexes


def resolve_entity(
    data,
    indexes,
    *,
    entity_type,
    name=None,
    provider=None,
    external_id=None,
    wikidata_qid=None,
):
    if entity_type not in ENTITY_TYPES:
        return None

    candidates = []

    if provider and external_id is not None:
        key = (
            entity_type,
            str(provider).strip().lower(),
            _external_id_key(external_id),
        )
        gm_id = indexes["byExternalId"].get(key)
        if gm_id:
            candidates.append(gm_id)

    if wikidata_qid:
        gm_id = indexes["byWikidataQid"].get(
            (entity_type, str(wikidata_qid).strip())
        )
        if gm_id:
            candidates.append(gm_id)

    if name:
        normalized = normalize_identity(name)
        if normalized:
            gm_id = indexes["byAlias"].get((entity_type, normalized))
            if gm_id:
                candidates.append(gm_id)

    unique = set(candidates)
    if len(unique) != 1:
        return None
    return indexes["byGmId"][unique.pop()]


def resolve_gm_id(*args, **kwargs):
    entity = resolve_entity(*args, **kwargs)
    return entity.get("gmId") if entity else None
