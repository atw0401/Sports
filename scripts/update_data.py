#!/usr/bin/env python3
import base64
import json
import mimetypes
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TEAMS = [
    {"id": 33, "name": "Tottenham Hotspur", "sport": "Football", "apiSport": "football",
     "teamUrl": "https://www.sofascore.com/football/team/tottenham-hotspur/33"},
    {"id": 4196, "name": "Bath Rugby", "sport": "Rugby Union", "apiSport": "rugby",
     "teamUrl": "https://www.sofascore.com/rugby/team/bath-rugby/4196"},
    {"id": 4713, "name": "England Football", "sport": "Football", "apiSport": "football",
     "teamUrl": "https://www.sofascore.com/football/team/england/4713"},
    {"id": 4226, "name": "England Rugby", "sport": "Rugby Union", "apiSport": "rugby",
     "teamUrl": "https://www.sofascore.com/rugby/team/england/4226"},
]

API_BASES = [
    "https://www.sofascore.com/api/v1",
    "https://api.sofascore.com/api/v1",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MySportsDashboard/1.0)",
    "Accept": "application/json,text/plain,*/*",
}

def get_bytes(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read(), response.headers.get_content_type()

def get_json(url):
    raw, _ = get_bytes(url)
    return json.loads(raw.decode("utf-8"))

def api_json(path):
    last_error = None
    for base in API_BASES:
        try:
            return get_json(base + path)
        except Exception as exc:
            last_error = exc
    raise last_error

def first_event(payload):
    events = payload.get("events") or []
    return events[0] if events else None

def compact_event(event):
    if not event:
        return None

    def score_value(side):
        score = event.get(side + "Score") or {}
        for key in ("current", "display", "normaltime"):
            value = score.get(key)
            if value is not None:
                return value
        return None

    tournament = event.get("tournament") or {}
    unique_tournament = event.get("uniqueTournament") or {}
    category = tournament.get("category") or {}
    sport = category.get("sport") or event.get("sport") or {}

    return {
        "id": event.get("id"),
        "slug": event.get("slug"),
        "customId": event.get("customId") or event.get("custom_id"),
        "startTimestamp": event.get("startTimestamp"),
        "homeTeam": {
            "name": (event.get("homeTeam") or {}).get("name"),
            "slug": (event.get("homeTeam") or {}).get("slug"),
        },
        "awayTeam": {
            "name": (event.get("awayTeam") or {}).get("name"),
            "slug": (event.get("awayTeam") or {}).get("slug"),
        },
        "homeScore": score_value("home"),
        "awayScore": score_value("away"),
        "tournament": tournament.get("name") or unique_tournament.get("name"),
        "sportSlug": sport.get("slug"),
    }

def fetch_badge(team_id):
    urls = [
        f"https://www.sofascore.com/api/v1/team/{team_id}/image",
        f"https://api.sofascore.com/api/v1/team/{team_id}/image",
    ]
    for url in urls:
        try:
            raw, content_type = get_bytes(url)
            if len(raw) < 128:
                continue
            mime = content_type or mimetypes.guess_type(url)[0] or "image/png"
            return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
        except Exception:
            pass
    return None

def main():
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "teams": []
    }

    for team in TEAMS:
        record = dict(team)
        try:
            past = api_json(f"/team/{team['id']}/events/last/0")
            future = api_json(f"/team/{team['id']}/events/next/0")
            record["past"] = compact_event(first_event(past))
            record["next"] = compact_event(first_event(future))
            record["badge"] = fetch_badge(team["id"])
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
