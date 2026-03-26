"""One-time backfill: update team & position for players with empty team field.

Uses MLB Stats API + Supabase REST API (no supabase Python package needed).
"""

import json
import os
import time
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://igrcygsbefgpbywadzno.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def fetch_team_id_to_abbrev() -> dict[int, str]:
    """Build team ID → abbreviation mapping from MLB Teams API."""
    resp = requests.get(f"{MLB_API_BASE}/teams", params={"sportId": 1}, timeout=10)
    resp.raise_for_status()
    return {t["id"]: t.get("abbreviation", "") for t in resp.json()["teams"]}


def fetch_empty_team_players() -> list[dict]:
    """Get all players with empty team field from Supabase."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/players",
        params={"select": "player_id,full_name,position", "team": "eq.", "limit": "200"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_mlb_api(player_id: int, team_map: dict[int, str]) -> dict | None:
    """Fetch player metadata from MLB Stats API."""
    try:
        resp = requests.get(
            f"{MLB_API_BASE}/people/{player_id}",
            params={"hydrate": "currentTeam"},
            timeout=10,
        )
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if not people:
            return None
        p = people[0]
        team_obj = p.get("currentTeam", {})
        team_abbrev = team_map.get(team_obj.get("id", 0), "")
        return {
            "team": team_abbrev,
            "position": p.get("primaryPosition", {}).get("abbreviation", ""),
            "full_name": p.get("fullName", ""),
            "first_name": p.get("firstName", ""),
            "last_name": p.get("lastName", ""),
        }
    except Exception as e:
        print(f"  MLB API error for {player_id}: {e}")
        return None


def update_player(player_id: int, data: dict) -> bool:
    """Update a player record in Supabase via REST API."""
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/players",
        params={"player_id": f"eq.{player_id}"},
        headers=HEADERS,
        data=json.dumps(data),
    )
    return resp.status_code < 300


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY environment variable required")
        return

    print("Loading MLB team mappings...")
    team_map = fetch_team_id_to_abbrev()
    print(f"  {len(team_map)} teams loaded\n")

    players = fetch_empty_team_players()
    print(f"Found {len(players)} players with empty team field\n")

    updated = 0
    failed = 0
    still_empty = 0

    for p in players:
        pid = p["player_id"]
        info = fetch_mlb_api(pid, team_map)
        if not info or not info["team"]:
            print(f"  SKIP {pid:>8} {p['full_name']:30s} (no team from API — FA/retired)")
            still_empty += 1
            continue

        update_data = {"team": info["team"], "position": info["position"]}

        # Also fix full_name if it was a fallback like "Player 123456"
        if p["full_name"].startswith("Player ") and info["full_name"]:
            update_data["full_name"] = info["full_name"]
            update_data["first_name"] = info["first_name"]
            update_data["last_name"] = info["last_name"]

        if update_player(pid, update_data):
            print(f"  OK   {pid:>8} {p['full_name']:30s} -> {info['team']:4s} {info['position']}")
            updated += 1
        else:
            print(f"  FAIL {pid:>8} {p['full_name']:30s}")
            failed += 1

        time.sleep(0.1)  # Be polite to MLB API

    print(f"\nDone: {updated} updated, {failed} failed, {still_empty} still empty (FA/retired)")


if __name__ == "__main__":
    main()
