"""Market-anchored forecast synthesis for prediction queries."""

import math
import re
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
    label = _clean_outcome_label(ordered[0][0]) or "Favorite"
    return label, ordered[0][1]


def _topic_tokens(topic: str) -> set[str]:
    stop = {"will", "the", "for", "and", "today", "tomorrow", "tonight", "odds", "probability"}
    return {
        token for token in re.sub(r"[^\w\s]", " ", topic.lower()).split()
        if len(token) > 2 and token not in stop
    }


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
    target_tokens = _topic_tokens(title)
    title_lower = title.lower()
    weather_query = any(term in title_lower for term in ("weather", "rain", "snow", "storm", "wind", "temperature"))
    weather_terms = {"forecast", "weather", "radar", "showers", "precip", "precipitation", "storm", "warning", "watch", "temperature", "wind"}
    candidates = []

    for item in list(report.x[:10]) + list(report.reddit[:8]) + list(report.web[:6]):
        text = getattr(item, "text", "") or getattr(item, "title", "") or getattr(item, "snippet", "")
        tokens = _tokenize(text)
        overlap = len(target_tokens & tokens)
        if overlap == 0:
            continue
        if weather_query and not (weather_terms & tokens):
            continue
        if LOW_SIGNAL_SOCIAL_TERMS & tokens and not DRIVER_TERMS & tokens:
            continue
        if overlap < 2 and not DRIVER_TERMS & tokens:
            continue
        bonus = 8 if DRIVER_TERMS & tokens else 0
        candidates.append((getattr(item, "score", 0) + overlap * 4 + bonus, text.strip()))

    candidates.sort(key=lambda row: row[0], reverse=True)
    results = []
    seen = set()
    for _, text in candidates:
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


def _build_forecast_item(
    title: str,
    polymarket_item: Optional[schema.PolymarketItem],
    kalshi_item: Optional[schema.KalshiItem],
    report: schema.Report,
) -> schema.ForecastItem:
    evidence = _top_evidence(report, title)
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
        forecast.uncertainty = _uncertainty_text(forecast.confidence_level, spread, True, True, evidence_count)
    elif poly_probability is not None:
        range_half = 0.04 if poly_quality >= 0.5 else 0.07
        forecast.forecast_probability = poly_probability
        forecast.forecast_range_low = max(0.01, poly_probability - range_half)
        forecast.forecast_range_high = min(0.99, poly_probability + range_half)
        forecast.anchor_source = "polymarket"
        movement = f" ({polymarket_item.price_movement})" if polymarket_item and polymarket_item.price_movement else ""
        forecast.market_view = f"Polymarket {poly_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, poly_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(forecast.confidence_level, None, False, True, evidence_count)
    elif kalshi_probability is not None:
        range_half = 0.05 if kalshi_quality >= 0.5 else 0.08
        forecast.forecast_probability = kalshi_probability
        forecast.forecast_range_low = max(0.01, kalshi_probability - range_half)
        forecast.forecast_range_high = min(0.99, kalshi_probability + range_half)
        forecast.anchor_source = "kalshi"
        movement = f" ({kalshi_item.price_movement})" if kalshi_item and kalshi_item.price_movement else ""
        forecast.market_view = f"Kalshi {kalshi_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, kalshi_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(forecast.confidence_level, None, False, True, evidence_count)
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

    forecast.upside_catalysts, forecast.downside_catalysts = _generic_catalysts(report, forecast.favorite_label)
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
