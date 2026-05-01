"""Kalshi prediction market search via public market-data API."""

import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import re

from . import http
from . import evidence_quality as eq
from .query_type import detect_query_type, is_exchange_snapshot_query
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


def _clean_market_text(value: Any) -> str:
    """Normalize exchange-provided display text without changing semantics."""
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+\?", "?", text)
    return text


_LEAGUE_TOKENS = {
    "nba": ("nba", "basketball"),
    "nfl": ("nfl", "football"),
    "mlb": ("mlb", "baseball"),
    "nhl": ("nhl", "hockey"),
}
_MACRO_SERIES_BY_TOKEN = {
    "fed": ["KXFEDDECISION", "KXFED"],
    "fomc": ["KXFEDDECISION", "KXFED"],
    "rates": ["KXFEDDECISION", "KXFED"],
    "rate": ["KXFEDDECISION", "KXFED"],
    "cut": ["KXFEDDECISION", "KXFED"],
    "cuts": ["KXFEDDECISION", "KXFED"],
    "hike": ["KXFEDDECISION", "KXFED"],
    "hikes": ["KXFEDDECISION", "KXFED"],
    "inflation": ["KXCPI"],
    "cpi": ["KXCPI"],
    "jobs": ["KXJOBS"],
    "payrolls": ["KXJOBS"],
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
_BROAD_LIVE_SERIES = [
    "KXBTC",
    "KXETH",
    "KXLLM1",
    "KXCLAUDE",
    "KXGPTCOST",
    "KXFEDDECISION",
    "KXFED",
    "KXCPI",
    "KXJOBS",
    "KXNBAGAME",
    "KXCS2GAME",
    "KXVALGAME",
    "KXLOLGAME",
    "KXCS2",
    "KXVAL",
    "KXLOL",
    "KXESPORTS",
    "KXCCT",
]


def _is_broad_live_board_topic(topic: str) -> bool:
    lowered = (topic or "").lower()
    if is_exchange_snapshot_query(topic, venue="kalshi"):
        return True
    if "kalshi" not in lowered:
        return False
    if not re.search(r"\blive markets?\b|\blive kalshi\b|\bkalshi live\b", lowered):
        return False
    return not re.search(r"\b(closing soon|ending soon|settling soon|in-game|ingame)\b", lowered)


def _series_key(market: Dict[str, Any]) -> str:
    for value in (market.get("series_ticker"), market.get("event_ticker"), market.get("ticker")):
        if value:
            return str(value).split("-", 1)[0]
    return ""


def _diverse_live_candidates(ranked: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
    """Keep broad Kalshi live boards from being filled by one high-volume family."""
    limit = cap * 2
    selected: List[Dict[str, Any]] = []
    seen_tickers: set[str] = set()
    seen_series: set[str] = set()
    seen_events: set[str] = set()

    def add(market: Dict[str, Any]) -> bool:
        ticker = market.get("ticker", "")
        if ticker and ticker in seen_tickers:
            return False
        selected.append(market)
        if ticker:
            seen_tickers.add(ticker)
        series = _series_key(market)
        if series:
            seen_series.add(series)
        event = market.get("event_ticker", "")
        if event:
            seen_events.add(event)
        return len(selected) >= limit

    for market in ranked:
        series = _series_key(market)
        if series and series not in seen_series:
            if add(market):
                return selected

    for market in ranked:
        event = market.get("event_ticker", "")
        if event and event not in seen_events:
            if add(market):
                return selected

    for market in ranked:
        if add(market):
            return selected
    return selected


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
    if eq.is_nba_market_text(topic):
        return "nba"
    topic_lower = topic.lower()
    if "cs2" in topic_lower or "counter strike" in topic_lower or "counter-strike" in topic_lower:
        return "cs2"
    if "valorant" in topic_lower:
        return "valorant"
    if "lol" in topic_lower or "league of legends" in topic_lower:
        return "lol"
    if "esports" in topic_lower:
        return "esports"
    for league, aliases in _LEAGUE_TOKENS.items():
        if any(alias in topic_lower for alias in aliases):
            return league
    return None


def _is_sports_slate_query(topic: str) -> bool:
    topic_lower = topic.lower()
    league = _detect_league(topic)
    if league in ("cs2", "valorant", "lol"):
        return any(term in topic_lower for term in ("matches", "games", "tonight", "today", "slate", "watchlist"))
    return bool(league and any(term in topic_lower for term in ("games tonight", "games today", "tonight", "today", "slate")))


def _is_combo_market(market: Dict[str, Any], event_title: str = "") -> bool:
    text = " ".join(part for part in (_market_text(market), event_title) if part).lower()
    ticker = str(market.get("ticker", "")).lower()
    event_ticker = str(market.get("event_ticker", "")).lower()
    comma_count = text.count(",")
    
    # Allow single match esports even if ticker has multigame (sometimes used for slate grouping)
    if (" vs " in text or " at " in text) and comma_count < 2:
        if any(token in ticker for token in ("cs2", "valorant", "lol", "esports")):
            return False

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


def _snapshot_market_actionability(market: Dict[str, Any]) -> float:
    current_probability = _pick_current_probability(market)
    previous_probability = _safe_float(market.get("previous_price_dollars"))
    movement_pct = None
    if current_probability is not None and previous_probability > 0:
        movement_pct = abs((current_probability - previous_probability) * 100)
    volume = _safe_float(market.get("volume_24h_fp")) or _safe_float(market.get("volume_fp"))
    liquidity = _safe_float(market.get("liquidity_dollars"))
    open_interest = _safe_float(market.get("open_interest_fp"))
    volume_score = min(1.0, math.log1p(volume) / math.log1p(500_000))
    liquidity_score = min(1.0, math.log1p(liquidity) / math.log1p(250_000))
    oi_score = min(1.0, math.log1p(open_interest) / math.log1p(500_000))
    movement_score = min(1.0, (movement_pct or 0.0) / 15.0)
    spread = None
    best_bid = _normalize_probability(_safe_optional_float(market.get("yes_bid_dollars") or market.get("yes_bid")))
    best_ask = _normalize_probability(_safe_optional_float(market.get("yes_ask_dollars") or market.get("yes_ask")))
    if best_bid is not None and best_ask is not None:
        spread = max(0.0, best_ask - best_bid)
    spread_score = max(0.0, min(1.0, 1.0 - ((spread if spread is not None else 0.18) / 0.20)))
    close_text = market.get("close_time") or market.get("expiration_time") or market.get("expected_expiration_time") or ""
    close_score = 0.10
    if close_text:
        try:
            days = max(0.0, (datetime.fromisoformat(str(close_text).replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds() / 86400.0)
            if days <= 1:
                close_score = 1.0
            elif days <= 3:
                close_score = 0.85
            elif days <= 7:
                close_score = 0.65
            elif days <= 14:
                close_score = 0.42
            elif days <= 30:
                close_score = 0.22
            else:
                close_score = 0.06
        except ValueError:
            close_score = 0.10
    return (
        0.34 * close_score +
        0.26 * volume_score +
        0.16 * liquidity_score +
        0.10 * oi_score +
        0.08 * spread_score +
        0.06 * movement_score
    )


def _live_board_event_priority(series_ticker: str, event: Dict[str, Any]) -> tuple[float, float, float]:
    event_dt = _event_datetime(event)
    now = datetime.now(timezone.utc)
    days_score = 0.0
    if event_dt is not None:
        delta_days = (event_dt - now).total_seconds() / 86_400
        if delta_days < -1:
            days_score = 0.0
        elif delta_days <= 1:
            days_score = 1.0
        elif delta_days <= 3:
            days_score = 0.90
        elif delta_days <= 7:
            days_score = 0.74
        elif delta_days <= 21:
            days_score = 0.50
        elif delta_days <= 45:
            days_score = 0.28
        else:
            days_score = max(0.02, 0.24 / (1.0 + (delta_days / 45.0)))

    series_bonus = 0.0
    if series_ticker in {"KXBTC", "KXETH", "KXNBAGAME", "KXCS2GAME", "KXVALGAME", "KXLOLGAME"}:
        series_bonus = 0.18
    elif series_ticker in {"KXLLM1", "KXCLAUDE", "KXGPTCOST"}:
        series_bonus = 0.10
    elif series_ticker in {"KXFEDDECISION", "KXFED", "KXCPI", "KXJOBS"}:
        series_bonus = 0.04

    updated_raw = event.get("last_updated_ts") or event.get("strike_date") or ""
    updated_score = 0.0
    if updated_raw:
        try:
            updated_dt = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
            age_days = max(0.0, (now - updated_dt).total_seconds() / 86_400)
            updated_score = max(0.0, min(1.0, 1.0 - (age_days / 14.0)))
        except ValueError:
            updated_score = 0.0

    return (
        days_score + series_bonus,
        1.0 if event.get("available_on_brokers", True) else 0.0,
        updated_score,
    )


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
    if _is_broad_live_board_topic(topic):
        series.extend(_BROAD_LIVE_SERIES)
    if tokens & {"ai", "llm", "llms", "model", "models", "claude", "chatgpt", "openai", "anthropic", "gemini"}:
        series.extend(["KXLLM1", "KXCLAUDE", "KXGPTCOST"])
    if tokens & {"golf", "pga", "zurich", "masters"}:
        series.append("KXPGATOUR")
    league = _detect_league(topic)
    if league == "nba":
        series.append("KXNBAGAME")
    if league == "cs2":
        series.extend(["KXCS2GAME", "KXCS2", "KXESPORTS", "KXCCT"])
    if league == "valorant":
        series.extend(["KXVALGAME", "KXVAL", "KXESPORTS"])
    if league == "lol":
        series.extend(["KXLOLGAME", "KXLOL", "KXESPORTS"])
    if league == "esports":
        series.extend(["KXCS2GAME", "KXVALGAME", "KXLOLGAME", "KXESPORTS"])
    for token, mapped in _MACRO_SERIES_BY_TOKEN.items():
        if token in tokens:
            series.extend(mapped)
    if tokens & {"bitcoin", "btc", "crypto"}:
        series.append("KXBTC")
    if tokens & {"ethereum", "eth"}:
        series.append("KXETH")
    deduped = []
    seen = set()
    for value in series:
        if value and value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _fetch_events_for_series(series_ticker: str, limit: int = 8) -> List[Dict[str, Any]]:
    params = {"series_ticker": series_ticker, "limit": str(max(limit, 25))}
    url = f"{EVENTS_URL}?{urlencode(params)}"
    try:
        events = http.request("GET", url, timeout=15, retries=2).get("events", [])
        now = datetime.now(timezone.utc)
        upcoming = []
        for event in events:
            event_date = _event_datetime(event)
            if event_date and event_date.date() < now.date():
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
        month_only_match = re.search(r"-(\d{2})([A-Z]{3})(?!\d)", ticker)
        if not month_only_match:
            return None
        year = 2000 + int(month_only_match.group(1))
        month = _MONTHS.get(month_only_match.group(2))
        if not month:
            return None
        try:
            return datetime(year, month, 1, tzinfo=timezone.utc)
        except ValueError:
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
        return http.request("GET", url, timeout=15, retries=2).get("markets", [])
    except Exception as exc:
        _log(f"event markets fetch failed for {event_ticker}: {exc}")
        return []


def _series_markets_for_topic(topic: str, depth: str) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Fetch direct event markets for known high-value Kalshi series."""
    series = _series_for_topic(topic)
    if not series:
        return [], {}
    live_board = _is_broad_live_board_topic(topic)
    if live_board:
        event_fetch_limit = {"quick": 8, "default": 10, "deep": 12}.get(depth, 10)
        event_select_limit = {"quick": 1, "default": 2, "deep": 3}.get(depth, 2)
    elif set(re.sub(r"[^\w\s]", " ", (topic or "").lower()).split()) & {"golf", "pga", "zurich", "masters"}:
        event_limit = {"quick": 25, "default": 35, "deep": 50}.get(depth, 35)
    else:
        event_limit = {"quick": 5, "default": 8, "deep": 12}.get(depth, 8)
    markets: List[Dict[str, Any]] = []
    event_titles: Dict[str, str] = {}
    wanted_months = _topic_months(topic)
    event_tickers: List[str] = []
    if live_board and depth == "quick":
        series_limit = min(12, len(_BROAD_LIVE_SERIES))
    else:
        series_limit = len(_BROAD_LIVE_SERIES) if live_board else 3
    for series_ticker in series[:series_limit]:
        fetch_limit = event_fetch_limit if live_board else event_limit
        events = _fetch_events_for_series(series_ticker, fetch_limit)
        if wanted_months:
            month_matches = [
                event for event in events
                if (event_date := _event_datetime(event)) and event_date.month in wanted_months
            ]
            if month_matches:
                events = month_matches
        if live_board:
            events = sorted(
                events,
                key=lambda event: _live_board_event_priority(series_ticker, event),
                reverse=True,
            )[:event_select_limit]
        for event in events:
            ticker = event.get("event_ticker", "")
            if not ticker:
                continue
            event_titles[ticker] = event.get("title", "")
            event_tickers.append(ticker)
    with ThreadPoolExecutor(max_workers=min(8, len(event_tickers) or 1)) as executor:
        futures = {executor.submit(_fetch_markets_for_event, ticker): ticker for ticker in event_tickers}
        for future in as_completed(futures):
            try:
                markets.extend(future.result())
            except Exception as exc:
                _log(f"series market fetch failed: {exc}")
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


def _topic_target_dates(topic: str, to_date: str) -> set[str]:
    refs = set()
    lowered = (topic or "").lower()
    for match in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", lowered):
        refs.add(f"{match.group(1)}-{match.group(2)}-{match.group(3)}")
    month_pattern = "|".join(sorted(_MONTHS, key=len, reverse=True))
    pattern = rf"\b({month_pattern.lower()})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b"
    default_year = None
    try:
        default_year = datetime.fromisoformat(str(to_date)[:10]).year
    except ValueError:
        pass
    for match in re.finditer(pattern, lowered):
        month = _MONTHS[match.group(1).upper()]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else default_year
        if year and 1 <= day <= 31:
            refs.add(f"{year:04d}-{month:02d}-{day:02d}")
    try:
        base = datetime.fromisoformat(str(to_date)[:10]).date()
    except ValueError:
        base = None
    if base and ("today" in lowered or "tonight" in lowered):
        refs.add(base.isoformat())
    if base and ("tomorrow" in lowered or "tomorrows" in lowered):
        refs.add((base + timedelta(days=1)).isoformat())
    return refs


def _market_event_date(market: Dict[str, Any], event_title: str = "") -> Optional[str]:
    for value in (market.get("event_ticker"), market.get("ticker"), event_title):
        text = str(value or "")
        match = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", text)
        if match:
            year = 2000 + int(match.group(1))
            month = _MONTHS.get(match.group(2))
            day = int(match.group(3))
            if month:
                try:
                    return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
                except ValueError:
                    pass
        month_only_match = re.search(r"-(\d{2})([A-Z]{3})(?!\d)", text)
        if month_only_match:
            year = 2000 + int(month_only_match.group(1))
            month = _MONTHS.get(month_only_match.group(2))
            if month:
                try:
                    return datetime(year, month, 1, tzinfo=timezone.utc).date().isoformat()
                except ValueError:
                    pass
    return None


def _market_in_topic_sports_window(topic: str, market: Dict[str, Any], event_title: str, to_date: str) -> bool:
    if not _detect_league(topic):
        return True
    target_dates = _topic_target_dates(topic, to_date)
    if not target_dates:
        return True
    event_date = _market_event_date(market, event_title)
    if not event_date:
        return True
    return event_date in target_dates


def _market_in_topic_macro_window(topic: str, market: Dict[str, Any], event_title: str = "") -> bool:
    tokens = set(re.sub(r"[^\w\s]", " ", (topic or "").lower()).split())
    if not (tokens & {"fed", "fomc", "rates", "rate", "cut", "cuts", "hike", "hikes", "cpi", "inflation", "jobs", "payrolls"}):
        return True
    wanted_months = _topic_months(topic)
    if not wanted_months:
        return True
    event_date = _market_event_date(market, event_title)
    if not event_date:
        return True
    try:
        return datetime.fromisoformat(event_date).month in wanted_months
    except ValueError:
        return True


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
        return http.request("GET", url, timeout=20, retries=2)
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
    live_board = _is_broad_live_board_topic(topic)

    markets: List[Dict[str, Any]] = []
    if not live_board:
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

    sports_window_filtered = [
        market for market in ranked
        if _market_in_topic_sports_window(topic, market, series_event_titles.get(market.get("event_ticker", ""), ""), to_date)
    ]
    if sports_window_filtered or _topic_target_dates(topic, to_date):
        ranked = sports_window_filtered
    macro_window_filtered = [
        market for market in ranked
        if _market_in_topic_macro_window(topic, market, series_event_titles.get(market.get("event_ticker", ""), ""))
    ]
    if macro_window_filtered:
        ranked = macro_window_filtered

    ranked.sort(
        key=lambda m: (
            -(
                (0.60 * m.get("relevance", 0.0) + 0.40 * _snapshot_market_actionability(m))
                if live_board else m.get("relevance", 0.0)
            ),
            -_safe_float(m.get("volume_24h_fp")) - _safe_float(m.get("volume_fp")),
            -_safe_float(m.get("open_interest_fp")),
        )
    )
    if live_board:
        filtered_ranked = [
            m for m in ranked
            if not _is_combo_market(m) and (_market_has_quality(m) or _pick_current_probability(m) is not None)
        ]
        candidates = _diverse_live_candidates(filtered_ranked or ranked, cap)
    elif _is_sports_slate_query(topic):
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

    event_data: Dict[str, dict] = {}
    event_titles: Dict[str, str] = dict(series_event_titles)
    if not (live_board and depth == "quick"):
        unique_events = sorted({m.get("event_ticker", "") for m in candidates if m.get("event_ticker")})
        with ThreadPoolExecutor(max_workers=min(8, len(unique_events) or 1)) as executor:
            futures = {executor.submit(_fetch_event, ticker): ticker for ticker in unique_events}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    raw_event = future.result().get("event", {})
                    event_data[ticker] = raw_event
                    event_titles[ticker] = raw_event.get("title", "")
                except Exception as exc:
                    _log(f"event fetch failed for {ticker}: {exc}")

    return {"markets": candidates, "event_titles": event_titles, "event_data": event_data, "_cap": cap}


def parse_kalshi_response(response: Dict[str, Any], topic: str = "") -> List[Dict[str, Any]]:
    """Parse Kalshi search response into normalized dicts."""
    items = []
    event_titles = response.get("event_titles", {})
    event_data = response.get("event_data", {})
    cap = response.get("_cap", RESULT_CAP["default"])

    for market in response.get("markets", []):
        ticker = market.get("ticker", "")
        event_ticker = market.get("event_ticker", "")
        series_ticker = market.get("series_ticker", "")
        raw_event = event_data.get(event_ticker, {})
        event_title = _clean_market_text(
            event_titles.get(event_ticker, market.get("subtitle", "")) or market.get("title", "")
        )
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
            if (
                topic_tokens & {"cut", "cuts", "decrease", "lower"}
                and "kxfeddecision" in ticker.lower()
                and not (text_tokens & {"cut", "cuts", "decrease", "lower"})
            ):
                continue
            if (
                topic_tokens & {"hike", "hikes", "increase", "raise"}
                and "kxfeddecision" in ticker.lower()
                and not (text_tokens & {"hike", "hikes", "increase", "raise"})
            ):
                continue
        question = _clean_market_text(market.get("title", ""))
        current_probability = _pick_current_probability(market)
        previous_probability = _safe_float(market.get("previous_price_dollars"))
        movement_pct = _safe_optional_float(market.get("movement_24h"))
        if movement_pct is None and current_probability is not None and previous_probability > 0:
            movement_pct = (current_probability - previous_probability) * 100
        best_bid = _normalize_probability(_safe_optional_float(market.get("yes_bid_dollars") or market.get("yes_bid")))
        best_ask = _normalize_probability(_safe_optional_float(market.get("yes_ask_dollars") or market.get("yes_ask")))
        spread = max(0.0, best_ask - best_bid) if best_bid is not None and best_ask is not None else None
        midpoint = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None

        raw_close_ts = market.get("close_time") or market.get("expiration_time") or market.get("expected_expiration_time") or ""
        end_datetime = raw_close_ts or None
        end_date = (raw_close_ts[:10] or None) if raw_close_ts else None
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
            "end_datetime": end_datetime,
            "rules": raw_event.get("settlement_terms", market.get("rules", "")),
            "description": raw_event.get("description", ""),
            "volume": volume,
            "liquidity": liquidity,
            "open_interest": open_interest,
            "market_type": "macro_binary" if ticker.startswith(("KXFED", "KXCPI", "KXJOBS")) else "",
            "relevance": relevance,
            "why_relevant": f"Kalshi market: {question[:60]}",
        })

    if is_exchange_snapshot_query(topic, venue="kalshi"):
        snapshot_cap = max(cap, 12)
        items.sort(
            key=lambda item: (
                -_snapshot_market_actionability({
                    "last_price_dollars": item.get("current_probability"),
                    "previous_price_dollars": (
                        item.get("current_probability") - ((item.get("movement_24h") or 0.0) / 100.0)
                        if item.get("current_probability") is not None and item.get("movement_24h") is not None
                        else None
                    ),
                    "yes_bid_dollars": item.get("best_bid"),
                    "yes_ask_dollars": item.get("best_ask"),
                    "volume_24h_fp": item.get("volume_24h"),
                    "open_interest_fp": item.get("open_interest"),
                    "liquidity_dollars": item.get("liquidity"),
                    "expiration_time": item.get("end_datetime") or item.get("end_date"),
                }),
                -(item.get("market_signal_quality") or 0.0),
                -(item.get("volume") or 0.0),
                -(item.get("open_interest") or 0.0),
            )
        )
        return items[:snapshot_cap]

    items.sort(
        key=lambda item: (
            -item.get("relevance", 0.0),
            -(item.get("volume") or 0.0),
            -(item.get("open_interest") or 0.0),
        )
    )
    return items[:cap]
