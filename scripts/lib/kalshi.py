"""Kalshi prediction market search via public market-data API."""

import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import http
from .relevance import token_overlap_relevance

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
MARKETS_URL = f"{API_BASE}/markets"
EVENT_URL = f"{API_BASE}/events"

PAGE_LIMITS = {
    "quick": 1,
    "default": 3,
    "deep": 5,
}

RESULT_CAP = {
    "quick": 5,
    "default": 15,
    "deep": 25,
}
_LEAGUE_TOKENS = {
    "nba": ("nba", "basketball"),
    "nfl": ("nfl", "football"),
    "mlb": ("mlb", "baseball"),
    "nhl": ("nhl", "hockey"),
}


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[KALSHI] {msg}\n")
        sys.stderr.flush()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _format_pct(delta: Optional[float]) -> Optional[str]:
    if delta is None or abs(delta) < 1.0:
        return None
    direction = "up" if delta > 0 else "down"
    return f"{direction} {abs(delta):.1f}% today"


def _pick_current_probability(market: Dict[str, Any]) -> Optional[float]:
    last_price = _safe_float(market.get("last_price_dollars"))
    if last_price > 0:
        return last_price

    yes_bid = _safe_float(market.get("yes_bid_dollars"))
    yes_ask = _safe_float(market.get("yes_ask_dollars"))
    if yes_bid > 0 and yes_ask > 0:
        return (yes_bid + yes_ask) / 2
    if yes_ask > 0:
        return yes_ask
    if yes_bid > 0:
        return yes_bid
    return None


def _market_text(market: Dict[str, Any]) -> str:
    parts = [
        market.get("title", ""),
        market.get("subtitle", ""),
        market.get("yes_sub_title", ""),
        market.get("no_sub_title", ""),
        market.get("ticker", ""),
        market.get("event_ticker", ""),
        market.get("series_ticker", ""),
    ]
    return " ".join(p for p in parts if p)


def _detect_league(topic: str) -> Optional[str]:
    topic_lower = topic.lower()
    for league, aliases in _LEAGUE_TOKENS.items():
        if any(alias in topic_lower for alias in aliases):
            return league
    return None


def _is_sports_slate_query(topic: str) -> bool:
    topic_lower = topic.lower()
    league = _detect_league(topic)
    return bool(league and any(term in topic_lower for term in ("games tonight", "games today", "tonight", "today", "slate")))


def _is_combo_market(market: Dict[str, Any], event_title: str = "") -> bool:
    text = " ".join(part for part in (_market_text(market), event_title) if part).lower()
    ticker = str(market.get("ticker", "")).lower()
    event_ticker = str(market.get("event_ticker", "")).lower()
    comma_count = text.count(",")
    if "multigame" in ticker or "crosscategory" in ticker or "multigame" in event_ticker or "crosscategory" in event_ticker:
        return True
    if "combo" in text:
        return True
    if comma_count >= 2 and (text.startswith("yes ") or text.startswith("no ")):
        return True
    return False


def _market_has_quality(market: Dict[str, Any]) -> bool:
    return any(
        _safe_float(market.get(field)) > 0
        for field in ("volume_24h_fp", "volume_fp", "open_interest_fp", "liquidity_dollars")
    )


def _market_relevance(topic: str, market: Dict[str, Any], event_title: str = "") -> float:
    text = " ".join(part for part in (_market_text(market), event_title) if part)
    text_score = token_overlap_relevance(topic, text)
    if _is_sports_slate_query(topic) and " vs " in event_title.lower() and not _is_combo_market(market, event_title):
        league = _detect_league(topic)
        event_lower = event_title.lower()
        if league == "nba":
            text_score = max(text_score, 0.72 if any(token in event_lower for token in (" vs ", " at ")) else text_score)

    current_probability = _pick_current_probability(market)
    previous_probability = _safe_float(market.get("previous_price_dollars"))
    movement_pct = None
    if current_probability is not None and previous_probability > 0:
        movement_pct = (current_probability - previous_probability) * 100

    volume_score = min(1.0, math.log1p(_safe_float(market.get("volume_24h_fp")) or _safe_float(market.get("volume_fp"))) / 10)
    liquidity_score = min(1.0, math.log1p(_safe_float(market.get("liquidity_dollars"))) / 8)
    oi_score = min(1.0, math.log1p(_safe_float(market.get("open_interest_fp"))) / 8)
    movement_score = min(1.0, abs(movement_pct or 0.0) / 15.0)

    market_quality = 0.35 * volume_score + 0.20 * liquidity_score + 0.25 * oi_score + 0.20 * movement_score
    if _is_combo_market(market, event_title):
        market_quality *= 0.1
        text_score *= 0.2
    return round(min(1.0, text_score * 0.8 + market_quality * 0.2), 2)


def _fetch_markets_page(cursor: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    params = {
        "status": "open",
        "limit": str(limit),
    }
    if cursor:
        params["cursor"] = cursor
    url = f"{MARKETS_URL}?{urlencode(params)}"
    return http.request("GET", url, timeout=20, retries=2)


def _fetch_event(event_ticker: str) -> Dict[str, Any]:
    url = f"{EVENT_URL}/{event_ticker}"
    return http.request("GET", url, timeout=15, retries=2)


def search_kalshi(topic: str, from_date: str, to_date: str, depth: str = "default") -> Dict[str, Any]:
    """Fetch open Kalshi markets, rank locally, and enrich the best matches with event titles."""
    page_count = PAGE_LIMITS.get(depth, PAGE_LIMITS["default"])
    cap = RESULT_CAP.get(depth, RESULT_CAP["default"])

    markets: List[Dict[str, Any]] = []
    cursor = None
    for _ in range(page_count):
        response = _fetch_markets_page(cursor=cursor)
        markets.extend(response.get("markets", []))
        cursor = response.get("cursor") or None
        if not cursor:
            break

    if not markets:
        return {"markets": [], "_cap": cap}

    ranked = []
    for market in markets:
        market["relevance"] = _market_relevance(topic, market)
        ranked.append(market)

    ranked.sort(
        key=lambda m: (
            -m.get("relevance", 0.0),
            -_safe_float(m.get("volume_24h_fp")) - _safe_float(m.get("volume_fp")),
            -_safe_float(m.get("open_interest_fp")),
        )
    )
    if _is_sports_slate_query(topic):
        filtered_ranked = [
            m for m in ranked
            if not _is_combo_market(m) and (_market_has_quality(m) or _pick_current_probability(m) is not None)
        ]
        candidates = filtered_ranked[: cap * 4] if filtered_ranked else []
    else:
        filtered_ranked = [
            m for m in ranked
            if not _is_combo_market(m) or _market_has_quality(m)
        ]
        candidates = filtered_ranked[: cap * 3] if filtered_ranked else ranked[: cap * 3]

    event_titles: Dict[str, str] = {}
    unique_events = sorted({m.get("event_ticker", "") for m in candidates if m.get("event_ticker")})
    with ThreadPoolExecutor(max_workers=min(8, len(unique_events) or 1)) as executor:
        futures = {executor.submit(_fetch_event, ticker): ticker for ticker in unique_events}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                event = future.result().get("event", {})
                event_titles[ticker] = event.get("title", "")
            except Exception as exc:
                _log(f"event fetch failed for {ticker}: {exc}")

    return {"markets": candidates, "event_titles": event_titles, "_cap": cap}


def parse_kalshi_response(response: Dict[str, Any], topic: str = "") -> List[Dict[str, Any]]:
    """Parse Kalshi search response into normalized dicts."""
    items = []
    event_titles = response.get("event_titles", {})
    cap = response.get("_cap", RESULT_CAP["default"])

    for market in response.get("markets", []):
        ticker = market.get("ticker", "")
        event_ticker = market.get("event_ticker", "")
        series_ticker = market.get("series_ticker", "")
        event_title = event_titles.get(event_ticker, market.get("subtitle", "")) or market.get("title", "")
        if _is_combo_market(market, event_title):
            continue
        question = market.get("title", "")
        current_probability = _pick_current_probability(market)
        previous_probability = _safe_float(market.get("previous_price_dollars"))
        movement_pct = None
        if current_probability is not None and previous_probability > 0:
            movement_pct = (current_probability - previous_probability) * 100

        end_date = (
            (market.get("expiration_time") or market.get("close_time") or market.get("expected_expiration_time") or "")[:10]
            or None
        )
        updated = (market.get("updated_time") or market.get("open_time") or "")[:10] or None

        relevance = _market_relevance(topic, market, event_title) if topic else market.get("relevance", 0.5)
        volume = _safe_float(market.get("volume_24h_fp")) or _safe_float(market.get("volume_fp"))
        liquidity = _safe_float(market.get("liquidity_dollars"))
        open_interest = _safe_float(market.get("open_interest_fp"))

        if not _market_has_quality(market) and _is_sports_slate_query(topic):
            continue

        items.append({
            "title": event_title,
            "question": question,
            "url": f"{MARKETS_URL}/{ticker}" if ticker else MARKETS_URL,
            "ticker": ticker,
            "event_ticker": event_ticker,
            "series_ticker": series_ticker,
            "current_probability": current_probability,
            "price_movement": _format_pct(movement_pct),
            "price_movement_pct": movement_pct,
            "date": updated,
            "end_date": end_date,
            "volume": volume,
            "liquidity": liquidity,
            "open_interest": open_interest,
            "relevance": relevance,
            "why_relevant": f"Kalshi market: {question[:60]}",
        })

    items.sort(
        key=lambda item: (
            -item.get("relevance", 0.0),
            -(item.get("volume") or 0.0),
            -(item.get("open_interest") or 0.0),
        )
    )
    return items[:cap]
