"""Kalshi prediction market search via public market-data API."""

import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import re

from . import http
from .query_type import detect_query_type
from .relevance import token_overlap_relevance

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
MARKETS_URL = f"{API_BASE}/markets"
EVENTS_URL = f"{API_BASE}/events"
EVENT_URL = f"{API_BASE}/events"
CANDLESTICKS_URL = f"{API_BASE}/markets/candlesticks"

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
_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _matchup_side_tokens(text: str) -> List[set[str]]:
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


def _topic_matchup_signature(topic: str) -> List[set[str]]:
    return _matchup_side_tokens(topic)


def _market_matches_matchup(topic: str, market: Dict[str, Any], event_title: str = "") -> bool:
    sides = _topic_matchup_signature(topic)
    if len(sides) != 2:
        return True

    text_tokens = {
        token
        for token in re.sub(r"[^\w\s]", " ", f"{_market_text(market)} {event_title}".lower()).split()
        if len(token) > 2
    }
    return all(side & text_tokens for side in sides)


def _log(msg: str):
    if sys.stderr.isatty():
        sys.stderr.write(f"[KALSHI] {msg}\n")
        sys.stderr.flush()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _safe_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_probability(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if 1.0 < value <= 100.0:
        return value / 100.0
    return value


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
        for field in ("volume_24h", "volume_24h_fp", "volume_fp", "candlestick_open_interest", "open_interest_fp", "liquidity_dollars")
    )


def _market_relevance(topic: str, market: Dict[str, Any], event_title: str = "") -> float:
    text = " ".join(part for part in (_market_text(market), event_title) if part)
    topic_tokens = {
        token
        for token in re.sub(r"[^\w\s]", " ", (topic or "").lower()).split()
        if token
    }
    text_tokens = {
        token
        for token in re.sub(r"[^\w\s]", " ", text.lower()).split()
        if token
    }
    text_score = token_overlap_relevance(topic, text)
    matchup_bonus = 0.0
    matchup_penalty = 0.0

    if len(_topic_matchup_signature(topic)) == 2:
        if _market_matches_matchup(topic, market, event_title):
            matchup_bonus = 0.20
        else:
            matchup_penalty = 0.35

    if _is_sports_slate_query(topic) and " vs " in event_title.lower() and not _is_combo_market(market, event_title):
        league = _detect_league(topic)
        event_lower = event_title.lower()
        if league == "nba":
            text_score = max(text_score, 0.72 if any(token in event_lower for token in (" vs ", " at ")) else text_score)
    if _detect_league(topic) == "nba" and str(market.get("event_ticker", "")).startswith("KXNBAGAME"):
        text_score = max(text_score, 0.78)
    if topic_tokens & {"cut", "cuts", "decrease", "lower"} and not (text_tokens & {"cut", "cuts", "decrease", "lower"}):
        text_score = min(text_score, 0.25)
    if topic_tokens & {"hike", "hikes", "increase", "raise"} and not (text_tokens & {"hike", "hikes", "increase", "raise"}):
        text_score = min(text_score, 0.25)

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
    relevance = text_score * 0.75 + market_quality * 0.25 + matchup_bonus - matchup_penalty
    return round(max(0.0, min(1.0, relevance)), 2)


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


def _series_for_topic(topic: str) -> List[str]:
    tokens = set(re.sub(r"[^\w\s]", " ", (topic or "").lower()).split())
    series = []
    if "nba" in tokens or "basketball" in tokens:
        series.append("KXNBAGAME")
    if tokens & {"fed", "fomc", "rates", "rate", "cuts", "cut", "hikes", "hike"}:
        series.append("KXFED")
    if tokens & {"bitcoin", "btc", "crypto"}:
        series.append("KXBTC")
    if tokens & {"ethereum", "eth"}:
        series.append("KXETH")
    return series


def _fetch_events_for_series(series_ticker: str, limit: int = 8) -> List[Dict[str, Any]]:
    params = {"series_ticker": series_ticker, "limit": str(max(limit, 25))}
    url = f"{EVENTS_URL}?{urlencode(params)}"
    try:
        events = http.request("GET", url, timeout=15, retries=1).get("events", [])
        now = datetime.now(timezone.utc)
        upcoming = []
        for event in events:
            event_date = _event_datetime(event)
            if event_date and event_date < now:
                continue
            upcoming.append(event)
        events = upcoming or events
        events.sort(key=lambda event: (
            not bool(event.get("available_on_brokers", True)),
            _event_datetime(event) or datetime.max.replace(tzinfo=timezone.utc),
            event.get("last_updated_ts") or "",
        ))
        return events[:limit]
    except Exception as exc:
        _log(f"event series fetch failed for {series_ticker}: {exc}")
        return []


def _event_datetime(event: Dict[str, Any]) -> Optional[datetime]:
    strike_date = event.get("strike_date")
    if strike_date:
        try:
            return datetime.fromisoformat(str(strike_date).replace("Z", "+00:00"))
        except ValueError:
            pass
    ticker = str(event.get("event_ticker", ""))
    match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", ticker)
    if not match:
        return None
    year = 2000 + int(match.group(1))
    month = _MONTHS.get(match.group(2))
    day = int(match.group(3))
    if not month:
        return None
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _fetch_markets_for_event(event_ticker: str, limit: int = 200) -> List[Dict[str, Any]]:
    params = {"status": "open", "limit": str(limit), "event_ticker": event_ticker}
    url = f"{MARKETS_URL}?{urlencode(params)}"
    try:
        return http.request("GET", url, timeout=15, retries=1).get("markets", [])
    except Exception as exc:
        _log(f"event markets fetch failed for {event_ticker}: {exc}")
        return []


def _series_markets_for_topic(topic: str, depth: str) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Fetch direct event markets for known high-value Kalshi series."""
    series = _series_for_topic(topic)
    if not series:
        return [], {}
    event_limit = {"quick": 5, "default": 8, "deep": 12}.get(depth, 8)
    markets: List[Dict[str, Any]] = []
    event_titles: Dict[str, str] = {}
    wanted_months = _topic_months(topic)
    for series_ticker in series[:3]:
        events = _fetch_events_for_series(series_ticker, event_limit)
        if wanted_months:
            month_matches = [
                event for event in events
                if (event_date := _event_datetime(event)) and event_date.month in wanted_months
            ]
            if month_matches:
                events = month_matches
        for event in events:
            ticker = event.get("event_ticker", "")
            if not ticker:
                continue
            event_titles[ticker] = event.get("title", "")
            markets.extend(_fetch_markets_for_event(ticker))
    return markets, event_titles


def _topic_months(topic: str) -> set[int]:
    aliases = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    tokens = re.sub(r"[^\w\s]", " ", (topic or "").lower()).split()
    return {aliases[token] for token in tokens if token in aliases}


def _fetch_batch_candlesticks(tickers: List[str]) -> Dict[str, Any]:
    """Fetch one-hour Kalshi candles for up to 100 market tickers."""
    if not tickers:
        return {}
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    params = {
        "market_tickers": ",".join(tickers[:100]),
        "period_interval": "60",
        "start_ts": str(int(start.timestamp())),
        "end_ts": str(int(now.timestamp())),
        "include_latest_before_start": "true",
    }
    url = f"{CANDLESTICKS_URL}?{urlencode(params)}"
    try:
        return http.request("GET", url, timeout=20, retries=1)
    except Exception as exc:
        _log(f"candlestick fetch failed: {exc}")
        return {"error": str(exc)}


def _candles_by_ticker(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    raw = (
        payload.get("candlesticks")
        or payload.get("market_candlesticks")
        or payload.get("markets")
        or payload.get("data")
        or []
    )
    if isinstance(raw, dict):
        result = {}
        for ticker, candles in raw.items():
            if isinstance(candles, list):
                result[str(ticker)] = candles
            elif isinstance(candles, dict):
                result[str(ticker)] = candles.get("candlesticks", []) or candles.get("candles", [])
        return result

    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            ticker = entry.get("market_ticker") or entry.get("ticker") or entry.get("market_id")
            candles = entry.get("candlesticks") or entry.get("candles") or entry.get("series") or []
            if ticker and isinstance(candles, list):
                by_ticker[str(ticker)] = candles
    return by_ticker


def _candle_value(candle: Dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
    for key in keys:
        value = _safe_optional_float(candle.get(key))
        if value is not None:
            return value
    yes = candle.get("yes")
    if isinstance(yes, dict):
        for key in keys:
            value = _safe_optional_float(yes.get(key))
            if value is not None:
                return value
    return None


def _candle_price(candle: Dict[str, Any]) -> Optional[float]:
    return _normalize_probability(_candle_value(candle, (
        "close",
        "yes_close",
        "price",
        "yes_price",
        "close_dollars",
        "yes_close_dollars",
    )))


def _candle_volume(candle: Dict[str, Any]) -> Optional[float]:
    return _candle_value(candle, ("volume", "volume_dollars", "yes_volume", "volume_fp"))


def _candle_open_interest(candle: Dict[str, Any]) -> Optional[float]:
    return _candle_value(candle, ("open_interest", "open_interest_dollars", "open_interest_fp"))


def _candle_timestamp(candle: Dict[str, Any]) -> Optional[str]:
    value = candle.get("end_ts") or candle.get("start_ts") or candle.get("ts") or candle.get("time")
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value)


def _summarize_candlestick_signals(candles: List[Dict[str, Any]], fallback_probability: Optional[float]) -> Dict[str, Any]:
    prices = [price for candle in candles if (price := _candle_price(candle)) is not None]
    volumes = [volume for candle in candles if (volume := _candle_volume(candle)) is not None]
    open_interests = [oi for candle in candles if (oi := _candle_open_interest(candle)) is not None]
    latest_price = prices[-1] if prices else fallback_probability
    first_price = prices[0] if prices else None
    movement = (latest_price - first_price) * 100 if latest_price is not None and first_price is not None else None
    latest_ts = _candle_timestamp(candles[-1]) if candles else None
    return {
        "movement_24h": movement,
        "volume_24h": sum(volumes) if volumes else None,
        "candlestick_open_interest": open_interests[-1] if open_interests else None,
        "signal_timestamp": latest_ts,
        "signal_missing_reason": "" if prices or volumes or open_interests else "candlestick data unavailable",
    }


def _apply_candlestick_signals(markets: List[Dict[str, Any]]) -> None:
    tickers = [m.get("ticker", "") for m in markets if m.get("ticker")]
    if not tickers:
        return
    payload = _fetch_batch_candlesticks(tickers)
    by_ticker = _candles_by_ticker(payload)
    fetch_error = payload.get("error") if isinstance(payload, dict) else None
    for market in markets:
        ticker = market.get("ticker", "")
        if fetch_error:
            market["signal_missing_reason"] = f"candlestick fetch failed: {fetch_error}"
            continue
        candles = by_ticker.get(ticker, [])
        summary = _summarize_candlestick_signals(candles, _pick_current_probability(market))
        market.update({key: value for key, value in summary.items() if value not in (None, "")})
        if summary.get("signal_missing_reason"):
            market["signal_missing_reason"] = summary["signal_missing_reason"]


def _market_signal_quality(
    probability: Optional[float],
    spread: Optional[float],
    movement_24h: Optional[float],
    volume_24h: Optional[float],
    liquidity: Optional[float],
    open_interest: Optional[float],
    signal_missing_reason: str = "",
) -> tuple[float, str]:
    volume_score = min(1.0, math.log1p(max(volume_24h or 0.0, 0.0)) / math.log1p(500_000))
    liquidity_score = min(1.0, math.log1p(max(liquidity or 0.0, 0.0)) / math.log1p(250_000))
    oi_score = min(1.0, math.log1p(max(open_interest or 0.0, 0.0)) / math.log1p(250_000))
    movement_score = min(1.0, abs(movement_24h or 0.0) / 20.0)
    spread_score = max(0.0, min(1.0, 1.0 - ((spread if spread is not None else 0.20) / 0.20)))
    missing = []
    if spread is None:
        missing.append("spread unavailable")
    if volume_24h is None:
        missing.append("24h volume unavailable")
    if signal_missing_reason:
        missing.append(signal_missing_reason)

    quality = 0.30 * volume_score + 0.22 * liquidity_score + 0.22 * oi_score + 0.16 * spread_score + 0.10 * movement_score
    if probability is not None and (probability <= 0.01 or probability >= 0.99):
        if max(volume_score, oi_score, movement_score) < 0.55:
            quality *= 0.65
            missing.append("near-certain price can be stale")
    return round(max(0.0, min(1.0, quality)), 3), "; ".join(dict.fromkeys(missing))


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

    series_markets, series_event_titles = _series_markets_for_topic(topic, depth)
    markets.extend(series_markets)
    deduped_markets: Dict[str, Dict[str, Any]] = {}
    for market in markets:
        ticker = market.get("ticker", "")
        if ticker:
            deduped_markets[ticker] = market
    markets = list(deduped_markets.values()) if deduped_markets else markets

    if not markets:
        return {"markets": [], "_cap": cap}

    ranked = []
    for market in markets:
        market["relevance"] = _market_relevance(topic, market, series_event_titles.get(market.get("event_ticker", ""), ""))
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

    _apply_candlestick_signals(candidates)

    event_titles: Dict[str, str] = dict(series_event_titles)
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
        if not _market_matches_matchup(topic, market, event_title):
            continue
        topic_tokens = {
            token
            for token in re.sub(r"[^\w\s]", " ", (topic or "").lower()).split()
            if token
        }
        text_tokens = {
            token
            for token in re.sub(r"[^\w\s]", " ", f"{_market_text(market)} {event_title}".lower()).split()
            if token
        }
        if detect_query_type(topic) != "market_watchlist":
            if topic_tokens & {"cut", "cuts", "decrease", "lower"} and not (text_tokens & {"cut", "cuts", "decrease", "lower"}):
                continue
            if topic_tokens & {"hike", "hikes", "increase", "raise"} and not (text_tokens & {"hike", "hikes", "increase", "raise"}):
                continue
        question = market.get("title", "")
        current_probability = _pick_current_probability(market)
        previous_probability = _safe_float(market.get("previous_price_dollars"))
        movement_pct = _safe_optional_float(market.get("movement_24h"))
        if movement_pct is None and current_probability is not None and previous_probability > 0:
            movement_pct = (current_probability - previous_probability) * 100
        best_bid = _normalize_probability(_safe_optional_float(market.get("yes_bid_dollars") or market.get("yes_bid")))
        best_ask = _normalize_probability(_safe_optional_float(market.get("yes_ask_dollars") or market.get("yes_ask")))
        spread = max(0.0, best_ask - best_bid) if best_bid is not None and best_ask is not None else None
        midpoint = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None

        end_date = (
            (market.get("expiration_time") or market.get("close_time") or market.get("expected_expiration_time") or "")[:10]
            or None
        )
        updated = (market.get("updated_time") or market.get("open_time") or "")[:10] or None

        relevance = _market_relevance(topic, market, event_title) if topic else market.get("relevance", 0.5)
        volume = _safe_optional_float(market.get("volume_24h")) or _safe_float(market.get("volume_24h_fp")) or _safe_float(market.get("volume_fp"))
        liquidity = _safe_float(market.get("liquidity_dollars"))
        open_interest = _safe_optional_float(market.get("candlestick_open_interest")) or _safe_float(market.get("open_interest_fp"))
        signal_quality, signal_missing_reason = _market_signal_quality(
            current_probability,
            spread,
            movement_pct,
            volume,
            liquidity,
            open_interest,
            market.get("signal_missing_reason", ""),
        )

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
            "implied_probability": current_probability,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "midpoint": midpoint,
            "movement_24h": movement_pct,
            "volume_24h": volume,
            "market_signal_quality": signal_quality,
            "signal_timestamp": market.get("signal_timestamp") or market.get("updated_time"),
            "signal_missing_reason": signal_missing_reason,
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
