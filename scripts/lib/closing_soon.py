"""Closing-soon and live-sports Polymarket discovery."""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from . import dates, kalshi, market_types, polymarket, sports_schedule


_INTENT_RE = re.compile(
    r"\b(closing soon|live markets?|live (?:sports )?games?|live sports|in-game|ingame|markets? ending soon|settling soon|ending soon)\b",
    re.I,
)


def is_closing_soon_query(topic: str) -> bool:
    return bool(_INTENT_RE.search(topic or ""))


def is_kalshi_live_board_query(topic: str) -> bool:
    """Kalshi's Live page is a broad market board, not only a close-window scan."""
    lowered = (topic or "").lower()
    if "kalshi" not in lowered:
        return False
    if not re.search(r"\blive markets?\b|\blive kalshi\b|\bkalshi live\b", lowered):
        return False
    return not re.search(r"\b(closing soon|ending soon|settling soon|in-game|ingame|right now)\b", lowered)


def wants_live_sports(topic: str) -> bool:
    lowered = (topic or "").lower()
    return bool(
        re.search(r"\b(live games?|live markets?|in-game|ingame|live sports|right now)\b", lowered)
        and re.search(r"\b(sports|nba|mlb|nhl|nfl|game|games|polymarket)\b", lowered)
    )


def preferred_venue(topic: str) -> str:
    lowered = (topic or "").lower()
    if "kalshi" in lowered:
        return "kalshi"
    if "polymarket" in lowered:
        return "polymarket"
    return ""


def infer_closing_window(topic: str, default_hours: int = 12) -> int:
    """Infer an appropriate 'closing soon' window (in hours) based on topic."""
    lowered = (topic or "").lower()
    # High frequency / high volatility -> narrow window
    if any(term in lowered for term in ("crypto", "bitcoin", "ethereum", "btc", "eth", "daily", "today")):
        return 6
    # Sports -> game day window
    if any(term in lowered for term in ("nba", "nfl", "mlb", "nhl", "sports", "game", "games")):
        return 24
    # Macro / Politics / Elections -> much broader window
    if any(term in lowered for term in ("election", "president", "politics", "fed", "rate", "inflation", "cpi")):
        return 72  # 3 days
    # Default
    return default_hours


def _now_local(now: Optional[datetime] = None) -> datetime:
    if now:
        return now.astimezone()
    current = datetime.now().astimezone()
    override = dates.current_local_date()
    return current.replace(year=override.year, month=override.month, day=override.day)


def _parse_end(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _fmt_date_words(day) -> List[str]:
    return [
        day.strftime("%B %-d") if hasattr(day, "strftime") else "",
        day.strftime("%b %-d") if hasattr(day, "strftime") else "",
    ]


def _extend_unique(target: List[str], extra: Iterable[str]) -> None:
    seen = {item.lower() for item in target}
    for seed in extra:
        normalized = re.sub(r"\s+", " ", str(seed or "")).strip()
        if normalized and normalized.lower() not in seen:
            target.append(normalized)
            seen.add(normalized.lower())


def closing_search_topics(
    topic: str,
    live_games: Iterable[sports_schedule.LiveGame] = (),
    *,
    max_seeds: int = 12,
) -> List[str]:
    live_games = list(live_games or ())
    local_today = dates.current_local_date()
    tomorrow = local_today + timedelta(days=1)
    lowered = (topic or "").lower()
    is_crypto = any(token in lowered for token in ("crypto", "bitcoin", "ethereum", "solana", "btc", "eth", "sol"))
    is_weather = any(token in lowered for token in ("weather", "temperature"))
    is_kalshi = "kalshi" in lowered
    sports_topic = any(term in lowered for term in ("sports", "nba", "mlb", "nhl", "nfl", "game", "games"))
    broad_topic = not (is_crypto or is_weather or sports_topic)
    seeds: List[str] = []
    if is_crypto:
        _extend_unique(seeds, [
            f"bitcoin up or down {local_today.strftime('%B %-d')}",
            f"ethereum up or down {local_today.strftime('%B %-d')}",
            f"solana up or down {local_today.strftime('%B %-d')}",
            f"bitcoin {local_today.strftime('%B %-d')}",
            f"ethereum {local_today.strftime('%B %-d')}",
            f"solana {local_today.strftime('%B %-d')}",
            "bitcoin up or down today",
            "ethereum up or down today",
            "solana up or down today",
            "crypto daily",
            "crypto tonight",
        ])
    elif is_kalshi:
        _extend_unique(seeds, [
            f"fed {local_today.strftime('%B %-d')}",
            f"cpi {local_today.strftime('%B %-d')}",
            f"jobs {local_today.strftime('%B %-d')}",
            f"bitcoin {local_today.strftime('%B %-d')}",
            f"temperature {local_today.strftime('%B %-d')}",
            "fed",
            "cpi",
            "jobs",
            "bitcoin",
            "temperature",
        ])
    elif is_weather:
        _extend_unique(seeds, [
            f"temperature {local_today.strftime('%B %-d')}",
            f"temperature {tomorrow.strftime('%B %-d')}",
            "temperature today",
            "temperature tomorrow",
            "weather today",
        ])
    elif sports_topic and not live_games:
        _extend_unique(seeds, ["NBA today", "MLB today", "NHL today", "NFL today", "sports today"])
    elif broad_topic and not live_games:
        _extend_unique(seeds, [
            f"bitcoin up or down {local_today.strftime('%B %-d')}",
            f"ethereum up or down {local_today.strftime('%B %-d')}",
            f"temperature {local_today.strftime('%B %-d')}",
            f"fed {local_today.strftime('%B %-d')}",
            "bitcoin up or down today",
            "ethereum up or down today",
            "temperature today",
            "fed today",
            "NBA today",
            "sports today",
        ])
    _extend_unique(seeds, ["daily", "today", "tomorrow", local_today.isoformat(), tomorrow.isoformat(), *_fmt_date_words(local_today), *_fmt_date_words(tomorrow)])
    for game in live_games:
        for alias in game.live_search_aliases:
            _extend_unique(seeds, [alias, f"{game.league} {alias}"])
        if game.start_time:
            _extend_unique(seeds, [f"{game.league} {game.away_abbreviation} {game.home_abbreviation} {game.start_time[:10]}"])
    if broad_topic and not live_games:
        _extend_unique(seeds, ["bitcoin", "ethereum", "temperature"])
    result = []
    seen = set()
    for seed in seeds:
        normalized = re.sub(r"\s+", " ", seed).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result[:max(1, int(max_seeds or 1))]


def _is_effectively_settled(item: dict) -> bool:
    prices = [float(price) for _, price in item.get("outcome_prices", []) if price is not None]
    if not prices:
        return False
    top = max(prices)
    bottom = min(prices)
    spread = item.get("spread")
    return (top >= 0.985 or bottom <= 0.015) and (spread is None or spread <= 0.01)


def _resolvability(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('question','')} {item.get('url','')}".lower()
    if "up or down" in text or "bitcoin" in text or "ethereum" in text:
        return "crypto reference-price market; verify Polymarket rules and live reference price"
    if "temperature" in text or item.get("market_type") == "weather_binary":
        return "weather market; verify the official station/source before treating it as resolved"
    if market_types.classify_market(item.get("title", ""), item.get("question", ""), item.get("url", "")) == "game_outcome":
        return "sports game outcome; verify live score and market rules"
    return "manual rule check required"


def _clean_token_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())


def _team_aliases(game: sports_schedule.LiveGame, side: str) -> List[str]:
    if side == "home":
        values = [game.home_team, game.home_short_name, game.home_abbreviation]
    else:
        values = [game.away_team, game.away_short_name, game.away_abbreviation]
    aliases = []
    for value in values:
        normalized = " ".join(_clean_token_text(value).split())
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _contains_alias(text: str, aliases: List[str]) -> bool:
    padded = f" {_clean_token_text(text)} "
    tokens = set(padded.split())
    for alias in aliases:
        alias = " ".join(_clean_token_text(alias).split())
        if not alias:
            continue
        if len(alias) <= 3:
            if alias in tokens:
                return True
        elif f" {alias} " in padded:
            return True
        else:
            parts = [part for part in alias.split() if len(part) > 3]
            if parts and any(part in tokens for part in parts):
                return True
    return False


def _match_live_game(item: dict, live_games: Iterable[sports_schedule.LiveGame]) -> Tuple[Optional[sports_schedule.LiveGame], float, str]:
    text = f"{item.get('title','')} {item.get('question','')} {item.get('url','')}"
    for game in live_games:
        home_aliases = _team_aliases(game, "home")
        away_aliases = _team_aliases(game, "away")
        home_match = _contains_alias(text, home_aliases)
        away_match = _contains_alias(text, away_aliases)
        if home_match and away_match:
            exact_names = (
                _clean_token_text(game.home_team) in _clean_token_text(text)
                and _clean_token_text(game.away_team) in _clean_token_text(text)
            )
            exact_abbr = bool(game.home_abbreviation and game.away_abbreviation and _contains_alias(text, [game.home_abbreviation]) and _contains_alias(text, [game.away_abbreviation]))
            confidence = 0.95 if exact_names else 0.85 if exact_abbr else 0.72
            return game, confidence, "direct_match"
    return None, 0.0, "no_live_game_match"


def _sports_reject_reason(item: dict, market_type: str, live_games: Iterable[sports_schedule.LiveGame]) -> str:
    text = f"{item.get('title','')} {item.get('question','')} {item.get('url','')}".lower()
    if "total games" in text or "games o/u" in text:
        return "total_games_prop"
    if "series" in text or "who will win series" in text:
        return "series_market"
    if market_type == "futures":
        return "series_market"
    if market_type in {"player_prop", "team_prop"}:
        return market_type
    live_match, _, reason = _match_live_game(item, live_games)
    if not live_match:
        return "wrong_matchup" if (" vs" in text or " at " in text) else reason
    return "not_direct_game_outcome"


def _closing_score(item: dict, minutes: float, live_match: Optional[sports_schedule.LiveGame], window_minutes: int) -> float:
    liquidity = max(0.0, float(item.get("liquidity") or 0.0))
    volume = max(0.0, float(item.get("volume_24h") or item.get("volume24hr") or 0.0))
    spread = item.get("spread")
    spread_quality = 0.5 if spread is None else max(0.0, 1.0 - min(1.0, float(spread) / 0.12))
    close_score = max(0.0, 1.0 - min(1.0, minutes / max(1, window_minutes)))
    liquidity_score = min(1.0, math.log1p(liquidity) / math.log1p(500_000))
    volume_score = min(1.0, math.log1p(volume) / math.log1p(250_000))
    live_bonus = 0.25 if live_match and live_match.is_live else 0.12 if live_match else 0.0
    return 100 * (0.34 * close_score + 0.24 * liquidity_score + 0.18 * spread_quality + 0.14 * volume_score + live_bonus)


def _kalshi_is_effectively_settled(item: dict) -> bool:
    prob = item.get("current_probability")
    spread = item.get("spread")
    if prob is None:
        return False
    near_edge = prob >= 0.985 or prob <= 0.015
    tight_spread = spread is None or spread <= 0.01
    return near_edge and tight_spread


def scan_kalshi_closing_soon(
    topic: str,
    from_date: str,
    to_date: str,
    *,
    window_hours: int = 12,
    include_effectively_settled: bool = False,
    now: Optional[datetime] = None,
    diagnostics: Optional[dict] = None,
    max_seeds: int = 12,
    max_candidates: int = 25,
    raw_cap_per_seed: int = 40,
    search_depth: str = "default",
) -> List[dict]:
    """Return normalized raw Kalshi dicts for near-expiry markets.

     Mirrors scan_polymarket_closing_soon but uses Kalshi's close_time field and
    skips the live-sports / matchup-rejection paths that only apply to Polymarket
    game-outcome markets.
    """
    if window_hours == 12:
        window_hours = infer_closing_window(topic, 12)
    local_now = _now_local(now)
    now_utc = local_now.astimezone(timezone.utc)
    window_minutes = int(window_hours * 60)
    markets_by_ticker: dict[str, dict] = {}
    raw_seen = 0
    for seed in closing_search_topics(topic, max_seeds=max_seeds):
        response = kalshi.search_kalshi(seed, from_date, to_date, depth=search_depth)
        parsed_markets = kalshi.parse_kalshi_response(response, topic=topic)
        limited_markets = parsed_markets[:max(1, int(raw_cap_per_seed or 1))]
        raw_seen += len(limited_markets)
        for market in limited_markets:
            ticker = market.get("ticker") or market.get("url")
            if ticker and ticker not in markets_by_ticker:
                markets_by_ticker[ticker] = market
    candidates: List[dict] = []
    skipped_no_close = 0
    skipped_expired = 0
    skipped_no_liquidity = 0
    skipped_settled = 0
    for item in markets_by_ticker.values():
        end_dt = _parse_end(item.get("end_datetime") or item.get("end_date"))
        if not end_dt:
            skipped_no_close += 1
            continue
        minutes = (end_dt - now_utc).total_seconds() / 60.0
        if minutes < 0:
            skipped_expired += 1
            continue
        if minutes > window_minutes:
            continue
        liquidity = float(item.get("liquidity") or 0.0)
        volume = float(item.get("volume") or 0.0)
        if liquidity <= 0 and volume <= 0:
            skipped_no_liquidity += 1
            continue
        if _kalshi_is_effectively_settled(item) and not include_effectively_settled:
            skipped_settled += 1
            continue
        close_score = max(0.0, 1.0 - min(1.0, minutes / max(1, window_minutes)))
        liquidity_score = min(1.0, math.log1p(max(liquidity, volume)) / math.log1p(500_000))
        rank = 100 * (0.5 * close_score + 0.35 * liquidity_score + 0.15)
        item["minutes_to_close"] = round(minutes, 1)
        item["closing_soon_reason"] = "closing_soon"
        item["resolvability"] = "Kalshi market; verify contract rules before treating as resolved"
        item["relevance"] = max(float(item.get("relevance") or 0.0), min(1.0, rank / 100.0))
        item["_closing_rank"] = rank
        candidates.append(item)
    candidates.sort(key=lambda item: item.get("_closing_rank", 0), reverse=True)
    if diagnostics is not None:
        diagnostics["kalshi_raw_seen"] = raw_seen
        diagnostics["kalshi_closing_candidates"] = len(candidates)
        diagnostics["kalshi_skipped_no_close"] = skipped_no_close
        diagnostics["kalshi_skipped_expired"] = skipped_expired
        diagnostics["kalshi_skipped_no_liquidity"] = skipped_no_liquidity
        diagnostics["kalshi_skipped_settled"] = skipped_settled
    return candidates[:max(1, int(max_candidates or 1))]


def scan_polymarket_closing_soon(
    topic: str,
    from_date: str,
    to_date: str,
    *,
    window_hours: int = 12,
    live_games: Optional[List[sports_schedule.LiveGame]] = None,
    include_effectively_settled: bool = False,
    now: Optional[datetime] = None,
    diagnostics: Optional[dict] = None,
    max_seeds: int = 12,
    max_candidates: int = 25,
    raw_cap_per_seed: int = 40,
    search_depth: str = "default",
) -> List[dict]:
    """Return normalized raw Polymarket dicts for near-expiry/live markets."""
    if window_hours == 12:
        window_hours = infer_closing_window(topic, 12)
    live_games = live_games or []
    live_only = bool(live_games) and wants_live_sports(topic)
    reject_counts: Counter[str] = Counter()
    local_now = _now_local(now)
    now_utc = local_now.astimezone(timezone.utc)
    window_minutes = int(window_hours * 60)
    events = {}
    raw_seen = 0
    for seed in closing_search_topics(topic, live_games, max_seeds=max_seeds):
        response = polymarket.search_polymarket(seed, from_date, to_date, depth=search_depth)
        raw_events = response.get("events", [])[:max(1, int(raw_cap_per_seed or 1))]
        raw_seen += len(raw_events)
        for event in raw_events:
            event_id = event.get("id") or event.get("slug")
            if event_id:
                events[event_id] = event
    parsed = polymarket.parse_polymarket_response({"events": list(events.values()), "_cap": 200}, topic=topic)
    candidates = []
    skipped_no_close = 0
    skipped_expired = 0
    skipped_no_liquidity = 0
    skipped_settled = 0
    for item in parsed:
        end_dt = _parse_end(item.get("end_datetime") or item.get("end_date"))
        if not end_dt:
            skipped_no_close += 1
            continue
        minutes = (end_dt - now_utc).total_seconds() / 60.0
        market_type = market_types.classify_market(item.get("title", ""), item.get("question", ""), item.get("url", ""))
        live_match = None
        live_confidence = 0.0
        live_reason = ""
        if live_games:
            if market_type == "game_outcome":
                live_match, live_confidence, live_reason = _match_live_game(item, live_games)
                if live_only and not live_match:
                    text = f"{item.get('title','')} {item.get('question','')}".lower()
                    reject_counts["wrong_matchup" if (" vs" in text or " at " in text) else (live_reason or "no_live_game_match")] += 1
                    continue
            elif live_only:
                reject_counts[_sports_reject_reason(item, market_type, live_games)] += 1
                continue
        if minutes < 0:
            skipped_expired += 1
            continue
        if minutes > window_minutes and not live_match:
            continue
        liquidity = float(item.get("liquidity") or 0.0)
        if liquidity <= 0:
            skipped_no_liquidity += 1
            continue
        if _is_effectively_settled(item) and not include_effectively_settled:
            skipped_settled += 1
            continue
        reason = "live_sports" if live_match and live_match.is_live else "starting_soon" if live_match else "closing_soon"
        item["minutes_to_close"] = round(minutes, 1)
        item["closing_soon_reason"] = reason
        item["live_game_context"] = live_match.context if live_match else ""
        item["live_game_league"] = live_match.league if live_match else ""
        item["live_match_confidence"] = round(live_confidence, 2) if live_match else None
        item["live_match_reason"] = live_reason if live_match else ""
        item["resolvability"] = _resolvability(item)
        item["relevance"] = max(float(item.get("relevance") or 0.0), min(1.0, _closing_score(item, minutes, live_match, window_minutes) / 100.0))
        item["_closing_rank"] = _closing_score(item, minutes, live_match, window_minutes)
        candidates.append(item)
    candidates.sort(key=lambda item: item.get("_closing_rank", 0), reverse=True)
    if diagnostics is not None:
        diagnostics["polymarket_raw_seen"] = raw_seen
        diagnostics["polymarket_closing_candidates"] = len(candidates)
        diagnostics["polymarket_skipped_no_close"] = skipped_no_close
        diagnostics["polymarket_skipped_expired"] = skipped_expired
        diagnostics["polymarket_skipped_no_liquidity"] = skipped_no_liquidity
        diagnostics["polymarket_skipped_settled"] = skipped_settled
        diagnostics["live_games"] = len(live_games)
        diagnostics["live_games_live"] = sum(1 for game in live_games if game.is_live)
        diagnostics["live_games_starting_soon"] = sum(1 for game in live_games if not game.is_live)
        diagnostics["live_polymarket_matches"] = sum(1 for item in candidates if item.get("closing_soon_reason") in {"live_sports", "starting_soon"})
        diagnostics["live_reject_reasons"] = dict(sorted(reject_counts.items()))
    return candidates[:max(1, int(max_candidates or 1))]
