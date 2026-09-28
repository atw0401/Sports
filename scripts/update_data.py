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
        "id": 4196, "espnId": 25898, "sportsDbId": 135199, "sportsDbLeagues": [4414, 4550, 5695], "sportsDbSeasons": ["2025-2026", "2026-2027"], "name": "Bath Rugby",
        "sport": "Rugby Union", "apiSport": "rugby", "espnSport": "rugby",
        "teamUrl": "https://www.sofascore.com/rugby/team/bath-rugby/4196",
    },
    {
        "id": 4713, "espnId": 448, "name": "England Football",
        "sport": "Football", "apiSport": "football", "espnSport": "soccer",
        "teamUrl": "https://www.sofascore.com/football/team/england/4713",
    },
    {
        "id": 4226, "espnId": 1, "sportsDbId": 137123, "sportsDbLeagues": [4714, 5852, 5479], "sportsDbSeasons": ["2026"], "name": "England Rugby",
        "sport": "Rugby Union", "apiSport": "rugby", "espnSport": "rugby",
        "teamUrl": "https://www.sofascore.com/rugby/team/england/4226",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 17) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.sofascore.com/",
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

def sofascore_event(event, fallback_sport):
    if not event:
        return None

    def sofa_score(side):
        score = event.get(side + "Score") or {}
        for key in ("current", "display", "normaltime"):
            if score.get(key) is not None:
                return score.get(key)
        return None

    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    tournament = event.get("tournament") or {}
    category = tournament.get("category") or {}
    sport = (category.get("sport") or event.get("sport") or {}).get("slug") or fallback_sport
    event_id = event.get("id")
    slug = event.get("slug") or "-".join(x for x in (home.get("slug"), away.get("slug")) if x)
    custom_id = event.get("customId") or event.get("custom_id")

    event_url = None
    if event_id and slug and custom_id:
        event_url = f"https://www.sofascore.com/{sport}/match/{slug}/{custom_id}#id:{event_id}"
    elif event_id:
        event_url = f"https://www.sofascore.com/event/{event_id}"

    return {
        "id": event_id,
        "startTimestamp": event.get("startTimestamp"),
        "homeTeam": {"name": home.get("name"), "slug": home.get("slug")},
        "awayTeam": {"name": away.get("name"), "slug": away.get("slug")},
        "homeScore": sofa_score("home"),
        "awayScore": sofa_score("away"),
        "tournament": tournament.get("name") or "",
        "sportSlug": sport,
        "slug": slug,
        "customId": custom_id,
        "eventUrl": event_url,
    }

def sofascore_data(team):
    bases = [
        "https://www.sofascore.com/api/v1",
        "https://api.sofascore.com/api/v1",
    ]
    last_error = None

    for base in bases:
        try:
            past_payload = get_json(f"{base}/team/{team['id']}/events/last/0")
            next_payload = get_json(f"{base}/team/{team['id']}/events/next/0")
            past_events = past_payload.get("events") or []
            next_events = next_payload.get("events") or []

            past = sofascore_event(past_events[0], team["apiSport"]) if past_events else None
            future = sofascore_event(next_events[0], team["apiSport"]) if next_events else None

            badge = None
            try:
                raw, content_type = get_bytes(f"{base}/team/{team['id']}/image")
                if raw:
                    mime = content_type or "image/png"
                    badge = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
            except Exception:
                pass

            if past is None and future is None:
                raise RuntimeError("SofaScore returned no events")

            return past, future, badge
        except Exception as exc:
            last_error = exc

    raise last_error or RuntimeError("SofaScore unavailable")

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
    team_id = str(team["sportsDbId"])
    base = "https://www.thesportsdb.com/api/v1/json/123"

    team_payload = get_json(f"{base}/lookupteam.php?id={team_id}")
    all_events = []

    # Team endpoints are useful as a fallback, but can favour the primary league.
    for endpoint, key_names in (
        ("eventslast.php", ("results", "events")),
        ("eventsnext.php", ("events", "results")),
    ):
        try:
            payload = get_json(f"{base}/{endpoint}?id={team_id}")
            for key in key_names:
                if payload.get(key):
                    all_events.extend(payload[key])
                    break
        except Exception:
            pass

    # Merge the team's known competitions so "last match" really means the
    # most recent match across league, cup and international competitions.
    for league_id in team.get("sportsDbLeagues", []):
        for season in team.get("sportsDbSeasons", []):
            try:
                payload = get_json(
                    f"{base}/eventsseason.php?id={league_id}&s={urllib.parse.quote(season)}"
                )
                for event in payload.get("events") or []:
                    home_id = str(event.get("idHomeTeam") or "")
                    away_id = str(event.get("idAwayTeam") or "")
                    if team_id in (home_id, away_id):
                        all_events.append(event)
            except Exception:
                pass

    compact = []
    seen = set()
    for event in all_events:
        event_id = str(event.get("idEvent") or "")
        if event_id and event_id in seen:
            continue
        if event_id:
            seen.add(event_id)
        parsed = sportsdb_event(event)
        if parsed and parsed.get("startTimestamp"):
            compact.append(parsed)

    if not compact:
        raise RuntimeError("TheSportsDB returned no rugby fixtures")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    completed = [
        event for event in compact
        if event["startTimestamp"] <= now_ts
        and event.get("homeScore") is not None
        and event.get("awayScore") is not None
    ]
    upcoming = [
        event for event in compact
        if event["startTimestamp"] >= now_ts
        and (event.get("homeScore") is None or event.get("awayScore") is None)
    ]

    previous = max(completed, key=lambda e: e["startTimestamp"]) if completed else None
    future = min(upcoming, key=lambda e: e["startTimestamp"]) if upcoming else None

    return previous, future, team_payload

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
        "source": "SofaScore with provider fallback",
        "teams": [],
    }

    for team in TEAMS:
        record = dict(team)
        try:
            # SofaScore is the preferred source because the app's click-through
            # behaviour and original design were built around its event IDs.
            past, future, badge = sofascore_data(team)
            record["past"] = past
            record["next"] = future
            record["badge"] = badge
            record["source"] = "SofaScore"
            record["ok"] = True
            record["error"] = None
        except Exception as sofa_exc:
            try:
                # Provider fallback keeps the app useful if SofaScore changes
                # its anti-bot rules or has an outage.
                if team["espnSport"] == "soccer":
                    events, payload = soccer_data(team)
                    past, future = choose_events(events)
                else:
                    past, future, payload = rugby_data(team)

                record["past"] = past
                record["next"] = future
                record["badge"] = team_badge(payload, team)
                record["source"] = "Fallback"
                record["ok"] = True
                record["error"] = f"SofaScore unavailable: {sofa_exc}"
            except Exception as fallback_exc:
                record["past"] = None
                record["next"] = None
                record["badge"] = None
                record["source"] = None
                record["ok"] = False
                record["error"] = f"SofaScore: {sofa_exc}; fallback: {fallback_exc}"
        output["teams"].append(record)

    Path("data.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
