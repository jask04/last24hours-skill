#!/usr/bin/env python3
"""Paper forecast ledger for last24hours.

Tracks hypothetical forecasts and market-watchlist picks for calibration.
This module does not place trades, size positions, or provide execution advice.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import plistlib
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = Path.home() / ".local" / "share" / "last24hours"
PAPER_DIR = DATA_DIR / "paper"
LOG_DIR = DATA_DIR / "logs"
DEFAULT_PORTFOLIO = REPO_ROOT / "fixtures" / "paper_portfolio.json"
LAUNCHD_LABEL = "com.jask.last24hours.paper-daily"
LAUNCHD_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"

sys.path.insert(0, str(SCRIPT_DIR))

import store
from lib import http
from lib import sports_schedule, weather


def _skill_version() -> str:
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else ""


def _now_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _load_portfolio(path: Path) -> List[Dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [entry for entry in entries if entry.get("enabled", True)]


def _prob(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def brier_score(probability: float, outcome: float) -> float:
    return (probability - outcome) ** 2


def log_loss(probability: float, outcome: float) -> float:
    p = min(0.99, max(0.01, probability))
    return -(outcome * math.log(p) + (1.0 - outcome) * math.log(1.0 - p))


def _domain(topic: str) -> str:
    lowered = (topic or "").lower()
    tokens = set(re.sub(r"[^\w\s]", " ", lowered).split())
    if "nba" in tokens:
        return "nba"
    if tokens & {"bitcoin", "btc", "ethereum", "eth", "crypto"}:
        return "crypto"
    if tokens & {"fed", "rate", "rates", "cut", "cuts", "inflation", "cpi", "recession"}:
        return "macro"
    if tokens & {"rain", "weather", "storm", "snow"}:
        return "weather"
    if tokens & {"ai", "coding", "model", "models"}:
        return "tech"
    return "broad"


def _probability_bucket(probability: float) -> str:
    if probability < 0.35:
        return "0-35"
    if probability < 0.50:
        return "35-50"
    if probability < 0.65:
        return "50-65"
    if probability < 0.80:
        return "65-80"
    return "80-100"


def _pick_probability_class(probability: Optional[float]) -> str:
    if probability is None:
        return "unknown"
    if probability >= 0.70:
        return "favorite"
    if probability <= 0.30:
        return "longshot"
    return "balanced"


def _parse_iso_date(value: Any) -> Optional[datetime.date]:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _target_date_for_topic(topic: str, created_at: Optional[str] = None) -> datetime.date:
    base = _parse_iso_date(created_at) or datetime.now().astimezone().date()
    lowered = (topic or "").lower()
    if "tomorrow" in lowered or "tmrw" in lowered:
        return base + timedelta(days=1)
    return base


def _slug_from_url(url: str) -> str:
    path = urlparse(url or "").path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else ""


def _market_map(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("id", "")): item for item in items if item.get("id")}


def _poly_key(item: Optional[Dict[str, Any]], outcome_label: str = "") -> str:
    if not item:
        return ""
    return "|".join([
        _slug_from_url(item.get("url", "")),
        item.get("question", "") or item.get("title", ""),
        outcome_label or "",
    ])


def _kalshi_key(item: Optional[Dict[str, Any]]) -> str:
    if not item:
        return ""
    return item.get("ticker") or _slug_from_url(item.get("url", ""))


def _evidence_payload(report: Dict[str, Any], item: Dict[str, Any]) -> str:
    payload = {
        "why_line": item.get("why_line", ""),
        "upside_catalysts": item.get("upside_catalysts", []),
        "downside_catalysts": item.get("downside_catalysts", []),
        "planning_notes": report.get("planning_notes", []),
        "evidence_fusion_stats": report.get("evidence_fusion_stats", {}),
    }
    return json.dumps(payload, sort_keys=True)


def _select_watchlist_item(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Prefer calibration-useful watchlist items when the top item is an extreme favorite."""
    if not items:
        return None
    top_probability = _prob(items[0].get("probability") or items[0].get("implied_probability"))
    if top_probability is None or top_probability < 0.85:
        return items[0]
    for item in items[1:]:
        probability = _prob(item.get("probability") or item.get("implied_probability"))
        if probability is not None and 0.35 <= probability <= 0.80:
            return item
    return items[0]


def extract_paper_picks(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract paper picks from a last24hours JSON report."""
    topic = report.get("topic", "")
    query_type = report.get("query_type") or ("market_watchlist" if report.get("market_watchlist") else "prediction")
    poly_by_id = _market_map(report.get("polymarket", []))
    kalshi_by_id = _market_map(report.get("kalshi", []))
    skill_version = _skill_version()
    picks: List[Dict[str, Any]] = []

    for forecast in report.get("forecasts", []):
        probability = _prob(forecast.get("forecast_probability"))
        if probability is None:
            continue
        poly_item = poly_by_id.get(str(forecast.get("polymarket_market_id") or ""))
        kalshi_item = kalshi_by_id.get(str(forecast.get("kalshi_market_id") or ""))
        anchor = forecast.get("anchor_source", "model_implied")
        if anchor == "kalshi" and kalshi_item:
            venue = "kalshi"
            key = _kalshi_key(kalshi_item)
            url = kalshi_item.get("url", "")
            question = kalshi_item.get("question", "")
            market_type = kalshi_item.get("market_type", "unknown")
            market_probability = _prob(kalshi_item.get("implied_probability") or kalshi_item.get("current_probability"))
            bid = kalshi_item.get("best_bid")
            ask = kalshi_item.get("best_ask")
            spread = kalshi_item.get("spread")
            end_date = kalshi_item.get("end_date")
        elif anchor == "polymarket" and poly_item:
            venue = "polymarket"
            key = _poly_key(poly_item, forecast.get("favorite_label", ""))
            url = poly_item.get("url", "")
            question = poly_item.get("question", "")
            market_type = poly_item.get("market_type", "unknown")
            market_probability = _prob(poly_item.get("implied_probability") or probability)
            bid = poly_item.get("best_bid")
            ask = poly_item.get("best_ask")
            spread = poly_item.get("spread")
            end_date = poly_item.get("end_date")
        elif anchor == "blended":
            venue = "blended"
            key = f"{_poly_key(poly_item, forecast.get('favorite_label', ''))}||{_kalshi_key(kalshi_item)}"
            url = (poly_item or kalshi_item or {}).get("url", "")
            question = (poly_item or kalshi_item or {}).get("question", "")
            market_type = (poly_item or kalshi_item or {}).get("market_type", "unknown")
            market_probability = probability
            bid = ask = spread = None
            end_date = (poly_item or kalshi_item or {}).get("end_date")
        else:
            venue = "weather_api" if anchor == "weather_api" else "model_implied"
            target_date = _target_date_for_topic(topic, report.get("generated_at"))
            key = f"{venue}|{topic}|{forecast.get('title', '')}|{target_date.isoformat()}"
            url = ""
            question = forecast.get("title", "")
            market_type = "weather" if anchor == "weather_api" else "model_implied"
            market_probability = probability
            bid = ask = spread = None
            end_date = target_date.isoformat() if anchor == "weather_api" else None
        if not key:
            continue
        picks.append({
            "topic": topic,
            "query_type": query_type,
            "pick_type": "forecast",
            "venue": venue,
            "venue_market_key": key,
            "market_url": url,
            "title": forecast.get("title", ""),
            "question": question or forecast.get("title", ""),
            "market_type": market_type,
            "outcome_label": forecast.get("favorite_label", "") or "Yes",
            "model_probability": probability,
            "market_probability": market_probability,
            "best_bid": bid,
            "best_ask": ask,
            "spread": spread,
            "anchor_source": anchor,
            "confidence": forecast.get("confidence_level", "low"),
            "end_date": end_date,
            "status": "open" if venue in {"kalshi", "polymarket", "weather_api"} else "unknown",
            "resolution_source": "nws_observations" if venue == "weather_api" else (venue if venue in {"kalshi", "polymarket"} else ""),
            "evidence_json": _evidence_payload(report, forecast),
            "notes_json": json.dumps({"domain": _domain(topic), "paper_only": True}, sort_keys=True),
            "skill_version": skill_version,
        })

    watchlist = report.get("market_watchlist", [])
    if watchlist:
        item = _select_watchlist_item(watchlist)
        if item is None:
            return picks
        probability = _prob(item.get("probability") or item.get("implied_probability"))
        if probability is not None:
            venue = str(item.get("venue") or "").lower()
            source_id = str(item.get("source_item_id") or "")
            source_item = (poly_by_id if venue == "polymarket" else kalshi_by_id).get(source_id)
            key = _kalshi_key(source_item) if venue == "kalshi" else _poly_key(source_item or item, item.get("outcome_label", ""))
            if not key:
                key = f"{venue}|{_slug_from_url(item.get('url', ''))}|{item.get('outcome_label', '')}"
            picks.append({
                "topic": topic,
                "query_type": "market_watchlist",
                "pick_type": "watchlist",
                "venue": venue or item.get("venue", ""),
                "venue_market_key": key,
                "market_url": item.get("url", ""),
                "title": item.get("title", ""),
                "question": item.get("question", ""),
                "market_type": item.get("market_type", "unknown"),
                "outcome_label": item.get("outcome_label", "Top outcome"),
                "model_probability": probability,
                "market_probability": _prob(item.get("market_probability") or item.get("implied_probability") or probability),
                "best_bid": item.get("best_bid"),
                "best_ask": item.get("best_ask"),
                "spread": item.get("spread"),
                "anchor_source": item.get("venue", "").lower(),
                "confidence": "watchlist",
                "end_date": item.get("end_date"),
                "status": "open" if venue in {"kalshi", "polymarket"} else "unknown",
                "resolution_source": venue if venue in {"kalshi", "polymarket"} else "",
                "evidence_json": json.dumps({"catalyst_summary": item.get("catalyst_summary", ""), "risk": item.get("risk", "")}, sort_keys=True),
                "notes_json": json.dumps({
                    "domain": _domain(topic),
                    "paper_only": True,
                    "rank_score": item.get("rank_score"),
                    "minutes_to_close": item.get("minutes_to_close"),
                    "closing_soon_reason": item.get("closing_soon_reason", ""),
                    "live_game_context": item.get("live_game_context", ""),
                    "live_game_league": item.get("live_game_league", ""),
                    "live_match_confidence": item.get("live_match_confidence"),
                    "live_match_reason": item.get("live_match_reason", ""),
                    "resolvability": item.get("resolvability", ""),
                }, sort_keys=True),
                "skill_version": skill_version,
            })
    return picks


def _store_picks(run_id: int, picks: List[Dict[str, Any]]) -> List[int]:
    ids = []
    version = _skill_version()
    for pick in picks:
        payload = dict(pick)
        payload["paper_run_id"] = run_id
        payload["skill_version"] = payload.get("skill_version") or version
        ids.append(store.add_paper_pick(payload))
    return ids


def _run_last24hours(topic: str, quick: bool) -> Dict[str, Any]:
    cmd = [sys.executable, str(SCRIPT_DIR / "last24hours.py"), topic, "--emit=json", "--no-native-web"]
    if quick:
        cmd.append("--quick")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"last24hours exited {result.returncode}")
    return json.loads(result.stdout)


def _resolve_manual(pick_id: int, outcome: str) -> Dict[str, Any]:
    normalized = outcome.strip().lower()
    if normalized in {"1", "true", "yes"}:
        value = 1.0
    elif normalized in {"0", "false", "no"}:
        value = 0.0
    else:
        raise SystemExit("--outcome must be one of 1, 0, true, false, yes, no")
    pick = store.get_paper_pick(pick_id)
    if not pick:
        raise SystemExit(f"Paper pick not found: {pick_id}")
    probability = _prob(pick.get("model_probability"))
    store.update_paper_pick_resolution(
        pick_id,
        status="resolved",
        resolution_value=value,
        resolution_source="manual",
        brier_score=brier_score(probability, value) if probability is not None else None,
        log_loss=log_loss(probability, value) if probability is not None else None,
    )
    return {"pick_id": pick_id, "status": "resolved", "resolution_value": value, "resolution_source": "manual"}


def _resolve_kalshi_payload(pick: Dict[str, Any], payload: Dict[str, Any]) -> tuple[str, Optional[float], str]:
    market = payload.get("market") if isinstance(payload.get("market"), dict) else payload
    status = str(market.get("status") or market.get("market_status") or "").lower()
    if status in {"open", "active", "initialized", "trading"}:
        return "open", None, "kalshi"
    result = str(
        market.get("result")
        or market.get("settlement_result")
        or market.get("settled_result")
        or market.get("winning_outcome")
        or market.get("outcome")
        or ""
    ).lower()
    if result in {"yes", "y", "true"}:
        return "resolved", 1.0, "kalshi"
    if result in {"no", "n", "false"}:
        return "resolved", 0.0, "kalshi"
    if status in {"settled", "finalized", "closed"}:
        return "unknown", None, "kalshi"
    return "unknown", None, "kalshi"


def _resolve_polymarket_payload(pick: Dict[str, Any], payload: Dict[str, Any]) -> tuple[str, Optional[float], str]:
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
        events = payload["events"]
    else:
        events = [payload]
    wanted_question = (pick.get("question") or "").lower()
    wanted_outcome = (pick.get("outcome_label") or "").lower()
    for event in events:
        markets = event.get("markets") or [event]
        for market in markets:
            question = str(market.get("question") or event.get("title") or "").lower()
            if wanted_question and wanted_question[:40] not in question and question[:40] not in wanted_question:
                continue
            winner = str(
                market.get("winner")
                or market.get("winningOutcome")
                or market.get("resolvedOutcome")
                or market.get("resolution")
                or ""
            ).lower()
            if winner:
                return "resolved", 1.0 if winner == wanted_outcome else 0.0, "polymarket"
            resolved_outcomes = market.get("resolvedOutcomes") or market.get("resolved_outcomes") or []
            if isinstance(resolved_outcomes, str):
                try:
                    resolved_outcomes = json.loads(resolved_outcomes)
                except json.JSONDecodeError:
                    resolved_outcomes = []
            if isinstance(resolved_outcomes, list) and resolved_outcomes:
                normalized = {str(value).lower() for value in resolved_outcomes}
                return "resolved", 1.0 if wanted_outcome in normalized else 0.0, "polymarket"
            outcomes = market.get("outcomes") or []
            prices = market.get("outcomePrices") or market.get("outcome_prices") or []
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except json.JSONDecodeError:
                    outcomes = []
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except json.JSONDecodeError:
                    prices = []
            pairs = list(zip(outcomes, prices))
            for label, price in pairs:
                if str(label).lower() == wanted_outcome:
                    p = _prob(price)
                    if p is not None and (p >= 0.99 or p <= 0.01):
                        return "resolved", 1.0 if p >= 0.99 else 0.0, "polymarket"
            event_closed = str(event.get("closed", False)).lower() == "true" or event.get("closed") is True
            market_closed = str(market.get("closed", False)).lower() == "true" or market.get("closed") is True
            if not event_closed and not market_closed:
                return "open", None, "polymarket"
    return "unknown", None, "polymarket"


def _normalize_team_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    aliases = {
        "hawks": "atlanta hawks",
        "knicks": "new york knicks",
        "raptors": "toronto raptors",
        "cavaliers": "cleveland cavaliers",
        "cavs": "cleveland cavaliers",
        "timberwolves": "minnesota timberwolves",
        "wolves": "minnesota timberwolves",
        "nuggets": "denver nuggets",
    }
    return aliases.get(text, text)


def _team_matches(label: str, candidate: str) -> bool:
    wanted = _normalize_team_text(label)
    actual = _normalize_team_text(candidate)
    if not wanted or not actual:
        return False
    if wanted == actual or wanted in actual or actual in wanted:
        return True
    wanted_tokens = wanted.split()
    actual_tokens = set(actual.split())
    return bool(wanted_tokens and wanted_tokens[-1] in actual_tokens)


def _nba_pick_date(pick: Dict[str, Any]) -> Optional[datetime.date]:
    end_date = _parse_iso_date(pick.get("end_date"))
    key = str(pick.get("venue_market_key") or "")
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", key)
    if match:
        return datetime.strptime("-".join(match.groups()), "%Y-%m-%d").date()
    return end_date


def _resolve_nba_pick(pick: Dict[str, Any]) -> Optional[tuple[str, Optional[float], str]]:
    if _domain(str(pick.get("topic") or pick.get("title") or "")) != "nba":
        return None
    game_date = _nba_pick_date(pick)
    if not game_date:
        return None
    if game_date > datetime.now().astimezone().date():
        return "open", None, "espn_nba"

    payload = http.get(
        sports_schedule.ESPN_SCOREBOARD_URL,
        params={"dates": game_date.strftime("%Y%m%d")},
        timeout=15,
        retries=2,
    )
    wanted_title = str(pick.get("title") or pick.get("question") or "")
    wanted_outcome = str(pick.get("outcome_label") or "")
    for event in payload.get("events", []):
        event_name = str(event.get("name") or event.get("shortName") or "")
        competitors = ((event.get("competitions") or [{}])[0].get("competitors") or [])
        labels = []
        winner_label = ""
        for competitor in competitors:
            team = competitor.get("team") or {}
            names = [
                team.get("displayName"),
                team.get("shortDisplayName"),
                team.get("name"),
                team.get("abbreviation"),
            ]
            labels.extend(str(name) for name in names if name)
            if competitor.get("winner") is True:
                winner_label = next((str(name) for name in names if name), "")
        if wanted_title and not any(_team_matches(label, wanted_title) for label in labels):
            continue
        status_type = (((event.get("competitions") or [{}])[0].get("status") or {}).get("type") or {})
        completed = status_type.get("completed") is True or str(status_type.get("name") or "").upper() in {"STATUS_FINAL", "STATUS_FINAL_OT"}
        if not completed:
            return "open", None, "espn_nba"
        if not winner_label:
            return "unknown", None, "espn_nba"
        return "resolved", 1.0 if _team_matches(wanted_outcome, winner_label) else 0.0, "espn_nba"
    return "open" if game_date >= datetime.now().astimezone().date() else "unknown", None, "espn_nba"


def _weather_target_date(pick: Dict[str, Any]) -> datetime.date:
    return (
        _parse_iso_date(pick.get("end_date"))
        or _parse_iso_date(str(pick.get("venue_market_key") or "").rsplit("|", 1)[-1])
        or _target_date_for_topic(str(pick.get("topic") or ""), pick.get("created_at"))
    )


def _resolve_weather_pick(pick: Dict[str, Any]) -> tuple[str, Optional[float], str]:
    target = _weather_target_date(pick)
    today = datetime.now().astimezone().date()
    if target >= today:
        return "open", None, "nws_observations"

    location = weather.resolve_location(str(pick.get("topic") or pick.get("title") or ""))
    if not location:
        return "unknown", None, "nws_observations"
    _, lat, lon = location
    point = http.get(f"{weather.NWS_BASE}/points/{lat:.4f},{lon:.4f}", headers=weather._headers(), timeout=10, retries=2)
    stations_url = (point.get("properties") or {}).get("observationStations")
    if not stations_url:
        return "unknown", None, "nws_observations"
    stations = http.get(stations_url, headers=weather._headers(), timeout=15, retries=2)
    features = stations.get("features") or []
    start = f"{target.isoformat()}T00:00:00Z"
    end = f"{(target + timedelta(days=1)).isoformat()}T00:00:00Z"
    saw_observation = False
    for feature in features[:5]:
        station_url = (feature.get("properties") or {}).get("@id") or feature.get("id")
        if not station_url:
            continue
        try:
            observations = http.get(
                f"{station_url}/observations",
                headers=weather._headers(),
                params={"start": start, "end": end},
                timeout=15,
                retries=2,
            )
        except Exception:
            continue
        for obs in observations.get("features", []):
            props = obs.get("properties") or {}
            saw_observation = True
            precip = ((props.get("precipitationLastHour") or {}).get("value"))
            try:
                if precip is not None and float(precip) > 0:
                    return "resolved", 1.0, "nws_observations"
            except (TypeError, ValueError):
                pass
            description = str(props.get("textDescription") or "").lower()
            if any(term in description for term in ("rain", "shower", "drizzle")):
                return "resolved", 1.0, "nws_observations"
    if saw_observation:
        return "resolved", 0.0, "nws_observations"
    return "unknown", None, "nws_observations"


def _resolve_pick(pick: Dict[str, Any]) -> Dict[str, Any]:
    venue = str(pick.get("venue") or "").lower()
    if venue == "kalshi":
        ticker = pick.get("venue_market_key")
        payload = http.request("GET", f"https://api.elections.kalshi.com/trade-api/v2/markets/{quote(str(ticker))}", timeout=20, retries=1)
        status, value, source = _resolve_kalshi_payload(pick, payload)
    elif venue == "polymarket":
        nba_resolution = _resolve_nba_pick(pick)
        if nba_resolution and nba_resolution[0] != "unknown":
            status, value, source = nba_resolution
        else:
            slug = str(pick.get("venue_market_key") or "").split("|", 1)[0]
            payload = http.request("GET", f"https://gamma-api.polymarket.com/events?slug={quote(slug)}", timeout=20, retries=1)
            status, value, source = _resolve_polymarket_payload(pick, payload)
    elif venue == "weather_api":
        status, value, source = _resolve_weather_pick(pick)
    else:
        return {"pick_id": pick["id"], "status": "unknown", "resolution_source": "manual_required"}
    probability = _prob(pick.get("model_probability"))
    brier = brier_score(probability, value) if status == "resolved" and probability is not None and value is not None else None
    loss = log_loss(probability, value) if status == "resolved" and probability is not None and value is not None else None
    store.update_paper_pick_resolution(
        pick["id"],
        status=status,
        resolution_value=value,
        resolution_source=source,
        brier_score=brier,
        log_loss=loss,
    )
    return {"pick_id": pick["id"], "status": status, "resolution_value": value, "resolution_source": source}


def resolve_open_picks(limit: int = 200) -> List[Dict[str, Any]]:
    results = []
    for pick in store.list_unresolved_paper_picks(limit=limit):
        try:
            results.append(_resolve_pick(pick))
        except Exception as exc:
            source = f"retryable_error:{type(exc).__name__}"
            store.update_paper_pick_resolution(pick["id"], status="open", resolution_source=source)
            results.append({"pick_id": pick["id"], "status": "open", "resolution_source": source, "error": str(exc)[:200]})
    return results


def calibration_summary(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = [p for p in picks if p.get("status") == "resolved" and p.get("resolution_value") is not None]
    if not resolved:
        return {"count": 0, "groups": {}}
    avg_brier = sum(float(p.get("brier_score") or 0) for p in resolved) / len(resolved)
    avg_log_loss = sum(float(p.get("log_loss") or 0) for p in resolved) / len(resolved)
    avg_prob = sum(float(p.get("model_probability") or 0) for p in resolved) / len(resolved)
    observed = sum(float(p.get("resolution_value") or 0) for p in resolved) / len(resolved)
    clv_values = [float(p["closing_line_value"]) for p in resolved if p.get("closing_line_value") is not None]
    probabilities = [float(p.get("model_probability") or 0) for p in resolved]
    favorite_count = sum(1 for probability in probabilities if probability >= 0.70)
    longshot_count = sum(1 for probability in probabilities if probability <= 0.30)
    groups: Dict[str, Dict[str, Any]] = {}
    for field in ("venue", "anchor_source", "pick_type", "market_type", "confidence"):
        for value in sorted({str(p.get(field) or "unknown") for p in resolved}):
            rows = [p for p in resolved if str(p.get(field) or "unknown") == value]
            groups[f"{field}:{value}"] = {
                "count": len(rows),
                "avg_probability": sum(float(p.get("model_probability") or 0) for p in rows) / len(rows),
                "observed_rate": sum(float(p.get("resolution_value") or 0) for p in rows) / len(rows),
                "avg_brier": sum(float(p.get("brier_score") or 0) for p in rows) / len(rows),
            }
    for value in sorted({_domain(str(p.get("topic") or "")) for p in resolved}):
        rows = [p for p in resolved if _domain(str(p.get("topic") or "")) == value]
        groups[f"domain:{value}"] = {
            "count": len(rows),
            "avg_probability": sum(float(p.get("model_probability") or 0) for p in rows) / len(rows),
            "observed_rate": sum(float(p.get("resolution_value") or 0) for p in rows) / len(rows),
            "avg_brier": sum(float(p.get("brier_score") or 0) for p in rows) / len(rows),
        }
    for value in sorted({_probability_bucket(float(p.get("model_probability") or 0)) for p in resolved}):
        rows = [p for p in resolved if _probability_bucket(float(p.get("model_probability") or 0)) == value]
        groups[f"probability_bucket:{value}"] = {
            "count": len(rows),
            "avg_probability": sum(float(p.get("model_probability") or 0) for p in rows) / len(rows),
            "observed_rate": sum(float(p.get("resolution_value") or 0) for p in rows) / len(rows),
            "avg_brier": sum(float(p.get("brier_score") or 0) for p in rows) / len(rows),
        }
    return {
        "count": len(resolved),
        "avg_brier": avg_brier,
        "avg_log_loss": avg_log_loss,
        "avg_probability": avg_prob,
        "observed_rate": observed,
        "favorite_pick_rate": favorite_count / len(resolved),
        "longshot_pick_rate": longshot_count / len(resolved),
        "avg_edge_from_50": sum(abs(probability - 0.50) for probability in probabilities) / len(resolved),
        "avg_closing_line_value": sum(clv_values) / len(clv_values) if clv_values else None,
        "groups": groups,
    }


def open_pick_diagnostics(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    open_picks = [p for p in picks if p.get("status") in {"open", "unknown"}]
    mix = {"favorite": 0, "balanced": 0, "longshot": 0, "unknown": 0}
    manual_only = 0
    missing_version = 0
    model_implied = 0
    for pick in open_picks:
        probability = _prob(pick.get("model_probability"))
        mix[_pick_probability_class(probability)] += 1
        if not pick.get("skill_version"):
            missing_version += 1
        if pick.get("venue") == "model_implied" or pick.get("anchor_source") == "model_implied":
            model_implied += 1
        has_auto_resolver = pick.get("venue") in {"kalshi", "polymarket", "weather_api"} or pick.get("resolution_source") in {"kalshi", "polymarket", "nws_observations", "espn_nba"}
        if pick.get("status") == "unknown" or not has_auto_resolver:
            manual_only += 1
    warnings = []
    total = len(open_picks)
    if total and mix["favorite"] / total >= 0.70:
        warnings.append(f"Open paper portfolio is favorite-heavy: {mix['favorite']} of {total} open picks are 70%+.")
    if model_implied:
        warnings.append(f"{model_implied} open/unknown picks are model-implied and may need manual resolution or a deterministic resolver.")
    if manual_only:
        warnings.append(f"{manual_only} open/unknown picks do not currently have a reliable automatic resolver.")
    if missing_version:
        warnings.append(f"{missing_version} open/unknown picks were created before skill-version tracking and should be treated as legacy samples.")
    return {
        "open_count": total,
        "mix": mix,
        "manual_or_unknown_resolution_count": manual_only,
        "model_implied_count": model_implied,
        "legacy_unversioned_count": missing_version,
        "warnings": warnings,
    }


def pick_quality_warnings(picks: List[Dict[str, Any]]) -> List[str]:
    diagnostics = open_pick_diagnostics(picks)
    return diagnostics["warnings"]


def suggestions_from_summary(summary: Dict[str, Any]) -> List[str]:
    if summary.get("count", 0) < 25:
        return [f"Need at least 25 resolved paper picks for global suggestions; currently have {summary.get('count', 0)}."]
    suggestions = []
    gap = summary["avg_probability"] - summary["observed_rate"]
    if abs(gap) >= 0.05:
        direction = "overconfident" if gap > 0 else "underconfident"
        suggestions.append(f"Global forecasts look {direction} by {abs(gap) * 100:.0f} points across {summary['count']} resolved picks; consider adjusting confidence ranges before changing point probabilities.")
    if summary.get("favorite_pick_rate", 0) >= 0.70:
        suggestions.append(
            f"Paper picks are heavily concentrated in favorites ({summary['favorite_pick_rate'] * 100:.0f}% at 70%+); track win rate alongside Brier/log-loss so the system does not improve by avoiding hard calls."
        )
    for name, group in sorted(summary.get("groups", {}).items()):
        if group["count"] < 10:
            continue
        group_gap = group["avg_probability"] - group["observed_rate"]
        if abs(group_gap) >= 0.08:
            direction = "overconfident" if group_gap > 0 else "underconfident"
            suggestions.append(f"{name} is {direction} by {abs(group_gap) * 100:.0f} points across {group['count']} resolved picks; review this class before changing weights.")
    return suggestions or ["No calibration adjustment suggested yet; resolved paper picks are within conservative thresholds."]


def _write_daily_report(
    run_id: int,
    created: List[int],
    resolved: List[Dict[str, Any]],
    errors: List[str],
    warnings: Optional[List[str]] = None,
) -> Path:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    path = PAPER_DIR / f"paper-daily-{_now_slug()}.json"
    payload = {
        "paper_run_id": run_id,
        "created_pick_ids": created,
        "resolved": resolved,
        "errors": errors,
        "warnings": warnings or [],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def cmd_daily(args) -> None:
    entries = _load_portfolio(Path(args.portfolio))
    if args.dry_run:
        print(json.dumps({"dry_run": True, "topics": [entry["topic"] for entry in entries]}, indent=2))
        return
    started = time.time()
    run_id = store.record_paper_run(Path(args.portfolio).stem, status="running", topics_attempted=len(entries), skill_version=_skill_version())
    created: List[int] = []
    errors: List[str] = []
    warnings: List[str] = []
    for entry in entries:
        try:
            report = _run_last24hours(entry["topic"], quick=args.quick)
            picks = extract_paper_picks(report)
            if not picks:
                warnings.append(f"{entry['topic']}: no usable paper pick found")
            warnings.extend(f"{entry['topic']}: {warning}" for warning in pick_quality_warnings(picks))
            created.extend(_store_picks(run_id, picks))
        except Exception as exc:
            errors.append(f"{entry['topic']}: {type(exc).__name__}: {exc}")
    resolved = resolve_open_picks()
    report_path = _write_daily_report(run_id, created, resolved, errors, warnings)
    store.update_paper_run(
        run_id,
        status="completed" if not errors else "partial",
        picks_created=len(created),
        picks_resolved=sum(1 for item in resolved if item.get("status") == "resolved"),
        report_path=str(report_path),
        error_message="; ".join(errors)[:500],
        duration_seconds=time.time() - started,
    )
    print(json.dumps({"paper_run_id": run_id, "picks_created": len(created), "resolved": resolved, "report_path": str(report_path), "errors": errors, "warnings": warnings}, indent=2))


def cmd_resolve(args) -> None:
    if args.pick_id and args.outcome is not None:
        print(json.dumps(_resolve_manual(args.pick_id, args.outcome), indent=2))
        return
    print(json.dumps({"resolved": resolve_open_picks(limit=args.limit)}, indent=2))


def cmd_report(args) -> None:
    recent = store.list_recent_paper_picks(days=args.days, limit=args.limit)
    summary = calibration_summary(store.list_resolved_paper_picks(days=args.days))
    print(json.dumps({"days": args.days, "summary": summary, "open_portfolio": open_pick_diagnostics(recent), "recent_picks": recent}, indent=2, default=str))


def cmd_suggest(args) -> None:
    summary = calibration_summary(store.list_resolved_paper_picks(days=args.days))
    print(json.dumps({"days": args.days, "summary": summary, "suggestions": suggestions_from_summary(summary)}, indent=2))


def _launchd_plist(time_value: str, load: bool = False) -> Dict[str, Any]:
    hour, minute = [int(part) for part in time_value.split(":", 1)]
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [
            sys.executable,
            str(SCRIPT_DIR / "paper.py"),
            "daily",
            "--portfolio",
            str(DEFAULT_PORTFOLIO),
            "--quick",
        ],
        "WorkingDirectory": str(REPO_ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(LOG_DIR / "paper-daily.out.log"),
        "StandardErrorPath": str(LOG_DIR / "paper-daily.err.log"),
        "RunAtLoad": bool(load),
    }


def cmd_install_launchd(args) -> None:
    plist = _launchd_plist(args.time, load=args.load)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        with LAUNCHD_PATH.open("wb") as fh:
            plistlib.dump(plist, fh)
    command = f"launchctl bootstrap gui/$UID {LAUNCHD_PATH}"
    print(json.dumps({"dry_run": args.dry_run, "plist_path": str(LAUNCHD_PATH), "plist": plist, "load_command": command}, indent=2))
    if args.load and not args.dry_run:
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(LAUNCHD_PATH)], check=False)


def cmd_uninstall_launchd(args) -> None:
    command = f"launchctl bootout gui/$UID {LAUNCHD_PATH}"
    if not args.dry_run:
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(LAUNCHD_PATH)], check=False)
        LAUNCHD_PATH.unlink(missing_ok=True)
    print(json.dumps({"dry_run": args.dry_run, "plist_path": str(LAUNCHD_PATH), "unload_command": command}, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track last24hours hypothetical paper forecasts")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="Run portfolio, store paper picks, and resolve old picks")
    daily.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO))
    daily.add_argument("--quick", action="store_true")
    daily.add_argument("--dry-run", action="store_true")
    daily.set_defaults(func=cmd_daily)

    resolve = sub.add_parser("resolve", help="Resolve open paper picks")
    resolve.add_argument("--pick-id", type=int)
    resolve.add_argument("--outcome")
    resolve.add_argument("--limit", type=int, default=200)
    resolve.set_defaults(func=cmd_resolve)

    report = sub.add_parser("report", help="Print calibration report")
    report.add_argument("--days", type=int, default=30)
    report.add_argument("--limit", type=int, default=50)
    report.set_defaults(func=cmd_report)

    suggest = sub.add_parser("suggest", help="Suggest conservative system improvements")
    suggest.add_argument("--days", type=int, default=90)
    suggest.set_defaults(func=cmd_suggest)

    install = sub.add_parser("install-launchd", help="Install macOS daily LaunchAgent")
    install.add_argument("--time", default="08:00")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--load", action="store_true")
    install.set_defaults(func=cmd_install_launchd)

    uninstall = sub.add_parser("uninstall-launchd", help="Remove macOS daily LaunchAgent")
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall_launchd)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
