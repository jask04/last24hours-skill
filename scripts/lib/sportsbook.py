"""Sportsbook odds context tier for /last24hours v1.0.54.

Surfaces public sportsbook lines (FanDuel, DraftKings, BetMGM, Caesars) as
*informational context* beside the Polymarket + Kalshi anchors. The skill is
paper-only; sportsbook odds are never used to execute trades or size stakes —
they exist so rationales can reference book consensus alongside prediction-market
probabilities.

Implementation goes through the-odds-api.com (https://the-odds-api.com) because
direct scraping of fanduel.com / sportsbook.draftkings.com violates their ToS and
their line data lives behind authenticated XHR endpoints. The free tier covers
NBA/NFL/MLB/NHL pre-game moneyline/spread/total lines at 500 requests/month.

Design notes:
  - Graceful no-key fallback: every helper returns ([], message) when
    ODDS_API_KEY is missing, never raises.
  - Dict-based item shape (mirrors polymarket / kalshi modules).
  - A monthly-usage counter at ~/.local/share/last24hours/sportsbook_usage.json
    is maintained by `record_api_call()` so later releases can enforce a
    per-run cap without surprising the user.
  - No in-play / live / futures / player-prop coverage in v1.0.54 — those
    come with the CS2 player-prop batch (v1.0.55-v1.0.57).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import http

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Sports coverage — the-odds-api keys for pre-game slates we already fan out.
SUPPORTED_SPORTS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
}

# Markets shipped in v1.0.54. Player props deferred to v1.0.57.
DEFAULT_MARKETS = ("h2h", "spreads", "totals")

# Books tracked by default. Override via LAST24HOURS_SPORTSBOOK_BOOKS=csv.
DEFAULT_BOOKS = ("fanduel", "draftkings", "betmgm", "caesars")

# Monthly usage ledger — prevents the free tier (500/mo) from being blown in
# a single bad run. The ledger is advisory; callers should respect
# `within_monthly_budget()`.
USAGE_FILE_DEFAULT = Path.home() / ".local" / "share" / "last24hours" / "sportsbook_usage.json"
MONTHLY_CAP = 480  # leave 20 calls of headroom before the free-tier ceiling

# Cache TTL for pre-game odds in seconds. Pre-game lines move on injury/news,
# not every second — 60s is plenty.
CACHE_TTL_SECONDS = 60

_SPORT_KEYWORDS = {
    "nba": re.compile(r"\bnba\b|basketball|lakers|warriors|celtics|bucks|knicks|mavericks|heat|suns|nuggets|bulls|sixers|76ers|pacers|pistons|spurs|thunder|rockets|kings|pelicans|timberwolves|wolves|jazz|hawks|raptors|cavaliers|cavs|magic|hornets|wizards|nets|grizzlies|clippers|trail blazers|blazers", re.I),
    "nfl": re.compile(r"\bnfl\b|football|chiefs|eagles|niners|49ers|ravens|bills|cowboys|lions|dolphins|jets|giants|patriots|steelers|bengals|browns|texans|colts|titans|jaguars|broncos|raiders|chargers|packers|bears|vikings|saints|falcons|panthers|buccaneers|bucs|seahawks|cardinals|rams|commanders", re.I),
    "mlb": re.compile(r"\bmlb\b|baseball|yankees|red sox|dodgers|giants|cubs|cardinals|braves|phillies|mets|nationals|marlins|pirates|reds|brewers|astros|rangers|athletics|mariners|angels|royals|twins|white sox|tigers|guardians|indians|orioles|blue jays|rays|padres|rockies|diamondbacks|dbacks", re.I),
    "nhl": re.compile(r"\bnhl\b|hockey|rangers|bruins|maple leafs|canadiens|senators|sabres|penguins|flyers|capitals|devils|islanders|blue jackets|hurricanes|panthers|lightning|red wings|blackhawks|avalanche|stars|wild|predators|blues|jets|oilers|flames|canucks|kraken|sharks|ducks|kings|golden knights|coyotes|mammoth", re.I),
}


def detect_sport(topic: str) -> Optional[str]:
    """Return the sport key (nba/nfl/mlb/nhl) a topic references, or None."""
    if not topic:
        return None
    for sport, pattern in _SPORT_KEYWORDS.items():
        if pattern.search(topic):
            return sport
    return None


def american_to_decimal(price: int) -> float:
    """Convert American odds to decimal (European) odds."""
    if price == 0:
        return 1.0
    if price > 0:
        return round(1.0 + (price / 100.0), 4)
    return round(1.0 + (100.0 / abs(price)), 4)


def american_to_implied_probability(price: int) -> float:
    """Convert American odds to implied probability (no vig adjustment)."""
    if price == 0:
        return 0.5
    if price > 0:
        return round(100.0 / (price + 100.0), 4)
    return round(abs(price) / (abs(price) + 100.0), 4)


def get_api_key(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return the-odds-api.com API key from env or config, or None."""
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key.strip() or None
    if config:
        value = config.get("ODDS_API_KEY")
        if value:
            return str(value).strip() or None
    return None


def sportsbook_disabled(config: Optional[Dict[str, Any]] = None) -> bool:
    """Return True when sportsbook source is hard-disabled via env."""
    value = str(
        (config or {}).get("LAST24HOURS_DISABLE_SPORTSBOOK")
        or os.environ.get("LAST24HOURS_DISABLE_SPORTSBOOK")
        or ""
    ).strip().lower()
    return value in {"1", "true", "yes", "on"}


def configured_books(config: Optional[Dict[str, Any]] = None) -> Tuple[str, ...]:
    """Return the configured list of book keys (lowercase)."""
    raw = (
        (config or {}).get("LAST24HOURS_SPORTSBOOK_BOOKS")
        or os.environ.get("LAST24HOURS_SPORTSBOOK_BOOKS")
        or ""
    ).strip()
    if not raw:
        return DEFAULT_BOOKS
    books = tuple(tok.strip().lower() for tok in raw.split(",") if tok.strip())
    return books or DEFAULT_BOOKS


def is_available(config: Optional[Dict[str, Any]] = None) -> bool:
    """Sportsbook source is available when a key is set and not disabled."""
    if sportsbook_disabled(config):
        return False
    return bool(get_api_key(config))


# ---------------------------------------------------------------------------
# Monthly usage ledger
# ---------------------------------------------------------------------------

def _usage_path() -> Path:
    override = os.environ.get("LAST24HOURS_SPORTSBOOK_USAGE_FILE")
    if override:
        return Path(override)
    return USAGE_FILE_DEFAULT


def _current_month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _load_usage() -> Dict[str, Any]:
    path = _usage_path()
    if not path.exists():
        return {"month": _current_month_key(), "count": 0}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {"month": _current_month_key(), "count": 0}
        if data.get("month") != _current_month_key():
            return {"month": _current_month_key(), "count": 0}
        return data
    except (OSError, json.JSONDecodeError):
        return {"month": _current_month_key(), "count": 0}


def _save_usage(data: Dict[str, Any]) -> None:
    path = _usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    except OSError:
        pass  # usage tracking is advisory; never fail a run over it


def record_api_call(n: int = 1) -> int:
    """Increment the monthly counter and return the new total."""
    data = _load_usage()
    data["count"] = int(data.get("count", 0)) + max(0, n)
    _save_usage(data)
    return data["count"]


def within_monthly_budget(reserve: int = 1) -> bool:
    """Return True when there is room for `reserve` more calls this month."""
    data = _load_usage()
    return int(data.get("count", 0)) + max(1, reserve) <= MONTHLY_CAP


def current_month_usage() -> Tuple[int, int]:
    """Return (calls_used, monthly_cap) for diagnostics."""
    data = _load_usage()
    return int(data.get("count", 0)), MONTHLY_CAP


# ---------------------------------------------------------------------------
# HTTP client + parser
# ---------------------------------------------------------------------------

def search_sportsbook(
    topic: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    sport_override: Optional[str] = None,
    markets: Tuple[str, ...] = DEFAULT_MARKETS,
    books: Optional[Tuple[str, ...]] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    """Fetch pre-game odds for the sport implied by `topic`.

    Returns a dict of shape:
      {
        "sport": "nba" | ... | None,
        "events": [<raw the-odds-api event>],
        "error": Optional[str],
        "meta": {"books": [...], "markets": [...], "cached": bool},
      }

    Never raises; failures are captured in `error`. When the API key is missing
    or the topic is not a supported sport, returns an empty payload with a
    descriptive message so callers can surface it in diagnostics without a
    noisy traceback.
    """
    result: Dict[str, Any] = {
        "sport": None,
        "events": [],
        "error": None,
        "meta": {"books": [], "markets": list(markets), "cached": False},
    }

    if sportsbook_disabled(config):
        result["error"] = "sportsbook disabled via LAST24HOURS_DISABLE_SPORTSBOOK"
        return result

    api_key = get_api_key(config)
    if not api_key:
        result["error"] = "ODDS_API_KEY not configured"
        return result

    sport = (sport_override or detect_sport(topic) or "").lower()
    if sport not in SUPPORTED_SPORTS:
        result["error"] = f"unsupported sport for sportsbook tier: {sport or 'none'}"
        return result
    result["sport"] = sport

    book_tuple = tuple(b.lower() for b in (books or configured_books(config)))
    result["meta"]["books"] = list(book_tuple)

    if not within_monthly_budget(reserve=1):
        result["error"] = "sportsbook monthly budget exhausted (>=480/500 calls)"
        return result

    sport_key = SUPPORTED_SPORTS[sport]
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "dateFormat": "iso",
        "bookmakers": ",".join(book_tuple),
    }

    try:
        response = http.get(url, params=params, timeout=timeout, retries=2)
        record_api_call(1)
    except http.HTTPError as e:
        result["error"] = f"HTTPError: {e} (status={getattr(e, 'status_code', None)})"
        return result
    except Exception as e:  # defensive: never propagate
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    if isinstance(response, list):
        result["events"] = response
    elif isinstance(response, dict):
        result["events"] = response.get("events", []) or []
        if response.get("error"):
            result["error"] = str(response["error"])
    else:
        result["error"] = f"unexpected response type: {type(response).__name__}"

    return result


def parse_sportsbook_response(
    response: Dict[str, Any],
    *,
    topic: str = "",
) -> List[Dict[str, Any]]:
    """Flatten raw the-odds-api events into per-quote dict items.

    One event → one item per (book, market_type, outcome) triplet. Each item:
      {
        "kind": "sportsbook_quote",
        "book": "fanduel",
        "sport": "nba",
        "market_type": "moneyline" | "spread" | "total",
        "event_key": "lakers-vs-warriors-2026-04-22",
        "event_title": "Los Angeles Lakers @ Golden State Warriors",
        "commence_time": "2026-04-22T02:30:00Z",
        "side": "Los Angeles Lakers",
        "line": -3.5 | None,
        "price_american": -175,
        "price_decimal": 1.5714,
        "implied_probability": 0.6364,
        "last_update": "2026-04-21T19:05:00Z",
        "url": "",  # the-odds-api free tier does not return per-book deeplinks
        "topic": topic,
      }
    """
    events = response.get("events") if isinstance(response, dict) else response
    if not isinstance(events, list):
        return []

    sport = (response.get("sport") if isinstance(response, dict) else None) or ""
    items: List[Dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue
        home = event.get("home_team") or ""
        away = event.get("away_team") or ""
        commence_time = event.get("commence_time") or ""
        event_key = _event_key(home, away, commence_time)
        event_title = f"{away} @ {home}" if home and away else (event.get("id") or "")

        for book in event.get("bookmakers", []) or []:
            if not isinstance(book, dict):
                continue
            book_key = (book.get("key") or "").lower()
            last_update = book.get("last_update") or ""
            for market in book.get("markets", []) or []:
                if not isinstance(market, dict):
                    continue
                market_key = (market.get("key") or "").lower()
                market_type = _normalize_market_key(market_key)
                if not market_type:
                    continue
                for outcome in market.get("outcomes", []) or []:
                    if not isinstance(outcome, dict):
                        continue
                    try:
                        price_american = int(outcome.get("price"))
                    except (TypeError, ValueError):
                        continue
                    side = outcome.get("name") or ""
                    line_val = outcome.get("point")
                    try:
                        line = float(line_val) if line_val is not None else None
                    except (TypeError, ValueError):
                        line = None
                    items.append({
                        "kind": "sportsbook_quote",
                        "book": book_key,
                        "sport": sport or detect_sport(f"{home} {away} {topic}") or "",
                        "market_type": market_type,
                        "event_key": event_key,
                        "event_title": event_title,
                        "commence_time": commence_time,
                        "side": side,
                        "line": line,
                        "price_american": price_american,
                        "price_decimal": american_to_decimal(price_american),
                        "implied_probability": american_to_implied_probability(price_american),
                        "last_update": last_update,
                        "url": "",
                        "topic": topic,
                    })

    return items


def consensus_rows(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse per-book quotes on the same (event, market, side) into one row.

    Each consensus row records the best American price for bettors of that side
    (highest positive / least-negative), the worst price, and the full book
    breakdown. Rationale surfacing in v1.0.57 will quote these rows directly.
    """
    buckets: Dict[Tuple[str, str, str, Optional[float]], List[Dict[str, Any]]] = {}
    for q in quotes:
        key = (q.get("event_key", ""), q.get("market_type", ""), q.get("side", ""), q.get("line"))
        buckets.setdefault(key, []).append(q)

    rows: List[Dict[str, Any]] = []
    for (event_key, market_type, side, line), group in buckets.items():
        prices = [q.get("price_american") for q in group if isinstance(q.get("price_american"), int)]
        if not prices:
            continue
        best = max(prices)  # best for the bettor — highest positive or least negative
        worst = min(prices)
        implied = sum(q.get("implied_probability", 0.0) for q in group) / len(group)
        sample = group[0]
        rows.append({
            "kind": "sportsbook_consensus",
            "event_key": event_key,
            "event_title": sample.get("event_title", ""),
            "sport": sample.get("sport", ""),
            "market_type": market_type,
            "side": side,
            "line": line,
            "best_price_american": best,
            "worst_price_american": worst,
            "avg_implied_probability": round(implied, 4),
            "books": [
                {
                    "book": q.get("book", ""),
                    "price_american": q.get("price_american"),
                    "last_update": q.get("last_update", ""),
                }
                for q in group
            ],
            "commence_time": sample.get("commence_time", ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MARKET_KEY_ALIASES = {
    "h2h": "moneyline",
    "moneyline": "moneyline",
    "ml": "moneyline",
    "spreads": "spread",
    "spread": "spread",
    "totals": "total",
    "total": "total",
}


def _normalize_market_key(key: str) -> Optional[str]:
    return _MARKET_KEY_ALIASES.get(key.lower()) if key else None


def _event_key(home: str, away: str, commence_time: str) -> str:
    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    date_part = (commence_time or "").split("T")[0]
    return f"{_slug(away)}-vs-{_slug(home)}-{date_part}".strip("-")
