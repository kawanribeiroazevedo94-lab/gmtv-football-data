#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
RESOLVER_VERSION = 4

DROP_WORDS = {
    "fc", "afc", "cf", "sc", "ac", "ec", "se", "ca", "cr", "fbc",
    "club", "clube", "football", "futebol", "calcio", "de", "do", "da", "the",
}

# Catálogo que deve ficar pré-resolvido mesmo quando não houver jogo na janela atual.
# O calendário continua vindo das fontes de fixtures; isto é somente identidade visual.
COMPETITION_CATALOG = (
    ("Brasileirão Série A", "Campeonato Brasileiro Série A", "Brazil"),
    ("Brasileirão Série B", "Campeonato Brasileiro Série B", "Brazil"),
    ("Copa do Brasil", "Copa do Brasil", "Brazil"),
    ("Supercopa do Brasil", "Supercopa do Brasil", "Brazil"),
    ("Campeonato Paulista", "Campeonato Paulista", "Brazil"),
    ("Campeonato Carioca", "Campeonato Carioca", "Brazil"),
    ("Campeonato Mineiro", "Campeonato Mineiro", "Brazil"),
    ("Campeonato Gaúcho", "Campeonato Gaúcho", "Brazil"),
    ("Copa Libertadores", "Copa Libertadores", "South America"),
    ("Copa Sul-Americana", "Copa Sudamericana", "South America"),
    ("Recopa Sul-Americana", "Recopa Sudamericana", "South America"),
    ("Premier League", "Premier League", "England"),
    ("La Liga", "La Liga", "Spain"),
    ("Serie A", "Serie A Italy", "Italy"),
    ("Bundesliga", "Bundesliga Germany", "Germany"),
    ("Ligue 1", "Ligue 1 France", "France"),
    ("Liga Portugal", "Primeira Liga Portugal", "Portugal"),
    ("Eredivisie", "Eredivisie Netherlands", "Netherlands"),
    ("UEFA Champions League", "UEFA Champions League", "Europe"),
    ("UEFA Europa League", "UEFA Europa League", "Europe"),
    ("UEFA Conference League", "UEFA Conference League", "Europe"),
    ("UEFA Super Cup", "UEFA Super Cup", "Europe"),
    ("FA Cup", "FA Cup England", "England"),
    ("Copa del Rey", "Copa del Rey", "Spain"),
    ("Coppa Italia", "Coppa Italia", "Italy"),
    ("DFB-Pokal", "DFB-Pokal", "Germany"),
    ("MLS", "Major League Soccer", "United States"),
    ("Liga MX", "Liga MX", "Mexico"),
    ("Campeonato Argentino", "Argentine Primera División", "Argentina"),
    ("Saudi Pro League", "Saudi Pro League", "Saudi Arabia"),
    ("FIFA Club World Cup", "FIFA Club World Cup", "World"),
    ("FIFA Intercontinental Cup", "FIFA Intercontinental Cup", "World"),
    ("Copa do Mundo", "FIFA World Cup", "World"),
    ("Copa América", "Copa América", "South America"),
    ("Eurocopa", "UEFA European Championship", "Europe"),
    ("UEFA Nations League", "UEFA Nations League", "Europe"),
)

# Correções de ambiguidade para clubes que aparecem no feed com nomes curtos.
TEAM_SEARCH_ALIASES = {
    "america mineiro": "América Futebol Clube Minas Gerais",
    "athletic": "Athletic Club Minas Gerais Brazil",
    "athletic club": "Athletic Club Minas Gerais Brazil",
    "atletico goianiense": "Atlético Clube Goianiense",
    "austria wien": "FK Austria Wien",
    "avai": "Avaí Futebol Clube",
    "bayern munich": "FC Bayern Munich",
    "benfica": "SL Benfica",
    "crb": "Clube de Regatas Brasil",
    "ceara": "Ceará Sporting Club",
    "criciuma": "Criciúma Esporte Clube",
    "cuiaba": "Cuiabá Esporte Clube",
    "fortaleza": "Fortaleza Esporte Clube",
    "goias": "Goiás Esporte Clube",
    "gremio novorizontino": "Grêmio Novorizontino",
    "inter milan": "FC Internazionale Milano",
    "juventude": "Esporte Clube Juventude",
    "londrina": "Londrina Esporte Clube",
    "nautico": "Clube Náutico Capibaribe",
    "oh leuven": "Oud-Heverlee Leuven",
    "ol lyonnes": "OL Lyonnes football",
    "operario pr": "Operário Ferroviário Esporte Clube",
    "paris saint germain": "Paris Saint-Germain FC",
    "roma": "AS Roma",
    "servette chenois": "Servette FC Chênois Féminin",
    "sport recife": "Sport Club do Recife",
    "sao bernardo": "São Bernardo Futebol Clube",
    "vila nova": "Vila Nova Futebol Clube",
}



TEAM_PRIME_CATALOG = (
    ("Flamengo", "Brazil"), ("Palmeiras", "Brazil"),
    ("Corinthians", "Brazil"), ("São Paulo", "Brazil"),
    ("Santos", "Brazil"), ("Grêmio", "Brazil"),
    ("Internacional", "Brazil"), ("Atlético Mineiro", "Brazil"),
    ("Cruzeiro", "Brazil"), ("Fluminense", "Brazil"),
    ("Botafogo", "Brazil"), ("Vasco da Gama", "Brazil"),
    ("Real Madrid", "Spain"), ("Barcelona", "Spain"),
    ("Atlético Madrid", "Spain"), ("Athletic Bilbao", "Spain"),
    ("Arsenal", "England"), ("Chelsea", "England"),
    ("Liverpool", "England"), ("Manchester City", "England"),
    ("Manchester United", "England"), ("Tottenham Hotspur", "England"),
    ("Bayern Munich", "Germany"), ("Borussia Dortmund", "Germany"),
    ("Bayer Leverkusen", "Germany"), ("RB Leipzig", "Germany"),
    ("Inter Milan", "Italy"), ("AC Milan", "Italy"),
    ("Juventus", "Italy"), ("Napoli", "Italy"), ("Roma", "Italy"),
    ("Paris Saint-Germain", "France"), ("Olympique Marseille", "France"),
    ("Monaco", "France"), ("Benfica", "Portugal"),
    ("Porto", "Portugal"), ("Sporting CP", "Portugal"),
    ("Ajax", "Netherlands"), ("PSV Eindhoven", "Netherlands"),
    ("Feyenoord", "Netherlands"), ("Boca Juniors", "Argentina"),
    ("River Plate", "Argentina"), ("Club América", "Mexico"),
    ("Monterrey", "Mexico"), ("Inter Miami", "United States"),
    ("Al Hilal", "Saudi Arabia"), ("Al Nassr", "Saudi Arabia"),
    ("Brazil", "Brazil"), ("Argentina", "Argentina"),
    ("England", "England"), ("Spain", "Spain"), ("France", "France"),
    ("Germany", "Germany"), ("Portugal", "Portugal"), ("Italy", "Italy"),
    ("Netherlands", "Netherlands"), ("Uruguay", "Uruguay"),
)

NATIONAL_TEAM_NAMES = {
    "argentina", "belgium", "brazil", "brasil", "colombia", "croatia",
    "england", "france", "germany", "italy", "mexico", "netherlands",
    "portugal", "spain", "uruguay", "united states", "usa",
}

# O P154 histórico da Série B apontava para uma marca de 2014. Esta exceção
# força o arquivo recente conhecido e passa pelo mesmo fetch/size gate.
CURATED_COMMONS_FILES = {
    "competition:brasileirao serie b":
        "Campeonato Brasileiro Série B logo (2025).svg",
}


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in DROP_WORDS]
    return " ".join(tokens).strip()


def http_json(url, headers=None, timeout=25):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GM-TV-Plus-Artwork/4.0 (central metadata pipeline)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _utc_now():
    return datetime.now(timezone.utc)


def _iso_z(value):
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _is_fresh_validated(entry):
    return bool(
        entry
        and entry.get("status") == "validated"
        and entry.get("resolverVersion") == RESOLVER_VERSION
        and isinstance(entry.get("url"), str)
        and entry["url"].startswith("https://")
    )


def _retry_blocked(entry):
    if not entry or entry.get("resolverVersion") != RESOLVER_VERSION:
        return False
    retry_at = _parse_utc(entry.get("nextRetryAfter"))
    return bool(retry_at and _utc_now() < retry_at)


def _classify_labels(labels):
    values = [normalize(label) for label in labels if label]
    national_markers = (
        "national association football team", "national football team",
        "national soccer team", "selecao nacional futebol",
    )
    federation_markers = (
        "football federation", "soccer federation", "football association",
        "football governing body", "federacao futebol", "confederacao futebol",
    )
    club_markers = (
        "association football club", "football club", "soccer club", "clube futebol",
    )
    competition_markers = (
        "association football competition", "football competition",
        "association football league", "football league", "soccer league",
        "football tournament", "sports league", "competicao futebol",
        "liga futebol", "torneio futebol",
    )

    def has(markers):
        return any(marker in value for value in values for marker in markers)

    if has(national_markers):
        return "national_team"
    if has(federation_markers):
        return "federation"
    if has(club_markers):
        return "club"
    if has(competition_markers):
        return "competition"
    return "unknown"


def wikidata_entity_type(qid):
    query = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    })
    payload = http_json(f"{WIKIDATA_API}?{query}")
    entity = (payload.get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}

    class_ids = []
    for entry in claims.get("P31") or []:
        try:
            value = entry["mainsnak"]["datavalue"]["value"]
            class_id = value.get("id") if isinstance(value, dict) else None
        except (KeyError, TypeError):
            class_id = None
        if class_id and class_id not in class_ids:
            class_ids.append(class_id)

    if not class_ids:
        return "unknown"

    query = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": "|".join(class_ids),
        "props": "labels",
        "languages": "en|pt",
        "format": "json",
    })
    payload = http_json(f"{WIKIDATA_API}?{query}")
    entities = payload.get("entities") or {}
    labels = []
    for class_id in class_ids:
        by_language = (entities.get(class_id) or {}).get("labels") or {}
        for language in ("en", "pt"):
            label = (by_language.get(language) or {}).get("value")
            if label:
                labels.append(label)
    return _classify_labels(labels)


def _expected_types(name, kind):
    if kind == "competition":
        return {"competition"}
    if kind == "team" and normalize(name) in NATIONAL_TEAM_NAMES:
        return {"national_team"}
    if kind == "team":
        return {"club"}
    return set()


def wikidata_search(name, kind, country_hint=None, search_name=None):
    expected = _expected_types(name, kind)
    if not expected:
        return None

    base = search_name or TEAM_SEARCH_ALIASES.get(normalize(name), name)
    terms = []
    if country_hint:
        terms.append(f"{base} {country_hint}")
    terms.append(base)

    seen = set()
    for term in terms:
        for language in ("en", "pt"):
            query = urllib.parse.urlencode({
                "action": "wbsearchentities",
                "search": term,
                "language": language,
                "uselang": language,
                "format": "json",
                "limit": 6,
                "type": "item",
            })
            payload = http_json(f"{WIKIDATA_API}?{query}")
            for result in payload.get("search", []):
                qid = result.get("id")
                if not qid or qid in seen:
                    continue
                seen.add(qid)
                if wikidata_entity_type(qid) in expected:
                    return qid
    return None


def wikidata_logo_filename(qid):
    if not qid:
        return None
    query = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    })
    payload = http_json(f"{WIKIDATA_API}?{query}")
    entity = (payload.get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}

    for entry in claims.get("P154") or []:
        try:
            filename = entry["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(filename, str) and filename.strip():
            lowered = filename.lower()
            if any(word in lowered for word in ("stadium", "photograph", "photo.jpg", "match.jpg")):
                continue
            return filename.strip()
    return None


def commons_thumb_info(filename, width=256):
    if not filename:
        return None
    query = urllib.parse.urlencode({
        "action": "query",
        "prop": "imageinfo",
        "titles": f"File:{filename}",
        "iiprop": "url|mime|size",
        "iiurlwidth": width,
        "format": "json",
        "formatversion": "2",
    })
    payload = http_json(f"{COMMONS_API}?{query}")
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        return None
    infos = pages[0].get("imageinfo") or []
    if not infos:
        return None
    info = infos[0]
    url = info.get("thumburl") or info.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    width_value = int(info.get("thumbwidth") or info.get("width") or 0)
    height_value = int(info.get("thumbheight") or info.get("height") or 0)
    mime = str(info.get("mime") or "")
    return {
        "url": url,
        "width": width_value,
        "height": height_value,
        "mime": mime,
    }



def commons_search_logo_file(name):
    query = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srnamespace": 6,
        "srsearch": f'"{name}" logo',
        "srlimit": 10,
        "format": "json",
    })
    payload = http_json(f"{COMMONS_API}?{query}")
    wanted_tokens = {
        token for token in normalize(name).split()
        if len(token) >= 3
    }
    for result in payload.get("query", {}).get("search", []):
        title = str(result.get("title") or "")
        if not title.lower().startswith("file:"):
            continue
        filename = title.split(":", 1)[1]
        lowered = normalize(filename)
        if any(bad in lowered for bad in ("stadium", "kit", "jersey", "flag", "map", "photo")):
            continue
        filename_tokens = set(lowered.split())
        if wanted_tokens and not (wanted_tokens & filename_tokens):
            continue
        if not any(word in lowered for word in ("logo", "crest", "badge", "emblem")):
            continue
        return filename
    return None

def verify_artwork_url(url, timeout=20):
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GM-TV-Plus-Artwork/4.0",
            "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            "Range": "bytes=0-1023",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            content_type = str(response.headers.get("Content-Type") or "").lower()
            head = response.read(256)
            return status in {200, 206} and content_type.startswith("image/") and bool(head)
    except Exception:
        return False


def _validated(name, qid, info, provider, source_file, previous=None):
    now = _utc_now()
    return {
        "name": name,
        "qid": qid,
        "url": info["url"],
        "status": "validated",
        "semanticStatus": "validated",
        "fetchStatus": "ok",
        "visualStatus": "approved",
        "provider": provider,
        "property": "P154" if provider == "wikidata-commons" else "curated-file",
        "sourceFile": source_file,
        "width": info.get("width"),
        "height": info.get("height"),
        "mime": info.get("mime"),
        "resolverVersion": RESOLVER_VERSION,
        "validatedAt": _iso_z(now),
        "nextRetryAfter": None,
        "supersededRejection": (previous or {}).get("rejectedReason"),
    }


def _unresolved(name, qid=None, error=None):
    now = _utc_now()
    return {
        "name": name,
        "qid": qid,
        "url": None,
        "status": "unresolved",
        "semanticStatus": "unresolved",
        "fetchStatus": "failed" if error else "not_checked",
        "visualStatus": "not_checked",
        "provider": None,
        "property": None,
        "sourceFile": None,
        "resolverVersion": RESOLVER_VERSION,
        "lastAttemptAt": _iso_z(now),
        "nextRetryAfter": _iso_z(now + timedelta(hours=12)),
        "lastError": error,
    }


def adopt_trusted_provider_artwork(name, kind, url, cache, provider):
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    if provider != "football-data":
        return None
    if not verify_artwork_url(url):
        return None
    key = f"{kind}:{normalize(name)}"
    info = {"url": url, "width": None, "height": None, "mime": None}
    cache[key] = _validated(
        name,
        None,
        info,
        "football-data",
        None,
        previous=cache.get(key),
    )
    return url


def resolve_artwork(name, kind, cache, country_hint=None, search_name=None, force=False):
    normalized = normalize(name)
    if not normalized:
        return None
    key = f"{kind}:{normalized}"
    previous = cache.get(key) or {}

    if not force and _is_fresh_validated(previous):
        return previous.get("url")
    if not force and _retry_blocked(previous):
        return None

    curated_file = CURATED_COMMONS_FILES.get(key)
    if curated_file:
        try:
            info = commons_thumb_info(curated_file)
            if info and max(info.get("width") or 0, info.get("height") or 0) >= 64 and verify_artwork_url(info["url"]):
                cache[key] = _validated(
                    name,
                    previous.get("qid"),
                    info,
                    "wikimedia-commons-curated",
                    curated_file,
                    previous=previous,
                )
                return info["url"]
        except Exception:
            pass

    qid = None
    try:
        qid = wikidata_search(
            name,
            kind,
            country_hint=country_hint,
            search_name=search_name,
        )
        filename = wikidata_logo_filename(qid)
        provider = "wikidata-commons"
        if not filename and qid:
            filename = commons_search_logo_file(search_name or name)
            provider = "wikimedia-commons-search"
        info = commons_thumb_info(filename)
        if (
            info
            and max(info.get("width") or 0, info.get("height") or 0) >= 64
            and verify_artwork_url(info["url"])
        ):
            cache[key] = _validated(
                name,
                qid,
                info,
                provider,
                filename,
                previous=previous,
            )
            return info["url"]
        error = "validated_entity_without_usable_logo"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    cache[key] = _unresolved(
        name,
        qid=qid or previous.get("qid"),
        error=error,
    )
    return None


def competition_country_hint(name):
    target = normalize(name)
    for display, _search, country in COMPETITION_CATALOG:
        if normalize(display) == target:
            return country
    return None


def competition_search_name(name):
    target = normalize(name)
    for display, search, _country in COMPETITION_CATALOG:
        if normalize(display) == target:
            return search
    return name


def prime_visual_catalog(cache):
    stats = {
        "competitionsTotal": 0,
        "competitionsValidated": 0,
        "competitionsUnresolved": [],
        "teamsTotal": 0,
        "teamsValidated": 0,
        "teamsUnresolved": [],
    }

    for display, search_name, country in COMPETITION_CATALOG:
        stats["competitionsTotal"] += 1
        url = resolve_artwork(
            display,
            "competition",
            cache,
            country_hint=country,
            search_name=search_name,
        )
        if url:
            stats["competitionsValidated"] += 1
        else:
            stats["competitionsUnresolved"].append(display)

    for name, country in TEAM_PRIME_CATALOG:
        stats["teamsTotal"] += 1
        url = resolve_artwork(
            name,
            "team",
            cache,
            country_hint=country,
        )
        if url:
            stats["teamsValidated"] += 1
        else:
            stats["teamsUnresolved"].append(name)

    return stats
