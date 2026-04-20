"""Closing-soon and live-sports Polymarket discovery."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from . import dates, market_types, polymarket, sports_schedule


_INTENT_RE = re.compile(
    r"\b(closing soon|live markets?|live (?:sports )?games?|live sports|in-game|ingame|markets? ending soon|settling soon|ending soon)\b",
    re.I,
)


def is_closing_soon_query(topic: str) -> bool:
    return bool(_INTENT_RE.search(topic or ""))


def wants_live_sports(topic: str) -> bool:
    lowered = (topic or "").lower()
    return bool(
        re.search(r"\b(live games?|live markets?|in-game|ingame|live sports|right now)\b", lowered)
        and re.search(r"\b(sports|nba|mlb|nhl|nfl|game|games|polymarket)\b", lowered)
    )


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


def closing_search_topics(topic: str, live_games: Iterable[sports_schedule.LiveGame] = ()) -> List[str]:
    live_games = list(live_games or ())
    local_today = dates.current_local_date()
    tomorrow = local_today + timedelta(days=1)
    lowered = (topic or "").lower()
    seeds = ["daily", "today", "tomorrow", local_today.isoformat(), tomorrow.isoformat()]
    seeds.extend(_fmt_date_words(local_today))
    if "crypto" in lowered or "bitcoin" in lowered or "ethereum" in lowered or "btc" in lowered or "eth" in lowered:
        seeds.extend([
            f"bitcoin {local_today.strftime('%B %-d')}",
            f"ethereum {local_today.strftime('%B %-d')}",
            f"bitcoin up or down {local_today.strftime('%B %-d')}",
            f"ethereum up or down {local_today.strftime('%B %-d')}",
            f"bitcoin {tomorrow.strftime('%B %-d')}",
            f"ethereum {tomorrow.strftime('%B %-d')}",
        ])
    if "weather" in lowered or "temperature" in lowered:
        seeds.extend([f"temperature {local_today.strftime('%B %-d')}", f"temperature {tomorrow.strftime('%B %-d')}"])
    for game in live_games:
        seeds.append(game.matchup)
        seeds.append(f"{game.league} {game.matchup}")
    sports_topic = any(term in lowered for term in ("sports", "nba", "mlb", "nhl", "nfl", "game", "games"))
    if sports_topic and not live_games:
        seeds.extend(["NBA today", "MLB today", "NHL today", "NFL today"])
    if not any(term in lowered for term in ("crypto", "bitcoin", "ethereum", "weather", "temperature")) and not sports_topic and not live_games:
        seeds.extend(["bitcoin", "ethereum", "temperature"])
    result = []
    seen = set()
    for seed in seeds:
        normalized = re.sub(r"\s+", " ", seed).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result[:12]


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


def _match_live_game(item: dict, live_games: Iterable[sports_schedule.LiveGame]) -> Optional[sports_schedule.LiveGame]:
    text = f"{item.get('title','')} {item.get('question','')}".lower()
    for game in live_games:
        teams = [game.home_team.lower(), game.away_team.lower()]
        if all(team and (team in text or any(part in text for part in team.split() if len(part) > 3)) for team in teams):
            return game
    return None


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


def scan_polymarket_closing_soon(
    topic: str,
    from_date: str,
    to_date: str,
    *,
    window_hours: int = 12,
    live_games: Optional[List[sports_schedule.LiveGame]] = None,
    include_effectively_settled: bool = False,
    now: Optional[datetime] = None,
) -> List[dict]:
    """Return normalized raw Polymarket dicts for near-expiry/live markets."""
    live_games = live_games or []
    local_now = _now_local(now)
    now_utc = local_now.astimezone(timezone.utc)
    window_minutes = int(window_hours * 60)
    events = {}
    for seed in closing_search_topics(topic, live_games):
        response = polymarket.search_polymarket(seed, from_date, to_date, depth="default")
        for event in response.get("events", []):
            event_id = event.get("id") or event.get("slug")
            if event_id:
                events[event_id] = event
    parsed = polymarket.parse_polymarket_response({"events": list(events.values()), "_cap": 200}, topic=topic)
    candidates = []
    for item in parsed:
        end_dt = _parse_end(item.get("end_datetime") or item.get("end_date"))
        if not end_dt:
            continue
        minutes = (end_dt - now_utc).total_seconds() / 60.0
        market_type = market_types.classify_market(item.get("title", ""), item.get("question", ""), item.get("url", ""))
        live_match = _match_live_game(item, live_games) if market_type == "game_outcome" else None
        if minutes < 0:
            continue
        if minutes > window_minutes and not live_match:
            continue
        liquidity = float(item.get("liquidity") or 0.0)
        if liquidity <= 0:
            continue
        if _is_effectively_settled(item) and not include_effectively_settled:
            continue
        reason = "live_sports" if live_match and live_match.is_live else "starting_soon" if live_match else "closing_soon"
        item["minutes_to_close"] = round(minutes, 1)
        item["closing_soon_reason"] = reason
        item["live_game_context"] = live_match.context if live_match else ""
        item["resolvability"] = _resolvability(item)
        item["relevance"] = max(float(item.get("relevance") or 0.0), min(1.0, _closing_score(item, minutes, live_match, window_minutes) / 100.0))
        item["_closing_rank"] = _closing_score(item, minutes, live_match, window_minutes)
        candidates.append(item)
    candidates.sort(key=lambda item: item.get("_closing_rank", 0), reverse=True)
    return candidates[:25]
