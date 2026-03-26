"""Normalize all player team names to MLB abbreviations.

Converts full team names (e.g., "New York Yankees") to abbreviations ("NYY").
Minor league teams are mapped to their MLB parent org abbreviation.
"""

import json
import os
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

# Minor league affiliate → MLB parent abbreviation
MINOR_LEAGUE_MAP = {
    "Worcester Red Sox": "BOS",
    "Louisville Bats": "CIN",
    "Las Vegas Aviators": "ATH",
    "Indianapolis Indians": "PIT",
    "Rochester Red Wings": "WSH",
    "Nashville Sounds": "MIL",
    "Charlotte Knights": "CWS",
    "Jacksonville Jumbo Shrimp": "MIA",
    "Reno Aces": "AZ",
    "Norfolk Tides": "BAL",
    "Tacoma Rainiers": "SEA",
    "St. Paul Saints": "MIN",
    "Durham Bulls": "TB",
    "Memphis Redbirds": "STL",
    "Scranton/Wilkes-Barre RailRiders": "NYY",
    "Albuquerque Isotopes": "COL",
    "Sacramento River Cats": "SF",
    "Sugar Land Space Cowboys": "HOU",
    "Lehigh Valley IronPigs": "PHI",
    "Oklahoma City Comets": "LAD",
    "Columbus Clippers": "CLE",
    "Omaha Storm Chasers": "KC",
    "Corpus Christi Hooks": "HOU",
    "Salt Lake Bees": "LAA",
    "Toledo Mud Hens": "DET",
    "FCL Blue Jays": "TOR",
    "Syracuse Mets": "NYM",
    "Springfield Cardinals": "STL",
    "ACL Cubs": "CHC",
    "Round Rock Express": "TEX",
    "Iowa Cubs": "CHC",
    "San Antonio Missions": "SD",
    "Gwinnett Stripers": "ATL",
    "Wisconsin Timber Rattlers": "MIL",
    "ACL Mariners": "SEA",
    "ACL Angels": "LAA",
    "ACL Athletics": "ATH",
    "Hartford Yard Goats": "COL",
    "Birmingham Barons": "CWS",
    "Buffalo Bisons": "TOR",
    "ACL Rangers": "TEX",
}


def fetch_mlb_team_name_to_abbrev() -> dict[str, str]:
    """Build full name → abbreviation mapping from MLB Teams API."""
    resp = requests.get(f"{MLB_API_BASE}/teams", params={"sportId": 1}, timeout=10)
    resp.raise_for_status()
    return {t["name"]: t.get("abbreviation", "") for t in resp.json()["teams"]}


def fetch_all_players_with_team() -> list[dict]:
    """Get all players with non-empty, non-abbreviated team names."""
    all_players = []
    offset = 0
    batch = 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/players",
            params={
                "select": "player_id,full_name,team",
                "team": "neq.",
                "limit": str(batch),
                "offset": str(offset),
            },
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        all_players.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return all_players


def update_player_team(player_id: int, team: str) -> bool:
    """Update a player's team in Supabase."""
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/players",
        params={"player_id": f"eq.{player_id}"},
        headers=HEADERS,
        data=json.dumps({"team": team}),
    )
    return resp.status_code < 300


def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY environment variable required")
        return

    print("Loading MLB team mappings...")
    mlb_map = fetch_mlb_team_name_to_abbrev()
    # Merge with minor league map
    full_map = {**MINOR_LEAGUE_MAP}
    for name, abbrev in mlb_map.items():
        full_map[name] = abbrev
    print(f"  {len(mlb_map)} MLB + {len(MINOR_LEAGUE_MAP)} MiLB mappings\n")

    players = fetch_all_players_with_team()
    print(f"Total players with team: {len(players)}\n")

    updated = 0
    skipped = 0
    unknown = 0

    for p in players:
        team = p["team"]
        # Already an abbreviation (3 chars or less)
        if len(team) <= 3:
            skipped += 1
            continue

        abbrev = full_map.get(team)
        if not abbrev:
            print(f"  UNKNOWN  {p['player_id']:>8} {p['full_name']:30s} team='{team}'")
            unknown += 1
            continue

        if update_player_team(p["player_id"], abbrev):
            updated += 1
        else:
            print(f"  FAIL     {p['player_id']:>8} {p['full_name']:30s}")

    print(f"\nDone: {updated} normalized, {skipped} already abbreviated, {unknown} unknown teams")


if __name__ == "__main__":
    main()
