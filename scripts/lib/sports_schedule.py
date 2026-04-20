"""Public sports schedule helpers for slate-style forecast queries."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from . import dates, http

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SCOREBOARD_URLS = {
    "nba": ESPN_SCOREBOARD_URL,
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}

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


@dataclass(frozen=True)
class LiveGame:
    league: str
    matchup: str
    home_team: str
    away_team: str
    start_time: str
    status_state: str
    status_detail: str
    event_id: str = ""
    home_short_name: str = ""
    away_short_name: str = ""
    home_abbreviation: str = ""
    away_abbreviation: str = ""
    period: int = 0
    clock: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None

    @property
    def is_live(self) -> bool:
        return self.status_state == "in"

    @property
    def context(self) -> str:
        score = ""
        if self.home_score is not None and self.away_score is not None:
            score = f"; {self.away_team} {self.away_score}, {self.home_team} {self.home_score}"
        clock = f"; period {self.period} {self.clock}".strip() if self.period or self.clock else ""
        return f"{self.league.upper()} {self.status_detail}{score}{clock}".strip()

    @property
    def live_search_aliases(self) -> List[str]:
        """Return Polymarket search terms for direct live game matching."""
        pairs = [
            (self.away_team, self.home_team),
            (self.home_team, self.away_team),
            (self.away_short_name, self.home_short_name),
            (self.home_short_name, self.away_short_name),
            (self.away_abbreviation, self.home_abbreviation),
            (self.home_abbreviation, self.away_abbreviation),
        ]
        aliases: List[str] = []
        for left, right in pairs:
            left = (left or "").strip()
            right = (right or "").strip()
            if left and right and left.lower() != right.lower():
                aliases.extend([
                    f"{left} at {right}",
                    f"{left} vs {right}",
                    f"{self.league.upper()} {left} {right}",
                ])
        seen = set()
        result = []
        for alias in [self.matchup, *aliases]:
            normalized = " ".join(alias.split())
            key = normalized.lower()
            if normalized and key not in seen:
                result.append(normalized)
                seen.add(key)
        return result


def _parse_espn_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).astimezone(timezone.utc)
    except ValueError:
        return None


def _score_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _team_value(competitor: dict, *keys: str) -> str:
    team = competitor.get("team") or {}
    for key in keys:
        value = team.get(key)
        if value:
            return str(value).strip()
    return ""


def _parse_live_game(league: str, event: dict, now_utc: datetime, starting_within_minutes: int) -> Optional[LiveGame]:
    comp = (event.get("competitions") or [{}])[0]
    status = comp.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    state = str(status_type.get("state") or "").lower()
    start_dt = _parse_espn_time(event.get("date", ""))
    starts_soon = False
    if start_dt:
        minutes_until = (start_dt - now_utc).total_seconds() / 60.0
        starts_soon = 0 <= minutes_until <= starting_within_minutes
    if state != "in" and not starts_soon:
        return None

    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home_team = _team_value(home, "displayName", "name", "shortDisplayName")
    away_team = _team_value(away, "displayName", "name", "shortDisplayName")
    matchup = event.get("name") or (f"{away_team} at {home_team}" if away_team and home_team else "")
    if not matchup:
        return None
    return LiveGame(
        league=league,
        matchup=matchup,
        home_team=home_team,
        away_team=away_team,
        start_time=event.get("date", ""),
        status_state="in" if state == "in" else "pre",
        status_detail=status_type.get("detail") or status_type.get("shortDetail") or status_type.get("description") or ("Live" if state == "in" else "Starting soon"),
        event_id=str(event.get("id") or ""),
        home_short_name=_team_value(home, "shortDisplayName", "name", "displayName"),
        away_short_name=_team_value(away, "shortDisplayName", "name", "displayName"),
        home_abbreviation=_team_value(home, "abbreviation"),
        away_abbreviation=_team_value(away, "abbreviation"),
        period=int(status.get("period") or 0),
        clock=str(status.get("displayClock") or ""),
        home_score=_score_int(home.get("score")),
        away_score=_score_int(away.get("score")),
    )


def is_nba_slate_query(topic: str) -> bool:
    """Return True when the query asks for a broad NBA game slate."""
    topic_lower = topic.lower()
    if "nba" not in topic_lower:
        return False
    return any(term in topic_lower for term in (
        "games today", "games tonight", "games tomorrow", "tomorrows nba games",
        "tomorrow's nba games", "todays nba games", "today's nba games",
        "nba slate", "tomorrow nba", "tonight nba", "today nba",
        "nba matchups", "nba matchups tomorrow", "matchups tomorrow",
    ))


def resolve_relative_nba_date(topic: str) -> Optional[str]:
    """Resolve today/tomorrow-style NBA slate language into YYYYMMDD."""
    if not is_nba_slate_query(topic):
        return None

    topic_lower = topic.lower()
    local_today = dates.current_local_date()
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


def fetch_live_games(
    leagues: Optional[List[str]] = None,
    date_yyyymmdd: Optional[str] = None,
    starting_within_minutes: int = 60,
    now: Optional[datetime] = None,
) -> List[LiveGame]:
    """Fetch live or starting-soon games from ESPN public scoreboards."""
    local_date = dates.current_local_date()
    date_yyyymmdd = date_yyyymmdd or local_date.strftime("%Y%m%d")
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    selected = leagues or ["nba", "mlb", "nhl", "nfl"]
    games: List[LiveGame] = []
    for league in selected:
        base = ESPN_SCOREBOARD_URLS.get(league)
        if not base:
            continue
        try:
            data = http.get(f"{base}?dates={date_yyyymmdd}", timeout=5, retries=1)
        except Exception:
            continue
        for event in data.get("events", []):
            parsed = _parse_live_game(league, event, now_utc, starting_within_minutes)
            if parsed:
                games.append(parsed)
    games.sort(key=lambda game: (0 if game.is_live else 1, game.start_time, game.league))
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
