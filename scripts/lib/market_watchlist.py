"""One-shot market discovery and ranking for market-watchlist prompts."""

import math
import re
from typing import Optional

from . import evidence_quality as eq, schema


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
}

_META_MARKET_TERMS = {
    "law banning", "ban sports prediction", "sports prediction markets enacted",
    "prediction markets", "market regulation", "banning sports",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.sub(r"[^\w\s-]", " ", (text or "").lower()).split()
        if len(token) > 2 and token not in _STOPWORDS
    }


def _domain(topic: str) -> str:
    tokens = _tokens(topic)
    lowered = (topic or "").lower()
    if "nba" in tokens:
        return "nba"
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
        return "Yes", item.current_probability
    if item.outcome_prices:
        ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
        label, probability = ordered[0]
        return str(label or "Top outcome"), probability
    return "Top outcome", None


def _market_text(item) -> str:
    return f"{getattr(item, 'title', '')} {getattr(item, 'question', '')} {getattr(item, 'url', '')}"


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
    return max(0.0, min(1.0, relevance))


def _is_bad_candidate(topic: str, item) -> bool:
    market_lower = _market_text(item).lower()
    domain = _domain(topic)
    if domain in {"sports", "nba"} and any(term in market_lower for term in _META_MARKET_TERMS):
        return True
    if domain == "nba" and not eq.is_nba_market_text(market_lower):
        return True
    if "parlay" in market_lower or "combo" in market_lower:
        return True
    return False


def _market_quality(volume: Optional[float], liquidity: Optional[float], open_interest: Optional[float]) -> float:
    vol = min(1.0, math.log1p(max(volume or 0.0, 0.0)) / math.log1p(2_000_000))
    liq = min(1.0, math.log1p(max(liquidity or 0.0, 0.0)) / math.log1p(500_000))
    oi = min(1.0, math.log1p(max(open_interest or 0.0, 0.0)) / math.log1p(500_000))
    return max(vol * 0.55 + liq * 0.30 + oi * 0.15, vol * 0.65 + liq * 0.35)


def _movement_score(movement_pct: Optional[float]) -> float:
    if movement_pct is None:
        return 0.0
    return min(1.0, abs(movement_pct) / 20.0)


def _source_text(item) -> str:
    if isinstance(item, schema.XItem):
        return item.text
    if isinstance(item, schema.RedditItem):
        return f"{item.title} r/{item.subreddit} {' '.join(item.comment_insights[:2])}"
    if isinstance(item, schema.WebSearchItem):
        return f"{item.title} {item.snippet} {item.source_domain}"
    if isinstance(item, schema.HackerNewsItem):
        return item.title
    return getattr(item, "title", "") or getattr(item, "text", "")


def _is_signal_evidence(topic: str, text: str, context: str = "") -> bool:
    domain = _domain(topic)
    tokens = _tokens(f"{text} {context}")
    topic_tokens = _tokens(topic)
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
    market_crypto_tokens = market_tokens & {"bitcoin", "btc", "ethereum", "eth", "solana", "xrp", "crypto"}
    scored = []
    evidence_items = list(report.x[:12]) + list(report.reddit[:10]) + list(report.web[:10]) + list(report.hackernews[:5])
    for evidence in evidence_items:
        text = _source_text(evidence)
        context = getattr(evidence, "source_domain", "") or getattr(evidence, "subreddit", "")
        tokens = _tokens(text)
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
        if not _is_signal_evidence(report.topic, text, context):
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
    best = None
    for other in other_items:
        other_tokens = _tokens(_market_text(other))
        common = len(item_tokens & other_tokens)
        if common < 3:
            continue
        _, other_probability = _market_probability(other)
        if other_probability is None:
            continue
        score = common / max(1, len(item_tokens | other_tokens))
        if not best or score > best[0]:
            best = (score, other, other_probability)
    if not best:
        return 0.0, ""
    spread = abs(probability - best[2]) * 100
    if spread < 5:
        return 0.05, f"Comparable {best[1].id} is within {spread:.0f} pts."
    return min(0.20, spread / 100.0), f"Comparable {best[1].id} differs by about {spread:.0f} pts on {label}."


def _format_money(value: Optional[float], label: str) -> Optional[str]:
    if value is None:
        return None
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M {label}"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K {label}"
    return f"${value:.0f} {label}"


def _market_signal(venue: str, probability: Optional[float], price_movement: Optional[str], volume: Optional[float], liquidity: Optional[float], open_interest: Optional[float]) -> str:
    parts = [venue]
    if probability is not None:
        parts.append(f"{probability * 100:.0f}% implied")
    if price_movement:
        parts.append(price_movement)
    for value in (
        _format_money(volume, "volume"),
        _format_money(liquidity, "liquidity"),
        _format_money(open_interest, "open interest"),
    ):
        if value:
            parts.append(value)
    return "; ".join(parts)


def _risk_line(evidence_score: float, movement_pct: Optional[float], quality: float, cross_note: str) -> str:
    risks = []
    if evidence_score < 0.20:
        risks.append("external catalyst evidence is thin")
    if quality < 0.30:
        risks.append("market depth is limited")
    if movement_pct is not None and abs(movement_pct) >= 10:
        risks.append("the recent move is large enough to retrace")
    if cross_note and "differs" in cross_note:
        risks.append("cross-venue pricing disagrees")
    if not risks:
        risks.append("fresh news or market repricing could change the ranking")
    return "; ".join(risks) + "."


def _candidate_to_watch_item(idx: int, report: schema.Report, item, venue: str, other_items: list) -> Optional[schema.MarketWatchItem]:
    if _is_bad_candidate(report.topic, item):
        return None

    relevance = _topic_relevance(report.topic, item)
    if _domain(report.topic) != "broad" and relevance < 0.25:
        return None

    outcome_label, probability = _market_probability(item)
    volume, liquidity, open_interest = _engagement_values(getattr(item, "engagement", None))
    quality = _market_quality(volume, liquidity, open_interest)
    movement = _movement_score(getattr(item, "price_movement_pct", None))
    evidence_score, catalyst_summary, evidence_refs = _evidence_for_market(report, item)
    spread_score, cross_note = _cross_market_note(item, other_items)
    rank_score = int(max(0, min(100, 100 * (
        0.34 * quality +
        0.25 * relevance +
        0.23 * evidence_score +
        0.12 * movement +
        0.06 * spread_score
    ))))

    if rank_score < 24 and _domain(report.topic) != "broad":
        return None

    why_bits = []
    if quality >= 0.55:
        why_bits.append("strong market depth")
    elif quality >= 0.30:
        why_bits.append("usable market depth")
    if movement >= 0.35:
        why_bits.append("notable recent move")
    if evidence_score >= 0.35:
        why_bits.append("fresh catalyst context")
    if spread_score >= 0.05:
        why_bits.append("cross-market disagreement/alignment signal")
    if not why_bits:
        why_bits.append("best available topic match, but lower-confidence")

    return schema.MarketWatchItem(
        id=f"MW{idx}",
        title=getattr(item, "title", "") or getattr(item, "question", ""),
        question=getattr(item, "question", "") or getattr(item, "title", ""),
        venue=venue,
        url=getattr(item, "url", ""),
        outcome_label=outcome_label,
        probability=probability,
        price_movement=getattr(item, "price_movement", None),
        price_movement_pct=getattr(item, "price_movement_pct", None),
        volume=volume,
        liquidity=liquidity,
        open_interest=open_interest,
        rank_score=rank_score,
        catalyst_summary=catalyst_summary,
        market_signal=_market_signal(venue, probability, getattr(item, "price_movement", None), volume, liquidity, open_interest),
        risk=_risk_line(evidence_score, getattr(item, "price_movement_pct", None), quality, cross_note),
        why_ranks=", ".join(why_bits),
        source_item_id=getattr(item, "id", ""),
        evidence_refs=evidence_refs,
        cross_market_note=cross_note,
        end_date=getattr(item, "end_date", None),
    )


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

    candidates.sort(key=lambda item: item.rank_score, reverse=True)
    results = []
    seen = set()
    for candidate in candidates:
        key = re.sub(r"\W+", " ", f"{candidate.title} {candidate.question}").lower().strip()
        if key in seen:
            continue
        seen.add(key)
        candidate.id = f"MW{len(results) + 1}"
        results.append(candidate)
        if len(results) >= limit:
            break
    return results
