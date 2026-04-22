"""One-shot market discovery and ranking for market-watchlist prompts."""

import math
import re
from datetime import date, timedelta
from typing import Optional

from . import dates, evidence_fusion, evidence_quality as eq, market_types, paper_bundles, schema


_WATCHLIST_PHRASES = re.compile(
    r"\b("
    r"markets?\s+to\s+watch|best|recommend|market\s+opportunit(?:y|ies)|"
    r"market\s+picks?|biggest\s+market\s+moves?|interesting|right\s+now|today|this\s+week|"
    r"polymarket|kalshi|prediction\s+markets?"
    r")\b",
    re.I,
)

_STOPWORDS = {
    "the", "and", "for", "with", "around", "right", "now", "today", "tonight",
    "tomorrow", "this", "week", "markets", "market", "watch", "best", "recommend",
    "prediction", "polymarket", "kalshi", "to", "on", "of", "in", "by", "a", "an",
}

_DOMAIN_SEEDS = {
    "nba": ["NBA", "NBA games today"],
    "sports": ["NBA", "NFL", "MLB", "NHL"],
    "esports": ["counter strike", "valorant", "lol", "esports today"],
    "macro": ["Fed rates", "inflation", "recession", "CPI", "jobs report"],
    "crypto": ["Bitcoin", "Ethereum", "crypto"],
    "weather": ["weather", "rain", "storm"],
    "elections": ["election", "approval", "senate", "house"],
}

_CATALYST_TERMS = {
    "injury", "lineup", "rest", "playoff", "seed", "fed", "fomc", "cpi",
    "inflation", "jobs", "gdp", "recession", "approval", "poll", "bitcoin",
    "ethereum", "etf", "weather", "storm", "rain", "forecast", "warning",
    "earnings", "court", "ruling", "deadline", "vote", "tariff", "data",
    "release", "rates", "cut", "hike",
}
_GENERIC_MARKET_TOKENS = {
    "nba", "nfl", "mlb", "nhl", "wnba", "sports", "game", "games", "winner",
    "champion", "championship", "conference", "playoffs", "playoff", "year",
    "april", "today", "tomorrow", "price", "will",
    "https", "http", "com", "event", "www", "polymarket", "kalshi",
    "esports", "counter", "strike", "counterstrike", "counter-strike", "cs2", "csgo",
    "valorant", "dota", "league", "legends",
}
_SPORTS_CORE_SIGNAL = {
    "injury", "injuries", "injured", "ruled", "questionable", "doubtful",
    "probable", "available", "inactive", "rest", "resting", "lineup", "lineups",
    "starter", "starters", "starting", "minutes", "restriction", "restricted",
    "back-to-back", "b2b",
}
_CRYPTO_LOW_SIGNAL_TERMS = {
    "airdrop", "airdrops", "mint", "swap", "gas", "fees", "rewards", "reward",
    "claim", "token", "tokens", "giveaway",
}
_CRYPTO_SIGNAL_TERMS = {
    "price", "prices", "etf", "inflows", "outflows", "liquidation",
    "liquidations", "volatility", "support", "resistance", "breakout",
    "macro", "rates", "treasury", "dollar", "volume", "open", "interest",
    "flow", "flows", "liquidity", "repricing", "market", "markets",
}
_CRYPTO_ENTITY_TOKENS = {"bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "crypto"}
_TECH_SIGNAL_TERMS = {
    "model", "models", "benchmark", "benchmarks", "arena", "coding", "ai",
    "release", "released", "launch", "launched", "eval", "leaderboard",
    "score", "scores", "claude", "openai", "anthropic", "google", "gemini",
}
_TECH_STRONG_SIGNAL_TERMS = {
    "benchmark", "benchmarks", "arena", "release", "released", "launch",
    "launched", "eval", "evals", "leaderboard", "score", "scores",
    "rank", "ranked", "ranking", "rankings", "wins", "won",
}
_TECH_LOW_SIGNAL_TERMS = {
    "directory", "directories", "bridge", "bridges", "tool", "tools", "workflow",
    "workflows", "free", "tier", "tiers", "feedback", "welcome", "list",
    "lists", "stack", "stacks", "mcp", "instance", "instance", "directory",
}
_TECH_GENERIC_TOKENS = {
    "ai", "model", "models", "coding", "code", "arena", "score", "scores",
    "benchmark", "benchmarks", "best", "company", "april", "end",
}
_TECH_ENTITY_ALIASES = {
    "anthropic": {"anthropic", "claude", "opus"},
    "openai": {"openai", "gpt", "chatgpt"},
    "google": {"google", "gemini", "deepmind"},
    "deepseek": {"deepseek"},
    "alibaba": {"alibaba", "qwen"},
    "zhipu": {"zhipu", "glm"},
    "moonshot": {"moonshot", "kimi"},
}
_TECH_ENTITY_TOKENS = set().union(*_TECH_ENTITY_ALIASES.values())
_MARKET_WATCHLIST_SPAM_PHRASES = {
    "daily winners", "stocks are on a tear", "need this in your feed",
    "signal room", "vip", "pump group", "free picks", "guaranteed",
    "most popular bets", "stop missing out", "keep cashing", "keeps cashing",
    "all my picks", "dm for picks",
}
_MARKET_WATCHLIST_SPAM_TOKENS = {
    "airdrop", "airdrops", "giveaway", "rewards", "reward", "claim",
    "mint", "lock", "locks", "parlay", "picks", "pick", "tail", "sprinkle",
    "vip", "signals", "promo", "promote", "winners", "winner", "cashing",
    "bets", "bet",
}
_SPORTS_PROMO_TOKENS = {
    "vip", "parlay", "parlays", "lock", "locks", "tail", "sprinkle", "cashing",
    "guaranteed", "promo", "picks", "pick", "bets", "bet", "winners", "winner",
}
_SPORTSBOOK_TOKENS = {"sportsbook", "sportsbooks", "draftkings", "fanduel", "betting"}
_SPORTS_RECAP_TOKENS = {"highlight", "highlights", "recap", "recaps"}
_ESPORTS_TITLE_TERMS = {"map pool", "cache", "major winner", "tournament winner", "champion"}
_ESPORTS_PROP_TERMS = {"props", "prop", "map", "maps", "kills", "odd", "even", "handicap", "total maps"}
_ESPORTS_SUBDOMAINS = {
    "cs2": {"counter", "strike", "counterstrike", "counter-strike", "cs2", "csgo"},
    "valorant": {"valorant", "vct"},
    "lol": {"lol", "league", "legends", "lec", "lcs"},
    "dota": {"dota"},
}

_META_MARKET_TERMS = {
    "law banning", "ban sports prediction", "sports prediction markets enacted",
    "prediction markets", "market regulation", "banning sports",
}

_NBA_SERIES_PROMPT_TERMS = {
    "series", "playoff series", "who will win series", "win series",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.sub(r"[^\w\s-]", " ", (text or "").lower()).split()
        if len(token) > 2 and token not in _STOPWORDS
    }


def _bump_debug_counter(report: schema.Report, key: str, amount: int = 1) -> None:
    debug = report.evidence_fusion_stats.setdefault("debug_counters", {})
    debug[key] = int(debug.get(key, 0) or 0) + amount


def _domain(topic: str) -> str:
    tokens = _tokens(topic)
    lowered = (topic or "").lower()
    if "nba" in tokens:
        return "nba"
    if eq.is_esports_query(lowered):
        return "esports"
    if tokens & {"nfl", "mlb", "nhl", "wnba", "sports", "football", "basketball", "baseball", "hockey"}:
        return "sports"
    if tokens & {"bitcoin", "btc", "ethereum", "eth", "crypto"}:
        return "crypto"
    if eq.is_weather_query(lowered):
        return "weather"
    if eq.is_macro_query(lowered) or tokens & {"macro", "fed", "rates", "inflation", "recession", "cpi"}:
        return "macro"
    if tokens & {"election", "elections", "approval", "senate", "house", "president", "governor"}:
        return "elections"
    if tokens & {"ai", "coding", "model", "models", "anthropic", "openai", "claude", "gemini", "deepseek", "alibaba", "qwen"}:
        return "tech"
    return "broad"


def search_topics(topic: str) -> list[str]:
    """Build topic-scoped market search seeds for watchlist mode."""
    domain = _domain(topic)
    seeds = list(_DOMAIN_SEEDS.get(domain, []))
    cleaned = _WATCHLIST_PHRASES.sub(" ", topic or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:")
    if cleaned and cleaned.lower() not in {seed.lower() for seed in seeds}:
        seeds.insert(0, cleaned)
    if not seeds:
        seeds = ["Fed rates", "NBA", "Bitcoin", "inflation", "election"]
    # Keep the quick path bounded.
    result = []
    seen = set()
    for seed in seeds:
        key = seed.lower()
        if key and key not in seen:
            result.append(seed)
            seen.add(key)
    return result[:5]


def _engagement_values(eng: Optional[schema.Engagement]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if not eng:
        return None, None, None
    return eng.volume, eng.liquidity, eng.open_interest


def _market_probability(item) -> tuple[str, Optional[float]]:
    if isinstance(item, schema.KalshiItem):
        return "Yes", item.implied_probability if item.implied_probability is not None else item.current_probability
    if getattr(item, "implied_probability", None) is not None:
        label = "Top outcome"
        if getattr(item, "outcome_prices", None):
            ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
            label = str(ordered[0][0] or label)
        return label, item.implied_probability
    if item.outcome_prices:
        ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
        label, probability = ordered[0]
        return str(label or "Top outcome"), probability
    return "Top outcome", None


def _market_text(item) -> str:
    return f"{getattr(item, 'title', '')} {getattr(item, 'question', '')} {getattr(item, 'url', '')}"


def _is_nba_watchlist_topic(topic: str) -> bool:
    return _domain(topic) == "nba"


def _is_explicit_nba_series_prompt(topic: str) -> bool:
    lowered = (topic or "").lower()
    return _is_nba_watchlist_topic(topic) and any(term in lowered for term in _NBA_SERIES_PROMPT_TERMS)


def _is_explicit_esports_prop_prompt(topic: str) -> bool:
    lowered = (topic or "").lower()
    return _domain(topic) == "esports" and any(term in lowered for term in _ESPORTS_PROP_TERMS)


def _is_explicit_esports_title_prompt(topic: str) -> bool:
    lowered = (topic or "").lower()
    return _domain(topic) == "esports" and any(term in lowered for term in _ESPORTS_TITLE_TERMS)


def _report_base_date(report: schema.Report) -> date:
    return dates.current_local_date()


def _watchlist_target_date(report: schema.Report) -> Optional[str]:
    topic_lower = (report.topic or "").lower()
    base = _report_base_date(report)
    explicit = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", report.topic or "")
    if explicit:
        return explicit.group(1)
    if "tomorrow" in topic_lower or "tomorrows" in topic_lower:
        return (base + timedelta(days=1)).isoformat()
    if "today" in topic_lower or "tonight" in topic_lower:
        return base.isoformat()
    return None


def _watchlist_date_compatible(item, target_date: Optional[str]) -> bool:
    if not target_date:
        return True
    market_text = " ".join(
        str(part) for part in (
            getattr(item, "title", ""),
            getattr(item, "question", ""),
            getattr(item, "url", ""),
            getattr(item, "ticker", ""),
            getattr(item, "event_ticker", ""),
            getattr(item, "end_date", ""),
            getattr(item, "end_datetime", ""),
        ) if part
    )
    refs = set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", market_text))
    if not refs:
        return True
    try:
        target = date.fromisoformat(target_date)
        allowed = {target.isoformat(), date.fromordinal(target.toordinal() + 1).isoformat()}
    except ValueError:
        allowed = {target_date}
    return bool(refs & allowed)


def _watchlist_exact_date_match(item, target_date: Optional[str]) -> bool:
    if not target_date:
        return True
    market_text = " ".join(
        str(part) for part in (
            getattr(item, "title", ""),
            getattr(item, "question", ""),
            getattr(item, "url", ""),
            getattr(item, "ticker", ""),
            getattr(item, "event_ticker", ""),
            getattr(item, "end_date", ""),
            getattr(item, "end_datetime", ""),
        ) if part
    )
    refs = set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", market_text))
    if not refs:
        return True
    return target_date in refs


def _watchlist_scope(report: schema.Report, item, market_type: str) -> str:
    text = _market_text(item).lower()
    if _is_nba_watchlist_topic(report.topic):
        if market_type == "game_outcome":
            return "game"
        if market_type == "futures" and "series" in text:
            return "series"
    return ""


def _is_esports_market_candidate(item, market_type: str) -> bool:
    text = _market_text(item).lower()
    if market_type in {"esports_prop", "esports_title"}:
        return True
    if market_type != "game_outcome":
        return False
    return bool(
        re.search(r"\bcounter[- ]strike(?:\s*2)?\b|\bcs2\b|\bcsgo\b|\bvalorant\b|\blol\b|league of legends|\bdota\b", text)
        or ("esports" in text and re.search(r"\bbo[1235]\b", text))
    )


def _same_matchup_signature(text: str) -> str:
    tokens = _tokens(text)
    teams = sorted(tokens & eq.NBA_TEAM_TOKENS)
    return "|".join(teams[:2]) if len(teams) >= 2 else ""


def _topic_relevance(topic: str, item) -> float:
    domain = _domain(topic)
    market_tokens = _tokens(_market_text(item))
    topic_tokens = _tokens(topic)
    market_lower = _market_text(item).lower()
    if not topic_tokens:
        return 0.35
    overlap = len(topic_tokens & market_tokens)
    relevance = min(1.0, overlap / max(2, min(len(topic_tokens), 6)))
    if domain == "nba":
        if "nba" in market_lower or eq.NBA_TEAM_TOKENS & market_tokens:
            relevance += 0.45
        else:
            relevance -= 0.35
    elif domain == "sports":
        if market_tokens & (eq.SPORTS_TEAM_TOKENS | {"nba", "nfl", "mlb", "nhl", "wnba"}):
            relevance += 0.35
    elif domain == "macro":
        if market_tokens & (eq.MACRO_SIGNAL_TERMS | {"macro"}):
            relevance += 0.35
    elif domain == "crypto":
        if market_tokens & {"bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "xrp"}:
            relevance += 0.35
    elif domain == "weather":
        if market_tokens & eq.WEATHER_QUERY_TERMS:
            relevance += 0.30
    elif domain == "elections":
        if market_tokens & {"election", "elections", "approval", "senate", "house", "president", "governor"}:
            relevance += 0.35
    elif domain == "tech":
        if market_tokens & (_TECH_SIGNAL_TERMS | _TECH_ENTITY_TOKENS):
            relevance += 0.35
    elif domain == "esports":
        if market_tokens & eq.ESPORTS_TERMS:
            relevance += 0.35
        else:
            relevance -= 0.35
        if (
            eq.is_cs2_query(topic)
            and not _is_explicit_esports_prop_prompt(topic)
            and not _is_explicit_esports_title_prompt(topic)
        ):
            if eq.is_cs2_market_text(market_lower):
                relevance += 0.35
            else:
                relevance -= 0.45
    return max(0.0, min(1.0, relevance))


def _is_bad_candidate(topic: str, item) -> bool:
    market_lower = _market_text(item).lower()
    domain = _domain(topic)
    market_type = _candidate_market_type(item)
    end_date = getattr(item, "end_date", None)
    if end_date:
        try:
            if date.fromisoformat(str(end_date)[:10]) < date.today():
                return True
        except ValueError:
            pass
    if domain in {"sports", "nba"} and any(term in market_lower for term in _META_MARKET_TERMS):
        return True
    if domain == "nba" and not eq.is_nba_market_text(market_lower):
        return True
    if (
        domain == "esports"
        and not _is_explicit_esports_prop_prompt(topic)
        and not _is_explicit_esports_title_prompt(topic)
        and not _is_esports_market_candidate(item, market_type)
    ):
        return True
    if (
        domain == "esports"
        and eq.is_cs2_query(topic)
        and not _is_explicit_esports_prop_prompt(topic)
        and not _is_explicit_esports_title_prompt(topic)
        and not eq.is_cs2_market_text(market_lower)
    ):
        return True
    if "parlay" in market_lower or "combo" in market_lower:
        return True
    return False


def _candidate_market_type(item) -> str:
    current = getattr(item, "market_type", "")
    if current and current != "unknown":
        return current
    return market_types.classify_market(
        getattr(item, "title", ""),
        getattr(item, "question", ""),
        getattr(item, "url", ""),
    )


def _market_quality(volume: Optional[float], liquidity: Optional[float], open_interest: Optional[float]) -> float:
    vol = min(1.0, math.log1p(max(volume or 0.0, 0.0)) / math.log1p(2_000_000))
    liq = min(1.0, math.log1p(max(liquidity or 0.0, 0.0)) / math.log1p(500_000))
    oi = min(1.0, math.log1p(max(open_interest or 0.0, 0.0)) / math.log1p(500_000))
    return max(vol * 0.55 + liq * 0.30 + oi * 0.15, vol * 0.65 + liq * 0.35)


def _depth_values(item) -> tuple[Optional[float], Optional[float], Optional[float]]:
    volume, liquidity, open_interest = _engagement_values(getattr(item, "engagement", None))
    volume = getattr(item, "volume_24h", None) if getattr(item, "volume_24h", None) is not None else volume
    return volume, liquidity, open_interest


def _movement_score(movement_pct: Optional[float]) -> float:
    if movement_pct is None:
        return 0.0
    return min(1.0, abs(movement_pct) / 20.0)


def _signal_quality(item, volume: Optional[float], liquidity: Optional[float], open_interest: Optional[float]) -> float:
    provided = getattr(item, "market_signal_quality", None)
    if provided is not None:
        return max(0.0, min(1.0, provided))
    return _market_quality(volume, liquidity, open_interest)


def _spread_score(spread: Optional[float]) -> float:
    if spread is None:
        return 0.25
    return max(0.0, min(1.0, 1.0 - spread / 0.20))


def _near_certain_penalty(probability: Optional[float], movement: float, signal_quality: float, market_type: str = "unknown") -> float:
    if probability is None:
        return 0.0
    if 0.02 < probability < 0.98:
        return 0.0
    if market_type == "threshold":
        if movement >= 0.35 and signal_quality >= 0.70:
            return 0.10
        return 0.35
    if movement >= 0.35 or signal_quality >= 0.65:
        return 0.0
    return 0.18


def _source_text(item) -> str:
    if isinstance(item, schema.XItem):
        return f"{item.text} {item.why_relevant}".strip()
    if isinstance(item, schema.RedditItem):
        comment_excerpts = " ".join(comment.excerpt for comment in (item.top_comments or [])[:2] if getattr(comment, "excerpt", ""))
        return f"{item.title} r/{item.subreddit} {' '.join(item.comment_insights[:3])} {comment_excerpts} {item.why_relevant}".strip()
    if isinstance(item, schema.WebSearchItem):
        return f"{item.title} {item.snippet} {item.source_domain} {item.why_relevant}"
    if isinstance(item, schema.HackerNewsItem):
        return item.title
    return getattr(item, "title", "") or getattr(item, "text", "")


def _primary_source_text(item) -> str:
    if isinstance(item, schema.XItem):
        return item.text
    if isinstance(item, schema.RedditItem):
        comment_excerpts = " ".join(comment.excerpt for comment in (item.top_comments or [])[:2] if getattr(comment, "excerpt", ""))
        return f"{item.title} {' '.join(item.comment_insights[:3])} {comment_excerpts}".strip()
    if isinstance(item, schema.WebSearchItem):
        return f"{item.title} {item.snippet}".strip()
    if isinstance(item, schema.HackerNewsItem):
        return item.title
    return getattr(item, "title", "") or getattr(item, "text", "")


def _market_evidence_domain(prompt_domain: str, market_type: str, market_tokens: set[str], market_text: str) -> str:
    lowered = market_text.lower()
    if prompt_domain == "esports" or (market_tokens & eq.ESPORTS_TERMS):
        return "esports"
    if market_type in {"crypto_daily", "threshold"} and market_tokens & _CRYPTO_ENTITY_TOKENS:
        return "crypto"
    if market_tokens & _CRYPTO_ENTITY_TOKENS:
        return "crypto"
    if market_type == "weather_binary" or (market_tokens & eq.WEATHER_QUERY_TERMS and ("temperature" in lowered or "weather" in lowered)):
        return "weather"
    if market_type in {"game_outcome", "player_prop", "team_prop"}:
        return "sports"
    if " vs" in lowered or ((market_tokens & eq.SPORTS_TEAM_TOKENS) and " at " in lowered):
        return "sports"
    if market_tokens & (eq.MACRO_SIGNAL_TERMS | {"macro", "fed", "fomc", "cpi", "inflation", "recession"}):
        return "macro"
    if market_tokens & {"election", "elections", "approval", "senate", "house", "president", "governor"}:
        return "elections"
    if market_tokens & {"ai", "model", "models", "coding", "openai", "anthropic", "google", "gemini", "claude"}:
        return "tech"
    return prompt_domain


def _is_spammy_market_evidence(text: str) -> bool:
    lowered = (text or "").lower()
    tokens = _tokens(text)
    ticket_tokens = {"ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat"}
    recruiting_tokens = {"scholarship", "scholarships", "applications", "campus", "university", "college", "student"}
    if tokens & ticket_tokens and not (tokens & (eq.SPORTS_HIGH_SIGNAL_TERMS - {"available"})):
        return True
    if any(term in lowered for term in ("scholar", "rooseveltu", "applications open", "college", "university", "campus")):
        return True
    if tokens & recruiting_tokens and not (tokens & eq.ESPORTS_HIGH_SIGNAL_TERMS):
        return True
    if any(phrase in lowered for phrase in _MARKET_WATCHLIST_SPAM_PHRASES):
        return True
    clean_sports_market_context = bool(tokens & eq.SPORTS_MARKET_CONTEXT_TERMS and tokens & (eq.SPORTS_TEAM_TOKENS | {"nba", "nfl", "mlb", "nhl"}))
    if tokens & _SPORTS_RECAP_TOKENS and not (tokens & eq.SPORTS_HIGH_SIGNAL_TERMS):
        return True
    if tokens & _SPORTSBOOK_TOKENS and not clean_sports_market_context:
        return True
    if tokens & _MARKET_WATCHLIST_SPAM_TOKENS:
        useful = tokens & (_CRYPTO_SIGNAL_TERMS | eq.SPORTS_HIGH_SIGNAL_TERMS | eq.WEATHER_SIGNAL_TERMS | eq.MACRO_SIGNAL_TERMS | _TECH_SIGNAL_TERMS)
        if tokens & _SPORTS_PROMO_TOKENS and not clean_sports_market_context:
            return True
        if not useful:
            return True
    return False


def _market_entity_overlap(market_tokens: set[str], evidence_tokens: set[str]) -> int:
    return len((market_tokens - _GENERIC_MARKET_TOKENS) & evidence_tokens)


def _canonical_tech_entities(text: str) -> set[str]:
    normalized_tokens = set(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())
    canonical = set()
    for name, aliases in _TECH_ENTITY_ALIASES.items():
        if normalized_tokens & aliases:
            canonical.add(name)
    return canonical


def _tech_market_entities(item, market_specific_tokens: set[str]) -> set[str]:
    market_entities = _canonical_tech_entities(" ".join(market_specific_tokens))
    outcome_label, _ = _market_probability(item)
    market_entities |= _canonical_tech_entities(outcome_label)
    return market_entities


def _is_market_specific_evidence(
    report_topic: str,
    item,
    market_type: str,
    text: str,
    context: str = "",
) -> bool:
    market_text = _market_text(item)
    market_tokens = _tokens(market_text)
    evidence_tokens = _tokens(f"{text} {context}")
    prompt_domain = _domain(report_topic)
    effective_domain = _market_evidence_domain(prompt_domain, market_type, market_tokens, market_text)

    if _is_spammy_market_evidence(text):
        return False

    market_specific_tokens = market_tokens - _GENERIC_MARKET_TOKENS
    overlap = _market_entity_overlap(market_tokens, evidence_tokens)

    if effective_domain == "crypto":
        market_crypto_tokens = market_tokens & _CRYPTO_ENTITY_TOKENS
        if market_crypto_tokens and not (market_crypto_tokens & evidence_tokens):
            return False
        return bool((evidence_tokens & _CRYPTO_ENTITY_TOKENS) and (evidence_tokens & _CRYPTO_SIGNAL_TERMS))

    if effective_domain == "weather":
        location_tokens = market_specific_tokens - eq.WEATHER_LOCATION_STOP - eq.WEATHER_QUERY_TERMS - {"highest", "temperature"}
        if location_tokens and not (location_tokens & evidence_tokens):
            return False
        return bool(evidence_tokens & eq.WEATHER_SIGNAL_TERMS)

    if effective_domain in {"sports", "nba"}:
        sports_team_overlap = len((market_tokens & eq.SPORTS_TEAM_TOKENS) & evidence_tokens)
        market_specific_overlap = len(market_specific_tokens & evidence_tokens)
        if market_tokens & eq.SPORTS_TEAM_TOKENS:
            if sports_team_overlap < 1:
                return False
        elif market_specific_overlap < 2:
            return False
        return eq.is_sports_rationale_evidence(
            text,
            context,
            exact_match=True,
            exact_date=True,
            allow_market_context=True,
        ) or bool(evidence_tokens & {"score", "scores", "clock", "period", "inning", "ejection", "ejected", "goalie", "pitcher", "delay"})

    if effective_domain == "macro":
        if overlap < 1 and not (evidence_tokens & eq.MACRO_STRONG_TERMS):
            return False
        return eq.is_macro_signal(text, market_specific_tokens or _tokens(report_topic), context)

    if effective_domain == "elections":
        if overlap < 1:
            return False
        return bool(evidence_tokens & {"poll", "polls", "approval", "vote", "election", "campaign", "primary", "debate"})

    if effective_domain == "tech":
        market_entities = _tech_market_entities(item, market_specific_tokens)
        evidence_entities = _canonical_tech_entities(f"{text} {context}")
        low_signal_tooling = bool(evidence_tokens & _TECH_LOW_SIGNAL_TERMS) and not bool(evidence_tokens & _TECH_STRONG_SIGNAL_TERMS)
        if not market_entities and len(evidence_entities) > 1:
            return False
        if market_entities and not evidence_entities:
            return False
        if market_entities and not (market_entities & evidence_entities):
            return False
        if market_entities and (evidence_entities - market_entities):
            return False
        if overlap < 1:
            return False
        if low_signal_tooling:
            return False
        return bool(evidence_tokens & _TECH_STRONG_SIGNAL_TERMS)

    if effective_domain == "esports":
        esports_entities = eq.esports_entity_tokens(market_text)
        evidence_entities = eq.esports_entity_tokens(text)
        if overlap < 1:
            return False
        if not eq.is_esports_rationale_evidence(text, context, exact_match=True):
            return False
        if esports_entities and not (esports_entities & evidence_entities):
            return False
        if tokens := _tokens(f"{text} {context}"):
            market_specific_overlap = len((market_specific_tokens - {"bo1", "bo2", "bo3", "bo5"}) & tokens)
            return market_specific_overlap >= 1
        return False

    if prompt_domain != "broad":
        if overlap < 1:
            return False
        return _is_signal_evidence(report_topic, text, context)

    return overlap >= 2 and bool(evidence_tokens & _CATALYST_TERMS)


def _is_signal_evidence(topic: str, text: str, context: str = "") -> bool:
    domain = _domain(topic)
    tokens = _tokens(f"{text} {context}")
    topic_tokens = _tokens(topic)
    if domain == "esports":
        return eq.is_esports_rationale_evidence(text, context, exact_match=True)
    if domain in {"sports", "nba"}:
        if tokens & eq.SPORTS_LOW_SIGNAL_TERMS and not (tokens & _SPORTS_CORE_SIGNAL):
            return False
        return bool((tokens & _SPORTS_CORE_SIGNAL) or (tokens & eq.SPORTS_MARKET_CONTEXT_TERMS and tokens & (eq.SPORTS_TEAM_TOKENS | {"nba", "nfl", "mlb", "nhl"})))
    if domain == "weather":
        return eq.is_weather_signal(text, topic_tokens, context, require_location=False)
    if domain == "macro":
        return eq.is_macro_signal(text, topic_tokens, context)
    if domain == "crypto":
        strong_crypto_signal = _CRYPTO_SIGNAL_TERMS - {"price", "prices", "volume", "open", "interest"}
        if tokens & _CRYPTO_LOW_SIGNAL_TERMS and not (tokens & strong_crypto_signal):
            return False
        return bool((tokens & {"bitcoin", "btc", "ethereum", "eth", "crypto", "etf"}) and (tokens & _CRYPTO_SIGNAL_TERMS))
    if domain == "elections":
        return bool(tokens & {"poll", "polls", "approval", "vote", "election", "campaign", "primary", "debate"})
    return bool(tokens & _CATALYST_TERMS)


def _evidence_for_market(report: schema.Report, item) -> tuple[float, str, list[str]]:
    market_tokens = _tokens(_market_text(item))
    domain = _domain(report.topic)
    market_specific_tokens = market_tokens - _GENERIC_MARKET_TOKENS
    market_team_tokens = market_tokens & eq.SPORTS_TEAM_TOKENS
    market_crypto_tokens = market_tokens & _CRYPTO_ENTITY_TOKENS
    market_type = _candidate_market_type(item)
    scored = []
    fused = evidence_fusion.fuse_evidence(report, _market_text(item), "market_watchlist", limit=3)
    if fused.candidate_count:
        report.evidence_fusion_stats["candidate_count"] = max(
            int(report.evidence_fusion_stats.get("candidate_count", 0) or 0),
            fused.candidate_count,
        )
        report.evidence_fusion_stats["driver_count"] = max(
            int(report.evidence_fusion_stats.get("driver_count", 0) or 0),
            len(fused.drivers),
        )
        report.evidence_fusion_stats["cluster_count"] = max(
            int(report.evidence_fusion_stats.get("cluster_count", 0) or 0),
            fused.cluster_count,
        )
    for driver in fused.drivers:
        driver_tokens = _tokens(driver.text)
        overlap = len(market_specific_tokens & driver_tokens)
        catalyst = len(driver_tokens & _CATALYST_TERMS)
        if (overlap or catalyst) and _is_market_specific_evidence(report.topic, item, market_type, driver.text):
            scored.append((driver.score + min(0.20, overlap * 0.04), driver, driver.text))
        elif overlap or catalyst:
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{domain}")

    evidence_items = list(report.x[:12]) + list(report.reddit[:10]) + list(report.web[:10]) + list(report.hackernews[:5])
    for evidence in evidence_items:
        text = _source_text(evidence)
        primary_text = _primary_source_text(evidence)
        context = getattr(evidence, "source_domain", "") or getattr(evidence, "subreddit", "")
        tokens = _tokens(primary_text)
        overlap = len(market_specific_tokens & tokens)
        catalyst = len(tokens & _CATALYST_TERMS)
        if domain in {"sports", "nba"}:
            if market_team_tokens and not (market_team_tokens & tokens):
                continue
            if not market_team_tokens and overlap < 2:
                continue
        elif domain == "crypto":
            if market_crypto_tokens and not (market_crypto_tokens & tokens):
                continue
            crypto_specific_overlap = len((market_specific_tokens - {"crypto", "cryptocurrency"}) & tokens)
            if (market_specific_tokens - {"crypto", "cryptocurrency"}) and crypto_specific_overlap < 1:
                continue
            if not market_crypto_tokens and overlap < 2:
                continue
        elif domain != "broad" and overlap < 1 and catalyst < 1:
            continue
        if overlap < 1 and catalyst < 1:
            continue
        if not _is_market_specific_evidence(report.topic, item, market_type, primary_text, context):
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{domain}")
            continue
        base_score = getattr(evidence, "score", 0) / 100.0
        scored.append((base_score + min(0.35, overlap * 0.06) + min(0.25, catalyst * 0.05), evidence, text))

    scored.sort(key=lambda row: row[0], reverse=True)
    if not scored:
        return 0.0, "Catalyst context is thin; ranking is mostly market-signal driven.", []

    best = []
    refs = []
    for _, evidence, text in scored[:2]:
        snippet = re.sub(r"\s+", " ", text).strip()
        if len(snippet) > 150:
            snippet = snippet[:150].rstrip() + "..."
        if snippet:
            best.append(snippet)
            ref_id = getattr(evidence, "id", "")
            ref_url = getattr(evidence, "url", "") or getattr(evidence, "hn_url", "")
            refs.append(f"{ref_id} {ref_url}".strip())
    return min(1.0, scored[0][0]), " | ".join(best), [ref for ref in refs if ref]


def _cross_market_note(item, other_items: list) -> tuple[float, str]:
    item_tokens = _tokens(_market_text(item))
    label, probability = _market_probability(item)
    if probability is None:
        return 0.0, ""
    item_numbers = _numeric_tokens(_market_text(item))
    sports_item_tokens = item_tokens & eq.SPORTS_TEAM_TOKENS
    best = None
    for other in other_items:
        other_tokens = _tokens(_market_text(other))
        common = len(item_tokens & other_tokens)
        if common < 3:
            continue
        other_numbers = _numeric_tokens(_market_text(other))
        if (item_numbers or other_numbers) and not (item_numbers & other_numbers):
            continue
        sports_other_tokens = other_tokens & eq.SPORTS_TEAM_TOKENS
        if sports_item_tokens or sports_other_tokens:
            if len(sports_item_tokens & sports_other_tokens) < min(2, len(sports_item_tokens | sports_other_tokens)):
                continue
        _, other_probability = _market_probability(other)
        if other_probability is None:
            continue
        score = common / max(1, len(item_tokens | other_tokens))
        if score < 0.30:
            continue
        if not best or score > best[0]:
            best = (score, other, other_probability)
    if not best:
        return 0.0, ""
    spread = abs(probability - best[2]) * 100
    if spread < 5:
        return 0.05, f"Comparable {best[1].id} is within {spread:.0f} pts."
    return min(0.20, spread / 100.0), f"Comparable {best[1].id} differs by about {spread:.0f} pts on {label}."


def _numeric_tokens(text: str) -> set[str]:
    values = set()
    for raw in re.findall(r"\b\d+(?:\.\d+)?\b", text or ""):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 1900 <= value <= 2100:
            continue
        values.add(raw.rstrip("0").rstrip(".") if "." in raw else raw)
    return values


def _format_money(value: Optional[float], label: str) -> Optional[str]:
    if value is None:
        return None
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M {label}"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K {label}"
    return f"${value:.0f} {label}"


def _format_pct_value(value: Optional[float], label: str) -> Optional[str]:
    if value is None:
        return None
    direction = "up" if value > 0 else "down"
    if abs(value) < 0.1:
        return f"flat {label}"
    return f"{direction} {abs(value):.1f} pts {label}"


def _market_signal(
    venue: str,
    probability: Optional[float],
    movement_24h: Optional[float],
    best_bid: Optional[float],
    best_ask: Optional[float],
    spread: Optional[float],
    volume: Optional[float],
    liquidity: Optional[float],
    open_interest: Optional[float],
    signal_quality: Optional[float],
    signal_missing_reason: str,
) -> str:
    parts = [venue]
    if probability is not None:
        parts.append(f"{probability * 100:.0f}% implied")
    move_text = _format_pct_value(movement_24h, "24h")
    if move_text:
        parts.append(move_text)
    if best_bid is not None and best_ask is not None:
        parts.append(f"bid/ask {best_bid * 100:.0f}/{best_ask * 100:.0f}")
    if spread is not None:
        parts.append(f"spread {spread * 100:.0f} pts")
    for value in (
        _format_money(volume, "24h volume"),
        _format_money(liquidity, "liquidity"),
        _format_money(open_interest, "open interest"),
    ):
        if value:
            parts.append(value)
    if signal_quality is not None:
        parts.append(f"signal quality {signal_quality * 100:.0f}/100")
    if signal_missing_reason:
        parts.append(signal_missing_reason)
    return "; ".join(parts)


def _risk_line(
    evidence_score: float,
    movement_pct: Optional[float],
    quality: float,
    cross_note: str,
    spread: Optional[float],
    probability: Optional[float],
    signal_missing_reason: str,
) -> str:
    risks = []
    if evidence_score < 0.20:
        risks.append("external catalyst evidence is thin")
    if quality < 0.30:
        risks.append("market signal is thin or stale")
    if spread is not None and spread >= 0.12:
        risks.append("spread is wide")
    if probability is not None and (probability <= 0.02 or probability >= 0.98):
        risks.append("near-certain price can reflect stale or effectively resolved risk")
    if movement_pct is not None and abs(movement_pct) >= 10:
        risks.append("the recent move is large enough to retrace")
    if cross_note and "differs" in cross_note:
        risks.append("cross-venue pricing disagrees")
    if signal_missing_reason:
        risks.append(signal_missing_reason)
    if not risks:
        risks.append("fresh news or market repricing could change the ranking")
    return "; ".join(risks) + "."


def _resolvability_score(resolvability: str, *, broad: bool = False) -> float:
    lowered = (resolvability or "").lower()
    if not lowered:
        return 0.0
    if "direct_market_resolution" in lowered:
        return 0.08
    if "crypto reference-price market" in lowered:
        return 0.06
    if "sports game outcome" in lowered:
        return 0.05
    if "weather market" in lowered:
        return 0.03
    if "manual rule check required" in lowered:
        return -0.12 if broad else -0.05
    return 0.0


def _has_closing_soon_note(report: schema.Report) -> bool:
    return any(note == "closing_soon" or note.startswith("live-games:") for note in getattr(report, "planning_notes", []))


def _is_nba_bundle_intent(report: schema.Report) -> bool:
    return _domain(report.topic) == "nba" and paper_bundles.wants_paper_bundles(report.topic)


def _is_direct_espn_game_market(report: schema.Report, item, market_type: str) -> bool:
    if not _is_nba_bundle_intent(report):
        return True
    text = _market_text(item).lower()
    if market_type != "game_outcome":
        return False
    if any(term in text for term in ("series", "total games", "player", "points o/u", "assists o/u", "rebounds o/u")):
        return False
    confidence = getattr(item, "live_match_confidence", None)
    return bool(getattr(item, "live_game_context", "")) and confidence is not None and confidence >= 0.70


def _esports_same_day_match_exists(other_items: list, report: schema.Report) -> bool:
    for other in other_items:
        other_type = _candidate_market_type(other)
        if other_type != "game_outcome":
            continue
        if not eq.is_esports_query(_market_text(other)):
            continue
        days_to_end = _days_to_end(getattr(other, "end_date", None))
        if days_to_end is not None and days_to_end <= 1:
            return True
    return False


def _closing_score(minutes_to_close: Optional[float], reason: str) -> float:
    if minutes_to_close is None:
        return 0.0
    minutes = max(0.0, float(minutes_to_close))
    if minutes <= 60:
        base = 1.0
    elif minutes <= 180:
        base = 0.82
    elif minutes <= 360:
        base = 0.62
    elif minutes <= 720:
        base = 0.42
    else:
        base = 0.12
    if reason == "live_sports":
        base += 0.18
    elif reason == "starting_soon":
        base += 0.10
    elif reason == "near_settlement":
        base += 0.08
    return min(1.0, base)


def _days_to_end(end_date: Optional[str]) -> Optional[int]:
    if not end_date:
        return None
    try:
        return (date.fromisoformat(str(end_date)[:10]) - date.today()).days
    except ValueError:
        return None


def _tech_has_company_focus(title: str, question: str) -> bool:
    return bool(_canonical_tech_entities(f"{title} {question}"))


def _tech_actionability_score(item, market_type: str) -> float:
    days_to_end = _days_to_end(getattr(item, "end_date", None))
    has_company_focus = _tech_has_company_focus(getattr(item, "title", ""), getattr(item, "question", ""))
    if has_company_focus and days_to_end is not None and days_to_end <= 45:
        return 1.0
    if has_company_focus and days_to_end is not None and days_to_end <= 90:
        return 0.80
    if has_company_focus:
        return 0.60
    if market_type == "threshold":
        if days_to_end is not None and days_to_end > 90:
            return 0.0
        if days_to_end is not None and days_to_end > 45:
            return 0.10
        return 0.22
    return 0.35


def _is_long_dated_threshold_watch(item: schema.MarketWatchItem) -> bool:
    days_to_end = _days_to_end(item.end_date)
    return bool(item.market_type == "threshold" and days_to_end is not None and days_to_end > 45)


def _is_preferred_tech_company_watch(item: schema.MarketWatchItem) -> bool:
    days_to_end = _days_to_end(item.end_date)
    return _tech_has_company_focus(item.title, item.question) and days_to_end is not None and days_to_end <= 45


def _candidate_to_watch_item(idx: int, report: schema.Report, item, venue: str, other_items: list) -> Optional[schema.MarketWatchItem]:
    if _is_bad_candidate(report.topic, item):
        return None

    domain = _domain(report.topic)
    market_type = _candidate_market_type(item)
    target_date = _watchlist_target_date(report)
    watchlist_scope = _watchlist_scope(report, item, market_type)
    if _is_nba_watchlist_topic(report.topic) and not watchlist_scope:
        return None
    if not _is_direct_espn_game_market(report, item, market_type):
        return None
    if domain == "esports" and market_type == "game_outcome" and not _watchlist_date_compatible(item, target_date):
        return None
    if domain == "esports" and "today" in (report.topic or "").lower():
        if market_type == "game_outcome" and not _watchlist_exact_date_match(item, target_date):
            return None

    relevance = _topic_relevance(report.topic, item)
    if _domain(report.topic) != "broad" and relevance < 0.25:
        return None

    outcome_label, probability = _market_probability(item)
    volume, liquidity, open_interest = _depth_values(item)
    movement_pct = getattr(item, "movement_24h", None)
    if movement_pct is None:
        movement_pct = getattr(item, "price_movement_pct", None)
    quality = _signal_quality(item, volume, liquidity, open_interest)
    movement = _movement_score(movement_pct)
    spread = getattr(item, "spread", None)
    spread_quality = _spread_score(spread)
    evidence_score, catalyst_summary, evidence_refs = _evidence_for_market(report, item)
    if domain == "esports" and _is_spammy_market_evidence(catalyst_summary):
        evidence_score = 0.0
        catalyst_summary = "Catalyst context is thin; ranking is mostly market-signal driven."
        evidence_refs = []
    cross_score, cross_note = _cross_market_note(item, other_items)
    certainty_penalty = _near_certain_penalty(probability, movement, quality, market_type)
    closing_mode = _has_closing_soon_note(report)
    minutes_to_close = getattr(item, "minutes_to_close", None)
    closing_reason = getattr(item, "closing_soon_reason", "") or ""
    live_game_context = getattr(item, "live_game_context", "") or ""
    live_game_league = getattr(item, "live_game_league", "") or ""
    live_match_confidence = getattr(item, "live_match_confidence", None)
    live_match_reason = getattr(item, "live_match_reason", "") or ""
    resolvability = getattr(item, "resolvability", "") or ""
    closing_signal = _closing_score(minutes_to_close, closing_reason)
    tech_actionability = _tech_actionability_score(item, market_type) if domain == "tech" else 0.0
    resolvability_score = _resolvability_score(resolvability, broad=(domain == "broad" and closing_mode))
    if domain == "esports":
        explicit_props = _is_explicit_esports_prop_prompt(report.topic)
        explicit_title = _is_explicit_esports_title_prompt(report.topic)
        same_day_match_exists = _esports_same_day_match_exists(other_items, report)
        days_to_end = _days_to_end(getattr(item, "end_date", None))
        if market_type == "esports_prop" and not explicit_props:
            return None
        if market_type == "esports_title" and not explicit_title and same_day_match_exists:
            return None
        if market_type == "game_outcome" and probability is not None and (probability <= 0.02 or probability >= 0.98):
            if movement < 0.20 and quality < 0.70 and (volume or 0) < 50_000:
                return None
    if (
        market_type == "threshold"
        and probability is not None
        and (probability <= 0.02 or probability >= 0.98)
        and not (movement >= 0.35 and quality >= 0.70 and (volume or 0) >= 250_000)
    ):
        return None
    if closing_mode:
        rank_score = int(max(0, min(100, 100 * (
            0.32 * closing_signal +
            0.22 * quality +
            0.14 * spread_quality +
            0.12 * movement +
            0.10 * evidence_score +
            0.06 * relevance +
            0.04 * cross_score +
            resolvability_score -
            certainty_penalty
        ))))
    else:
        rank_score = int(max(0, min(100, 100 * (
            0.40 * quality +
            0.24 * relevance +
            0.14 * evidence_score +
            0.12 * movement +
            0.06 * spread_quality +
            0.04 * cross_score +
            max(0.0, resolvability_score) -
            certainty_penalty
        ))))

    if closing_mode and not closing_signal:
        return None
    if rank_score < 24 and _domain(report.topic) != "broad":
        return None
    if domain == "tech":
        days_to_end = _days_to_end(getattr(item, "end_date", None))
        if _tech_has_company_focus(getattr(item, "title", ""), getattr(item, "question", "")) and days_to_end is not None and days_to_end <= 45:
            rank_score += 18
        rank_score = int(max(0, min(100, rank_score + round(14 * tech_actionability))))
        if (
            market_type == "threshold"
            and days_to_end is not None
            and days_to_end > 45
        ):
            rank_score = max(0, rank_score - 14)
        if (
            market_type == "threshold"
            and days_to_end is not None
            and days_to_end > 90
            and (volume or 0) <= 0
            and (getattr(item, "volume_24h", None) or 0) <= 0
            and quality < 0.50
        ):
            rank_score = max(0, rank_score - 12)
    if domain == "esports":
        days_to_end = _days_to_end(getattr(item, "end_date", None))
        if market_type == "game_outcome":
            if days_to_end is not None and days_to_end <= 1:
                rank_score += 12
            rank_score += 6
            if probability is not None and probability >= 0.98 and evidence_score < 0.20:
                rank_score = max(0, rank_score - 12)
                if same_day_match_exists and quality < 0.95:
                    rank_score = max(0, rank_score - 10)
        elif market_type == "esports_title":
            if days_to_end is not None and days_to_end > 7:
                rank_score = max(0, rank_score - 16)
        rank_score = max(0, min(100, rank_score))
    if _is_nba_watchlist_topic(report.topic):
        if watchlist_scope == "game":
            rank_score += 8 if not _is_explicit_nba_series_prompt(report.topic) else 2
            if getattr(item, "live_game_context", ""):
                rank_score += 4
        elif watchlist_scope == "series":
            if _is_explicit_nba_series_prompt(report.topic):
                rank_score += 6
            else:
                rank_score -= 6
                if quality < 0.55 and movement < 0.20:
                    rank_score -= 8
        rank_score = max(0, min(100, rank_score))

    why_bits = []
    if closing_reason == "live_sports":
        why_bits.append("live sports")
    elif closing_reason == "starting_soon":
        why_bits.append("starting soon")
    elif minutes_to_close is not None:
        why_bits.append("closing soon")
    if spread is not None and spread <= 0.04:
        why_bits.append("tight spread")
    elif spread is not None and spread >= 0.12:
        why_bits.append("wide spread caveat")
    if (volume or 0) >= 250_000:
        why_bits.append("high 24h volume")
    if quality >= 0.60:
        why_bits.append("strong market signal")
    elif quality >= 0.30:
        why_bits.append("usable market signal")
    else:
        why_bits.append("thin/stale market signal")
    if movement >= 0.35:
        why_bits.append("large 24h repricing")
    if evidence_score >= 0.35:
        why_bits.append("fresh catalyst context")
    elif domain == "tech" and evidence_score > 0:
        why_bits.append("light catalyst context")
    elif domain == "esports" and evidence_score < 0.20:
        why_bits.append("market-signal driven despite thin catalyst context")
    if cross_score >= 0.05:
        why_bits.append("cross-market disagreement/alignment signal")
    if resolvability == "direct_market_resolution":
        why_bits.append("clear settlement path")
    elif resolvability:
        why_bits.append(resolvability.replace("_", " "))
    if not why_bits:
        why_bits.append("best available topic match, but lower-confidence")
    if market_type == "player_prop":
        why_bits.insert(0, "player prop")
    elif market_type == "team_prop":
        why_bits.insert(0, "team prop")
    elif market_type == "threshold":
        why_bits.insert(0, "threshold market")
    elif market_type == "esports_prop":
        why_bits.insert(0, "esports prop")
    elif market_type == "esports_title":
        why_bits.insert(0, "esports title market")
    elif watchlist_scope == "series":
        why_bits.insert(0, "playoff series")
    elif watchlist_scope == "game":
        why_bits.insert(0, "day-of-game watch")

    return schema.MarketWatchItem(
        id=f"MW{idx}",
        title=(getattr(item, "question", "") if market_type in {"player_prop", "team_prop", "threshold"} else getattr(item, "title", "")) or getattr(item, "question", ""),
        question=getattr(item, "question", "") or getattr(item, "title", ""),
        venue=venue,
        url=getattr(item, "url", ""),
        outcome_label=outcome_label,
        probability=probability,
        price_movement=getattr(item, "price_movement", None),
        price_movement_pct=getattr(item, "price_movement_pct", None),
        implied_probability=getattr(item, "implied_probability", None),
        best_bid=getattr(item, "best_bid", None),
        best_ask=getattr(item, "best_ask", None),
        spread=spread,
        midpoint=getattr(item, "midpoint", None),
        movement_24h=movement_pct,
        volume_24h=getattr(item, "volume_24h", None),
        market_signal_quality=quality,
        signal_timestamp=getattr(item, "signal_timestamp", None),
        signal_missing_reason=getattr(item, "signal_missing_reason", ""),
        market_type=market_type,
        volume=volume,
        liquidity=liquidity,
        open_interest=open_interest,
        rank_score=rank_score,
        catalyst_summary=catalyst_summary,
        market_signal=_market_signal(
            venue,
            probability,
            movement_pct,
            getattr(item, "best_bid", None),
            getattr(item, "best_ask", None),
            spread,
            volume,
            liquidity,
            open_interest,
            quality,
            getattr(item, "signal_missing_reason", ""),
        ),
        risk=_risk_line(
            evidence_score,
            movement_pct,
            quality,
            cross_note,
            spread,
            probability,
            getattr(item, "signal_missing_reason", ""),
        ),
        why_ranks=", ".join(why_bits),
        source_item_id=getattr(item, "id", ""),
        evidence_refs=evidence_refs,
        cross_market_note=cross_note,
        end_date=getattr(item, "end_date", None),
        end_datetime=getattr(item, "end_datetime", None),
        minutes_to_close=minutes_to_close,
        closing_soon_reason=closing_reason,
        live_game_context=live_game_context,
        live_game_league=live_game_league,
        live_match_confidence=live_match_confidence,
        live_match_reason=live_match_reason,
        resolvability=resolvability,
        watchlist_scope=watchlist_scope,
    )


def _should_suppress_low_signal_candidate(
    report: schema.Report,
    item: schema.MarketWatchItem,
    stronger_items: list[schema.MarketWatchItem],
    all_candidates: list[schema.MarketWatchItem],
) -> bool:
    domain = _domain(report.topic)
    if domain not in {"tech", "crypto"}:
        return False
    if len(stronger_items) < 2:
        return False
    days_to_end = _days_to_end(item.end_date)
    long_dated = days_to_end is not None and days_to_end >= 90
    low_volume = (item.volume or 0) <= 0 and (item.volume_24h or 0) <= 0
    low_signal = (item.market_signal_quality or 0) < 0.45
    preferred_near_term = domain == "tech" and any(_is_preferred_tech_company_watch(candidate) for candidate in stronger_items[:5])
    if domain == "tech" and _is_long_dated_threshold_watch(item) and preferred_near_term:
        return True
    if domain == "tech" and _is_long_dated_threshold_watch(item):
        available_company_rows = sum(1 for candidate in all_candidates if _is_preferred_tech_company_watch(candidate))
        if available_company_rows >= 2:
            return True
    if not (long_dated and low_volume and low_signal):
        return False
    return any((candidate.rank_score - item.rank_score) >= 5 for candidate in stronger_items[:3])


def _watch_item_domain(item: schema.MarketWatchItem) -> str:
    return _market_evidence_domain(
        "broad",
        item.market_type,
        _tokens(f"{item.title} {item.question}"),
        f"{item.title} {item.question}",
    )


def _esports_subdomain_for_item(item: schema.MarketWatchItem) -> str:
    text = f"{item.title} {item.question}".lower()
    tokens = _tokens(text)
    for name, alias_tokens in _ESPORTS_SUBDOMAINS.items():
        if tokens & alias_tokens:
            return name
    return ""


def _should_delay_duplicate_esports_title_candidate(
    report: schema.Report,
    candidate: schema.MarketWatchItem,
    results: list[schema.MarketWatchItem],
    remaining: list[schema.MarketWatchItem],
) -> bool:
    if _domain(report.topic) != "esports" or eq.is_cs2_query(report.topic):
        return False
    candidate_title = _esports_subdomain_for_item(candidate)
    if not candidate_title:
        return False
    existing_titles = {_esports_subdomain_for_item(item) for item in results}
    existing_titles.discard("")
    if candidate_title not in existing_titles:
        return False
    return any(
        (title := _esports_subdomain_for_item(other)) and title not in existing_titles
        for other in remaining
    )


def _should_suppress_stale_esports_candidate(
    report: schema.Report,
    candidate: schema.MarketWatchItem,
    stronger_items: list[schema.MarketWatchItem],
    all_candidates: list[schema.MarketWatchItem],
) -> bool:
    if _domain(report.topic) != "esports":
        return False
    if candidate.market_type != "game_outcome":
        return False
    probability = candidate.probability or candidate.market_probability or candidate.implied_probability
    if probability is None or probability < 0.98:
        return False
    if (candidate.market_signal_quality or 0.0) < 0.75:
        return False
    if "thin" not in (candidate.catalyst_summary or "").lower():
        return False
    candidate_subdomain = _esports_subdomain_for_item(candidate)
    same_day_others = [
        item for item in all_candidates
        if item is not candidate
        and item.market_type == "game_outcome"
        and item.end_date == candidate.end_date
        and (item.rank_score >= candidate.rank_score - 18)
        and (item.probability or item.market_probability or item.implied_probability or 0.0) < 0.98
        and _esports_subdomain_for_item(item) == candidate_subdomain
    ]
    if len(same_day_others) < 1:
        return False
    return True


def _should_delay_duplicate_domain_candidate(
    report: schema.Report,
    candidate: schema.MarketWatchItem,
    results: list[schema.MarketWatchItem],
    remaining: list[schema.MarketWatchItem],
) -> bool:
    if _domain(report.topic) != "broad" or not _has_closing_soon_note(report):
        return False
    if len(results) >= 3:
        return False
    candidate_domain = _watch_item_domain(candidate)
    if not candidate_domain or candidate_domain == "broad":
        return False
    existing_domains = {_watch_item_domain(item) for item in results}
    if candidate_domain not in existing_domains:
        return False
    return any(
        (domain := _watch_item_domain(other)) not in {"", "broad"} and domain not in existing_domains
        for other in remaining
    )


def _should_drop_broad_manual_rule_candidate(report: schema.Report, candidate: schema.MarketWatchItem) -> bool:
    if _domain(report.topic) != "broad" or not _has_closing_soon_note(report):
        return False
    if candidate.resolvability != "manual rule check required":
        return False
    if candidate.rank_score >= 26 and (candidate.market_signal_quality or 0.0) >= 0.60:
        return False
    return True


def _should_delay_duplicate_esports_board_candidate(
    report: schema.Report,
    candidate: schema.MarketWatchItem,
    results: list[schema.MarketWatchItem],
    remaining: list[schema.MarketWatchItem],
) -> bool:
    if _domain(report.topic) != "esports" or eq.is_cs2_query(report.topic):
        return False
    candidate_domain = _esports_subdomain_for_item(candidate)
    if not candidate_domain:
        return False
    existing_domains = {_esports_subdomain_for_item(item) for item in results}
    if candidate_domain not in existing_domains:
        return False
    return any(
        (domain := _esports_subdomain_for_item(other)) and domain not in existing_domains
        for other in remaining
    )


def _should_suppress_nba_series_candidate(
    report: schema.Report,
    candidate: schema.MarketWatchItem,
    stronger_items: list[schema.MarketWatchItem],
    all_candidates: list[schema.MarketWatchItem],
) -> bool:
    if not _is_nba_watchlist_topic(report.topic) or _is_explicit_nba_series_prompt(report.topic):
        return False
    if candidate.watchlist_scope != "series":
        return False
    stronger_games = [item for item in all_candidates if item.watchlist_scope == "game" and item.rank_score >= candidate.rank_score - 4]
    if len(stronger_games) >= 3 and (
        (candidate.market_signal_quality or 0.0) < 0.58
        or ((candidate.volume or 0) < 100_000 and (candidate.volume_24h or 0) < 100_000)
        or candidate.rank_score < 50
    ):
        return True
    return False


def synthesize_market_watchlist(report: schema.Report, limit: int = 5) -> list[schema.MarketWatchItem]:
    """Rank topic-scoped Polymarket/Kalshi candidates for market-watchlist mode."""
    candidates = []
    for item in report.polymarket:
        candidate = _candidate_to_watch_item(len(candidates) + 1, report, item, "Polymarket", list(report.kalshi))
        if candidate:
            candidates.append(candidate)
    for item in report.kalshi:
        candidate = _candidate_to_watch_item(len(candidates) + 1, report, item, "Kalshi", list(report.polymarket))
        if candidate:
            candidates.append(candidate)

    closing_mode = _has_closing_soon_note(report)
    explicit_series_prompt = _is_explicit_nba_series_prompt(report.topic)
    if closing_mode:
        candidates.sort(
            key=lambda item: (
                2 if item.closing_soon_reason == "live_sports" else 1 if item.closing_soon_reason == "starting_soon" else 0,
                item.rank_score,
                -(item.minutes_to_close if item.minutes_to_close is not None else 10_000),
            ),
            reverse=True,
        )
    else:
        candidates.sort(
            key=lambda item: (
                2 if (item.watchlist_scope == "series" and explicit_series_prompt) else
                1 if item.watchlist_scope == "game" else
                0 if item.watchlist_scope == "series" else -1,
                item.rank_score,
                item.market_signal_quality or 0.0,
            ),
            reverse=True,
        )
    results = []
    seen = set()
    for idx, candidate in enumerate(candidates):
        if _should_suppress_nba_series_candidate(report, candidate, results, candidates):
            _bump_debug_counter(report, "suppressed_nba_series_watchlist_candidates")
            continue
        if _should_suppress_low_signal_candidate(report, candidate, results, candidates):
            _bump_debug_counter(report, "suppressed_long_dated_watchlist_candidates")
            continue
        if _should_suppress_stale_esports_candidate(report, candidate, results, candidates):
            _bump_debug_counter(report, "suppressed_stale_esports_watchlist_candidates")
            continue
        if _should_drop_broad_manual_rule_candidate(report, candidate):
            _bump_debug_counter(report, "suppressed_manual_rule_watchlist_candidates")
            continue
        if _should_delay_duplicate_domain_candidate(report, candidate, results, candidates[idx + 1:]):
            _bump_debug_counter(report, "suppressed_duplicate_domain_watchlist_candidates")
            continue
        if _should_delay_duplicate_esports_board_candidate(report, candidate, results, candidates[idx + 1:]):
            _bump_debug_counter(report, "suppressed_duplicate_esports_board_candidates")
            continue
        if _should_delay_duplicate_esports_title_candidate(report, candidate, results, candidates[idx + 1:]):
            _bump_debug_counter(report, "suppressed_duplicate_esports_title_watchlist_candidates")
            continue
        key = re.sub(r"\W+", " ", f"{candidate.title} {candidate.question}").lower().strip()
        if key in seen:
            continue
        seen.add(key)
        candidate.id = f"MW{len(results) + 1}"
        results.append(candidate)
        if len(results) >= limit:
            break
    return results
