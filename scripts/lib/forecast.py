"""Market-anchored forecast synthesis for prediction queries."""

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from . import query_type as qt, schema

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
    "forecast", "forecasts", "weather", "radar", "precip", "precipitation", "showers",
    "storm", "storms", "thunderstorm", "thunderstorms", "warning", "warnings",
    "watch", "watches", "wind", "winds", "temperature", "temperatures", "front",
    "humidity", "model", "models", "rainfall", "snowfall", "accumulation",
}
WEATHER_WEAK_TERMS = {"rain", "snow", "storm", "cold", "hot", "weather"}
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
MACRO_CONTEXT_TERMS = {"cut", "cuts", "hike", "hikes", "rate", "rates", "bps", "basis", "meeting", "economy", "economic"}
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
    "song", "music", "sabrina", "tallow", "eat", "food", "well",
}
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
SPORTS_TEAM_TOKENS = {
    "lakers", "warriors", "celtics", "knicks", "heat", "raptors", "bulls",
    "wizards", "rockets", "sixers", "76ers", "pacers", "nets", "nuggets",
    "grizzlies", "spurs", "mavs", "mavericks", "thunder", "suns", "clippers",
}


@dataclass
class _EvidenceCandidate:
    score: float
    text: str
    tokens: set[str]
    source: str
    team_hits: int
    signal_hits: int


def _tokenize(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s-]", " ", (text or "").lower()).split())


def _matchup_side_tokens(text: str) -> list[set[str]]:
    text_lower = text.lower()
    separator = None
    for candidate in (" vs. ", " vs ", " at "):
        if candidate in text_lower:
            separator = candidate
            break
    if not separator:
        return []
    stop = {"the", "and", "at", "vs", "vs.", "of", "today", "tonight", "tomorrow"}
    sides = []
    for side in text_lower.split(separator, 1):
        tokens = {
            token
            for token in re.sub(r"[^\w\s]", " ", side).split()
            if len(token) > 2 and token not in stop
        }
        if tokens:
            sides.append(tokens)
    return sides if len(sides) == 2 else []


def _matchup_signature(text: str) -> Optional[str]:
    sides = _matchup_side_tokens(text)
    if len(sides) != 2:
        return None
    normalized = [" ".join(sorted(side)) for side in sides]
    normalized.sort()
    return " | ".join(normalized)


def market_quality(engagement: Optional[schema.Engagement], movement_pct: Optional[float] = None) -> float:
    """Return a 0-1 market quality score shared by both venues."""
    if engagement is None:
        return 0.0
    volume = math.log1p(engagement.volume or 0.0)
    liquidity = math.log1p(engagement.liquidity or 0.0)
    open_interest = math.log1p(engagement.open_interest or 0.0)
    movement = min(1.0, abs(movement_pct or 0.0) / 20.0)
    raw = 0.45 * volume + 0.25 * liquidity + 0.20 * open_interest + 0.10 * movement
    return min(1.0, raw / 6.5) if raw > 0 else 0.0


def _clean_outcome_label(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "")).strip()
    if not cleaned:
        return ""
    if cleaned.lower() in {"the", "there", "1", "2", "3", "4", "5"}:
        return ""
    return cleaned


def _top_polymarket_probability(item: schema.PolymarketItem) -> tuple[Optional[str], Optional[float]]:
    if not item.outcome_prices:
        return None, None
    ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
    label = _clean_outcome_label(ordered[0][0]) or None
    return label, ordered[0][1]


def _topic_tokens(topic: str) -> set[str]:
    stop = {"will", "the", "for", "and", "today", "tomorrow", "tonight", "odds", "probability"}
    return {
        token for token in re.sub(r"[^\w\s]", " ", topic.lower()).split()
        if len(token) > 2 and token not in stop
    }


def _is_sports_query(text: str) -> bool:
    text_lower = (text or "").lower()
    matchup = _matchup_signature(text_lower)
    sports_terms = {"nba", "nfl", "nhl", "mlb", "wnba", "basketball", "football", "soccer", "baseball", "game", "games"}
    return bool(matchup or (SPORTS_TEAM_TOKENS & _tokenize(text_lower)) or any(term in text_lower for term in sports_terms))


def _is_weather_query(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens & {"weather", "rain", "snow", "storm", "wind", "temperature", "forecast", "hurricane", "tornado", "showers"})


def _is_macro_query(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens & {"fed", "fomc", "powell", "cpi", "inflation", "jobs", "gdp", "recession", "approval", "poll", "polls", "rates", "rate", "economy"})


def _favorite_tokens(favorite_label: str) -> set[str]:
    return {
        token for token in _tokenize(favorite_label)
        if token not in {"yes", "no", "favorite"} and len(token) > 2
    }


def _sports_candidate_score(
    text: str,
    title: str,
    source: str,
    base_score: float,
    author: str = "",
    community: str = "",
) -> Optional[_EvidenceCandidate]:
    tokens = _tokenize(f"{text} {author} {community}")
    if "check" in tokens and "out" in tokens:
        tokens.discard("out")
    title_tokens = _topic_tokens(title)
    sides = _matchup_side_tokens(title)
    overlap = len(title_tokens & tokens)
    team_hits = sum(1 for side in sides if side & tokens) if sides else 0
    signal_hits = len(SPORTS_DRIVER_TERMS & tokens)
    concrete_hits = len(SPORTS_HIGH_SIGNAL_TERMS & tokens)
    if sides and team_hits == 0:
        return None
    if concrete_hits == 0:
        return None
    if team_hits < len(sides):
        return None
    if overlap == 0:
        return None

    score = min(base_score, 80) * 0.25 + overlap * 5 + concrete_hits * 5
    if team_hits == len(sides) and sides:
        score += 12
    elif team_hits:
        score += 4

    if concrete_hits:
        score += 12
    if {"injury", "injuries", "ruled", "questionable", "doubtful", "rest", "lineup", "lineups", "inactive", "available"} & tokens:
        score += 10
    if {"playoff", "playoffs", "seed", "seeding", "elimination", "clinch", "clinched", "tank", "tanking"} & tokens:
        score += 6
    if SPORTS_MARKET_CONTEXT_TERMS & tokens and concrete_hits:
        score += 4
    if SPORTS_REPORTER_TOKENS & _tokenize(f"{author} {community}"):
        score += 8

    if SPORTS_LOW_SIGNAL_TERMS & tokens:
        score -= 18
        if not concrete_hits:
            score -= 18
    if SPORTS_RECAP_TERMS & tokens and not concrete_hits:
        score -= 14
    mentioned_teams = len(SPORTS_TEAM_TOKENS & tokens)
    if mentioned_teams >= 4:
        return None
    if mentioned_teams >= 3 and not SPORTS_HIGH_SIGNAL_TERMS & tokens:
        score -= 10
    if score < 22:
        return None

    return _EvidenceCandidate(
        score=score,
        text=text.strip(),
        tokens=tokens,
        source=source,
        team_hits=team_hits,
        signal_hits=concrete_hits,
    )


def _generic_candidate_score(
    text: str,
    title: str,
    base_score: float,
    weather_query: bool = False,
    macro_query: bool = False,
    source_context: str = "",
) -> Optional[_EvidenceCandidate]:
    context = f"{text} {source_context}".strip()
    tokens = _tokenize(context)
    title_tokens = _topic_tokens(title)
    overlap = len(title_tokens & tokens)

    if overlap == 0:
        return None

    if weather_query:
        location_tokens = title_tokens - WEATHER_WEAK_TERMS - {"tomorrow", "today", "tonight"}
        if not (WEATHER_SIGNAL_TERMS & tokens):
            return None
        if location_tokens and not (location_tokens & tokens):
            return None
        if overlap < 2 and not (WEATHER_SIGNAL_TERMS & tokens):
            return None

    if macro_query:
        macro_overlap = len((title_tokens - {"will", "have", "us", "usa", "by", "in", "end", "next", "month", "year"}) & tokens)
        signal_hits = len(MACRO_SIGNAL_TERMS & tokens)
        strong_hits = len(MACRO_STRONG_TERMS & tokens)
        if MACRO_BAD_CONTEXT_TERMS & tokens:
            return None
        if signal_hits == 0:
            return None
        if strong_hits == 0 and macro_overlap < 2:
            return None
        if signal_hits < 2 and not (MACRO_CONTEXT_TERMS & tokens and macro_overlap >= 1):
            return None
        if not ((MACRO_STRONG_TERMS & tokens) or (MACRO_SUPPORT_TERMS & tokens and macro_overlap >= 1)):
            return None
        if "recession" in title_tokens and "recession" in tokens and not (RECESSION_SUPPORT_TERMS & tokens):
            return None

    if LOW_SIGNAL_SOCIAL_TERMS & tokens and not DRIVER_TERMS & tokens:
        return None
    if overlap < 2 and not DRIVER_TERMS & tokens:
        return None

    score = base_score + overlap * 4
    if DRIVER_TERMS & tokens:
        score += 8
    if weather_query and WEATHER_SIGNAL_TERMS & tokens:
        score += 10
    if macro_query:
        score += len(MACRO_SIGNAL_TERMS & tokens) * 4
        if MACRO_STRONG_TERMS & tokens:
            score += 8
    return _EvidenceCandidate(
        score=score,
        text=text.strip(),
        tokens=tokens,
        source="generic",
        team_hits=0,
        signal_hits=len(DRIVER_TERMS & tokens),
    )


def _collect_evidence_candidates(report: schema.Report, title: str) -> list[_EvidenceCandidate]:
    title_lower = title.lower()
    sports_query = _is_sports_query(title) or _is_sports_query(report.topic)
    weather_query = _is_weather_query(title) or _is_weather_query(report.topic)
    macro_query = _is_macro_query(title) or _is_macro_query(report.topic)
    candidates: list[_EvidenceCandidate] = []

    for item in report.x[:12]:
        text = getattr(item, "text", "") or ""
        if not text:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _sports_candidate_score(text, title, "x", base_score, author=getattr(item, "author_handle", ""))
            if sports_query
            else _generic_candidate_score(
                text,
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "author_handle", ""),
            )
        )
        if candidate:
            candidates.append(candidate)

    for item in report.reddit[:10]:
        text = getattr(item, "title", "") or ""
        if not text:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _sports_candidate_score(text, title, "reddit", base_score, community=getattr(item, "subreddit", ""))
            if sports_query
            else _generic_candidate_score(
                f"{text} {getattr(item, 'subreddit', '')}",
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "subreddit", ""),
            )
        )
        if candidate:
            candidates.append(candidate)

    for item in report.web[:8]:
        text = f"{getattr(item, 'title', '')} {getattr(item, 'snippet', '')}".strip()
        if not text:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _sports_candidate_score(text, title, "web", base_score, community=getattr(item, "source_domain", ""))
            if sports_query
            else _generic_candidate_score(
                text,
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "source_domain", ""),
            )
        )
        if candidate:
            candidates.append(candidate)

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _polymarket_match_score(topic: str, item: schema.PolymarketItem) -> tuple[int, int, float]:
    topic_signature = _matchup_signature(topic)
    item_signature = _matchup_signature(item.title or item.question)
    signature_match = int(bool(topic_signature and topic_signature == item_signature))
    tokens = _topic_tokens(topic)
    market_tokens = _tokenize(f"{item.title} {item.question}")
    overlap = len(tokens & market_tokens)
    return signature_match, overlap, item.relevance


def _best_polymarket(topic: str, items: list[schema.PolymarketItem]) -> Optional[schema.PolymarketItem]:
    if not items:
        return None
    ranked = sorted(items, key=lambda item: (_polymarket_match_score(topic, item), item.score), reverse=True)
    return ranked[0]


def _best_kalshi(topic: str, items: list[schema.KalshiItem]) -> Optional[schema.KalshiItem]:
    if not items:
        return None
    topic_signature = _matchup_signature(topic)
    if topic_signature:
        matching = [
            item for item in items
            if _matchup_signature(item.title or item.question) == topic_signature
        ]
        if matching:
            return max(matching, key=lambda item: item.score)
    ranked = sorted(items, key=lambda item: (len(_topic_tokens(topic) & _tokenize(f"{item.title} {item.question}")), item.score), reverse=True)
    return ranked[0]


def _matching_kalshi_for_polymarket(
    poly_item: schema.PolymarketItem,
    kalshi_items: list[schema.KalshiItem],
) -> Optional[schema.KalshiItem]:
    signature = _matchup_signature(poly_item.title or poly_item.question)
    if signature:
        for item in kalshi_items:
            if _matchup_signature(item.title or item.question) == signature:
                return item
    return None


def _top_evidence(report: schema.Report, title: str, limit: int = 2) -> list[str]:
    candidates = _collect_evidence_candidates(report, title)
    results = []
    seen = set()
    for candidate in candidates:
        text = candidate.text
        if not text:
            continue
        short = text.replace("\n", " ")[:180].strip()
        if short in seen:
            continue
        seen.add(short)
        results.append(short + ("..." if len(text) > 180 else ""))
        if len(results) >= limit:
            break
    return results


def _evidence_has_conflict(candidates: list[_EvidenceCandidate], favorite_label: str) -> bool:
    favorite = _favorite_tokens(favorite_label)
    if not favorite:
        return False
    favorite_support = False
    opposing_support = False
    for candidate in candidates[:5]:
        if candidate.signal_hits == 0:
            continue
        if favorite & candidate.tokens:
            favorite_support = True
        elif candidate.team_hits >= 1:
            opposing_support = True
    return favorite_support and opposing_support


def _model_implied_range(report: schema.Report) -> tuple[float, float]:
    evidence_count = len(report.x[:5]) + len(report.reddit[:5]) + len(report.web[:5])
    if evidence_count >= 5:
        return 0.48, 0.58
    if evidence_count >= 2:
        return 0.44, 0.58
    return 0.40, 0.60


def _confidence_label(spread: Optional[float], quality: float, evidence_count: int, has_market: bool) -> str:
    if not has_market:
        return "low"
    if spread is not None and spread >= 0.12:
        return "moderate-low"
    if quality >= 0.65 and evidence_count >= 3:
        return "moderate"
    if quality >= 0.45:
        return "moderate-low"
    return "low"


def _uncertainty_text(
    confidence: str,
    spread: Optional[float],
    has_both_markets: bool,
    has_market: bool,
    evidence_count: int,
    evidence_conflict: bool = False,
) -> str:
    if not has_market:
        return "No clean market exists, so this is model-implied and should be treated cautiously."
    parts = []
    if has_both_markets and spread is not None:
        if spread >= 0.12:
            parts.append(f"Polymarket and Kalshi disagree by about {spread * 100:.0f} points.")
        elif spread >= 0.05:
            parts.append(f"Polymarket and Kalshi are directionally aligned but still {spread * 100:.0f} points apart.")
        else:
            parts.append("Polymarket and Kalshi are broadly aligned.")
    if evidence_count < 2:
        parts.append("Supporting non-market evidence is thin.")
    elif evidence_conflict:
        parts.append("Recent non-market evidence is mixed, so the market line still carries most of the weight.")
    if confidence == "moderate":
        parts.append("Confidence is moderate for a live market-backed forecast.")
    elif confidence == "moderate-low":
        parts.append("Confidence is moderate-low because the line is still sensitive to fresh information.")
    else:
        parts.append("Confidence is low.")
    return " ".join(parts)


def _generic_catalysts(report: schema.Report, favorite_label: str) -> tuple[list[str], list[str]]:
    topic = report.topic.lower()
    if any(term in topic for term in ("rain", "snow", "storm", "weather", "temperature", "wind")):
        return (
            ["More severe radar/model runs", "New watches or warnings"],
            ["A weaker storm track", "Drying trend in updated weather models"],
        )
    if any(term in topic for term in ("election", "poll", "approval", "rate cut", "inflation", "cpi", "fed", "recession", "gdp", "jobs")):
        return (
            ["Fresh polling or data releases that favor the market direction", "Official statements that reinforce the current line"],
            ["Contradictory data or polling", "Sharp repricing in related macro or prediction markets"],
        )
    label = favorite_label or "the current favorite"
    return (
        [f"Positive lineup/injury news for {label}", "Supportive late market movement"],
        [f"Negative lineup/injury news for {label}", "Any sharp move against the current favorite near the event"],
    )


def _generic_fallback_why_line(report: schema.Report) -> str:
    topic = report.topic.lower()
    if _is_weather_query(topic):
        return "Model-implied because no clean market exists and no high-signal weather evidence surfaced in the last 24 hours."
    if _is_macro_query(topic):
        return "Mostly market-driven right now; no high-signal macro or policy evidence surfaced in the last 24 hours."
    return "Mostly market-driven right now; supporting evidence is thin."


def _sports_catalysts(candidates: list[_EvidenceCandidate], favorite_label: str) -> tuple[list[str], list[str]]:
    favorite = favorite_label or "the favorite"
    all_tokens = set()
    for candidate in candidates[:5]:
        all_tokens |= candidate.tokens

    up = []
    down = []

    if {"questionable", "doubtful", "out", "inactive"} & all_tokens:
        up.append(f"Positive availability news for {favorite}")
        down.append(f"A downgrade or scratch for {favorite}")
    if {"rest", "resting", "back-to-back", "b2b", "minutes", "restriction", "restricted"} & all_tokens:
        up.append("A softer rest/minutes spot than expected")
        down.append("A tougher rest spot or minutes restriction")
    if {"lineup", "lineups", "starter", "starters", "starting"} & all_tokens:
        up.append(f"A stronger-than-expected starting lineup for {favorite}")
        down.append("A surprise lineup downgrade")
    if {"playoff", "playoffs", "seed", "seeding", "elimination", "clinch", "clinched", "tank", "tanking"} & all_tokens:
        up.append("Clearer playoff or motivation edge")
        down.append("Motivation or seeding incentives breaking the other way")
    if not up:
        up.append(f"Positive lineup/injury news for {favorite}")
    if not down:
        down.append(f"Negative lineup/injury news for {favorite}")
    if len(up) < 2:
        up.append("Supportive late market movement")
    if len(down) < 2:
        down.append("Any sharp move against the current favorite near tipoff")
    return up[:2], down[:2]


def _build_forecast_item(
    title: str,
    polymarket_item: Optional[schema.PolymarketItem],
    kalshi_item: Optional[schema.KalshiItem],
    report: schema.Report,
) -> schema.ForecastItem:
    evidence_candidates = _collect_evidence_candidates(report, title)
    evidence = []
    for candidate in evidence_candidates:
        short = candidate.text.replace("\n", " ")[:180].strip()
        if short and short not in evidence:
            evidence.append(short + ("..." if len(candidate.text) > 180 else ""))
        if len(evidence) >= 2:
            break
    evidence_count = len(evidence)

    poly_label, poly_probability = (None, None)
    if polymarket_item:
        poly_label, poly_probability = _top_polymarket_probability(polymarket_item)
    kalshi_probability = kalshi_item.current_probability if kalshi_item else None

    poly_quality = market_quality(
        polymarket_item.engagement if polymarket_item else None,
        polymarket_item.price_movement_pct if polymarket_item else None,
    ) if polymarket_item else 0.0
    kalshi_quality = market_quality(
        kalshi_item.engagement if kalshi_item else None,
        kalshi_item.price_movement_pct if kalshi_item else None,
    ) if kalshi_item else 0.0

    forecast = schema.ForecastItem(title=title)
    forecast.favorite_label = poly_label or "Yes"
    forecast.why_line = evidence[0] if evidence else ""
    forecast.polymarket_market_id = polymarket_item.id if polymarket_item else None
    forecast.kalshi_market_id = kalshi_item.id if kalshi_item else None
    forecast.polymarket_probability = poly_probability
    forecast.kalshi_probability = kalshi_probability

    if poly_probability is not None and kalshi_probability is not None:
        poly_weight = max(0.15, poly_quality or 0.0)
        kalshi_weight = max(0.15, kalshi_quality or 0.0)
        blended = ((poly_probability * poly_weight) + (kalshi_probability * kalshi_weight)) / (poly_weight + kalshi_weight)
        spread = abs(poly_probability - kalshi_probability)
        range_half = 0.04 + min(0.12, spread / 2)
        forecast.forecast_probability = blended
        forecast.forecast_range_low = max(0.01, blended - range_half)
        forecast.forecast_range_high = min(0.99, blended + range_half)
        forecast.anchor_source = "blended"
        forecast.market_spread = spread
        forecast.market_view = (
            f"Polymarket {poly_probability * 100:.0f}% | Kalshi {kalshi_probability * 100:.0f}% "
            f"(spread {spread * 100:.0f} pts; {'Polymarket' if poly_weight >= kalshi_weight else 'Kalshi'} carries more weight)"
        )
        quality = max(poly_quality, kalshi_quality)
        forecast.confidence_level = _confidence_label(spread, quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            spread,
            True,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    elif poly_probability is not None:
        range_half = 0.04 if poly_quality >= 0.5 else 0.07
        forecast.forecast_probability = poly_probability
        forecast.forecast_range_low = max(0.01, poly_probability - range_half)
        forecast.forecast_range_high = min(0.99, poly_probability + range_half)
        forecast.anchor_source = "polymarket"
        movement = f" ({polymarket_item.price_movement})" if polymarket_item and polymarket_item.price_movement else ""
        forecast.market_view = f"Polymarket {poly_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, poly_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            None,
            False,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    elif kalshi_probability is not None:
        range_half = 0.05 if kalshi_quality >= 0.5 else 0.08
        forecast.forecast_probability = kalshi_probability
        forecast.forecast_range_low = max(0.01, kalshi_probability - range_half)
        forecast.forecast_range_high = min(0.99, kalshi_probability + range_half)
        forecast.anchor_source = "kalshi"
        movement = f" ({kalshi_item.price_movement})" if kalshi_item and kalshi_item.price_movement else ""
        forecast.market_view = f"Kalshi {kalshi_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, kalshi_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            None,
            False,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    else:
        low, high = _model_implied_range(report)
        forecast.model_implied = True
        forecast.forecast_probability = (low + high) / 2
        forecast.forecast_range_low = low
        forecast.forecast_range_high = high
        forecast.anchor_source = "model_implied"
        forecast.market_view = "No clean Polymarket or Kalshi market found."
        forecast.confidence_level = _confidence_label(None, 0.0, evidence_count, has_market=False)
        forecast.uncertainty = _uncertainty_text(forecast.confidence_level, None, False, False, evidence_count)

    if _is_sports_query(title) or _is_sports_query(report.topic):
        forecast.upside_catalysts, forecast.downside_catalysts = _sports_catalysts(evidence_candidates, forecast.favorite_label)
        if not forecast.why_line:
            forecast.why_line = "Mostly market-driven right now; no clean injury, lineup, or rest signal surfaced in the last 24 hours."
    else:
        forecast.upside_catalysts, forecast.downside_catalysts = _generic_catalysts(report, forecast.favorite_label)
        if not forecast.why_line:
            forecast.why_line = _generic_fallback_why_line(report)
    return forecast


def synthesize_forecasts(report: schema.Report) -> list[schema.ForecastItem]:
    """Create market-anchored forecast objects for prediction queries."""
    if qt.detect_query_type(report.topic) != "prediction":
        return []

    forecasts: list[schema.ForecastItem] = []
    is_nba_slate = "nba" in report.topic.lower() and "games" in report.topic.lower()

    if is_nba_slate and report.polymarket:
        seen = set()
        for poly_item in report.polymarket:
            signature = _matchup_signature(poly_item.title or poly_item.question)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            kalshi_item = _matching_kalshi_for_polymarket(poly_item, report.kalshi)
            forecasts.append(_build_forecast_item(poly_item.title or poly_item.question, poly_item, kalshi_item, report))
        return forecasts

    top_poly = _best_polymarket(report.topic, report.polymarket)
    top_kalshi = _best_kalshi(report.topic, report.kalshi)
    if top_poly and top_kalshi and _matchup_signature(top_poly.title or top_poly.question):
        matched_kalshi = _matching_kalshi_for_polymarket(top_poly, report.kalshi)
        if matched_kalshi:
            top_kalshi = matched_kalshi

    title = top_poly.title if top_poly else top_kalshi.title if top_kalshi else report.topic
    forecasts.append(_build_forecast_item(title, top_poly, top_kalshi, report))
    return forecasts
