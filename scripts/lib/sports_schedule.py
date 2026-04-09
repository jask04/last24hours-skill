"""Public sports schedule helpers for slate-style forecast queries."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from . import http

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

NBA_TEAM_SUBREDDITS = {
    "atlanta hawks": ["nba", "atlantahawks", "sportsbook"],
    "boston celtics": ["nba", "bostonceltics", "sportsbook"],
    "brooklyn nets": ["nba", "gonets", "sportsbook"],
    "charlotte hornets": ["nba", "charlottehornets", "sportsbook"],
    "chicago bulls": ["nba", "chicagobulls", "sportsbook"],
    "cleveland cavaliers": ["nba", "clevelandcavs", "sportsbook"],
    "dallas mavericks": ["nba", "mavericks", "sportsbook"],
    "denver nuggets": ["nba", "denvernuggets", "sportsbook"],
    "detroit pistons": ["nba", "detroitpistons", "sportsbook"],
    "golden state warriors": ["nba", "warriors", "sportsbook"],
    "houston rockets": ["nba", "rockets", "sportsbook"],
    "indiana pacers": ["nba", "pacers", "sportsbook"],
    "los angeles clippers": ["nba", "laclippers", "sportsbook"],
    "los angeles lakers": ["nba", "lakers", "sportsbook"],
    "memphis grizzlies": ["nba", "memphisgrizzlies", "sportsbook"],
    "miami heat": ["nba", "heat", "sportsbook"],
    "milwaukee bucks": ["nba", "mkebucks", "sportsbook"],
    "minnesota timberwolves": ["nba", "timberwolves", "sportsbook"],
    "new orleans pelicans": ["nba", "nolapelicans", "sportsbook"],
    "new york knicks": ["nba", "nyknicks", "sportsbook"],
    "oklahoma city thunder": ["nba", "thunder", "sportsbook"],
    "orlando magic": ["nba", "orlandomagic", "sportsbook"],
    "philadelphia 76ers": ["nba", "sixers", "sportsbook"],
    "phoenix suns": ["nba", "suns", "sportsbook"],
    "portland trail blazers": ["nba", "ripcity", "sportsbook"],
    "sacramento kings": ["nba", "kings", "sportsbook"],
    "san antonio spurs": ["nba", "nbaspurs", "sportsbook"],
    "toronto raptors": ["nba", "torontoraptors", "sportsbook"],
    "utah jazz": ["nba", "utahjazz", "sportsbook"],
    "washington wizards": ["nba", "washingtonwizards", "sportsbook"],
}


def is_nba_slate_query(topic: str) -> bool:
    """Return True when the query asks for a broad NBA game slate."""
    topic_lower = topic.lower()
    if "nba" not in topic_lower:
        return False
    return any(term in topic_lower for term in (
        "games today", "games tonight", "games tomorrow", "tomorrows nba games",
        "tomorrow's nba games", "todays nba games", "today's nba games",
        "nba slate", "tomorrow nba", "tonight nba", "today nba",
    ))


def resolve_relative_nba_date(topic: str) -> Optional[str]:
    """Resolve today/tomorrow-style NBA slate language into YYYYMMDD."""
    if not is_nba_slate_query(topic):
        return None

    topic_lower = topic.lower()
    local_today = datetime.now().astimezone().date()
    if "tomorrow" in topic_lower or "tomorrows" in topic_lower:
        target = local_today + timedelta(days=1)
    else:
        target = local_today
    return target.strftime("%Y%m%d")


def fetch_nba_games(date_yyyymmdd: str) -> List[str]:
    """Fetch NBA games for a date from ESPN's public scoreboard endpoint."""
    url = f"{ESPN_SCOREBOARD_URL}?dates={date_yyyymmdd}"
    data = http.get(url, timeout=15, retries=2)
    games = []
    for event in data.get("events", []):
        name = event.get("name")
        if name:
            games.append(name)
    return games


def expand_nba_slate_query(topic: str) -> Tuple[Optional[str], List[str]]:
    """Expand a broad NBA slate query into matchup-specific subqueries."""
    date_yyyymmdd = resolve_relative_nba_date(topic)
    if not date_yyyymmdd:
        return None, []

    games = fetch_nba_games(date_yyyymmdd)
    return date_yyyymmdd, games


def matchup_team_names(topic: str) -> List[str]:
    """Extract normalized NBA team names from a matchup-style topic."""
    text = topic.lower()
    teams = []
    for team_name in NBA_TEAM_SUBREDDITS:
        if team_name in text:
            teams.append(team_name)
    return teams


def matchup_subreddits(topic: str) -> List[str]:
    """Return subreddit candidates for an NBA matchup query."""
    subs: List[str] = []
    for team_name in matchup_team_names(topic):
        for sub in NBA_TEAM_SUBREDDITS.get(team_name, []):
            if sub not in subs:
                subs.append(sub)
    return subs
