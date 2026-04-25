"""Market contract type heuristics shared by forecasts and watchlists."""

from __future__ import annotations

import re
from typing import Literal

from . import evidence_quality as eq

MarketType = Literal[
    "game_outcome",
    "player_prop",
    "team_prop",
    "futures",
    "esports_prop",
    "esports_title",
    "crypto_daily",
    "threshold",
    "macro_binary",
    "weather_binary",
    "unknown",
]

_MATCHUP_MARKERS = (" vs. ", " vs ", " at ")
_PLAYER_PROP_MARKERS = (
    " o/u ",
    " over/under ",
    " points o/u",
    " rebounds o/u",
    " assists o/u",
    " threes o/u",
    " steals o/u",
    " blocks o/u",
    " pts o/u",
    " ast o/u",
    " reb o/u",
)
_PLAYER_PROP_STATS = {
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "threes",
    "turnovers",
    "pra",
    "pts",
    "reb",
    "ast",
}
_GAME_OUTCOME_MARKERS = {"moneyline", "winner", "win the game", "wins the game", "to win"}
_TEAM_PROP_MARKERS = {"team total", "total points", "spread", "handicap"}
_FUTURES_MARKERS = {
    "champion",
    "championship",
    "conference",
    "finals",
    "playoffs",
    "mvp",
    "rookie of the year",
    "cy young",
    "tournament",
}
_THRESHOLD_MARKERS = {
    "above",
    "below",
    "reach",
    "hit",
    "exceed",
    "over $",
    "under $",
    "price will",
    "price on",
    "price range",
    "what price",
    "between $",
}
_MACRO_MARKERS = {
    "fed",
    "fomc",
    "rates",
    "rate",
    "cpi",
    "inflation",
    "recession",
    "gdp",
    "jobs",
    "unemployment",
}
_WEATHER_MARKERS = {
    "rain",
    "snow",
    "storm",
    "weather",
    "temperature",
    "precipitation",
    "hurricane",
    "tornado",
}
_CRYPTO_MARKERS = {"bitcoin", "btc", "ethereum", "eth", "solana", "xrp", "crypto"}
_KALSHI_SPORTS_MARKET_RE = re.compile(r"/markets/KX(?:NBA|NFL|MLB|NHL)[A-Z]*", re.IGNORECASE)
_KALSHI_SPORTS_SERIES_RE = re.compile(r"/markets/KX(?:NBA|NFL|MLB|NHL)(?:SERIES|PLAYOFF|FINAL|FINALS)", re.IGNORECASE)
_KALSHI_MACRO_MARKET_RE = re.compile(r"/markets/KX(?:FED|FEDDECISION|CPI|JOBS)[A-Z0-9.-]*", re.IGNORECASE)
_ESPORTS_TERMS = {
    "counter", "strike", "counterstrike", "counter-strike", "cs2", "csgo",
    "valorant", "dota", "esports", "lol",
}
_ESPORTS_MATCH_MARKERS = {"bo1", "bo2", "bo3", "bo5", "winner", "match"}
_ESPORTS_PROP_MARKERS = {
    "map 1", "map 2", "map 3", "map winner", "total maps", "odd/even total kills",
    "total kills", "kills", "handicap", "correct score",
    # Player-level prop markers (v1.0.55 groundwork, primarily CS2/Valorant/LoL)
    "headshot", "headshots", "adr", "first kill", "first blood",
    "1v1", "clutch", "entry kill", "mvp", "bomb plant", "pistol round",
    "assists", "deaths", "kd", "k/d", "rating",
}
_ESPORTS_TITLE_MARKERS = {"map pool", "major winner", "tournament winner", "cache", "add cache", "champion"}


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s-]", " ", (text or "").lower()).split())


def _has_matchup(text: str) -> bool:
    text_lower = (text or "").lower()
    return any(marker in text_lower for marker in _MATCHUP_MARKERS)


def _looks_like_kalshi_sports_game_contract(text_lower: str, url: str) -> bool:
    if not _KALSHI_SPORTS_MARKET_RE.search(url or ""):
        return False
    if "winner" not in text_lower:
        return False
    return bool(("game " in text_lower and " at " in text_lower) or _has_matchup(text_lower))


def _looks_like_kalshi_sports_series_contract(text_lower: str, url: str) -> bool:
    if not _KALSHI_SPORTS_MARKET_RE.search(url or ""):
        return False
    if "series" in text_lower and "winner" in text_lower:
        return True
    return bool(_KALSHI_SPORTS_SERIES_RE.search(url or "") and "winner" in text_lower)


def classify_market(title: str = "", question: str = "", url: str = "") -> MarketType:
    """Classify what the displayed contract probability represents."""
    text = f"{title} {question} {url}".strip()
    text_lower = text.lower()
    tokens = _tokens(text_lower)

    if any(marker in text_lower for marker in _PLAYER_PROP_MARKERS):
        return "player_prop"
    if ":" in question and (tokens & _PLAYER_PROP_STATS):
        return "player_prop"

    if _looks_like_kalshi_sports_series_contract(text_lower, url):
        return "futures"

    if _looks_like_kalshi_sports_game_contract(text_lower, url):
        return "game_outcome"

    if _KALSHI_MACRO_MARKET_RE.search(url or ""):
        return "macro_binary"

    if any(marker in text_lower for marker in _ESPORTS_PROP_MARKERS):
        return "esports_prop"
    if any(marker in text_lower for marker in _ESPORTS_TITLE_MARKERS) and (
        tokens & _ESPORTS_TERMS
        or any(marker in text_lower for marker in ("map pool", "cache", "add cache"))
    ):
        return "esports_title"
    if (tokens & _ESPORTS_TERMS) and _has_matchup(text_lower):
        if any(marker in text_lower for marker in _ESPORTS_MATCH_MARKERS):
            return "game_outcome"
        if re.search(r"\(bo[1-5]\)", text_lower):
            return "game_outcome"

    if any(marker in text_lower for marker in _FUTURES_MARKERS):
        return "futures"

    if any(marker in text_lower for marker in _TEAM_PROP_MARKERS):
        return "team_prop"

    if _has_matchup(text_lower) and (tokens & eq.SPORTS_TEAM_TOKENS):
        if any(marker in text_lower for marker in _GAME_OUTCOME_MARKERS):
            return "game_outcome"
        if ":" not in question and not (tokens & _PLAYER_PROP_STATS):
            return "game_outcome"
        return "player_prop"

    if _has_matchup(text_lower) and re.search(r"/event/(nba|nfl|mlb|nhl)-", text_lower):
        if ":" not in question and not (tokens & _PLAYER_PROP_STATS):
            return "game_outcome"

    if (tokens & eq.SPORTS_TEAM_TOKENS) and any(marker in text_lower for marker in _GAME_OUTCOME_MARKERS):
        return "game_outcome"

    if any(marker in text_lower for marker in _THRESHOLD_MARKERS):
        return "threshold"
    if "up or down" in text_lower and (tokens & _CRYPTO_MARKERS):
        return "crypto_daily"
    if tokens & _WEATHER_MARKERS:
        return "weather_binary"
    if tokens & _MACRO_MARKERS:
        return "macro_binary"

    return "unknown"


def is_direct_game_outcome(title: str = "", question: str = "", url: str = "") -> bool:
    return classify_market(title, question, url) == "game_outcome"
