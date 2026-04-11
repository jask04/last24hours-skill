"""Shared domain-quality heuristics for forecast evidence and rendering."""

import re


LOW_SIGNAL_SOCIAL_TERMS = {
    "ticket", "tickets", "selling", "sale", "resale", "bettorbot", "pick", "picks",
    "parlay", "lock", "tail", "sprinkle", "dm", "interested",
}
DRIVER_TERMS = {
    "injury", "injuries", "out", "ruled", "questionable", "doubtful", "available",
    "rest", "resting", "lineup", "lineups", "starter", "starters", "inactive",
    "playoff", "playoffs", "seed", "seeding", "elimination", "clinch", "clinched",
    "tank", "tanking", "forecast", "radar", "storm", "warning", "watch",
    "poll", "approval", "inflation", "cpi", "jobs", "rate", "rates", "fed",
}

WEATHER_SIGNAL_TERMS = {
    "forecast", "forecasts", "radar", "precip", "precipitation", "showers",
    "storm", "storms", "thunderstorm", "thunderstorms", "warning", "warnings",
    "watch", "watches", "wind", "winds", "temperature", "temperatures", "front",
    "humidity", "model", "models", "rainfall", "snowfall", "accumulation",
}
WEATHER_WEAK_TERMS = {"rain", "snow", "storm", "cold", "hot", "weather"}
WEATHER_QUERY_TERMS = WEATHER_SIGNAL_TERMS | WEATHER_WEAK_TERMS | {"hurricane", "tornado"}
WEATHER_LOCATION_STOP = WEATHER_WEAK_TERMS | {"tomorrow", "today", "tonight", "chance", "probability", "odds"}

MACRO_SIGNAL_TERMS = {
    "fed", "fomc", "powell", "cpi", "inflation", "jobs", "payrolls", "gdp",
    "recession", "unemployment", "yield", "yields", "treasury", "treasuries",
    "cut", "cuts", "hike", "hikes", "bps", "basis", "approval", "poll", "polls",
    "economy", "economic", "rate", "rates",
}
MACRO_STRONG_TERMS = {
    "fomc", "powell", "cpi", "inflation", "jobs", "payrolls", "gdp", "recession",
    "unemployment", "yield", "yields", "treasury", "treasuries", "approval",
    "poll", "polls",
}
MACRO_CONTEXT_TERMS = {
    "cut", "cuts", "hike", "hikes", "rate", "rates", "bps", "basis",
    "meeting", "economy", "economic",
}
MACRO_SUPPORT_TERMS = {
    "market", "markets", "pricing", "priced", "probability", "odds", "yields",
    "yield", "treasury", "treasuries", "payrolls", "unemployment", "meeting",
    "data", "release", "releases", "forecast", "estimates",
}
RECESSION_SUPPORT_TERMS = {
    "market", "markets", "pricing", "priced", "probability", "odds", "gdp",
    "jobs", "inflation", "yield", "yields", "treasury", "treasuries",
    "economists", "data", "forecast", "estimates",
}
MACRO_BAD_CONTEXT_TERMS = {
    "grass", "beef", "dog", "album", "hair", "tour", "content", "wedding",
    "song", "music", "sabrina", "tallow", "eat", "food", "well", "biden",
    "lied", "destroyed", "congrats", "wowee", "screaming",
}
MACRO_TOPIC_STOP = {"will", "the", "us", "usa", "have", "has", "a", "an", "in", "by", "june", "2026", "end", "of", "next", "month", "year"}

SPORTS_DRIVER_TERMS = {
    "injury", "injuries", "injured", "ruled", "questionable", "doubtful",
    "probable", "available", "inactive", "rest", "resting", "lineup", "lineups",
    "starter", "starters", "starting", "minutes", "restriction", "restricted",
    "back-to-back", "b2b", "playoff", "playoffs", "seed", "seeding", "elimination",
    "clinch", "clinched", "tank", "tanking", "odds", "line", "spread", "moneyline",
}
SPORTS_HIGH_SIGNAL_TERMS = {
    "injury", "injuries", "ruled", "questionable", "doubtful", "probable",
    "available", "inactive", "rest", "resting", "lineup", "lineups", "starter",
    "starters", "starting", "minutes", "restriction", "restricted", "back-to-back",
    "b2b", "playoff", "playoffs", "seed", "seeding", "elimination", "clinch",
    "clinched", "tank", "tanking",
}
SPORTS_MARKET_CONTEXT_TERMS = {"odds", "line", "spread", "moneyline"}
SPORTS_LOW_SIGNAL_TERMS = {
    "ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat",
    "giveaway", "fs", "wtb", "parlay", "bettorbot", "pick", "picks", "lock",
    "tail", "sprinkle", "hype", "buzz", "vibes", "dm", "interested",
}
SPORTS_RECAP_TERMS = {
    "matchup", "season", "series", "previous", "meeting", "sportsbook",
    "fanduel", "draftkings", "check", "showdown", "get", "ready",
}
SPORTS_REPORTER_TOKENS = {
    "beat", "reporter", "reports", "insider", "news", "updates", "wire",
    "fantasylabs", "underdog", "rotowire", "gameday", "injuryreport",
}
NBA_TEAM_TOKENS = {
    "hawks", "celtics", "nets", "hornets", "bulls", "cavaliers", "cavs",
    "mavericks", "mavs", "nuggets", "pistons", "warriors", "rockets",
    "pacers", "clippers", "lakers", "grizzlies", "heat", "bucks",
    "timberwolves", "wolves", "pelicans", "knicks", "thunder", "magic",
    "76ers", "sixers", "suns", "blazers", "kings", "spurs", "raptors",
    "jazz", "wizards",
}
SPORTS_TEAM_TOKENS = NBA_TEAM_TOKENS | {"guardians", "braves", "yankees", "mets", "dodgers", "giants", "rangers"}


def tokenize(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s-]", " ", (text or "").lower()).split())


def is_weather_query(text: str) -> bool:
    return bool(tokenize(text) & WEATHER_QUERY_TERMS)


def is_macro_query(text: str) -> bool:
    return bool(tokenize(text) & (MACRO_SIGNAL_TERMS | {"fomc", "powell"}))


def weather_signal_tokens(text: str, source_context: str = "") -> set[str]:
    return tokenize(f"{text} {source_context}")


def macro_signal_tokens(text: str, source_context: str = "") -> set[str]:
    return tokenize(f"{text} {source_context}")


def is_weather_signal(
    text: str,
    title_tokens: set[str],
    source_context: str = "",
    require_location: bool = True,
) -> bool:
    tokens = weather_signal_tokens(text, source_context)
    location_tokens = title_tokens - WEATHER_LOCATION_STOP
    if not (WEATHER_SIGNAL_TERMS & tokens):
        return False
    if require_location and location_tokens and not (location_tokens & tokens):
        return False
    return True


def is_macro_signal(text: str, title_tokens: set[str], source_context: str = "") -> bool:
    tokens = macro_signal_tokens(text, source_context)
    macro_overlap = len((title_tokens - MACRO_TOPIC_STOP) & tokens)
    signal_hits = len(MACRO_SIGNAL_TERMS & tokens)
    strong_hits = len(MACRO_STRONG_TERMS & tokens)

    if MACRO_BAD_CONTEXT_TERMS & tokens:
        return False
    if signal_hits == 0:
        return False
    if strong_hits == 0 and macro_overlap < 2:
        return False
    if signal_hits < 2 and not (MACRO_CONTEXT_TERMS & tokens and macro_overlap >= 1):
        return False
    if not ((MACRO_STRONG_TERMS & tokens) or (MACRO_SUPPORT_TERMS & tokens and macro_overlap >= 1)):
        return False
    if "recession" in title_tokens and "recession" in tokens and not (RECESSION_SUPPORT_TERMS & tokens):
        return False
    return True


def is_nba_market_text(text: str) -> bool:
    tokens = tokenize(text)
    lowered = (text or "").lower()
    has_team = bool(NBA_TEAM_TOKENS & tokens)
    has_game_marker = any(marker in lowered for marker in (" vs. ", " vs ", " at ", "spread", "moneyline"))
    return has_team and ("nba" in lowered or has_game_marker)
