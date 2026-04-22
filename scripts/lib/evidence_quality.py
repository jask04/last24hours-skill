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
WEATHER_QUERY_TERMS = (
    WEATHER_SIGNAL_TERMS - {"watch", "watches", "warning", "warnings"}
) | WEATHER_WEAK_TERMS | {"hurricane", "tornado"}
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
    "clinch", "clinched", "tank", "tanking", "line", "spread", "moneyline",
}
SPORTS_HIGH_SIGNAL_TERMS = {
    "injury", "injuries", "ruled", "questionable", "doubtful", "probable",
    "available", "inactive", "rest", "resting", "lineup", "lineups", "starter",
    "starters", "starting", "minutes", "restriction", "restricted", "back-to-back",
    "b2b", "playoff", "playoffs", "seed", "seeding", "elimination", "clinch",
    "clinched", "tank", "tanking",
}
SPORTS_MARKET_CONTEXT_TERMS = {"line", "spread", "moneyline"}
SPORTS_LOW_SIGNAL_TERMS = {
    "ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat",
    "giveaway", "fs", "wtb", "parlay", "bettorbot", "pick", "picks", "lock",
    "tail", "sprinkle", "hype", "buzz", "vibes", "dm", "interested", "vip",
    "cashing", "bets",
}
SPORTS_REJECT_TERMS = {
    "gamethread", "highlight", "highlights", "live", "score", "scores", "2k",
    "mycareer",
}
SPORTS_GENERIC_PREVIEW_TERMS = {
    "preview", "previews", "matchup", "matchups", "strategy", "strategies",
    "overpower", "thrilling", "showdown", "watch", "channel", "tickets",
    "sportsbook", "fanduel", "draftkings", "betting", "odds", "previous", "meeting",
    "iconic", "ats", "angle", "favorite", "favorites", "probabilities",
}
SPORTS_RECAP_TERMS = {
    "matchup", "season", "series", "previous", "meeting", "sportsbook",
    "fanduel", "draftkings", "check", "showdown", "get", "ready", "ats", "angle",
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
ESPORTS_TERMS = {
    "esports", "counter", "strike", "counterstrike", "counter-strike", "cs2", "csgo",
    "valorant", "league", "legends", "dota", "bo1", "bo2", "bo3", "bo5",
}
CS2_TERMS = {"counter", "strike", "counterstrike", "counter-strike", "cs2", "csgo"}
ESPORTS_HIGH_SIGNAL_TERMS = {
    "roster", "standin", "stand-in", "sub", "substitute", "bench", "benched", "coach",
    "veto", "map", "pool", "patch", "update", "qualifier", "qualifiers", "playoffs",
    "playoff", "bracket", "elimination", "seed", "seeding", "lan", "travel", "server",
    "ping", "illness", "sick", "injury", "injured",
}
ESPORTS_LOW_SIGNAL_TERMS = {
    "highlight", "highlights", "clip", "clips", "giveaway", "skin", "skins", "case",
    "cases", "inventory", "fragmovie", "ace", "best plays", "montage", "dev", "log",
    "developer", "trailer", "giveaways", "promo", "bet", "bets", "pick", "picks",
    "potd", "deposit", "signup", "sign", "whale", "movements", "prizepicks", "cash",
    "cashing", "watch", "stream", "live", "vod", "vods", "listing", "listings",
    "schedule", "schedules", "score", "scores", "scored",
}
ESPORTS_NOISE_TERMS = {
    "animgraph", "downdetector", "download", "install", "issue", "issues", "status",
    "outage", "outages", "maintenance", "reply", "replies", "scholarship", "watchparty",
}
ESPORTS_PROP_REJECT_TERMS = {
    "giveaway", "giveaways", "promo", "promotional", "clip", "clips", "highlight",
    "highlights", "watch", "stream", "live", "listing", "listings", "schedule",
    "schedules", "score", "scores", "vod", "vods", "recap", "recaps", "org",
    "organization", "announcement", "announcements",
}
ESPORTS_ENTITY_STOP = ESPORTS_TERMS | {
    "match", "matches", "game", "games", "qualifier", "qualifiers", "playoff",
    "playoffs", "bracket", "round", "group", "stage", "series", "main",
    "regular", "academy", "esports", "today", "tomorrow", "tonight",
}


def tokenize(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s-]", " ", (text or "").lower()).split())


def is_weather_query(text: str) -> bool:
    tokens = tokenize(text)
    if tokens & WEATHER_QUERY_TERMS:
        return True
    return bool((tokens & {"watch", "watches", "warning", "warnings"}) and (tokens & {"weather", "storm", "tornado", "hurricane", "flood", "flooding", "severe"}))


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
    if "kxnbagame" in lowered or "kxnbaseries" in lowered:
        return True
    if "nba" in lowered and re.search(r"\bgame\s+\d+:", lowered) and any(marker in lowered for marker in (" at ", " vs ", " vs. ")):
        return True
    has_team = bool(NBA_TEAM_TOKENS & tokens)
    has_game_marker = any(marker in lowered for marker in (" vs. ", " vs ", " at ", "spread", "moneyline"))
    return has_team and ("nba" in lowered or has_game_marker)


def is_esports_query(text: str) -> bool:
    lowered = (text or "").lower()
    tokens = tokenize(text)
    if tokens & ESPORTS_TERMS:
        return True
    if extract_esports_players(text) and has_player_prop_stat_marker(text):
        return True
    return any(phrase in lowered for phrase in ("counter-strike", "league of legends"))


def is_cs2_market_text(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(re.search(r"\bcounter[- ]strike(?:\s*2)?\b|\bcs2\b|\bcsgo\b", lowered))


def is_cs2_query(text: str) -> bool:
    return is_cs2_market_text(text)


def is_valorant_market_text(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(re.search(r"\bvalorant\b|\bvct\b", lowered))


def is_valorant_query(text: str) -> bool:
    return is_valorant_market_text(text)


def is_lol_market_text(text: str) -> bool:
    lowered = (text or "").lower()
    if re.search(r"\bleague of legends\b|\blcs\b|\blec\b|\blck\b|\blpl\b", lowered):
        return True
    if re.search(r"\blol\b", lowered) and is_esports_query(text):
        return True
    return False


def is_lol_query(text: str) -> bool:
    return is_lol_market_text(text)


def esports_subdomain_of(text: str) -> str:
    """Return the specific eSports subdomain label ('cs2', 'valorant', 'lol') or '' when text is not subdomain-specific."""
    if is_cs2_market_text(text):
        return "cs2"
    if is_valorant_market_text(text):
        return "valorant"
    if is_lol_market_text(text):
        return "lol"
    return ""


def inferred_esports_subdomain(text: str) -> str:
    explicit = esports_subdomain_of(text)
    if explicit:
        return explicit
    for subdomain in ("cs2", "valorant", "lol"):
        if extract_esports_players(text, subdomain=subdomain):
            return subdomain
    return ""


# ---------------------------------------------------------------------------
# eSports player-prop detection (v1.0.55 groundwork)
#
# Conservative curated rosters of current top-tier pro players. These lists
# feed `extract_esports_players()` / `is_cs2_player_text()` helpers and the
# player-prop query classifier in `forecast.py`. No scraped feeds — every
# entry is a deliberate add.
# ---------------------------------------------------------------------------

CS2_PLAYER_TOKENS = {
    # NAVI / tier-1 Europe
    "s1mple", "b1t", "w0nderful", "jl", "aleksib", "iem",
    # G2 / Vitality / Team Falcons / MOUZ / FaZe
    "zywoo", "niko", "m0nesy", "sh1ro", "ax1le", "device", "twistzz",
    "ropz", "broky", "rain", "karrigan", "magisk", "blamef", "frozen",
    "jame", "hooch", "donk", "perfecto", "ilay", "flamie",
    # North America / SA
    "ethan", "stewie2k", "snow", "floppy", "junior", "yekindar",
}
VALORANT_PLAYER_TOKENS = {
    "tenz", "aspas", "less", "derke", "yay", "chronicle", "cryocells",
    "suygetsu", "ange1", "zekken", "marved", "sacy", "leo", "sayf",
    "fns", "n4rrate", "crashies", "boostio", "something", "jinggg",
}
LOL_PLAYER_TOKENS = {
    "faker", "chovy", "showmaker", "zeus", "oner", "keria", "ruler",
    "viper", "gumayusi", "canyon", "bdd", "peyz", "zeka", "deokdam",
    "bin", "caps", "jankos", "rekkles",
}

# Aggregate roster used when the query does not specify a subdomain.
_ESPORTS_ALL_PLAYERS = CS2_PLAYER_TOKENS | VALORANT_PLAYER_TOKENS | LOL_PLAYER_TOKENS

# Stat markers that indicate a *player-level* prop (not match-level). Mirrored
# in `market_types._ESPORTS_PROP_MARKERS` so the market classifier agrees.
ESPORTS_PROP_STAT_MARKERS = {
    "kills", "headshot", "headshots", "adr", "first kill", "first blood",
    "1v1", "clutch", "entry kill", "mvp", "bomb plant", "pistol round",
    "assists", "deaths", "kd", "k/d", "rating", "props", "prop",
}


def _roster_for_subdomain(subdomain: str) -> set[str]:
    sub = (subdomain or "").lower()
    if sub == "cs2":
        return CS2_PLAYER_TOKENS
    if sub == "valorant":
        return VALORANT_PLAYER_TOKENS
    if sub == "lol":
        return LOL_PLAYER_TOKENS
    return _ESPORTS_ALL_PLAYERS


def extract_esports_players(text: str, *, subdomain: str = "") -> set[str]:
    """Return the set of roster tokens present in `text` for the subdomain.

    When `subdomain` is empty, the aggregate CS2+Valorant+LoL roster is used.
    Matching is lowercase token-level; "s1mple" and "S1mple" both match, but
    "s1mple's kills" does — the tokenizer strips punctuation.
    """
    roster = _roster_for_subdomain(subdomain)
    tokens = tokenize(text)
    return tokens & roster


def extract_cs2_players(text: str) -> set[str]:
    """CS2-subdomain convenience wrapper."""
    return extract_esports_players(text, subdomain="cs2")


def is_cs2_player_text(text: str) -> bool:
    """True when text mentions a known CS2 pro player."""
    return bool(extract_cs2_players(text))


def has_player_prop_stat_marker(text: str) -> bool:
    """True when text contains a player-level stat marker (kills, ADR, etc.)."""
    lowered = (text or "").lower()
    tokens = tokenize(text)
    if tokens & ESPORTS_PROP_STAT_MARKERS:
        return True
    return any(
        phrase in lowered
        for phrase in ("first kill", "first blood", "bomb plant", "pistol round", "player prop", "player-prop")
    )


def is_esports_player_prop_query(text: str) -> bool:
    """True when the query pairs an eSports signal with a player-prop signal.

    A query qualifies when it matches *both* of:
      - eSports context: a named pro player OR an eSports domain term
      - player-prop context: a named pro player OR a stat marker
        (kills/headshots/ADR/etc.)

    This requires a two-signal match so unrelated text like "donk the dictator"
    (player token appears but no esports or stat context) does not trigger.
    It stays disjoint from match-level `_is_esports_match_query`, which
    continues to reject kills/props/handicap outright.
    """
    if not text:
        return False
    has_player = bool(extract_esports_players(text))
    has_domain = is_esports_query(text)
    has_stat = has_player_prop_stat_marker(text)
    esports_signal = has_player or has_domain
    prop_signal = has_player or has_stat
    if not (esports_signal and prop_signal):
        return False
    # Guard: bare "player name + esports term" with no stat marker is still
    # treated as a prop query (pro handle + title is a strong enough signal),
    # but "player name alone" is not — an esports term or stat marker must
    # co-occur so non-gaming contexts involving the same handle do not trip.
    if has_player and not (has_domain or has_stat):
        return False
    return True


def is_esports_prop_evidence(
    text: str,
    source_context: str = "",
    *,
    topic: str = "",
    strict_player_match: bool = False,
) -> bool:
    raw = f"{text or ''} {source_context or ''}"
    lowered = raw.lower()
    tokens = tokenize(raw)
    topic_subdomain = esports_subdomain_of(topic)
    text_subdomain = esports_subdomain_of(raw)
    topic_players = extract_esports_players(topic, subdomain=topic_subdomain)
    text_players = extract_esports_players(raw, subdomain=topic_subdomain)
    topic_has_stat = has_player_prop_stat_marker(topic)
    text_has_stat = has_player_prop_stat_marker(raw)

    if lowered.lstrip().startswith("@"):
        return False
    if topic_subdomain and text_subdomain and text_subdomain != topic_subdomain:
        return False
    if topic_players and not (topic_players & text_players):
        return False
    if topic_has_stat and not text_has_stat:
        return False
    if strict_player_match and not text_players:
        return False
    if tokens & ESPORTS_PROP_REJECT_TERMS:
        high_signal = ESPORTS_HIGH_SIGNAL_TERMS | {"kill", "kills", "headshot", "headshots", "adr", "solo"}
        if not (tokens & high_signal and text_players):
            return False
    if tokens & ESPORTS_NOISE_TERMS and not text_players:
        return False
    if topic_players and text_players:
        return True
    if strict_player_match:
        return False
    return bool((tokens & ESPORTS_HIGH_SIGNAL_TERMS) and has_player_prop_stat_marker(raw))


def is_esports_rationale_evidence(
    text: str,
    source_context: str = "",
    *,
    exact_match: bool = False,
    topic: str = "",
) -> bool:
    tokens = tokenize(f"{text or ''} {source_context or ''}")
    lowered = f"{text or ''} {source_context or ''}".lower()

    players = extract_esports_players(topic) if topic else set()
    has_player_match = False
    if players:
        for p in players:
            if p in lowered:
                has_player_match = True
                break

    if lowered.lstrip().startswith("@"):
        return False
    if any(phrase in lowered for phrase in ("watch live", "live now", "tune in", "match listing", "upcoming matches")):
        return False
    if tokens & ESPORTS_NOISE_TERMS and not (tokens & (ESPORTS_HIGH_SIGNAL_TERMS - {"update"})) and not has_player_match:
        return False
    if tokens & ESPORTS_LOW_SIGNAL_TERMS and not has_player_match:
        if not (tokens & (ESPORTS_HIGH_SIGNAL_TERMS - {"map", "pool", "patch", "update"})):
            return False
    if {"score", "scores", "scored"} & tokens and not (tokens & (ESPORTS_HIGH_SIGNAL_TERMS - {"map", "pool"})) and not has_player_match:
        return False
    if exact_match and not (tokens & ESPORTS_HIGH_SIGNAL_TERMS) and not has_player_match:
        return False
    return has_player_match or bool(tokens & ESPORTS_HIGH_SIGNAL_TERMS)


def esports_entity_tokens(text: str) -> set[str]:
    lowered = (text or "").lower()
    sides = re.split(r"\bvs\.?\b|\bat\b", lowered)
    collected: set[str] = set()
    for side in sides[:2]:
        side_tokens = {
            token
            for token in re.sub(r"[^a-z0-9\s-]", " ", side).split()
            if token and token not in ESPORTS_ENTITY_STOP and not re.fullmatch(r"bo\d", token)
        }
        collected |= side_tokens
    return collected


def classify_sports_evidence(
    text: str,
    source_context: str = "",
    *,
    exact_match: bool = False,
    exact_date: bool = False,
    allow_market_context: bool = False,
) -> str:
    """Classify sports evidence quality for forecast rationale selection."""
    raw = f"{text or ''} {source_context or ''}"
    lowered = raw.lower()
    tokens = tokenize(raw)
    if "check" in tokens and "out" in tokens:
        tokens.discard("out")

    status_terms = {
        "injury", "injuries", "injured", "ruled", "questionable", "doubtful",
        "probable", "available", "inactive", "scratch", "scratched",
        "status", "report", "listed",
    }
    rest_terms = {
        "rest", "resting", "minutes", "restriction", "restricted",
        "back-to-back", "b2b",
    }
    lineup_terms = {"lineup", "lineups", "starter", "starters", "starting"}
    lineup_status_terms = status_terms | {"confirmed", "announced", "expected"}
    incentive_terms = {
        "elimination", "eliminated", "clinch", "clinched",
        "tank", "tanking",
    }
    market_terms = SPORTS_MARKET_CONTEXT_TERMS | {"movement", "moved", "steam"}
    line_movement_terms = {"movement", "moved", "steam", "shift", "shifted", "shortened", "drifted"}
    ticket_terms = {"ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat", "fs", "wtb"}
    media_guide_phrases = (
        "how to watch",
        "live stream",
        "stream it online",
        "tv, live stream",
        "tv and stream",
        "tv channel",
    )
    sportsbook_copy_phrases = (
        "ats angle",
        "point spread",
        "moneyline",
        "over/under",
        "market & probabilities",
        "market and probabilities",
        "best bets",
        "predictions for all games",
    )
    recap_phrases = (
        "statement win",
        "dominant showing",
        "roll past",
        "rolled past",
        "take down",
        "took down",
        "not backing down",
        "lived up to the hype",
    )
    low_signal_context_terms = {"nbapicksai", "sportsbook", "sportsbetting"}

    has_status = bool(tokens & status_terms)
    has_rest = bool(tokens & rest_terms)
    has_lineup_status = bool(tokens & lineup_terms and tokens & lineup_status_terms)
    has_incentive = bool(tokens & incentive_terms)
    if {"playoff", "playoffs"} & tokens and tokens & {"elimination", "eliminated", "clinch", "clinched"}:
        has_incentive = True
    if "must" in tokens and "win" in tokens and (
        tokens & {"elimination", "eliminated", "clinch", "clinched"}
    ):
        has_incentive = True
    has_high_signal = has_status or has_rest or has_lineup_status or has_incentive

    if source_context and tokenize(source_context) & low_signal_context_terms and not has_high_signal:
        return "low_signal"
    if any(phrase in lowered for phrase in media_guide_phrases) and not has_high_signal:
        return "low_signal"
    if any(phrase in lowered for phrase in sportsbook_copy_phrases) and not has_high_signal:
        return "low_signal"
    if any(phrase in lowered for phrase in recap_phrases) and not (has_status or has_rest or has_lineup_status):
        return "low_signal"
    if tokens & ticket_terms and not (has_rest or has_lineup_status or has_incentive or (tokens & (status_terms - {"available"}))):
        return "low_signal"
    if SPORTS_LOW_SIGNAL_TERMS & tokens and not has_high_signal:
        return "low_signal"
    if (SPORTS_REJECT_TERMS & tokens or {"game", "thread"} <= tokens or {"live", "score"} <= tokens) and not has_high_signal:
        return "reject"
    if has_high_signal and exact_match:
        return "high_signal"
    if allow_market_context and exact_match and exact_date and tokens & market_terms and (
        tokens & line_movement_terms or not (tokens & SPORTS_GENERIC_PREVIEW_TERMS)
    ):
        return "market_context"
    if SPORTS_GENERIC_PREVIEW_TERMS & tokens:
        return "generic_preview"
    if tokens & market_terms:
        return "market_context" if allow_market_context and exact_match and exact_date else "generic_preview"
    return "reject"


def is_sports_rationale_evidence(
    text: str,
    source_context: str = "",
    *,
    exact_match: bool = False,
    exact_date: bool = False,
    allow_market_context: bool = False,
) -> bool:
    category = classify_sports_evidence(
        text,
        source_context,
        exact_match=exact_match,
        exact_date=exact_date,
        allow_market_context=allow_market_context,
    )
    return category in {"high_signal", "market_context"}
