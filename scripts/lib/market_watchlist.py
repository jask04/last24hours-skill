"""One-shot market discovery and ranking for market-watchlist prompts."""

import math
import re
from datetime import date
from typing import Optional

from . import evidence_fusion, evidence_quality as eq, market_types, schema


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
    if "parlay" in market_lower or "combo" in market_lower:
        return True
    return False


def _candidate_market_type(item) -> str:
    return getattr(item, "market_type", "") or market_types.classify_market(
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
    fused = evidence_fusion.fuse_evidence(report, _market_text(item), "market_watchlist", limit=3)
    if fused.candidate_count:
        report.evidence_fusion_stats = {
            "candidate_count": max(
                int(report.evidence_fusion_stats.get("candidate_count", 0) or 0),
                fused.candidate_count,
            ),
            "driver_count": max(
                int(report.evidence_fusion_stats.get("driver_count", 0) or 0),
                len(fused.drivers),
            ),
            "cluster_count": max(
                int(report.evidence_fusion_stats.get("cluster_count", 0) or 0),
                fused.cluster_count,
            ),
        }
    for driver in fused.drivers:
        driver_tokens = _tokens(driver.text)
        overlap = len(market_specific_tokens & driver_tokens)
        catalyst = len(driver_tokens & _CATALYST_TERMS)
        if overlap or catalyst:
            scored.append((driver.score + min(0.20, overlap * 0.04), driver, driver.text))

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


def _has_closing_soon_note(report: schema.Report) -> bool:
    return any(note == "closing_soon" or note.startswith("live-games:") for note in getattr(report, "planning_notes", []))


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


def _candidate_to_watch_item(idx: int, report: schema.Report, item, venue: str, other_items: list) -> Optional[schema.MarketWatchItem]:
    if _is_bad_candidate(report.topic, item):
        return None

    relevance = _topic_relevance(report.topic, item)
    if _domain(report.topic) != "broad" and relevance < 0.25:
        return None

    outcome_label, probability = _market_probability(item)
    market_type = _candidate_market_type(item)
    volume, liquidity, open_interest = _depth_values(item)
    movement_pct = getattr(item, "movement_24h", None)
    if movement_pct is None:
        movement_pct = getattr(item, "price_movement_pct", None)
    quality = _signal_quality(item, volume, liquidity, open_interest)
    movement = _movement_score(movement_pct)
    spread = getattr(item, "spread", None)
    spread_quality = _spread_score(spread)
    evidence_score, catalyst_summary, evidence_refs = _evidence_for_market(report, item)
    cross_score, cross_note = _cross_market_note(item, other_items)
    certainty_penalty = _near_certain_penalty(probability, movement, quality, market_type)
    closing_mode = _has_closing_soon_note(report)
    minutes_to_close = getattr(item, "minutes_to_close", None)
    closing_reason = getattr(item, "closing_soon_reason", "") or ""
    live_game_context = getattr(item, "live_game_context", "") or ""
    resolvability = getattr(item, "resolvability", "") or ""
    closing_signal = _closing_score(minutes_to_close, closing_reason)
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
            0.04 * cross_score -
            certainty_penalty
        ))))
    else:
        rank_score = int(max(0, min(100, 100 * (
            0.40 * quality +
            0.24 * relevance +
            0.14 * evidence_score +
            0.12 * movement +
            0.06 * spread_quality +
            0.04 * cross_score -
            certainty_penalty
        ))))

    if closing_mode and not closing_signal:
        return None
    if rank_score < 24 and _domain(report.topic) != "broad":
        return None

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
        resolvability=resolvability,
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

    closing_mode = _has_closing_soon_note(report)
    if closing_mode:
        candidates.sort(
            key=lambda item: (
                1 if item.closing_soon_reason == "live_sports" else 0,
                item.rank_score,
                -(item.minutes_to_close if item.minutes_to_close is not None else 10_000),
            ),
            reverse=True,
        )
    else:
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
    if results and not any(item.venue.lower() == "kalshi" for item in results):
        best_kalshi = next((item for item in candidates if item.venue.lower() == "kalshi"), None)
        cutoff = results[-1].rank_score
        if best_kalshi and best_kalshi.rank_score >= max(30, cutoff - 10):
            results[-1] = best_kalshi
            results.sort(key=lambda item: item.rank_score, reverse=True)
            for idx, item in enumerate(results, start=1):
                item.id = f"MW{idx}"
    return results
