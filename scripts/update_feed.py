#!/usr/bin/env python3
import hashlib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Sao_Paulo")
FOOTBALL_DATA_URL = "https://api.football-data.org/v4/matches"
OPENFOOTBALL_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

OUT = Path("data/football-feed.json")
ARTWORK_CACHE = Path("data/artwork-cache.json")

EURO_DATASETS = [
    ("en.1.json", "Premier League", "PL", "Europe/London"),
    ("en.2.json", "Championship", "ELC", "Europe/London"),
    ("de.1.json", "Bundesliga", "BL1", "Europe/Berlin"),
    ("es.1.json", "LaLiga", "PD", "Europe/Madrid"),
    ("it.1.json", "Serie A", "SA", "Europe/Rome"),
    ("fr.1.json", "Ligue 1", "FL1", "Europe/Paris"),
    ("nl.1.json", "Eredivisie", "DED", "Europe/Amsterdam"),
    ("pt.1.json", "Primeira Liga", "PPL", "Europe/Lisbon"),
]

ANNUAL_DATASETS = [
    ("br.1.json", "Brasileirão Série A", "BSA", "America/Sao_Paulo"),
]

DROP_WORDS = {
    "fc", "afc", "cf", "sc", "ac", "ec", "se", "ca", "cr", "fbc",
    "club", "clube", "football", "futebol", "calcio", "de", "do", "da", "the",
}

def http_json(url, headers=None, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GM-TV-Plus-Football-Feed/1.0 (public metadata cache)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def normalize(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in DROP_WORDS]
    return " ".join(tokens).strip()

def season_folder(today):
    if today.month >= 7:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    return f"{today.year - 1}-{str(today.year)[-2:]}"

def safe_logo(value):
    if isinstance(value, str) and value.startswith("https://"):
        return value
    return None

def app_date_time(utc_value):
    if not utc_value:
        return None, None
    parsed = datetime.fromisoformat(utc_value.replace("Z", "+00:00"))
    local = parsed.astimezone(APP_TZ)
    return local.date().isoformat(), local.strftime("%H:%M")

def make_fd_match(item):
    local_date, kickoff = app_date_time(item.get("utcDate"))
    comp = item.get("competition") or {}
    home = item.get("homeTeam") or {}
    away = item.get("awayTeam") or {}
    return {
        "id": f"fd:{item.get('id')}",
        "date": local_date,
        "kickoff": kickoff,
        "utcDate": item.get("utcDate"),
        "status": item.get("status"),
        "competition": {
            "id": comp.get("id"),
            "code": comp.get("code"),
            "name": comp.get("name"),
            "logo": safe_logo(comp.get("emblem")),
            "normalized": normalize(comp.get("name")),
        },
        "home": {
            "id": home.get("id"),
            "name": home.get("shortName") or home.get("name"),
            "fullName": home.get("name"),
            "crest": safe_logo(home.get("crest")),
            "normalized": normalize(home.get("shortName") or home.get("name")),
        },
        "away": {
            "id": away.get("id"),
            "name": away.get("shortName") or away.get("name"),
            "fullName": away.get("name"),
            "crest": safe_logo(away.get("crest")),
            "normalized": normalize(away.get("shortName") or away.get("name")),
        },
        "sources": ["football-data"],
        "sourcePriority": 100,
    }

def openfootball_utc(match, source_tz):
    raw_date = match.get("date")
    if not raw_date:
        return None
    raw_time = match.get("time") or "12:00"
    try:
        local = datetime.combine(
            date.fromisoformat(raw_date),
            time.fromisoformat(raw_time),
            tzinfo=ZoneInfo(source_tz),
        )
    except ValueError:
        return None
    return local.astimezone(timezone.utc)

def make_of_match(match, competition_name, competition_code, source_tz, dataset):
    utc_dt = openfootball_utc(match, source_tz)
    if utc_dt is None:
        return None

    local = utc_dt.astimezone(APP_TZ)
    home = str(match.get("team1") or "").strip()
    away = str(match.get("team2") or "").strip()
    if not home or not away:
        return None

    raw_id = f"{dataset}|{match.get('date')}|{match.get('time')}|{home}|{away}"
    digest = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]

    return {
        "id": f"of:{digest}",
        "date": local.date().isoformat(),
        "kickoff": local.strftime("%H:%M"),
        "utcDate": utc_dt.isoformat().replace("+00:00", "Z"),
        "status": "SCHEDULED",
        "competition": {
            "id": None,
            "code": competition_code,
            "name": competition_name,
            "logo": None,
            "normalized": normalize(competition_name),
        },
        "home": {
            "id": None,
            "name": home,
            "fullName": home,
            "crest": None,
            "normalized": normalize(home),
        },
        "away": {
            "id": None,
            "name": away,
            "fullName": away,
            "crest": None,
            "normalized": normalize(away),
        },
        "sources": ["openfootball"],
        "sourcePriority": 50,
    }

def loose_team_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a

def find_equivalent(existing, candidate):
    for item in existing:
        if item.get("date") != candidate.get("date"):
            continue

        ih = item.get("home", {}).get("normalized")
        ia = item.get("away", {}).get("normalized")
        ch = candidate.get("home", {}).get("normalized")
        ca = candidate.get("away", {}).get("normalized")

        direct = loose_team_match(ih, ch) and loose_team_match(ia, ca)
        swapped = loose_team_match(ih, ca) and loose_team_match(ia, ch)
        if direct or swapped:
            return item

    return None

def fetch_football_data(token, date_from, date_to):
    # Consulta um dia extra em cada ponta e filtra depois no fuso do app.
    query = urllib.parse.urlencode(
        {
            "dateFrom": (date_from - timedelta(days=1)).isoformat(),
            "dateTo": (date_to + timedelta(days=1)).isoformat(),
        }
    )
    payload = http_json(
        f"{FOOTBALL_DATA_URL}?{query}",
        headers={"X-Auth-Token": token},
    )

    output = []
    for item in payload.get("matches", []):
        parsed = make_fd_match(item)
        if parsed["date"] is None:
            continue
        local_date = date.fromisoformat(parsed["date"])
        if date_from <= local_date <= date_to:
            output.append(parsed)
    return output

def fetch_openfootball(date_from, date_to):
    season = season_folder(date_from)
    datasets = [
        (f"{season}/{filename}", comp, code, tz)
        for filename, comp, code, tz in EURO_DATASETS
    ]
    datasets += [
        (f"{date_from.year}/{filename}", comp, code, tz)
        for filename, comp, code, tz in ANNUAL_DATASETS
    ]

    matches = []
    status = []

    for dataset, comp, code, tz in datasets:
        url = f"{OPENFOOTBALL_BASE}/{dataset}"
        try:
            payload = http_json(url)
            used = 0
            for raw in payload.get("matches", []):
                item = make_of_match(raw, comp, code, tz, dataset)
                if item is None:
                    continue
                local_date = date.fromisoformat(item["date"])
                if date_from <= local_date <= date_to:
                    matches.append(item)
                    used += 1

            status.append(
                {
                    "dataset": dataset,
                    "ok": True,
                    "matchesInWindow": used,
                }
            )
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            status.append(
                {
                    "dataset": dataset,
                    "ok": False,
                    "error": type(exc).__name__,
                }
            )

    return matches, status

def load_artwork_cache():
    if not ARTWORK_CACHE.exists():
        return {}
    try:
        return json.loads(ARTWORK_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def wikidata_search(name, kind):
    keywords = (
        ("football", "soccer", "club", "team")
        if kind == "team"
        else ("football", "soccer", "league", "competition", "championship")
    )

    for language in ("en", "pt"):
        query = urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": name,
                "language": language,
                "uselang": language,
                "format": "json",
                "limit": 5,
                "type": "item",
            }
        )
        payload = http_json(f"{WIKIDATA_API}?{query}")
        results = payload.get("search", [])

        for result in results:
            description = str(result.get("description") or "").lower()
            if any(keyword in description for keyword in keywords):
                return result.get("id")

        if results:
            return results[0].get("id")

    return None

def wikidata_logo(qid):
    if not qid:
        return None

    query = urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }
    )
    payload = http_json(f"{WIKIDATA_API}?{query}")
    entity = (payload.get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}

    for property_id in ("P154", "P18"):
        entries = claims.get(property_id) or []
        if not entries:
            continue

        try:
            filename = entries[0]["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue

        if isinstance(filename, str) and filename:
            encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="()_,-.")
            return (
                "https://commons.wikimedia.org/wiki/"
                f"Special:Redirect/file/{encoded}?width=192"
            )

    return None

def resolve_artwork(name, kind, cache):
    normalized = normalize(name)
    if not normalized:
        return None

    key = f"{kind}:{normalized}"
    if key in cache:
        return cache[key].get("url")

    try:
        qid = wikidata_search(name, kind)
        url = wikidata_logo(qid)
    except Exception:
        qid = None
        url = None

    cache[key] = {
        "name": name,
        "qid": qid,
        "url": url,
    }
    return url

def enrich_missing_artwork(matches, cache):
    for item in matches:
        comp = item["competition"]
        home = item["home"]
        away = item["away"]

        if not comp.get("logo") and comp.get("name"):
            comp["logo"] = resolve_artwork(
                comp["name"],
                "competition",
                cache,
            )

        if not home.get("crest") and home.get("name"):
            home["crest"] = resolve_artwork(
                home["name"],
                "team",
                cache,
            )

        if not away.get("crest") and away.get("name"):
            away["crest"] = resolve_artwork(
                away["name"],
                "team",
                cache,
            )

def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise SystemExit("FOOTBALL_DATA_TOKEN não configurado.")

    now = datetime.now(APP_TZ)
    date_from = now.date()
    date_to = date_from + timedelta(days=6)

    fd_ok = True
    fd_error = None

    try:
        football_data = fetch_football_data(
            token,
            date_from,
            date_to,
        )
    except Exception as exc:
        football_data = []
        fd_ok = False
        fd_error = f"{type(exc).__name__}: {exc}"

    openfootball, open_status = fetch_openfootball(
        date_from,
        date_to,
    )

    merged = list(football_data)

    for candidate in openfootball:
        donor = find_equivalent(
            merged,
            candidate,
        )

        if donor is None:
            merged.append(candidate)
        elif "openfootball" not in donor["sources"]:
            donor["sources"].append("openfootball")

    artwork_cache = load_artwork_cache()
    enrich_missing_artwork(
        merged,
        artwork_cache,
    )

    merged.sort(
        key=lambda item: (
            item.get("date") or "9999-99-99",
            item.get("kickoff") or "99:99",
            item.get("competition", {}).get("name") or "",
            item.get("home", {}).get("name") or "",
        )
    )

    days = []

    for offset in range(7):
        current = date_from + timedelta(days=offset)
        day_matches = [
            match
            for match in merged
            if match.get("date") == current.isoformat()
        ]

        days.append(
            {
                "date": current.isoformat(),
                "label": (
                    "HOJE"
                    if offset == 0
                    else current.strftime("%d/%m")
                ),
                "count": len(day_matches),
                "matches": day_matches,
            }
        )

    feed = {
        "schema": 1,
        "generatedAt": (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "timezone": "America/Sao_Paulo",
        "window": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
        },
        "sources": {
            "footballData": {
                "ok": fd_ok,
                "matches": len(football_data),
                "error": fd_error,
            },
            "openFootball": {
                "ok": any(item["ok"] for item in open_status),
                "matches": len(openfootball),
                "datasets": open_status,
            },
            "wikidataArtwork": {
                "cachedEntries": len(artwork_cache),
            },
        },
        "days": days,
        "matches": merged,
    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        json.dumps(
            feed,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ARTWORK_CACHE.write_text(
        json.dumps(
            artwork_cache,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "feed gerado: "
        f"{len(merged)} partidas | "
        f"football-data={len(football_data)} | "
        f"openfootball={len(openfootball)} | "
        f"artwork-cache={len(artwork_cache)}"
    )

if __name__ == "__main__":
    main()
