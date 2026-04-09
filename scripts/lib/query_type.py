"""Query type detection for source selection and scoring adjustments."""

import re
from typing import Literal

QueryType = Literal["product", "concept", "opinion", "how_to", "comparison", "breaking_news", "prediction"]

# Pattern-based classification (no LLM, no external deps)
_PRODUCT_PATTERNS = re.compile(
    r"\b(price|pricing|cost|buy|purchase|deal|discount|subscription|plan|tier|free tier|alternative|prompt|prompts|prompting|template|templates)\b", re.I
)
_CONCEPT_PATTERNS = re.compile(
    r"\b(what is|what are|explain|definition|how does|how do|overview|introduction|guide to|primer)\b", re.I
)
_OPINION_PATTERNS = re.compile(
    r"\b(worth it|thoughts on|opinion|review|experience with|recommend|should i|pros and cons|good or bad)\b", re.I
)
_HOWTO_PATTERNS = re.compile(
    r"\b(how to|tutorial|step by step|setup|install|configure|deploy|migrate|implement|build a|create a|prompting|prompts?|best practices|tips|examples|animation|animations|video workflow|render pipeline)\b",
    re.I,
)
_COMPARISON_PATTERNS = re.compile(
    r"\b(vs\.?|versus|compared to|comparison|better than|difference between|switch from)\b", re.I
)
_BREAKING_PATTERNS = re.compile(
    r"\b(latest|breaking|just announced|launched|released|new|update|news|happened|today|this week)\b", re.I
)
_PREDICTION_PATTERNS = re.compile(
    r"\b("
    r"predict|prediction|forecast|forecasting|odds|line|spread|moneyline|implied probability|probability|"
    r"chance|likely|likelihood|win probability|cover|over/under|over under|favorite|underdog|"
    r"election|primary|ballot|polls?|outcome|result|bet on|market for|polymarket|kalshi|"
    r"storm|rain|snow|temperature|hurricane|tornado|landfall|playoffs?|finals?|matchup|game|tonight|"
    r"fed|inflation|cpi|jobs report|gdp|recession|rate cut|rate hike|earnings|approval rating"
    r")\b",
    re.I,
)
_FORECASTABLE_DOMAIN_PATTERNS = re.compile(
    r"\b("
    r"nba|nfl|mlb|nhl|wnba|ncaa|soccer|football|baseball|basketball|tennis|golf|ufc|mma|boxing|"
    r"weather|storm|rain|snow|wind|temperature|hurricane|tornado|heatwave|wildfire|"
    r"election|senate|house|president|governor|polling|approval|"
    r"stocks?|stock market|s&p|nasdaq|bitcoin|btc|eth|crypto|economy|inflation|cpi|jobs|gdp|fed|rates?"
    r")\b",
    re.I,
)
_OUTCOME_PHRASE_PATTERNS = re.compile(
    r"\b("
    r"who wins?|who will win|will .+ win|does .+ win|beats? .+|make the playoffs|miss the playoffs|"
    r"landfall|passes?|fails?|approved?|signs?|cuts?|hikes?|hits? \d+|above \d+|below \d+"
    r")\b",
    re.I,
)


def detect_query_type(topic: str) -> QueryType:
    """Classify a query into a type using pattern matching.

    Returns the first match in priority order:
    comparison > how_to > product > opinion > prediction > concept > breaking_news.
    """
    # Most specific first
    if _COMPARISON_PATTERNS.search(topic):
        if _PREDICTION_PATTERNS.search(topic) or _FORECASTABLE_DOMAIN_PATTERNS.search(topic) or _OUTCOME_PHRASE_PATTERNS.search(topic):
            return "prediction"
        return "comparison"
    if _HOWTO_PATTERNS.search(topic):
        return "how_to"
    if _PRODUCT_PATTERNS.search(topic):
        return "product"
    if _OPINION_PATTERNS.search(topic):
        return "opinion"
    if _PREDICTION_PATTERNS.search(topic) or _FORECASTABLE_DOMAIN_PATTERNS.search(topic) or _OUTCOME_PHRASE_PATTERNS.search(topic):
        return "prediction"
    if _CONCEPT_PATTERNS.search(topic):
        return "concept"
    if _BREAKING_PATTERNS.search(topic):
        return "breaking_news"

    # Default to forecast mode for ambiguous but plausibly forecastable requests.
    if _FORECASTABLE_DOMAIN_PATTERNS.search(topic):
        return "prediction"

    return "breaking_news"


# Source tiering by query type.
# Tier 1: always run. Tier 2: run if available. Tier 3: opt-in only.
# Sources not listed are implicitly tier 3 (opt-in).
SOURCE_TIERS = {
    "product":       {"tier1": {"reddit", "x", "web"},        "tier2": {"hn", "tiktok", "youtube"}},
    "concept":       {"tier1": {"reddit", "hn", "web"},        "tier2": {"x", "youtube"}},
    "opinion":       {"tier1": {"x", "reddit"},                "tier2": {"bluesky", "hn", "web"}},
    "how_to":        {"tier1": {"reddit", "hn", "web"},        "tier2": {"x", "youtube"}},
    "comparison":    {"tier1": {"reddit", "x", "hn"},          "tier2": {"web", "youtube"}},
    "breaking_news": {"tier1": {"x", "reddit", "web", "hn"},   "tier2": {"bluesky", "truthsocial", "youtube"}},
    "prediction":    {"tier1": {"polymarket", "kalshi", "x", "reddit", "web"},   "tier2": {"hn", "bluesky"}},
}

# WebSearch penalty adjustment by query type.
# Points subtracted from websearch score (0-100 scale). 0 = no penalty, 15 = full penalty.
# Concept/how_to queries benefit from authoritative web sources.
WEBSEARCH_PENALTY_BY_TYPE = {
    "product": 15,        # default: social discussion > blog posts
    "concept": 0,         # web docs are the best source
    "opinion": 15,        # social discussion > blog posts
    "how_to": 5,          # tutorials on web are valuable
    "comparison": 10,     # mix of social and web
    "breaking_news": 10,  # news sites are valuable
    "prediction": 8,      # web still matters as explanatory evidence
}

# Tiebreaker priority overrides by query type.
# Maps source type name to priority (lower = higher priority).
TIEBREAKER_BY_TYPE = {
    "product":       {"reddit": 0, "x": 1, "web": 2, "hn": 3, "tiktok": 4, "youtube": 5, "instagram": 6, "polymarket": 7},
    "concept":       {"hn": 0, "reddit": 1, "web": 2, "x": 3, "youtube": 4, "tiktok": 5, "instagram": 6, "polymarket": 7},
    "opinion":       {"x": 0, "reddit": 1, "bluesky": 2, "hn": 3, "web": 4, "youtube": 5, "tiktok": 6, "polymarket": 7},
    "how_to":        {"reddit": 0, "hn": 1, "web": 2, "x": 3, "youtube": 4, "tiktok": 5, "instagram": 6, "polymarket": 7},
    "comparison":    {"reddit": 0, "x": 1, "hn": 2, "web": 3, "youtube": 4, "tiktok": 5, "instagram": 6, "polymarket": 7},
    "breaking_news": {"x": 0, "reddit": 1, "web": 2, "hn": 3, "bluesky": 4, "tiktok": 5, "youtube": 6, "polymarket": 7},
    "prediction":    {"kalshi": 0, "polymarket": 1, "x": 2, "reddit": 3, "web": 4, "hn": 5, "bluesky": 6, "youtube": 7, "tiktok": 8, "instagram": 9},
}


def is_source_enabled(source: str, query_type: QueryType, explicitly_requested: bool = False) -> bool:
    """Check if a source should run for a given query type.

    Tier 1 and Tier 2 sources are enabled. Tier 3 (unlisted) sources only run
    if explicitly requested via --search flag. Truth Social is always opt-in.
    """
    if source == "truthsocial":
        return explicitly_requested

    if explicitly_requested:
        return True

    tiers = SOURCE_TIERS.get(query_type, SOURCE_TIERS["breaking_news"])
    return source in tiers["tier1"] or source in tiers["tier2"]
