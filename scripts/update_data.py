#!/usr/bin/env python3
import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEAMS = [
    {
        "id": 33, "espnId": 367, "name": "Tottenham Hotspur",
        "sport": "Football", "apiSport": "football", "espnSport": "soccer",
        "teamUrl": "https://www.sofascore.com/football/team/tottenham-hotspur/33",
    },
    {
        "id": 4196, "espnId": 25898, "sportsDbId": 135199, "name": "Bath Rugby",
        "sport": "Rugby Union", "apiSport": "rugby", "espnSport": "rugby",
        "teamUrl": "https://www.sofascore.com/rugby/team/bath-rugby/4196",
    },
    {
        "id": 4713, "espnId": 448, "name": "England Football",
        "sport": "Football", "apiSport": "football", "espnSport": "soccer",
        "teamUrl": "https://www.sofascore.com/football/team/england/4713",
    },
    {
        "id": 4226, "espnId": 1, "sportsDbId": 137123, "name": "England Rugby",
        "sport": "Rugby Union", "apiSport": "rugby", "espnSport": "rugby",
        "teamUrl": "https://www.sofascore.com/rugby/team/england/4226",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MySportsDashboard/1.0)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
}

def get_bytes(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.headers.get_content_type()

def get_json(url):
    raw, _ = get_bytes(url)
    return json.loads(raw.decode("utf-8"))

def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None

def pick_competitors(event):
    competitions = event.get("competitions") or []
    competition = competitions[0] if competitions else {}
    competitors = competition.get("competitors") or event.get("competitors") or []
    home = next((x for x in competitors if x.get("homeAway") == "home"), None)
    away = next((x for x in competitors if x.get("homeAway") == "away"), None)
    if not home and len(competitors) >= 1:
        home = competitors[0]
    if not away and len(competitors) >= 2:
        away = competitors[1]
    return competition, home or {}, away or {}

def competitor_name(competitor):
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("shortDisplayName") or team.get("name")

def competitor_slug(competitor):
    team = competitor.get("team") or {}
    return team.get("slug")

def competitor_id(competitor):
    team = competitor.get("team") or {}
    return str(team.get("id") or competitor.get("id") or "")

def competitor_score(competitor):
    score = competitor.get("score")
    if isinstance(score, dict):
        for key in ("displayValue", "value"):
            if score.get(key) is not None:
                return score.get(key)
    if score is not None and not isinstance(score, dict):
        return score
    return None

def event_completed(event):
    competition, _, _ = pick_competitors(event)
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    if status_type.get("completed") is True:
        return True
    state = str(status_type.get("state") or "").lower()
    name = str(status_type.get("name") or "").lower()
    return state == "post" or "final" in name or name in {"status_full_time", "ft"}

def event_competition(event):
    league = event.get("league") or {}
    if isinstance(league, dict):
        for key in ("name", "displayName", "shortName"):
            if league.get(key):
                return league.get(key)
    competition, _, _ = pick_competitors(event)
    league = competition.get("league") or {}
    if isinstance(league, dict):
        for key in ("name", "displayName", "shortName"):
            if league.get(key):
                return league.get(key)
    notes = competition.get("notes") or []
    if notes and isinstance(notes[0], dict) and notes[0].get("headline"):
        return notes[0]["headline"]
    season_type = event.get("seasonType") or {}
    if isinstance(season_type, dict):
        return season_type.get("name") or ""
    return ""

def event_url(event):
    for link in event.get("links") or []:
        if link.get("href"):
            return link["href"]
    competition, _, _ = pick_competitors(event)
    for link in competition.get("links") or []:
        if link.get("href"):
            return link["href"]
    return None

def compact_event(event):
    if not event:
        return None
    competition, home, away = pick_competitors(event)
    dt = parse_time(event.get("date") or competition.get("date"))
    return {
        "id": event.get("id"),
        "startTimestamp": int(dt.timestamp()) if dt else None,
        "homeTeam": {"name": competitor_name(home), "slug": competitor_slug(home)},
        "awayTeam": {"name": competitor_name(away), "slug": competitor_slug(away)},
        "homeScore": competitor_score(home),
        "awayScore": competitor_score(away),
        "tournament": event_competition(event),
        "eventUrl": event_url(event),
    }

def dedupe_events(events):
    seen = {}
    for event in events:
        key = str(event.get("id") or "")
        if key:
            seen[key] = event
    return list(seen.values())

def choose_events(events):
    now = datetime.now(timezone.utc)
    parsed = []
    for event in dedupe_events(events):
        competition, _, _ = pick_competitors(event)
        dt = parse_time(event.get("date") or competition.get("date"))
        if dt:
            parsed.append((dt, event, event_completed(event)))

    completed = [item for item in parsed if item[2] or item[0] < now]
    upcoming = [item for item in parsed if not item[2] and item[0] >= now]

    last_event = max(completed, key=lambda x: x[0])[1] if completed else None
    next_event = min(upcoming, key=lambda x: x[0])[1] if upcoming else None
    return compact_event(last_event), compact_event(next_event)

def soccer_data(team):
    events = []
    logo_payload = None
    errors = []
    for season in (2026, 2027):
        for suffix in ("", "&fixture=true"):
            url = (
                f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/all/"
                f"teams/{team['espnId']}/schedule?season={season}{suffix}"
            )
            try:
                payload = get_json(url)
                logo_payload = logo_payload or payload
                events.extend(payload.get("events") or [])
            except Exception as exc:
                errors.append(str(exc))

    if not events:
        raise RuntimeError("; ".join(errors) or "No ESPN soccer events")
    return events, logo_payload or {}

def sportsdb_event(event):
    if not event:
        return None

    timestamp = event.get("strTimestamp")
    dt = parse_time(timestamp)

    if not dt:
        date = event.get("dateEvent")
        time = event.get("strTime") or "00:00:00"
        if date:
            dt = parse_time(f"{date}T{time}+00:00")

    def clean_score(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except Exception:
            return value

    event_id = event.get("idEvent")
    return {
        "id": event_id,
        "startTimestamp": int(dt.timestamp()) if dt else None,
        "homeTeam": {
            "name": event.get("strHomeTeam"),
            "slug": None,
        },
        "awayTeam": {
            "name": event.get("strAwayTeam"),
            "slug": None,
        },
        "homeScore": clean_score(event.get("intHomeScore")),
        "awayScore": clean_score(event.get("intAwayScore")),
        "tournament": event.get("strLeague") or event.get("strEventAlternate") or "",
        "eventUrl": f"https://www.thesportsdb.com/event/{event_id}" if event_id else None,
    }

def rugby_data(team):
    team_id = team["sportsDbId"]
    base = "https://www.thesportsdb.com/api/v1/json/123"

    last_payload = get_json(f"{base}/eventslast.php?id={team_id}")
    next_payload = get_json(f"{base}/eventsnext.php?id={team_id}")
    team_payload = get_json(f"{base}/lookupteam.php?id={team_id}")

    previous_events = last_payload.get("results") or last_payload.get("events") or []
    next_events = next_payload.get("events") or next_payload.get("results") or []

    previous = sportsdb_event(previous_events[0]) if previous_events else None
    upcoming = sportsdb_event(next_events[0]) if next_events else None

    if previous is None and upcoming is None:
        raise RuntimeError("TheSportsDB returned no rugby fixtures")

    return previous, upcoming, team_payload

def team_badge(payload, team):
    logo_url = None

    # TheSportsDB rugby team lookup.
    teams = payload.get("teams") if isinstance(payload, dict) else None
    if teams:
        info = teams[0] or {}
        logo_url = info.get("strBadge") or info.get("strLogo")

    # ESPN soccer schedule payload.
    if not logo_url:
        info = payload.get("team") if isinstance(payload, dict) else None
        if isinstance(info, dict):
            logo_url = info.get("logo")
            if not logo_url:
                logos = info.get("logos") or []
                if logos:
                    logo_url = logos[0].get("href")

    if not logo_url and isinstance(payload, dict):
        for event in payload.get("events") or []:
            _, home, away = pick_competitors(event)
            for competitor in (home, away):
                if competitor_id(competitor) == str(team["espnId"]):
                    info = competitor.get("team") or {}
                    logo_url = info.get("logo")
                    if not logo_url:
                        logos = info.get("logos") or []
                        if logos:
                            logo_url = logos[0].get("href")
                    if logo_url:
                        break
            if logo_url:
                break

    if not logo_url:
        return None

    try:
        raw, content_type = get_bytes(logo_url)
        if not raw:
            return logo_url
        mime = content_type or "image/png"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return logo_url

def main():
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "ESPN + TheSportsDB",
        "teams": [],
    }

    for team in TEAMS:
        record = dict(team)
        try:
            if team["espnSport"] == "soccer":
                events, payload = soccer_data(team)
                past, future = choose_events(events)
            else:
                past, future, payload = rugby_data(team)

            record["past"] = past
            record["next"] = future
            record["badge"] = team_badge(payload, team)
            record["ok"] = True
            record["error"] = None
        except Exception as exc:
            record["past"] = None
            record["next"] = None
            record["badge"] = None
            record["ok"] = False
            record["error"] = str(exc)
        output["teams"].append(record)

    Path("data.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
