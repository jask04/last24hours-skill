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
DRY_RUN_TOPIC_TIMEOUT_SECONDS = 45

sys.path.insert(0, str(SCRIPT_DIR))

import store
from lib import closing_soon, evidence_quality as eq
from lib import http
from lib import sports_schedule, weather


def _skill_version() -> str:
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else ""


def _paper_watchlist_fast_args(topic: str, extra_args: Optional[List[str]] = None) -> List[str]:
    args = list(extra_args or [])
    lowered = (topic or "").lower()
    if not closing_soon.is_closing_soon_query(topic or ""):
        return args
    if "--paper-fast-watchlist" not in args:
        args.append("--paper-fast-watchlist")
    if "--search" in args:
        return args
    if "kalshi" in lowered:
        args.extend(["--search", "kalshi"])
    else:
        args.extend(["--search", "polymarket"])
    return args


def _now_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _load_portfolio(path: Path) -> List[Dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    normalized = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        item = dict(entry)
        if "expected_pick_types" not in item:
            expected = item.get("expected_pick_type")
            item["expected_pick_types"] = [expected] if expected else []
        item.setdefault("last24hours_args", [])
        item.setdefault("pick_policy", "default")
        item.setdefault("dedupe_policy", "allow")
        item.setdefault("dedupe_window_days", 7)
        normalized.append(item)
    return normalized


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
    if eq.is_esports_query(lowered):
        return "esports"
    if tokens & {"bitcoin", "btc", "ethereum", "eth", "crypto"}:
        return "crypto"
    if tokens & {"fed", "rate", "rates", "cut", "cuts", "inflation", "cpi", "recession"}:
        return "macro"
    if tokens & {"rain", "weather", "storm", "snow"}:
        return "weather"
    if tokens & {"ai", "coding", "model", "models"}:
        return "tech"
    return "broad"


def _subdomain(topic: str) -> str:
    lowered = (topic or "").lower()
    return eq.inferred_esports_subdomain(lowered)


def _watchlist_item_reason_class(topic: str, item: Dict[str, Any]) -> str:
    topic_text = str(topic or "")
    if closing_soon.is_closing_soon_query(topic_text):
        return _closing_soon_item_reason_class(topic_text, item)
    if _domain(topic_text) != "esports":
        return ""
    market_text = " ".join(
        str(part or "")
        for part in (
            item.get("title", ""),
            item.get("question", ""),
            item.get("url", ""),
        )
    )
    if not eq.is_esports_query(market_text):
        return "wrong_domain_market"
    topic_subdomain = _subdomain(topic_text)
    market_subdomain = eq.inferred_esports_subdomain(market_text)
    if topic_subdomain and market_subdomain and topic_subdomain != market_subdomain:
        return "wrong_subdomain"
    if eq.is_esports_player_prop_query(topic_text) and str(item.get("market_type") or "") != "esports_prop":
        return "wrong_market_type"
    return ""


def _closing_soon_supported_market_type(item: Dict[str, Any]) -> bool:
    return str(item.get("market_type") or "") in {"crypto_daily", "threshold", "weather_binary", "game_outcome"}


def _closing_soon_topic_domain(topic: str) -> str:
    lowered = (topic or "").lower()
    if "crypto" in lowered or "bitcoin" in lowered or "ethereum" in lowered or "solana" in lowered:
        return "crypto"
    if "kalshi" in lowered:
        return "kalshi"
    return "broad"


def _closing_soon_item_domain(item: Dict[str, Any]) -> str:
    text = " ".join(
        str(part or "")
        for part in (
            item.get("title", ""),
            item.get("question", ""),
            item.get("url", ""),
        )
    )
    market_type = str(item.get("market_type") or "")
    if market_type == "crypto_daily":
        return "crypto"
    if market_type == "weather_binary":
        return "weather"
    if market_type == "game_outcome":
        return "sports"
    inferred = _domain(text)
    if inferred != "broad":
        return inferred
    if market_type == "threshold":
        return "threshold"
    return inferred


def _closing_soon_effectively_settled(item: Dict[str, Any]) -> bool:
    probability = _prob(item.get("probability") or item.get("implied_probability") or item.get("market_probability"))
    spread = item.get("spread")
    if probability is None:
        return False
    tight_spread = spread is None or float(spread) <= 0.01
    return (probability >= 0.985 or probability <= 0.015) and tight_spread


def _closing_soon_item_reason_class(topic: str, item: Dict[str, Any]) -> str:
    if not item:
        return "no_near_expiry_candidates"
    if item.get("minutes_to_close") is None and not item.get("closing_soon_reason"):
        return "no_near_expiry_candidates"
    if _closing_soon_effectively_settled(item):
        return "all_candidates_effectively_settled"
    if not _closing_soon_supported_market_type(item):
        return "all_candidates_low_quality"
    if "manual rule check required" in str(item.get("resolvability") or "").lower():
        return "all_candidates_low_quality"
    topic_domain = _closing_soon_topic_domain(topic)
    if topic_domain == "kalshi" and str(item.get("venue") or "").lower() != "kalshi":
        return "domain_mismatch"
    if topic_domain == "crypto" and _closing_soon_item_domain(item) != "crypto":
        return "domain_mismatch"
    return ""


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


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text.replace("Z", "+00:00"), text):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed
            return parsed.astimezone().replace(tzinfo=None)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _age_bucket(created_at: Any, now: Optional[datetime] = None) -> str:
    created = _parse_timestamp(created_at)
    if created is None:
        return "unknown"
    current = now or datetime.now()
    age_days = max(0.0, (current - created).total_seconds() / 86400.0)
    if age_days < 1:
        return "0-1d"
    if age_days < 3:
        return "1-3d"
    if age_days < 7:
        return "3-7d"
    if age_days < 14:
        return "7-14d"
    return "14d+"


def _safe_json_loads(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(str(raw))
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _stored_rationale_text(pick: Dict[str, Any]) -> str:
    payload = _safe_json_loads(pick.get("evidence_json"))
    return " ".join(
        str(value or "").strip()
        for value in (
            payload.get("why_line", ""),
            payload.get("catalyst_summary", ""),
            payload.get("rationale", ""),
        )
        if value
    ).strip()


def _parse_skill_version_value(value: Any) -> Optional[tuple[int, int, int]]:
    text = str(value or "").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _skill_version_era(value: Any) -> str:
    parsed = _parse_skill_version_value(value)
    if parsed is None:
        return "legacy_unversioned"
    if parsed < (1, 0, 20):
        return "pre_1_0_20"
    if parsed < (1, 0, 24):
        return "v1_0_20_to_1_0_23"
    return "v1_0_24_plus"


def _looks_like_alert_spam(text: str) -> bool:
    raw = (text or "").strip()
    letters = [char for char in raw if char.isalpha()]
    uppercase = [char for char in letters if char.isupper()]
    upper_ratio = (len(uppercase) / len(letters)) if letters else 0.0
    loud_tokens = sum(1 for token in raw.split() if len(token) >= 4 and token.isupper())
    return upper_ratio >= 0.45 or loud_tokens >= 4


def _legacy_noisy_rationale_reason(pick: Dict[str, Any]) -> Optional[str]:
    text = _stored_rationale_text(pick)
    if not text:
        return None
    lowered = text.lower()
    neutral_prefixes = (
        "mostly market-driven right now",
        "no clean market exists",
        "official nws hourly forecast",
        "catalyst context is thin",
        "direct scheduled nba game-outcome market",
        "direct nba game-outcome market",
    )
    if any(prefix in lowered for prefix in neutral_prefixes):
        return None
    tokens = eq.tokenize(text)
    noisy_phrases = {
        "top traders",
        "betting big",
        "most popular bets",
        "stop missing out",
        "keep cashing",
        "signal room",
        "vip picks",
        "daily winners",
    }
    if any(phrase in lowered for phrase in noisy_phrases):
        return "promo_macro_or_crypto"
    if {"parlay", "lock", "tail", "vip", "cashing", "sportsbook", "draftkings", "fanduel"} & tokens:
        return "promo_or_sportsbook"
    if "breaking" in tokens and _looks_like_alert_spam(text):
        return "alert_spam"

    status_terms = {
        "injury", "injuries", "injured", "ruled", "questionable", "doubtful",
        "probable", "available", "inactive", "scratch", "scratched", "status",
        "report", "listed",
    }
    rest_terms = {"rest", "resting", "minutes", "restriction", "restricted", "back-to-back", "b2b"}
    lineup_terms = {"lineup", "lineups", "starter", "starters", "starting", "confirmed", "announced", "expected"}
    elimination_terms = {"elimination", "eliminated", "clinch", "clinched", "must-win"}
    line_move_terms = {"movement", "moved", "steam", "shift", "shifted", "shortened", "drifted"}
    sportsbook_phrases = {
        "ats angle",
        "point spread",
        "moneyline",
        "over/under",
        "market & probabilities",
        "market and probabilities",
        "best bets",
        "predictions for all games",
    }
    media_guide_phrases = {
        "how to watch",
        "live stream",
        "stream it online",
        "tv, live stream",
        "tv and stream",
        "tv channel",
    }
    sports_recap_phrases = {
        "statement win",
        "dominant showing",
        "roll past",
        "rolled past",
        "take down",
        "took down",
        "not backing down",
        "lived up to the hype",
        "game preview",
        "[highlights]",
    }
    has_status_signal = bool(tokens & status_terms)
    has_rest_signal = bool(tokens & rest_terms)
    has_lineup_signal = bool(tokens & lineup_terms and tokens & (status_terms | {"confirmed", "announced", "expected"}))
    has_elimination_signal = bool(tokens & elimination_terms)
    has_line_move_signal = bool(tokens & eq.SPORTS_MARKET_CONTEXT_TERMS and tokens & line_move_terms)
    has_clean_sports_signal = has_status_signal or has_rest_signal or has_lineup_signal or has_elimination_signal or has_line_move_signal
    if not has_clean_sports_signal:
        if any(phrase in lowered for phrase in sportsbook_phrases):
            return "sportsbook_copy"
        if any(phrase in lowered for phrase in media_guide_phrases):
            return "media_guide"
        if any(phrase in lowered for phrase in sports_recap_phrases):
            return "sports_recap"
        if {"ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat"} & tokens:
            return "ticket_chatter"
    return None


def _is_legacy_noisy_rationale(pick: Dict[str, Any]) -> bool:
    return _legacy_noisy_rationale_reason(pick) is not None


def _existing_pick_rows(
    venue_market_key: str,
    *,
    open_only: bool = False,
    window_days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not venue_market_key:
        return []
    conn = store._connect()
    try:
        query = "SELECT * FROM paper_picks WHERE venue_market_key = ?"
        params: List[Any] = [venue_market_key]
        if open_only:
            query += " AND status IN ('open', 'unknown')"
        if window_days is not None:
            query += " AND created_at >= datetime('now', ?)"
            params.append(f"-{max(1, int(window_days))} days")
        query += " ORDER BY created_at DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


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
        "source_health": (report.get("evidence_fusion_stats", {}) or {}).get("source_health", {}),
    }
    return json.dumps(payload, sort_keys=True)


def _select_watchlist_item(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Prefer calibration-useful watchlist items when the top item is an extreme favorite."""
    if not items:
        return None
    if any(item.get("closing_soon_reason") for item in items):
        top = items[0]
        top_probability = _prob(top.get("probability") or top.get("implied_probability"))
        if top_probability is None or top_probability < 0.95:
            return top
        for item in items[1:]:
            probability = _prob(item.get("probability") or item.get("implied_probability"))
            if probability is not None and 0.20 <= probability <= 0.95 and item.get("closing_soon_reason"):
                return item
        return top
    nba_mixed_watchlist = any(str(item.get("watchlist_scope") or "") in {"game", "series"} for item in items)
    if nba_mixed_watchlist:
        top = items[0]
        top_scope = str(top.get("watchlist_scope") or "")
        top_rank = float(top.get("rank_score") or 0)
        if top_scope == "series":
            preferred_game = next(
                (
                    item for item in items[1:]
                    if str(item.get("watchlist_scope") or "") == "game"
                    and float(item.get("rank_score") or 0) >= top_rank - 6
                ),
                None,
            )
            if preferred_game:
                return preferred_game
    top_probability = _prob(items[0].get("probability") or items[0].get("implied_probability"))
    if top_probability is None or top_probability < 0.85:
        return items[0]
    for item in items[1:]:
        probability = _prob(item.get("probability") or item.get("implied_probability"))
        if probability is not None and 0.35 <= probability <= 0.80:
            return item
    return items[0]


def _pick_watchlist_scope(pick: Dict[str, Any]) -> str:
    notes = _safe_json_loads(pick.get("notes_json"))
    return str(notes.get("watchlist_scope") or "")


def _pick_subdomain(pick: Dict[str, Any]) -> str:
    notes = _safe_json_loads(pick.get("notes_json"))
    subdomain = str(notes.get("subdomain") or "")
    if subdomain:
        return subdomain
    inferred = eq.inferred_esports_subdomain(
        " ".join(
            str(part or "")
            for part in (
                pick.get("title", ""),
                pick.get("question", ""),
                pick.get("market_url", ""),
            )
        )
    )
    if inferred:
        return inferred
    return _subdomain(str(pick.get("topic") or ""))


def _esports_market_text(pick: Dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in (
            pick.get("title", ""),
            pick.get("question", ""),
            pick.get("market_url", ""),
            pick.get("venue_market_key", ""),
        )
    ).strip()


def _esports_open_warning_reasons(pick: Dict[str, Any]) -> List[str]:
    if _domain(str(pick.get("topic") or "")) != "esports":
        return []
    reasons: List[str] = []
    market_text = _esports_market_text(pick)
    stored_subdomain = _pick_subdomain(pick)
    inferred_subdomain = eq.inferred_esports_subdomain(market_text)
    market_type = str(pick.get("market_type") or "").strip().lower()
    if not eq.is_esports_query(market_text):
        reasons.append("non_esports_market")
    if stored_subdomain and not inferred_subdomain:
        reasons.append("unsupported_subdomain_label")
    elif stored_subdomain and inferred_subdomain and stored_subdomain != inferred_subdomain:
        reasons.append("subdomain_mismatch")
    if market_type in {"player_prop", "esports_prop"} and not eq.is_esports_player_prop_query(market_text):
        reasons.append("prop_contract_mismatch")
    if market_type == "model_implied":
        reasons.append("model_implied_open")
    if not stored_subdomain:
        reasons.append("missing_subdomain")
    return reasons


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
            "notes_json": json.dumps({
                "domain": _domain(topic),
                "subdomain": _subdomain(topic),
                "paper_only": True,
            }, sort_keys=True),
            "skill_version": skill_version,
        })

    bundles = report.get("paper_bundles", [])
    if bundles:
        bundle = bundles[0]
        legs = bundle.get("legs", [])
        baseline = _prob(bundle.get("combined_probability_independence"))
        leg_keys = []
        for leg in legs:
            leg_keys.append(
                "|".join(
                    str(part or "")
                    for part in (
                        leg.get("venue"),
                        leg.get("source_item_id") or _slug_from_url(leg.get("url", "")),
                        leg.get("outcome_label"),
                    )
                )
            )
        key = f"paper_bundle|{_domain(topic)}|{'||'.join(leg_keys)}"
        picks.append({
            "topic": topic,
            "query_type": "market_watchlist",
            "pick_type": "bundle",
            "venue": "paper_bundle",
            "venue_market_key": key,
            "market_url": "",
            "title": bundle.get("title", "Paper Bundle"),
            "question": bundle.get("title", "Paper Bundle"),
            "market_type": "paper_bundle",
            "outcome_label": "Paper bundle",
            "model_probability": baseline,
            "market_probability": baseline,
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "anchor_source": "paper_bundle",
            "confidence": bundle.get("confidence_bucket", "low"),
            "end_date": None,
            "status": "unknown",
            "resolution_source": "",
            "evidence_json": json.dumps({
                "rationale": bundle.get("rationale", ""),
                "fragility": bundle.get("fragility", ""),
                "correlation_warning": bundle.get("correlation_warning", ""),
            }, sort_keys=True),
            "notes_json": json.dumps({
                "domain": _domain(topic),
                "subdomain": _subdomain(topic),
                "paper_only": True,
                "bundle_id": bundle.get("id", ""),
                "combined_probability_independence": baseline,
                "correlation_warning": bundle.get("correlation_warning", ""),
                "legs": legs,
            }, sort_keys=True),
            "skill_version": skill_version,
        })

    watchlist = report.get("market_watchlist", [])
    if watchlist:
        item = _select_watchlist_item(watchlist)
        if item is None:
            return picks
        if _watchlist_item_reason_class(topic, item):
            return picks
        watchlist_subdomain = _subdomain(topic) or eq.inferred_esports_subdomain(
            " ".join(
                str(part or "")
                for part in (
                    item.get("title", ""),
                    item.get("question", ""),
                    item.get("url", ""),
                )
            )
        )
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
                "evidence_json": json.dumps({
                    "catalyst_summary": item.get("catalyst_summary", ""),
                    "risk": item.get("risk", ""),
                    "source_health": (report.get("evidence_fusion_stats", {}) or {}).get("source_health", {}),
                }, sort_keys=True),
                "notes_json": json.dumps({
                    "domain": _domain(topic),
                    "subdomain": watchlist_subdomain,
                    "paper_only": True,
                    "watchlist_scope": item.get("watchlist_scope", ""),
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


def _run_last24hours(
    topic: str,
    quick: bool,
    extra_args: Optional[List[str]] = None,
    *,
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    forwarded_args = _paper_watchlist_fast_args(topic, extra_args)
    cmd = [sys.executable, str(SCRIPT_DIR / "last24hours.py"), topic, "--emit=json", "--no-native-web"]
    if quick:
        cmd.append("--quick")
    for arg in forwarded_args:
        cmd.append(str(arg))
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"last24hours exited {result.returncode}")
    return json.loads(result.stdout)


def _filter_picks_by_policy(picks: List[Dict[str, Any]], pick_policy: str) -> List[Dict[str, Any]]:
    policy = str(pick_policy or "default").strip().lower()
    if policy == "default":
        return picks
    if policy == "forecast_only":
        return [pick for pick in picks if pick.get("pick_type") == "forecast"]
    if policy == "watchlist_only":
        return [pick for pick in picks if pick.get("pick_type") == "watchlist"]
    if policy == "bundle_only":
        return [pick for pick in picks if pick.get("pick_type") == "bundle"]
    return picks


def _pick_types(picks: List[Dict[str, Any]]) -> List[str]:
    return sorted({str(pick.get("pick_type") or "") for pick in picks if pick.get("pick_type")})


def _validate_expected_pick_types(entry: Dict[str, Any], picks: List[Dict[str, Any]]) -> List[str]:
    expected = [str(value) for value in entry.get("expected_pick_types", []) if value]
    if not expected:
        return []
    actual = _pick_types(picks)
    if not actual:
        return [f"{entry['topic']}: expected pick types {', '.join(expected)} but extracted no paper picks"]
    if not any(pick_type in expected for pick_type in actual):
        return [f"{entry['topic']}: expected pick types {', '.join(expected)} but extracted {', '.join(actual)}"]
    return []


def _apply_dedupe_policy(
    entry: Dict[str, Any],
    picks: List[Dict[str, Any]],
    warnings: List[str],
    debug_counters: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    policy = str(entry.get("dedupe_policy") or "allow").strip().lower()
    if policy == "allow":
        return picks
    window_days = int(entry.get("dedupe_window_days") or 7)
    kept: List[Dict[str, Any]] = []
    for pick in picks:
        key = str(pick.get("venue_market_key") or "")
        if not key:
            kept.append(pick)
            continue
        duplicates = []
        if policy == "skip_if_open_duplicate":
            duplicates = _existing_pick_rows(key, open_only=True)
        elif policy == "skip_if_recent_duplicate":
            duplicates = _existing_pick_rows(key, window_days=window_days)
        if duplicates:
            warnings.append(
                f"{entry['topic']}: skipped duplicate {pick.get('pick_type', 'pick')} for {key} under {policy} ({len(duplicates)} existing row(s))"
            )
            if debug_counters is not None:
                debug_counters["skipped_duplicate_paper_rows"] = int(debug_counters.get("skipped_duplicate_paper_rows", 0) or 0) + 1
            continue
        kept.append(pick)
    return kept


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


COINGECKO_IDS = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
}


def _parse_crypto_threshold(topic: str) -> Optional[tuple[str, str, float]]:
    lowered = (topic or "").lower()
    asset_id = None
    for token, cid in COINGECKO_IDS.items():
        if re.search(rf"\b{token}\b", lowered):
            asset_id = cid
            break
    if not asset_id:
        return None
    direction_match = re.search(r"\b(above|over|greater than|>=|>|below|under|less than|<=|<)\b", lowered)
    if not direction_match:
        return None
    direction_token = direction_match.group(1)
    direction = "above" if direction_token in {"above", "over", "greater than", ">=", ">"} else "below"
    amount_match = re.search(r"(\d+(?:[.,]\d+)?)(k|m|b)?\b", lowered[direction_match.end():])
    if not amount_match:
        return None
    raw_value = amount_match.group(1).replace(",", "")
    try:
        threshold = float(raw_value)
    except ValueError:
        return None
    suffix = amount_match.group(2)
    if suffix == "k":
        threshold *= 1_000
    elif suffix == "m":
        threshold *= 1_000_000
    elif suffix == "b":
        threshold *= 1_000_000_000
    return asset_id, direction, threshold


def _crypto_target_date(pick: Dict[str, Any]) -> "datetime.date":
    parsed = _parse_iso_date(pick.get("end_date"))
    if parsed:
        return parsed
    lowered = str(pick.get("topic") or "").lower()
    base = _parse_iso_date(pick.get("created_at")) or datetime.now().astimezone().date()
    if "today" in lowered:
        return base
    if "tomorrow" in lowered:
        return base + timedelta(days=1)
    if "this week" in lowered or "by end of week" in lowered or "eow" in lowered:
        return base + timedelta(days=(6 - base.weekday()) % 7 or 7)
    if "this month" in lowered or "by end of month" in lowered:
        if base.month == 12:
            return datetime(base.year, 12, 31).date()
        return (datetime(base.year, base.month + 1, 1) - timedelta(days=1)).date()
    return base


def _fetch_crypto_spot(asset_id: str) -> Optional[float]:
    try:
        payload = http.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": asset_id, "vs_currencies": "usd"},
            timeout=15,
            retries=2,
        )
        price = ((payload or {}).get(asset_id) or {}).get("usd")
        if price is not None:
            return float(price)
    except Exception:
        pass
    kraken_pair = {"bitcoin": "XBTUSD", "ethereum": "ETHUSD", "solana": "SOLUSD"}.get(asset_id)
    if not kraken_pair:
        return None
    try:
        payload = http.get(f"https://api.kraken.com/0/public/Ticker", params={"pair": kraken_pair}, timeout=15, retries=1)
        result = (payload or {}).get("result") or {}
        for _, data in result.items():
            last = (data.get("c") or [None])[0]
            if last is not None:
                return float(last)
    except Exception:
        return None
    return None


def _resolve_crypto_pick(pick: Dict[str, Any]) -> tuple[str, Optional[float], str]:
    parsed = _parse_crypto_threshold(str(pick.get("topic") or pick.get("title") or ""))
    if not parsed:
        return "unknown", None, "manual_required"
    asset_id, direction, threshold = parsed
    target = _crypto_target_date(pick)
    today = datetime.now().astimezone().date()
    if target > today:
        return "open", None, "coingecko"
    spot = _fetch_crypto_spot(asset_id)
    if spot is None:
        return "unknown", None, "coingecko"
    hit = spot >= threshold if direction == "above" else spot <= threshold
    return "resolved", 1.0 if hit else 0.0, "coingecko"


def _resolve_pick(pick: Dict[str, Any]) -> Dict[str, Any]:
    venue = str(pick.get("venue") or "").lower()
    topic = str(pick.get("topic") or pick.get("title") or "")
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
    elif _domain(topic) == "crypto":
        status, value, source = _resolve_crypto_pick(pick)
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


def _scope_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    return {
        "count": n,
        "avg_probability": sum(float(p.get("model_probability") or 0) for p in rows) / n,
        "observed_rate": sum(float(p.get("resolution_value") or 0) for p in rows) / n,
        "avg_brier": sum(float(p.get("brier_score") or 0) for p in rows) / n,
    }


def _add_scope_groups(
    groups: Dict[str, Dict[str, Any]],
    resolved: List[Dict[str, Any]],
    axis: str,
    bucket_fn,
    *,
    skip_empty: bool = False,
) -> None:
    values = {bucket_fn(p) for p in resolved}
    if skip_empty:
        values = {v for v in values if v}
    for value in sorted(values):
        rows = [p for p in resolved if bucket_fn(p) == value]
        if not rows:
            continue
        groups[f"{axis}:{value}"] = _scope_summary(rows)


def calibration_summary(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    resolved_all = [p for p in picks if p.get("status") == "resolved" and p.get("resolution_value") is not None]
    legacy_noisy_count = sum(1 for pick in resolved_all if _is_legacy_noisy_rationale(pick))
    resolved = [pick for pick in resolved_all if not _is_legacy_noisy_rationale(pick)]
    if not resolved:
        return {
            "count": 0,
            "raw_resolved_count": len(resolved_all),
            "excluded_legacy_noisy_count": legacy_noisy_count,
            "groups": {},
        }
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
        _add_scope_groups(groups, resolved, field, lambda p, f=field: str(p.get(f) or "unknown"))
    _add_scope_groups(groups, resolved, "domain", lambda p: _domain(str(p.get("topic") or "")))
    _add_scope_groups(groups, resolved, "subdomain", _pick_subdomain, skip_empty=True)
    _add_scope_groups(
        groups,
        resolved,
        "probability_bucket",
        lambda p: _probability_bucket(float(p.get("model_probability") or 0)),
    )
    _add_scope_groups(groups, resolved, "watchlist_scope", _pick_watchlist_scope, skip_empty=True)
    return {
        "count": len(resolved),
        "raw_resolved_count": len(resolved_all),
        "excluded_legacy_noisy_count": legacy_noisy_count,
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


def current_skill_comparable_summary(
    picks: List[Dict[str, Any]],
    *,
    min_version: str = "1.0.24",
) -> Dict[str, Any]:
    resolved_all = [p for p in picks if p.get("status") == "resolved" and p.get("resolution_value") is not None]
    minimum = _parse_skill_version_value(min_version)
    comparable: List[Dict[str, Any]] = []
    excluded_legacy_noisy = 0
    excluded_pre_current = 0
    excluded_unversioned = 0
    for pick in resolved_all:
        if _is_legacy_noisy_rationale(pick):
            excluded_legacy_noisy += 1
            continue
        version = _parse_skill_version_value(pick.get("skill_version"))
        if version is None:
            excluded_unversioned += 1
            continue
        if minimum and version < minimum:
            excluded_pre_current += 1
            continue
        comparable.append(pick)
    summary = calibration_summary(comparable)
    summary["min_skill_version"] = min_version
    summary["raw_resolved_count"] = len(resolved_all)
    summary["excluded_legacy_noisy_count"] = excluded_legacy_noisy
    summary["excluded_pre_current_version_count"] = excluded_pre_current
    summary["excluded_unversioned_count"] = excluded_unversioned
    return summary


def post_1_0_30_nba_watchlist_summary(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    minimum = _parse_skill_version_value("1.0.30")
    filtered = []
    for pick in picks:
        if pick.get("status") != "resolved" or pick.get("resolution_value") is None:
            continue
        version = _parse_skill_version_value(pick.get("skill_version"))
        if version is None or version < minimum:
            continue
        if pick.get("pick_type") != "watchlist" or _domain(str(pick.get("topic") or "")) != "nba":
            continue
        if _is_legacy_noisy_rationale(pick):
            continue
        filtered.append(pick)
    summary = calibration_summary(filtered)
    summary["min_skill_version"] = "1.0.30"
    summary["pick_type"] = "watchlist"
    summary["domain"] = "nba"
    return summary


def post_1_0_38_esports_summary(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    minimum = _parse_skill_version_value("1.0.38")
    filtered = []
    for pick in picks:
        if pick.get("status") != "resolved" or pick.get("resolution_value") is None:
            continue
        version = _parse_skill_version_value(pick.get("skill_version"))
        if version is None or version < minimum:
            continue
        if _domain(str(pick.get("topic") or "")) != "esports":
            continue
        if _is_legacy_noisy_rationale(pick):
            continue
        filtered.append(pick)
    summary = calibration_summary(filtered)
    summary["min_skill_version"] = "1.0.38"
    summary["domain"] = "esports"
    summary["pick_type_visibility"] = sorted({str(pick.get("pick_type") or "") for pick in filtered if pick.get("pick_type")})
    summary["subdomain_visibility"] = sorted({_pick_subdomain(pick) for pick in filtered if _pick_subdomain(pick)})
    summary["market_type_visibility"] = sorted({str(pick.get("market_type") or "") for pick in filtered if pick.get("market_type")})
    summary["missing_subdomain_count"] = sum(1 for pick in filtered if not _pick_subdomain(pick))
    if summary.get("count", 0) == 0:
        summary["empty_reason"] = "No resolved post-1.0.38 esports paper rows yet."
        summary["operator_note"] = "eSports reporting is wired up, but no post-1.0.38 esports paper rows have resolved yet."
        summary["pick_type_visibility"] = []
        summary["market_type_visibility"] = []
    elif summary["missing_subdomain_count"]:
        summary["operator_note"] = (
            f"{summary['missing_subdomain_count']} resolved post-1.0.38 esports paper row(s) "
            "still have empty subdomain labeling and should be treated as degraded audit samples."
        )
    return summary


def closing_soon_health_summary(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    relevant = []
    for pick in picks:
        if pick.get("pick_type") != "watchlist":
            continue
        topic = str(pick.get("topic") or "")
        if not closing_soon.is_closing_soon_query(topic):
            continue
        relevant.append(pick)
    summary = {
        "count": len(relevant),
        "open_count": sum(1 for pick in relevant if pick.get("status") in {"open", "unknown"}),
        "resolved_count": sum(1 for pick in relevant if pick.get("status") == "resolved"),
        "by_venue": {},
        "by_market_type": {},
        "open_anchor_mix": {"anchored": 0, "model_implied": 0},
        "empty_reason": "",
    }
    if not relevant:
        summary["empty_reason"] = "No closing-soon watchlist rows in the selected report window."
        return summary
    venues = sorted({str(pick.get("venue") or "") for pick in relevant if pick.get("venue")})
    market_types = sorted({str(pick.get("market_type") or "") for pick in relevant if pick.get("market_type")})
    summary["by_venue"] = {venue: sum(1 for pick in relevant if str(pick.get("venue") or "") == venue) for venue in venues}
    summary["by_market_type"] = {market_type: sum(1 for pick in relevant if str(pick.get("market_type") or "") == market_type) for market_type in market_types}
    for pick in relevant:
        if pick.get("status") not in {"open", "unknown"}:
            continue
        if str(pick.get("anchor_source") or "") == "model_implied":
            summary["open_anchor_mix"]["model_implied"] += 1
        else:
            summary["open_anchor_mix"]["anchored"] += 1
    return summary


def _is_degraded_report(report: Dict[str, Any]) -> bool:
    forecasts = report.get("forecasts") or []
    if any(bool(item.get("model_implied")) for item in forecasts):
        return True
    source_status = (((report.get("evidence_fusion_stats") or {}).get("source_health") or {}).get("source_status") or {})
    return any(str(info.get("status") or "") in {"degraded", "error", "blocked"} for info in source_status.values() if isinstance(info, dict))


def _closing_note_value(report: Dict[str, Any], prefix: str) -> int:
    for note in report.get("planning_notes") or []:
        if isinstance(note, str) and note.startswith(prefix):
            try:
                return int(note.split(":", 1)[1])
            except (IndexError, ValueError):
                return 0
    return 0


def _closing_soon_raw_candidates(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for bucket in ("polymarket", "kalshi"):
        for item in report.get(bucket) or []:
            if item.get("minutes_to_close") is not None or item.get("closing_soon_reason"):
                candidates.append(item)
    return candidates


def _closing_soon_reason_class_for_report(topic: str, report: Dict[str, Any]) -> str:
    raw_candidates = _closing_soon_raw_candidates(report)
    if not raw_candidates:
        skipped_settled = _closing_note_value(report, "closing-pm-skipped-settled:") + _closing_note_value(report, "closing-ka-skipped-settled:")
        if skipped_settled > 0:
            return "all_candidates_effectively_settled"
        return "no_near_expiry_candidates"
    compatible = [item for item in raw_candidates if not _closing_soon_item_reason_class(topic, item)]
    if compatible:
        return ""
    reasons = {_closing_soon_item_reason_class(topic, item) for item in raw_candidates}
    for preferred in ("domain_mismatch", "all_candidates_effectively_settled", "all_candidates_low_quality"):
        if preferred in reasons:
            return preferred
    return "all_candidates_low_quality"


def _bundle_reason_class_for_report(report: Dict[str, Any]) -> str:
    reason = str(report.get("paper_bundle_reason") or "").strip().lower()
    if not reason:
        return ""
    if "no future nba games found" in reason or "no nba games for the requested date window" in reason:
        return "no_future_games_in_window"
    if "marks them final" in reason or "already live" in reason or "scheduled and not already live" in reason:
        return "all_games_live_or_final"
    if "same-game or same-team overlap" in reason or "favorite-only" in reason:
        return "bundle_overlap_or_favorite_only"
    if (
        "too few direct nba game-outcome markets" in reason
        or "too few direct nba game markets" in reason
        or "trusted espn" in reason
        or "usable probabilities" in reason
        or "positive liquidity" in reason
        or "no watchlist markets cleared" in reason
    ):
        return "too_few_qualified_direct_markets"
    return "no_compatible_market"


def _report_market_subdomains(report: Dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for bucket in ("polymarket", "kalshi"):
        for item in report.get(bucket) or []:
            text = " ".join(
                str(part or "")
                for part in (
                    item.get("title", ""),
                    item.get("question", ""),
                    item.get("url", ""),
                    item.get("ticker", ""),
                    item.get("event_ticker", ""),
                )
            )
            subdomain = eq.inferred_esports_subdomain(text)
            if subdomain:
                values.add(subdomain)
    return values


def _dry_run_reason_class(entry: Dict[str, Any], report: Dict[str, Any], picks: List[Dict[str, Any]]) -> str:
    if picks:
        return ""
    if _is_degraded_report(report):
        return "degraded_evidence_only"
    topic = str(entry.get("topic") or "")
    if str(entry.get("pick_policy") or "").strip().lower() == "bundle_only":
        reason = _bundle_reason_class_for_report(report)
        if reason:
            return reason
    if closing_soon.is_closing_soon_query(topic):
        reason = _closing_soon_reason_class_for_report(topic, report)
        if reason:
            return reason
    watchlist = report.get("market_watchlist") or []
    if watchlist:
        reason = _watchlist_item_reason_class(topic, _select_watchlist_item(watchlist) or {})
        if reason:
            return reason
    topic_subdomain = _subdomain(topic)
    market_subdomains = _report_market_subdomains(report)
    if topic_subdomain and market_subdomains and topic_subdomain not in market_subdomains:
        return "wrong_subdomain"
    return "no_compatible_market"


def _daily_dry_run_entry(entry: Dict[str, Any], *, quick: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "topic": entry["topic"],
        "last24hours_args": list(entry.get("last24hours_args", [])),
        "pick_policy": entry.get("pick_policy", "default"),
        "dedupe_policy": entry.get("dedupe_policy", "allow"),
        "expected_pick_types": list(entry.get("expected_pick_types", [])),
        "warnings": [],
    }
    debug_counters: Dict[str, int] = {}
    started = time.time()
    try:
        report = _run_last24hours(
            entry["topic"],
            quick=quick,
            extra_args=entry.get("last24hours_args", []),
            timeout_seconds=DRY_RUN_TOPIC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["elapsed_seconds"] = round(time.time() - started, 2)
        result["warnings"].append(
            f"{entry['topic']}: dry-run timed out after {DRY_RUN_TOPIC_TIMEOUT_SECONDS}s before a usable paper result was produced."
        )
        return result
    except Exception as exc:
        result["status"] = "error"
        result["elapsed_seconds"] = round(time.time() - started, 2)
        result["warnings"].append(f"{entry['topic']}: dry-run failed with {type(exc).__name__}: {exc}")
        return result
    picks = extract_paper_picks(report)
    result["extracted_pick_count"] = len(picks)
    picks = _filter_picks_by_policy(picks, entry.get("pick_policy", "default"))
    result["post_policy_pick_count"] = len(picks)
    picks = _apply_dedupe_policy(entry, picks, result["warnings"], debug_counters)
    result["post_dedupe_pick_count"] = len(picks)
    result["pick_types"] = _pick_types(picks)
    result["warnings"].extend(_validate_expected_pick_types(entry, picks))
    if picks:
        result["warnings"].extend(pick_quality_warnings(picks))
    duplicate_skip = any("skipped duplicate" in warning for warning in result["warnings"])
    if not picks and duplicate_skip:
        result["status"] = "duplicate_skip"
    elif not picks and _is_degraded_report(report):
        result["status"] = "degraded_run"
        result["reason_class"] = "degraded_evidence_only"
        result["warnings"].append(f"{entry['topic']}: no usable paper pick found because the run degraded or only degraded evidence-level output remained.")
    elif not picks:
        result["reason_class"] = _dry_run_reason_class(entry, report, picks)
        result["status"] = "no_compatible_pick"
        result["warnings"].append(
            f"{entry['topic']}: no usable paper pick found after policy and compatibility filters (reason_class={result['reason_class']})."
        )
    else:
        result["status"] = "ready"
    if debug_counters:
        result["debug_counters"] = debug_counters
    result["elapsed_seconds"] = round(time.time() - started, 2)
    return result


def open_pick_diagnostics(picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    open_picks = [p for p in picks if p.get("status") in {"open", "unknown"}]
    mix = {"favorite": 0, "balanced": 0, "longshot": 0, "unknown": 0}
    manual_only = 0
    missing_version = 0
    model_implied = 0
    paper_bundle_count = 0
    legacy_noisy_rationale_count = 0
    by_skill_version: Dict[str, int] = {}
    by_pick_type: Dict[str, int] = {}
    by_domain: Dict[str, int] = {}
    by_subdomain: Dict[str, int] = {}
    by_watchlist_scope: Dict[str, int] = {}
    by_age_bucket: Dict[str, int] = {}
    by_version_era: Dict[str, int] = {}
    duplicate_keys: Dict[str, int] = {}
    duplicate_rows: Dict[str, List[Dict[str, Any]]] = {}
    mixed_scope_clusters = []
    legacy_noisy_by_skill_version: Dict[str, int] = {}
    legacy_noisy_by_pick_type: Dict[str, int] = {}
    legacy_noisy_by_domain: Dict[str, int] = {}
    legacy_noisy_by_subdomain: Dict[str, int] = {}
    legacy_noisy_by_reason: Dict[str, int] = {}
    legacy_noisy_examples: List[Dict[str, Any]] = []
    source_health_status_rollup: Dict[str, Dict[str, int]] = {}
    esports_rows: List[Dict[str, Any]] = []
    esports_flagged_rows: List[Dict[str, Any]] = []
    esports_flagged_by_reason: Dict[str, int] = {}
    now = datetime.now()
    for pick in open_picks:
        is_paper_bundle = pick.get("pick_type") == "bundle" or pick.get("venue") == "paper_bundle"
        if is_paper_bundle:
            paper_bundle_count += 1
        probability = _prob(pick.get("model_probability"))
        mix[_pick_probability_class(probability)] += 1
        noisy_reason = _legacy_noisy_rationale_reason(pick)
        if noisy_reason:
            legacy_noisy_rationale_count += 1
        skill_version = str(pick.get("skill_version") or "")
        if not skill_version:
            missing_version += 1
            skill_bucket = "legacy_unversioned"
        else:
            skill_bucket = skill_version
        by_skill_version[skill_bucket] = by_skill_version.get(skill_bucket, 0) + 1
        version_era = _skill_version_era(skill_version)
        by_version_era[version_era] = by_version_era.get(version_era, 0) + 1
        pick_type = str(pick.get("pick_type") or "unknown")
        by_pick_type[pick_type] = by_pick_type.get(pick_type, 0) + 1
        domain = _domain(str(pick.get("topic") or ""))
        by_domain[domain] = by_domain.get(domain, 0) + 1
        subdomain = _pick_subdomain(pick)
        if subdomain:
            by_subdomain[subdomain] = by_subdomain.get(subdomain, 0) + 1
        watchlist_scope = _pick_watchlist_scope(pick)
        if watchlist_scope:
            by_watchlist_scope[watchlist_scope] = by_watchlist_scope.get(watchlist_scope, 0) + 1
        if noisy_reason:
            legacy_noisy_by_skill_version[skill_bucket] = legacy_noisy_by_skill_version.get(skill_bucket, 0) + 1
            legacy_noisy_by_pick_type[pick_type] = legacy_noisy_by_pick_type.get(pick_type, 0) + 1
            legacy_noisy_by_domain[domain] = legacy_noisy_by_domain.get(domain, 0) + 1
            if subdomain:
                legacy_noisy_by_subdomain[subdomain] = legacy_noisy_by_subdomain.get(subdomain, 0) + 1
            legacy_noisy_by_reason[noisy_reason] = legacy_noisy_by_reason.get(noisy_reason, 0) + 1
            if len(legacy_noisy_examples) < 8:
                legacy_noisy_examples.append({
                    "id": pick.get("id"),
                    "skill_version": skill_bucket,
                    "domain": domain,
                    "subdomain": subdomain,
                    "pick_type": pick_type,
                    "reason": noisy_reason,
                    "title": pick.get("title") or pick.get("topic") or "",
                    "created_at": pick.get("created_at"),
                    "why_line_excerpt": _stored_rationale_text(pick)[:180],
                })
        age_bucket = _age_bucket(pick.get("created_at"), now=now)
        by_age_bucket[age_bucket] = by_age_bucket.get(age_bucket, 0) + 1
        key = str(pick.get("venue_market_key") or "")
        if key:
            duplicate_keys[key] = duplicate_keys.get(key, 0) + 1
            duplicate_rows.setdefault(key, []).append(pick)
        source_health = _safe_json_loads(pick.get("evidence_json")).get("source_health", {})
        statuses = source_health.get("source_status", {}) if isinstance(source_health, dict) else {}
        for source_name, status_payload in statuses.items():
            if not isinstance(status_payload, dict):
                continue
            status = str(status_payload.get("status") or "unknown")
            source_rollup = source_health_status_rollup.setdefault(str(source_name), {})
            source_rollup[status] = int(source_rollup.get(status, 0) or 0) + 1
        if pick.get("venue") == "model_implied" or pick.get("anchor_source") == "model_implied":
            model_implied += 1
        has_auto_resolver = (
            pick.get("venue") in {"kalshi", "polymarket", "weather_api"}
            or pick.get("resolution_source") in {"kalshi", "polymarket", "nws_observations", "espn_nba", "coingecko"}
            or (_domain(str(pick.get("topic") or "")) == "crypto")
        )
        if not is_paper_bundle and (pick.get("status") == "unknown" or not has_auto_resolver):
            manual_only += 1
        if domain == "esports":
            esports_row = {
                "id": pick.get("id"),
                "title": str(pick.get("title") or pick.get("question") or pick.get("topic") or ""),
                "subdomain": subdomain,
                "pick_type": pick_type,
                "market_type": str(pick.get("market_type") or ""),
                "status": str(pick.get("status") or ""),
            }
            esports_rows.append(esports_row)
            warning_reasons = _esports_open_warning_reasons(pick)
            if warning_reasons:
                flagged_row = dict(esports_row)
                flagged_row["warning_reasons"] = warning_reasons
                esports_flagged_rows.append(flagged_row)
                for reason in warning_reasons:
                    esports_flagged_by_reason[reason] = esports_flagged_by_reason.get(reason, 0) + 1
    duplicate_market_key_count = sum(1 for count in duplicate_keys.values() if count > 1)
    duplicate_row_count = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    duplicate_clusters = {key: count for key, count in sorted(duplicate_keys.items()) if count > 1}
    duplicate_cluster_summaries = []
    duplicate_open_row_count_legacy_era = 0
    duplicate_open_row_count_current_dedupe_era = 0
    for key, rows in sorted(duplicate_rows.items()):
        if len(rows) <= 1:
            continue
        ordered = sorted(rows, key=lambda row: _parse_timestamp(row.get("created_at")) or datetime.min, reverse=True)
        for row in ordered[1:]:
            era = _skill_version_era(row.get("skill_version"))
            if era == "v1_0_24_plus":
                duplicate_open_row_count_current_dedupe_era += 1
            else:
                duplicate_open_row_count_legacy_era += 1
        duplicate_cluster_summaries.append({
            "venue_market_key": key,
            "count": len(rows),
            "domains": sorted({_domain(str(row.get("topic") or "")) for row in rows}),
            "version_eras": sorted({_skill_version_era(row.get("skill_version")) for row in rows}),
        })
    nba_watch_rows = [pick for pick in open_picks if _domain(str(pick.get("topic") or "")) == "nba" and pick.get("pick_type") == "watchlist"]
    for pick in nba_watch_rows:
        if _pick_watchlist_scope(pick) != "series":
            continue
        series_key = str(pick.get("venue_market_key") or "")
        same_rows = [
            other for other in nba_watch_rows
            if other is not pick
            and _pick_watchlist_scope(other) == "game"
            and str(other.get("venue") or "") == str(pick.get("venue") or "")
            and any(team in str(other.get("title") or "").lower() for team in re.sub(r"[^a-z0-9\s]", " ", str(pick.get("title") or "").lower()).split() if team in eq.NBA_TEAM_TOKENS)
        ]
        if same_rows:
            mixed_scope_clusters.append({
                "series_key": series_key,
                "series_title": pick.get("title") or pick.get("question") or "",
                "game_titles": sorted({row.get("title") or row.get("question") or "" for row in same_rows}),
            })
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
    if legacy_noisy_rationale_count:
        warnings.append(f"{legacy_noisy_rationale_count} open/unknown picks contain legacy rationale text that would fail the current paper-safe filters.")
    if legacy_noisy_by_reason:
        top_reason = max(sorted(legacy_noisy_by_reason.items()), key=lambda row: row[1])[0]
        warnings.append(f"Top legacy rationale failure mode: {top_reason.replace('_', ' ')}.")
    if esports_flagged_rows:
        warnings.append(
            f"{len(esports_flagged_rows)} open esports row(s) have domain/subdomain/type mismatches or degraded labels and should be treated as audit-only samples."
        )
    if duplicate_market_key_count:
        warnings.append(
            f"{duplicate_row_count} open paper rows overlap with an already-open market key across {duplicate_market_key_count} repeated market key(s); broader sampling should avoid redundant duplicates."
        )
    return {
        "open_count": total,
        "mix": mix,
        "manual_or_unknown_resolution_count": manual_only,
        "paper_bundle_count": paper_bundle_count,
        "paper_only_bundle_count": paper_bundle_count,
        "model_implied_count": model_implied,
        "legacy_unversioned_count": missing_version,
        "legacy_noisy_rationale_count": legacy_noisy_rationale_count,
        "by_skill_version": dict(sorted(by_skill_version.items())),
        "by_pick_type": dict(sorted(by_pick_type.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "by_subdomain": dict(sorted(by_subdomain.items())),
        "by_watchlist_scope": dict(sorted(by_watchlist_scope.items())),
        "by_age_bucket": dict(sorted(by_age_bucket.items())),
        "by_version_era": dict(sorted(by_version_era.items())),
        "duplicate_market_key_count": duplicate_market_key_count,
        "duplicate_open_row_count": duplicate_row_count,
        "duplicate_open_row_count_legacy_era": duplicate_open_row_count_legacy_era,
        "duplicate_open_row_count_current_dedupe_era": duplicate_open_row_count_current_dedupe_era,
        "duplicate_clusters": duplicate_clusters,
        "duplicate_cluster_summaries": duplicate_cluster_summaries,
        "mixed_scope_clusters": mixed_scope_clusters,
        "legacy_noisy_by_skill_version": dict(sorted(legacy_noisy_by_skill_version.items())),
        "legacy_noisy_by_pick_type": dict(sorted(legacy_noisy_by_pick_type.items())),
        "legacy_noisy_by_domain": dict(sorted(legacy_noisy_by_domain.items())),
        "legacy_noisy_by_subdomain": dict(sorted(legacy_noisy_by_subdomain.items())),
        "legacy_noisy_by_reason": dict(sorted(legacy_noisy_by_reason.items())),
        "legacy_noisy_examples": legacy_noisy_examples,
        "source_health_status_rollup": {key: dict(sorted(value.items())) for key, value in sorted(source_health_status_rollup.items())},
        "esports_open_slice": {
            "count": len(esports_rows),
            "by_pick_type": {
                key: sum(1 for row in esports_rows if row.get("pick_type") == key)
                for key in sorted({str(row.get("pick_type") or "") for row in esports_rows if row.get("pick_type")})
            },
            "by_subdomain": {
                key: value for key, value in sorted(by_subdomain.items())
                if key in {row["subdomain"] for row in esports_rows if row["subdomain"]}
            },
            "by_market_type": {
                key: sum(1 for row in esports_rows if row.get("market_type") == key)
                for key in sorted({str(row.get("market_type") or "") for row in esports_rows if row.get("market_type")})
            },
            "missing_subdomain_count": sum(1 for row in esports_rows if not row.get("subdomain")),
            "rows_missing_subdomain": [row for row in esports_rows if not row.get("subdomain")][:5],
            "rows": esports_rows[:8],
            "empty_reason": "" if esports_rows else "No open esports paper rows right now.",
        },
        "esports_legacy_degraded_slice": {
            "count": len(esports_flagged_rows),
            "by_reason": dict(sorted(esports_flagged_by_reason.items())),
            "rows": esports_flagged_rows[:8],
            "empty_reason": "" if esports_flagged_rows else "No open esports audit-warning rows right now.",
        },
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
    debug_counters: Optional[Dict[str, int]] = None,
) -> Path:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    path = PAPER_DIR / f"paper-daily-{_now_slug()}.json"
    payload = {
        "paper_run_id": run_id,
        "created_pick_ids": created,
        "resolved": resolved,
        "errors": errors,
        "warnings": warnings or [],
        "debug_counters": debug_counters or {},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def cmd_daily(args) -> None:
    entries = _load_portfolio(Path(args.portfolio))
    if args.dry_run:
        results = []
        errors = []
        for entry in entries:
            print(f"[dry-run] evaluating {entry['topic']}", file=sys.stderr)
            try:
                results.append(_daily_dry_run_entry(entry, quick=args.quick))
            except Exception as exc:
                errors.append(f"{entry['topic']}: {type(exc).__name__}: {exc}")
        print(json.dumps({
            "dry_run": True,
            "topics": [entry["topic"] for entry in entries],
            "results": results,
            "errors": errors,
        }, indent=2))
        return
    started = time.time()
    run_id = store.record_paper_run(Path(args.portfolio).stem, status="running", topics_attempted=len(entries), skill_version=_skill_version())
    created: List[int] = []
    errors: List[str] = []
    warnings: List[str] = []
    debug_counters: Dict[str, int] = {}
    for entry in entries:
        try:
            report = _run_last24hours(entry["topic"], quick=args.quick, extra_args=entry.get("last24hours_args", []))
            picks = extract_paper_picks(report)
            picks = _filter_picks_by_policy(picks, entry.get("pick_policy", "default"))
            picks = _apply_dedupe_policy(entry, picks, warnings, debug_counters)
            if not picks:
                warnings.append(f"{entry['topic']}: no usable paper pick found")
            warnings.extend(_validate_expected_pick_types(entry, picks))
            warnings.extend(f"{entry['topic']}: {warning}" for warning in pick_quality_warnings(picks))
            created.extend(_store_picks(run_id, picks))
        except Exception as exc:
            errors.append(f"{entry['topic']}: {type(exc).__name__}: {exc}")
    resolved = resolve_open_picks()
    report_path = _write_daily_report(run_id, created, resolved, errors, warnings, debug_counters)
    store.update_paper_run(
        run_id,
        status="completed" if not errors else "partial",
        picks_created=len(created),
        picks_resolved=sum(1 for item in resolved if item.get("status") == "resolved"),
        report_path=str(report_path),
        error_message="; ".join(errors)[:500],
        duration_seconds=time.time() - started,
    )
    print(json.dumps({"paper_run_id": run_id, "picks_created": len(created), "resolved": resolved, "report_path": str(report_path), "errors": errors, "warnings": warnings, "debug_counters": debug_counters}, indent=2))


def cmd_resolve(args) -> None:
    if args.pick_id and args.outcome is not None:
        print(json.dumps(_resolve_manual(args.pick_id, args.outcome), indent=2))
        return
    print(json.dumps({"resolved": resolve_open_picks(limit=args.limit)}, indent=2))


def cmd_report(args) -> None:
    recent = store.list_recent_paper_picks(days=args.days, limit=args.limit)
    summary = calibration_summary(store.list_resolved_paper_picks(days=args.days))
    comparable = current_skill_comparable_summary(store.list_resolved_paper_picks(days=args.days))
    print(json.dumps({
        "days": args.days,
        "summary": summary,
        "current_skill_comparable_sample": comparable,
        "post_1_0_30_nba_watchlist_sample": post_1_0_30_nba_watchlist_summary(recent),
        "post_1_0_38_esports_sample": post_1_0_38_esports_summary(recent),
        "closing_soon_health": closing_soon_health_summary(recent),
        "open_portfolio": open_pick_diagnostics(recent),
        "recent_picks": recent,
    }, indent=2, default=str))


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
