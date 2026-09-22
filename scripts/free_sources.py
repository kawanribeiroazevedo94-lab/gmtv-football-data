#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

APP_TZ_NAME = "America/Sao_Paulo"
OPENLIGADB_BASE = "https://api.openligadb.de"
WIKIMEDIA_API = "https://en.wikipedia.org/w/api.php"

DROP_WORDS = {
    "fc", "afc", "cf", "sc", "ac", "ec", "se", "ca", "cr", "fbc",
    "club", "clube", "football", "futebol", "calcio",
    "de", "do", "da", "the",
}

OPENLIGADB_COMPETITIONS = (
    {"providerId": 4937, "shortcut": "bl1", "name": "Bundesliga", "code": "BL1"},
    {"providerId": 4938, "shortcut": "bl2", "name": "2. Bundesliga", "code": "BL2"},
    {"providerId": 4946, "shortcut": "ucl", "name": "UEFA Champions League", "code": "UCL"},
    {"providerId": 6000, "shortcut": "uel2026", "name": "UEFA Europa League", "code": "UEL"},
    {"providerId": 4936, "shortcut": "la1", "name": "LaLiga", "code": "PD"},
    {"providerId": 5996, "shortcut": "pl", "name": "Premier League", "code": "PL"},
)

WIKIMEDIA_COMPETITIONS = (
    {
        "key": "uwcl",
        "name": "UEFA Women's Champions League",
        "code": "UWCL",
        "timezone": "Europe/Paris",
        "suffix": "UEFA Women's Champions League league phase",
    },
    {
        "key": "uecl",
        "name": "UEFA Conference League",
        "code": "UECL",
        "timezone": "Europe/Paris",
        "suffix": "UEFA Conference League league phase",
    },
)


def app_timezone():
    return ZoneInfo(APP_TZ_NAME)


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in DROP_WORDS]
    return " ".join(tokens).strip()


def http_json(url, headers=None, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GM-TV-Plus-Football-Feed/2.0 (central metadata pipeline)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def current_season_start(today):
    return today.year if today.month >= 7 else today.year - 1


def wikipedia_season_label(today):
    start = current_season_start(today)
    return f"{start}–{str(start + 1)[-2:]}"


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def make_openligadb_match(raw, competition):
    utc_dt = parse_iso_datetime(
        raw.get("matchDateTimeUTC") or raw.get("matchDateTimeUtc")
    )
    if utc_dt is None:
        return None

    team1 = raw.get("team1") or {}
    team2 = raw.get("team2") or {}
    home_name = str(team1.get("teamName") or "").strip()
    away_name = str(team2.get("teamName") or "").strip()
    match_id = raw.get("matchID")
    if not home_name or not away_name or match_id is None:
        return None

    local = utc_dt.astimezone(app_timezone())
    return {
        "id": f"oldb:{match_id}",
        "date": local.date().isoformat(),
        "kickoff": local.strftime("%H:%M"),
        "utcDate": utc_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "FINISHED" if bool(raw.get("matchIsFinished")) else "SCHEDULED",
        "competition": {
            "id": competition["providerId"],
            "idProvider": "openligadb",
            "code": competition["code"],
            "name": competition["name"],
            "logo": None,
            "normalized": normalize(competition["name"]),
        },
        "home": {
            "id": team1.get("teamId"),
            "idProvider": "openligadb",
            "name": home_name,
            "fullName": home_name,
            "crest": None,
            "normalized": normalize(home_name),
        },
        "away": {
            "id": team2.get("teamId"),
            "idProvider": "openligadb",
            "name": away_name,
            "fullName": away_name,
            "crest": None,
            "normalized": normalize(away_name),
        },
        "sources": ["openligadb"],
        "sourcePriority": 70,
        "provenance": {
            "provider": "openligadb",
            "providerMatchId": match_id,
            "providerCompetitionId": competition["providerId"],
            "shortcut": competition["shortcut"],
        },
    }


def parse_openligadb_matches(payload, competition, date_from, date_to):
    output = []
    if not isinstance(payload, list):
        return output
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        parsed = make_openligadb_match(raw, competition)
        if parsed is None:
            continue
        try:
            local_date = date.fromisoformat(parsed["date"])
        except ValueError:
            continue
        if date_from <= local_date <= date_to:
            output.append(parsed)
    return output


def fetch_openligadb(date_from, date_to):
    season = current_season_start(date_from)
    matches = []
    statuses = []
    for competition in OPENLIGADB_COMPETITIONS:
        url = f"{OPENLIGADB_BASE}/getmatchdata/{competition['shortcut']}/{season}"
        try:
            parsed = parse_openligadb_matches(
                http_json(url), competition, date_from, date_to
            )
            matches.extend(parsed)
            statuses.append({
                "shortcut": competition["shortcut"],
                "providerCompetitionId": competition["providerId"],
                "ok": True,
                "matchesInWindow": len(parsed),
                "error": None,
            })
        except Exception as exc:
            statuses.append({
                "shortcut": competition["shortcut"],
                "providerCompetitionId": competition["providerId"],
                "ok": False,
                "matchesInWindow": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return matches, statuses


def strip_wiki_markup(value):
    value = str(value or "")
    value = re.sub(r"<ref\b[^>]*>.*?</ref>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<ref\b[^>]*/>", " ", value, flags=re.I)
    value = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", value)
    value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    previous = None
    while previous != value:
        previous = value
        value = re.sub(
            r"\{\{(?:flagicon|fbaicon|small|nowrap)\b[^{}]*\}\}",
            " ", value, flags=re.I,
        )
    value = value.replace("'''", "").replace("''", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_balanced_templates(text, names):
    accepted = {normalize(name) for name in names}
    found = []
    i = 0
    size = len(text)
    while i < size - 1:
        if text[i:i + 2] != "{{":
            i += 1
            continue
        depth = 1
        j = i + 2
        while j < size - 1 and depth:
            pair = text[j:j + 2]
            if pair == "{{":
                depth += 1
                j += 2
                continue
            if pair == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    block = text[i:j]
                    header = block[2:].split("|", 1)[0]
                    if normalize(header) in accepted:
                        found.append(block)
                    break
                continue
            j += 1
        if depth == 0:
            i = j
        else:
            break
    return found


def split_top_level(value):
    parts = []
    current = []
    template_depth = 0
    link_depth = 0
    i = 0
    while i < len(value):
        pair = value[i:i + 2]
        if pair == "{{":
            template_depth += 1
            current.append(pair)
            i += 2
            continue
        if pair == "}}" and template_depth:
            template_depth -= 1
            current.append(pair)
            i += 2
            continue
        if pair == "[[":
            link_depth += 1
            current.append(pair)
            i += 2
            continue
        if pair == "]]" and link_depth:
            link_depth -= 1
            current.append(pair)
            i += 2
            continue
        if value[i] == "|" and template_depth == 0 and link_depth == 0:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(value[i])
        i += 1
    parts.append("".join(current))
    return parts


def parse_template_parameters(block):
    parts = split_top_level(block[2:-2])
    params = {}
    for raw in parts[1:]:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = normalize(key)
        if key:
            params[key] = value.strip()
    return params


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_wiki_date(value):
    raw = str(value or "")
    start_date = re.search(
        r"\{\{\s*start\s+date"
        r"\s*\|\s*(\d{4})"
        r"\s*\|\s*(\d{1,2})"
        r"\s*\|\s*(\d{1,2})",
        raw,
        flags=re.I,
    )
    if start_date:
        try:
            return date(
                int(start_date.group(1)),
                int(start_date.group(2)),
                int(start_date.group(3)),
            )
        except ValueError:
            return None

    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    textual = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b",
        strip_wiki_markup(raw),
    )
    if textual:
        month = MONTHS.get(textual.group(2).lower())
        if month is None:
            return None
        try:
            return date(int(textual.group(3)), month, int(textual.group(1)))
        except ValueError:
            return None
    return None


def parse_wiki_time(value):
    found = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        strip_wiki_markup(value),
    )
    if not found:
        return None
    try:
        return time(int(found.group(1)), int(found.group(2)))
    except ValueError:
        return None


def parse_wikimedia_matches(wikitext, competition, date_from, date_to, provenance=None):
    templates = extract_balanced_templates(
        wikitext,
        {"football box", "football box collapsible", "footballbox"},
    )
    source_tz = ZoneInfo(competition["timezone"])
    app_tz = app_timezone()
    output = []
    for block in templates:
        params = parse_template_parameters(block)
        match_date = parse_wiki_date(params.get("date"))
        kickoff = parse_wiki_time(params.get("time"))
        home = strip_wiki_markup(params.get("team1") or params.get("home"))
        away = strip_wiki_markup(params.get("team2") or params.get("away"))
        if match_date is None or kickoff is None or not home or not away:
            continue

        source_local = datetime.combine(match_date, kickoff, tzinfo=source_tz)
        utc_dt = source_local.astimezone(timezone.utc)
        app_local = utc_dt.astimezone(app_tz)
        if not (date_from <= app_local.date() <= date_to):
            continue

        raw_id = f"{competition['code']}|{utc_dt.isoformat()}|{home}|{away}"
        digest = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
        output.append({
            "id": f"wm:{digest}",
            "date": app_local.date().isoformat(),
            "kickoff": app_local.strftime("%H:%M"),
            "utcDate": utc_dt.isoformat().replace("+00:00", "Z"),
            "status": "SCHEDULED",
            "competition": {
                "id": None,
                "idProvider": "wikimedia",
                "code": competition["code"],
                "name": competition["name"],
                "logo": None,
                "normalized": normalize(competition["name"]),
            },
            "home": {
                "id": None,
                "idProvider": "wikimedia",
                "name": home,
                "fullName": home,
                "crest": None,
                "normalized": normalize(home),
            },
            "away": {
                "id": None,
                "idProvider": "wikimedia",
                "name": away,
                "fullName": away,
                "crest": None,
                "normalized": normalize(away),
            },
            "sources": ["wikimedia"],
            "sourcePriority": 60,
            "provenance": {
                "provider": "wikimedia",
                "page": (provenance or {}).get("page"),
                "pageId": (provenance or {}).get("pageId"),
                "revisionId": (provenance or {}).get("revisionId"),
                "revisionTimestamp": (provenance or {}).get("revisionTimestamp"),
            },
        })
    return output


def fetch_wikimedia_page(title):
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    payload = http_json(WIKIMEDIA_API + "?" + urllib.parse.urlencode(params))
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError("Wikimedia sem página retornada")
    page = pages[0]
    if page.get("missing"):
        raise RuntimeError(f"Wikimedia página ausente: {title}")
    revisions = page.get("revisions") or []
    if not revisions:
        raise RuntimeError(f"Wikimedia sem revisão: {title}")
    revision = revisions[0]
    content = revision.get("slots", {}).get("main", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Wikimedia sem wikitext: {title}")
    return {
        "page": page.get("title") or title,
        "pageId": page.get("pageid"),
        "revisionId": revision.get("revid"),
        "revisionTimestamp": revision.get("timestamp"),
        "wikitext": content,
    }


def fetch_wikimedia(date_from, date_to):
    season_label = wikipedia_season_label(date_from)
    matches = []
    statuses = []
    for competition in WIKIMEDIA_COMPETITIONS:
        title = f"{season_label} {competition['suffix']}"
        try:
            page = fetch_wikimedia_page(title)
            parsed = parse_wikimedia_matches(
                page["wikitext"], competition, date_from, date_to, provenance=page
            )
            matches.extend(parsed)
            statuses.append({
                "key": competition["key"],
                "page": page["page"],
                "pageId": page["pageId"],
                "revisionId": page["revisionId"],
                "revisionTimestamp": page["revisionTimestamp"],
                "ok": True,
                "matchesInWindow": len(parsed),
                "error": None,
            })
        except Exception as exc:
            statuses.append({
                "key": competition["key"],
                "page": title,
                "pageId": None,
                "revisionId": None,
                "revisionTimestamp": None,
                "ok": False,
                "matchesInWindow": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return matches, statuses

# ---------------------------------------------------------------------------
# BSD / GoalDir: fonte complementar, centralizada e sem artwork automático.
# Somente competições explicitamente auditadas entram no feed.
# ---------------------------------------------------------------------------
BSD_API_BASE = "https://sports.bzzoiro.com/api/v2"
BSD_COMPETITIONS = {
    9: {
        "name": "Brasileirão Série A",
        "code": "BSA",
    },
    34: {
        "name": "Brasileirão Série B",
        "code": "BSB",
    },
    5: {
        "name": "Bundesliga",
        "code": "BL1",
    },
    94: {
        "name": "2. Bundesliga",
        "code": "BL2",
    },
    7: {
        "name": "UEFA Champions League",
        "code": "UCL",
    },
    8: {
        "name": "UEFA Europa League",
        "code": "UEL",
    },
    83: {
        "name": "UEFA Conference League",
        "code": "UECL",
    },
}


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bsd_league_id(raw):
    value = raw.get("league_id")
    if value is None and isinstance(raw.get("league"), dict):
        value = raw["league"].get("id")
    return _int_or_none(value)


def _bsd_team(raw, side):
    obj = raw.get(f"{side}_team")
    team_id = raw.get(f"{side}_team_id")
    name = None

    if isinstance(obj, dict):
        if team_id is None:
            team_id = obj.get("id")
        name = (
            obj.get("name")
            or obj.get("team_name")
            or obj.get("short_name")
        )
    elif obj is not None:
        name = str(obj)

    if name is None:
        name = (
            raw.get(f"{side}_team_name")
            or raw.get(f"{side}_name")
        )

    name = str(name or "").strip()
    return _int_or_none(team_id), name


def make_bsd_match(raw):
    if not isinstance(raw, dict):
        return None

    league_id = _bsd_league_id(raw)
    competition = BSD_COMPETITIONS.get(league_id)
    if competition is None:
        return None

    event_id = raw.get("id")
    if event_id is None:
        event_id = raw.get("event_id")
    if event_id is None:
        return None

    utc_dt = parse_iso_datetime(
        raw.get("event_date")
        or raw.get("event_datetime")
        or raw.get("start_time")
        or raw.get("date")
    )
    if utc_dt is None:
        return None

    home_id, home_name = _bsd_team(raw, "home")
    away_id, away_name = _bsd_team(raw, "away")
    if not home_name or not away_name:
        return None

    local = utc_dt.astimezone(app_timezone())
    raw_status = str(
        raw.get("status")
        or raw.get("event_status")
        or ""
    ).strip().lower()
    status = (
        "FINISHED"
        if raw_status in {
            "finished", "ft", "completed", "complete", "ended"
        }
        else "SCHEDULED"
    )

    return {
        "id": f"bsd:{event_id}",
        "date": local.date().isoformat(),
        "kickoff": local.strftime("%H:%M"),
        "utcDate": (
            utc_dt.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "status": status,
        "competition": {
            "id": league_id,
            "idProvider": "bsd",
            "code": competition["code"],
            "name": competition["name"],
            "logo": None,
            "normalized": normalize(competition["name"]),
        },
        "home": {
            "id": home_id,
            "idProvider": "bsd",
            "name": home_name,
            "fullName": home_name,
            "crest": None,
            "normalized": normalize(home_name),
        },
        "away": {
            "id": away_id,
            "idProvider": "bsd",
            "name": away_name,
            "fullName": away_name,
            "crest": None,
            "normalized": normalize(away_name),
        },
        "sources": ["bsd"],
        "sourcePriority": 80,
        "provenance": {
            "provider": "bsd",
            "providerEventId": event_id,
            "providerLeagueId": league_id,
            "providerSeasonId": raw.get("season_id"),
        },
    }


def fetch_bsd(token, date_from, date_to):
    token = str(token or "").strip()
    if not token:
        return [], {
            "configured": False,
            "ok": False,
            "matches": 0,
            "pages": 0,
            "error": "BSD_TOKEN not configured",
        }

    query = urllib.parse.urlencode({
        "date_from": (date_from - timedelta(days=1)).isoformat(),
        "date_to": (date_to + timedelta(days=1)).isoformat(),
        "limit": 200,
    })
    url = f"{BSD_API_BASE}/events/?{query}"
    headers = {"Authorization": f"Token {token}"}
    matches = []
    seen_ids = set()
    pages = 0

    try:
        while url and pages < 20:
            payload = http_json(
                url,
                headers=headers,
                timeout=30,
            )
            pages += 1

            if isinstance(payload, dict):
                rows = payload.get("results") or payload.get("events") or []
                next_url = payload.get("next")
            elif isinstance(payload, list):
                rows = payload
                next_url = None
            else:
                rows = []
                next_url = None

            for raw in rows:
                item = make_bsd_match(raw)
                if item is None:
                    continue
                if item["id"] in seen_ids:
                    continue
                local_date = date.fromisoformat(item["date"])
                if date_from <= local_date <= date_to:
                    seen_ids.add(item["id"])
                    matches.append(item)

            if not next_url:
                break
            url = urllib.parse.urljoin(url, str(next_url))

        return matches, {
            "configured": True,
            "ok": True,
            "matches": len(matches),
            "pages": pages,
            "error": None,
        }
    except Exception as exc:
        return [], {
            "configured": True,
            "ok": False,
            "matches": 0,
            "pages": pages,
            "error": f"{type(exc).__name__}: {exc}",
        }
