"""Public sports schedule helpers for slate-style forecast queries."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import List, Optional, Tuple

from . import dates, http

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SCOREBOARD_URLS = {
    "nba": ESPN_SCOREBOARD_URL,
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_RE = "|".join(_WEEKDAYS)

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
    game_date: str = ""

    @property
    def is_live(self) -> bool:
        return self.status_state == "in"

    @property
    def is_final(self) -> bool:
        return self.status_state == "post" or "final" in (self.status_detail or "").lower()

    @property
    def context(self) -> str:
        status = self.status_detail or "Scheduled"
        score = ""
        if (self.is_live or self.is_final) and self.home_score is not None and self.away_score is not None:
            score = f"; {self.away_team} {self.away_score}, {self.home_team} {self.home_score}"
        clock = ""
        if self.is_live and (self.period or self.clock):
            clock_bits = []
            if self.period:
                clock_bits.append(f"period {self.period}")
            if self.clock and self.clock != "0.0":
                clock_bits.append(self.clock)
            if clock_bits:
                clock = f"; {' '.join(clock_bits)}"
        start = f"; start {self.start_time}" if self.start_time and not self.is_live and not self.is_final else ""
        return f"{self.league.upper()} {status}{score}{clock}{start}".strip()

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


def _parse_scoreboard_game(league: str, event: dict) -> Optional[LiveGame]:
    comp = (event.get("competitions") or [{}])[0]
    status = comp.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    state = str(status_type.get("state") or "").lower()
    start_dt = _parse_espn_time(event.get("date", ""))
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home_team = _team_value(home, "displayName", "name", "shortDisplayName")
    away_team = _team_value(away, "displayName", "name", "shortDisplayName")
    matchup = event.get("name") or (f"{away_team} at {home_team}" if away_team and home_team else "")
    if not matchup:
        return None
    status_state = state if state in {"pre", "in", "post"} else ("pre" if start_dt else state)
    return LiveGame(
        league=league,
        matchup=matchup,
        home_team=home_team,
        away_team=away_team,
        start_time=event.get("date", ""),
        status_state=status_state,
        status_detail=status_type.get("detail") or status_type.get("shortDetail") or status_type.get("description") or ("Live" if state == "in" else "Scheduled"),
        event_id=str(event.get("id") or ""),
        home_short_name=_team_value(home, "shortDisplayName", "name", "displayName"),
        away_short_name=_team_value(away, "shortDisplayName", "name", "displayName"),
        home_abbreviation=_team_value(home, "abbreviation"),
        away_abbreviation=_team_value(away, "abbreviation"),
        period=int(status.get("period") or 0),
        clock=str(status.get("displayClock") or ""),
        home_score=_score_int(home.get("score")),
        away_score=_score_int(away.get("score")),
        game_date=start_dt.date().isoformat() if start_dt else "",
    )


def _parse_live_game(league: str, event: dict, now_utc: datetime, starting_within_minutes: int) -> Optional[LiveGame]:
    game = _parse_scoreboard_game(league, event)
    if not game:
        return None
    start_dt = _parse_espn_time(game.start_time)
    starts_soon = False
    if start_dt:
        minutes_until = (start_dt - now_utc).total_seconds() / 60.0
        starts_soon = 0 <= minutes_until <= starting_within_minutes
    if game.status_state != "in" and not starts_soon:
        return None
    if starts_soon and game.status_state != "in":
        return LiveGame(
            **{
                **game.__dict__,
                "status_state": "pre",
                "status_detail": game.status_detail or "Starting soon",
            }
        )
    return game


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


def _date_mentions(topic: str) -> List[date]:
    """Extract month/day[/year] dates from user text."""
    local_today = dates.current_local_date()
    pattern = re.compile(
        rf"\b(?:(?:{_WEEKDAY_RE})\s+)?({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
        re.I,
    )
    mentions: List[date] = []
    for match in pattern.finditer(topic or ""):
        month = _MONTHS[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        year = int(match.group(3) or local_today.year)
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        mentions.append(value)
    return mentions


def _next_weekday(start: date, weekday: int) -> date:
    delta = (weekday - start.weekday()) % 7
    return start + timedelta(days=delta)


def resolve_nba_date_window(topic: str, max_days: int = 7) -> Optional[Tuple[str, str]]:
    """Resolve explicit or relative NBA event windows into YYYYMMDD bounds."""
    lowered = (topic or "").lower()
    if "nba" not in lowered:
        return None
    if not any(term in lowered for term in ("game", "games", "matchup", "matchups", "market", "markets", "parlay", "bundle", "multi-leg")):
        return None

    mentions = _date_mentions(topic)
    if len(mentions) >= 2:
        start, end = mentions[0], mentions[1]
    elif len(mentions) == 1:
        start = end = mentions[0]
    else:
        local_today = dates.current_local_date()
        start = local_today
        if "tomorrow" in lowered:
            start = local_today + timedelta(days=1)
        elif not any(term in lowered for term in ("today", "tonight", "through", "until", " to ", " up to ", "up until")):
            return None

        weekday_match = re.search(rf"\b(?:through|until|to|up to|up until)\s+(?:next\s+)?({_WEEKDAY_RE})\b", lowered)
        if weekday_match:
            end = _next_weekday(start, _WEEKDAYS[weekday_match.group(1)])
        else:
            end = start

    if end < start:
        start, end = end, start
    if (end - start).days + 1 > max_days:
        end = start + timedelta(days=max_days - 1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def is_nba_date_window_query(topic: str) -> bool:
    return resolve_nba_date_window(topic) is not None


def _date_iter(start_yyyymmdd: str, end_yyyymmdd: str) -> List[str]:
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d").date()
    values = []
    current = start
    while current <= end:
        values.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return values


def fetch_nba_game_records(date_yyyymmdd: str) -> List[LiveGame]:
    """Fetch NBA scoreboard records for a date from ESPN's public endpoint."""
    url = f"{ESPN_SCOREBOARD_URL}?dates={date_yyyymmdd}"
    data = http.get(url, timeout=15, retries=2)
    games: List[LiveGame] = []
    for event in data.get("events", []):
        parsed = _parse_scoreboard_game("nba", event)
        if parsed:
            games.append(parsed)
    games.sort(key=lambda game: (game.start_time, game.matchup))
    return games


def fetch_nba_games(date_yyyymmdd: str) -> List[str]:
    """Fetch NBA games for a date from ESPN's public scoreboard endpoint."""
    return [game.matchup for game in fetch_nba_game_records(date_yyyymmdd)]


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


def expand_nba_date_window_query(topic: str, max_days: int = 7) -> Tuple[Optional[str], Optional[str], List[LiveGame]]:
    """Expand an NBA date-window prompt into scheduled ESPN games."""
    window = resolve_nba_date_window(topic, max_days=max_days)
    if not window:
        return None, None, []
    start, end = window
    games: List[LiveGame] = []
    for date_yyyymmdd in _date_iter(start, end):
        games.extend(fetch_nba_game_records(date_yyyymmdd))
    return start, end, games


def _clean_token_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())


def _team_aliases(game: LiveGame, side: str) -> List[str]:
    if side == "home":
        values = [game.home_team, game.home_short_name, game.home_abbreviation]
    else:
        values = [game.away_team, game.away_short_name, game.away_abbreviation]
    aliases = []
    for value in values:
        normalized = " ".join(_clean_token_text(value).split())
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _contains_alias(text: str, aliases: List[str]) -> bool:
    padded = f" {_clean_token_text(text)} "
    tokens = set(padded.split())
    for alias in aliases:
        alias = " ".join(_clean_token_text(alias).split())
        if not alias:
            continue
        if len(alias) <= 3:
            if alias in tokens:
                return True
        elif f" {alias} " in padded:
            return True
        else:
            parts = [part for part in alias.split() if len(part) > 3]
            if parts and any(part in tokens for part in parts):
                return True
    return False


def match_game_for_market_text(text: str, games: List[LiveGame]) -> Tuple[Optional[LiveGame], float, str]:
    """Match market text to an ESPN game by requiring both teams."""
    for game in games or []:
        home_match = _contains_alias(text, _team_aliases(game, "home"))
        away_match = _contains_alias(text, _team_aliases(game, "away"))
        if home_match and away_match:
            exact_names = (
                _clean_token_text(game.home_team) in _clean_token_text(text)
                and _clean_token_text(game.away_team) in _clean_token_text(text)
            )
            exact_abbr = bool(
                game.home_abbreviation
                and game.away_abbreviation
                and _contains_alias(text, [game.home_abbreviation])
                and _contains_alias(text, [game.away_abbreviation])
            )
            confidence = 0.95 if exact_names else 0.85 if exact_abbr else 0.72
            return game, confidence, "direct_match"
    return None, 0.0, "no_game_match"


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
